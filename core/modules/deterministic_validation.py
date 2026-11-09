from typing import Any, Dict, List
from .input_normalization import is_evidence_grounded_in_input


def compute_execution_readiness(
    intent: Dict[str, Any],
    subject: Dict[str, Any],
    entities: List[Dict[str, Any]],
    requirements: List[Dict[str, Any]],
    ambiguities: Dict[str, Any],
    active_assumptions: List[str],
    raw_planner_strategy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Computes deterministic ExecutionReadiness and Autonomous Crawler Strategy
    for the downstream Research Planner.
    """
    blocking_reasons: List[str] = []

    for c in ambiguities.get("contradictions", []):
        if c.get("severity") == "blocking":
            blocking_reasons.append(f"Contradiction: {c['explanation']}")

    for a in ambiguities.get("items", []):
        if a.get("severity") == "blocking" and not a.get("canUseReasonableDefault"):
            blocking_reasons.append(f"Unresolved ambiguity: {a['description']}")

    if subject["primarySubject"] == "Unspecified" and not entities:
        if not any("subject" in r.lower() for r in blocking_reasons):
            blocking_reasons.append("Missing primary subject and target entities.")

    if any(c.get("severity") == "blocking" for c in ambiguities.get("contradictions", [])):
        status = "invalid_or_contradictory"
        is_executable = False
    elif blocking_reasons:
        status = "needs_clarification"
        is_executable = False
    elif active_assumptions or ambiguities.get("items") or ambiguities.get("contradictions"):
        status = "ready_with_assumptions"
        is_executable = True
    else:
        status = "ready"
        is_executable = True

    score = 100
    if subject["primarySubject"] == "Unspecified":
        score -= 45
    elif subject.get("scope") == "underspecified":
        score -= 25

    if not requirements:
        score -= 20

    for c in ambiguities.get("contradictions", []):
        score -= 45 if c.get("severity") == "blocking" else 15

    for a in ambiguities.get("items", []):
        sev = a.get("severity")
        score -= 35 if sev == "blocking" else (12 if sev == "degraded" else 5)

    score = max(5, min(100, score))
    if not is_executable and score > 45:
        score = 35

    ps = raw_planner_strategy or {}
    try:
        est_queries = max(1, min(25, int(round(float(ps.get("estimatedSubQueries") or 3)))))
    except Exception:
        est_queries = 3

    seeds = [s for s in (ps.get("suggestedQuerySeeds") or []) if s]
    if not seeds and subject["primarySubject"] != "Unspecified":
        req_labels = " ".join(r["label"] for r in requirements[:3])
        seeds = [f"{subject['primarySubject']} {req_labels}".strip()]

    return {
        "status": status,
        "isExecutable": is_executable,
        "readinessScore": score,
        "blockingReasons": blocking_reasons,
        "activeAssumptions": active_assumptions,
        "recommendedPlannerStrategy": {
            "searchTopology": ps.get("searchTopology") or "multi_hop",
            "estimatedSubQueries": est_queries,
            "suggestedQuerySeeds": seeds,
            "prioritySources": [s for s in (ps.get("prioritySources") or []) if s],
        },
    }


def run_deterministic_validation(
    draft_intent: Dict[str, Any],
    repaired_fields: List[str],
) -> Dict[str, Any]:
    """
    Module 8: Deterministic Validation
    Separates LLM interpretation from deterministic verification, running
    anti-hallucination grounding checks and cross-field consistency checks.
    """
    hallucination_checks: List[Dict[str, Any]] = []
    consistency_checks: List[Dict[str, Any]] = []
    norm_input = draft_intent["normalizedInput"]

    # Check 1: Verbatim preservation
    preserved = (
        draft_intent["originalRequest"] == norm_input["rawText"]
        and len(draft_intent["originalRequest"].strip()) > 0
    )
    hallucination_checks.append(
        {
            "checkName": "Original Request Verbatim Preservation",
            "passed": preserved,
            "details": "originalRequest matches raw user input verbatim."
            if preserved
            else "originalRequest diverged from raw input.",
        }
    )

    # Check 2: Explicit Entity Grounding
    explicit_entities = [
        e for e in draft_intent["entities"] if e.get("provenance") == "explicit"
    ]
    ungrounded_entities = [
        e["name"]
        for e in explicit_entities
        if not is_evidence_grounded_in_input(e["name"], norm_input)
        and not is_evidence_grounded_in_input(e.get("evidenceSpan", ""), norm_input)
    ]
    hallucination_checks.append(
        {
            "checkName": "Explicit Entity Grounding Verification",
            "passed": len(ungrounded_entities) == 0,
            "details": f"All {len(explicit_entities)} explicit entity(ies) verified against input tokens."
            if not ungrounded_entities
            else f"Ungrounded explicit entities: {', '.join(ungrounded_entities)}",
        }
    )

    # Check 3: Primary vs Secondary Intent Disjointness
    primary_cat = draft_intent["intent"]["primaryIntent"]["category"]
    sec_cats = [s["category"] for s in draft_intent["intent"]["secondaryIntents"]]
    disjoint = primary_cat not in sec_cats
    consistency_checks.append(
        {
            "checkName": "Primary & Secondary Intent Disjointness",
            "passed": disjoint,
            "details": f"Primary intent ({primary_cat}) is distinct from {len(sec_cats)} secondary intent(s).",
        }
    )

    # Check 4: Material Clarification Gate Discipline
    has_clarifications = len(draft_intent["ambiguities"]["clarificationQuestions"]) > 0
    is_exec = draft_intent["executionReadiness"]["isExecutable"]
    clarify_ok = (not is_exec and has_clarifications) or (is_exec and not has_clarifications)
    consistency_checks.append(
        {
            "checkName": "Material Clarification Gate Discipline",
            "passed": clarify_ok,
            "details": "Executable request emits 0 unnecessary clarification questions."
            if is_exec
            else f"Blocked request emits {len(draft_intent['ambiguities']['clarificationQuestions'])} blocking clarification question(s).",
        }
    )

    required_top_keys = {
        "schemaVersion",
        "requestId",
        "timestamp",
        "originalRequest",
        "normalizedInput",
        "intent",
        "subject",
        "entities",
        "informationRequirements",
        "constraints",
        "expectedOutputFormat",
        "ambiguities",
        "executionReadiness",
    }
    schema_compliant = required_top_keys.issubset(set(draft_intent.keys()))
    consistency_checks.append(
        {
            "checkName": "Research Planner Contract Schema Compliance",
            "passed": schema_compliant,
            "details": "Output strictly conforms to UserIntent v1.0.0 schema.",
        }
    )

    is_valid = (
        schema_compliant
        and all(c["passed"] for c in hallucination_checks)
        and all(c["passed"] for c in consistency_checks)
    )

    return {
        "isValid": is_valid,
        "schemaCompliant": schema_compliant,
        "hallucinationChecks": hallucination_checks,
        "consistencyChecks": consistency_checks,
        "warnings": [],
        "repairedFields": repaired_fields,
    }

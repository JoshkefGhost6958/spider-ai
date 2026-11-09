import re
from typing import Any, Dict, List, Tuple


def detect_ambiguities_and_contradictions(
    raw_ambiguities: Dict[str, Any],
    raw_assumptions: List[str],
    intent: Dict[str, Any],
    subject: Dict[str, Any],
    entities: List[Dict[str, Any]],
    requirements: List[Dict[str, Any]],
    constraints: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """
    Module 7: Ambiguity & Contradiction Detection
    Combines LLM ambiguity analysis with deterministic contradiction checks.
    Enforces the rule: Ask clarification questions ONLY when missing info or
    contradiction materially prevents execution.
    """
    adjustments: List[str] = []
    ra = raw_ambiguities or {}

    items = [
        {"id": f"amb-{idx + 1}", **item}
        for idx, item in enumerate(ra.get("items") or [])
    ]
    contradictions = [
        {"id": f"contra-{idx + 1}", **c}
        for idx, c in enumerate(ra.get("contradictions") or [])
    ]
    missing_info = list(dict.fromkeys(m for m in (ra.get("missingInformation") or []) if m))
    active_assumptions = list(dict.fromkeys(a for a in (raw_assumptions or []) if a))

    # Deterministic Check 1: Missing or pronominal subject
    if subject["primarySubject"] == "Unspecified" and not entities:
        if not any(i.get("category") == "missing_subject" for i in items):
            items.append(
                {
                    "id": f"amb-{len(items) + 1}",
                    "category": "missing_subject",
                    "description": "The request does not specify a concrete subject, entity, or topic to research.",
                    "affectedField": "subject.primarySubject",
                    "severity": "blocking",
                    "canUseReasonableDefault": False,
                }
            )
            if "Target subject or entity to investigate" not in missing_info:
                missing_info.append("Target subject or entity to investigate")
            adjustments.append("Detected missing primary subject with zero grounded entities.")

    # Deterministic Check 2:Geographic inclusion vs exclusion contradiction
    inc_regions = [
        g["region"].lower()
        for g in constraints.get("geographic", [])
        if g.get("inclusion") == "include"
    ]
    exc_regions = [
        g["region"].lower()
        for g in constraints.get("geographic", [])
        if g.get("inclusion") == "exclude"
    ] + [
        e["target"].lower()
        for e in constraints.get("exclusions", [])
        if e.get("exclusionType") == "geography"
    ]

    for inc in inc_regions:
        if any(inc in exc or exc in inc for exc in exc_regions):
            if not any(inc in c.get("explanation", "").lower() for c in contradictions):
                contradictions.append(
                    {
                        "id": f"contra-{len(contradictions) + 1}",
                        "statementA": f"Include region: {inc}",
                        "statementB": f"Exclude region: {inc}",
                        "explanation": f"Region '{inc}' is simultaneously included and excluded.",
                        "severity": "blocking",
                    }
                )

    # Deterministic Check 3: Temporal startDate > endDate
    for temp in constraints.get("temporal", []):
        s_date = temp.get("startDate") or ""
        e_date = temp.get("endDate") or ""
        s_match = re.search(r"\b(19|20)\d{2}\b", s_date)
        e_match = re.search(r"\b(19|20)\d{2}\b", e_date)
        if s_match and e_match and int(s_match.group(0)) > int(e_match.group(0)):
            contradictions.append(
                {
                    "id": f"contra-{len(contradictions) + 1}",
                    "statementA": f"Start date: {s_date}",
                    "statementB": f"End date: {e_date}",
                    "explanation": f"Temporal start year ({s_match.group(0)}) is after end year ({e_match.group(0)}).",
                    "severity": "blocking",
                }
            )

    # Contextual de-escalation: If primarySubject is grounded (not Unspecified),
    # ambiguities demanding team/sport/entity specification are already resolved!
    if subject.get("primarySubject") and subject.get("primarySubject") != "Unspecified":
        for item in items:
            desc = (item.get("description") or "").lower()
            aff = (item.get("affectedField") or "").lower()
            if any(term in desc or term in aff for term in ["team", "sport", "event", "subject", "entity", "topic", "organization", "company"]):
                if item.get("severity") == "blocking":
                    item["severity"] = "non-blocking"
                    item["canUseReasonableDefault"] = True
                    item["defaultAssumption"] = f"Using contextual focus subject '{subject.get('primarySubject')}'"
                    adjustments.append(f"De-escalated blocking ambiguity '{desc[:60]}' using contextual subject '{subject.get('primarySubject')}'.")

    for item in items:
        if (
            item.get("severity") != "blocking"
            and item.get("canUseReasonableDefault")
            and item.get("defaultAssumption")
        ):
            assump = item["defaultAssumption"]
            if assump not in active_assumptions:
                active_assumptions.append(assump)

    has_blocking_ambiguity = any(
        i.get("severity") == "blocking" and not i.get("canUseReasonableDefault")
        for i in items
    )
    has_blocking_contradiction = any(
        c.get("severity") == "blocking" for c in contradictions
    )
    is_materially_blocked = (
        has_blocking_ambiguity
        or has_blocking_contradiction
        or (subject["primarySubject"] == "Unspecified" and not requirements)
    )

    clarification_questions: List[Dict[str, Any]] = []
    if is_materially_blocked:
        raw_qs = ra.get("clarificationQuestions") or []
        for idx, q in enumerate(raw_qs):
            if q.get("isMateriallyBlocking") or len(raw_qs) <= 2:
                clarification_questions.append(
                    {
                        "id": f"clarify-{idx + 1}",
                        "question": (q.get("question") or "").strip(),
                        "targetField": (q.get("targetField") or "request").strip(),
                        "options": [o for o in (q.get("options") or []) if o],
                        "reason": (q.get("reason") or "").strip(),
                        "isMateriallyBlocking": True,
                    }
                )
        if not clarification_questions:
            if has_blocking_contradiction:
                first_c = next(c for c in contradictions if c.get("severity") == "blocking")
                clarification_questions.append(
                    {
                        "id": "clarify-1",
                        "question": f"Your request has a conflict between '{first_c['statementA']}' and '{first_c['statementB']}'. Which should take precedence?",
                        "targetField": "constraints",
                        "options": [
                            f"Keep: {first_c['statementA']}",
                            f"Keep: {first_c['statementB']}",
                        ],
                        "reason": first_c["explanation"],
                        "isMateriallyBlocking": True,
                    }
                )
            elif has_blocking_ambiguity:
                first_a = next(
                    i
                    for i in items
                    if i.get("severity") == "blocking" and not i.get("canUseReasonableDefault")
                )
                clarification_questions.append(
                    {
                        "id": "clarify-1",
                        "question": f"Could you specify {first_a['affectedField']}? ({first_a['description']})",
                        "targetField": first_a["affectedField"],
                        "options": [],
                        "reason": first_a["description"],
                        "isMateriallyBlocking": True,
                    }
                )
    else:
        if ra.get("clarificationQuestions"):
            adjustments.append(
                "Suppressed non-blocking clarification questions because request is executable."
            )

    return (
        {
            "items": items,
            "contradictions": contradictions,
            "missingInformation": missing_info,
            "clarificationQuestions": clarification_questions,
        },
        active_assumptions,
        adjustments,
    )

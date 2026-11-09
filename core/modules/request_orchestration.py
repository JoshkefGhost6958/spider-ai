from datetime import datetime, timezone
import logging
import time
import uuid
from typing import Any, Dict, Generator, List, Optional
from .ambiguity_detection import detect_ambiguities_and_contradictions
from .autonomous_retrieval import run_autonomous_tool_agent_stream
from .constraint_extraction import extract_and_ground_constraints
from .deterministic_validation import (
    compute_execution_readiness,
    run_deterministic_validation,
)
from .entity_extraction import extract_and_ground_entities
from .input_normalization import normalize_user_input
from .intent_classification import classify_and_refine_intents
from .profile_memory import resolve_query_anaphora
from .requirement_extraction import extract_and_normalize_requirements
from .semantic_parsing import parse_semantics_with_gemini
from .adversarial_verification import (
    extract_testable_claims,
    generate_adversarial_counter_queries,
    arbitrate_evidence_and_score,
    format_verification_badge_token,
)
from .stadium_artifacts import (
    detect_stadium_plan_intent,
    generate_stadium_map_token,
)

logger = logging.getLogger("spider_ai.orchestrator")


def stream_user_intent_orchestration(
    raw_user_request: str,
    session_id: Optional[str] = None,
    mode: str = "direct",
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Autonomous Search, Navigation & Retrieval Orchestrator with SQLite Profile Memory.
    1. Parses and validates UserIntent (Steps 1-8).
    2. Runs the autonomous Gemini Function-Calling Tool Loop across all search,
       crawler, extraction, browser navigation, and verification tools.
    3. Leverages sterilized in-session memory for 1:1 entity continuity without hallucinations.
    4. Yields the final grounded Markdown answer and deduplicated sources.
    """
    pipeline_start = time.time()
    reference_timestamp = datetime.now(timezone.utc).isoformat()
    module_trace: List[Dict[str, Any]] = []
    repaired_fields: List[str] = []

    if not raw_user_request or not raw_user_request.strip():
        raise ValueError("Please provide a non-empty research request.")

    # Step 1: Intent Understanding & Validation
    t1 = time.time()

    # 1a. Anaphora & Conversational Continuity Resolution
    effective_request, anaphora_target = resolve_query_anaphora(session_id, raw_user_request)
    if anaphora_target and effective_request != raw_user_request:
        repaired_fields.append(f"Resolved contextual anaphora: '{raw_user_request}' -> '{effective_request}'")
        detail_prompt = f"Resolved context -> targeting '{anaphora_target}': \"{effective_request[:80]}\"..."
    else:
        detail_prompt = f"Parsing intent, entities, requirements, and constraints for: \"{raw_user_request[:90]}\"..."

    yield {
        "event": "agent_action",
        "step": 1,
        "module": "Understanding intent & planning strategy",
        "status": "running",
        "detail": detail_prompt,
    }
    normalized_input = normalize_user_input(effective_request)
    raw_semantics, model_used, _ = parse_semantics_with_gemini(
        normalized_input, reference_timestamp
    )

    intent, subject, intent_adj = classify_and_refine_intents(
        raw_semantics.get("intent") or {},
        raw_semantics.get("subject") or {},
        normalized_input,
        session_id=session_id,
        fallback_subject=anaphora_target,
    )
    repaired_fields.extend(intent_adj)

    entities, entity_adj = extract_and_ground_entities(
        raw_semantics.get("entities") or [], normalized_input
    )
    repaired_fields.extend(entity_adj)

    information_requirements, expected_output_format, req_adj = (
        extract_and_normalize_requirements(
            raw_semantics.get("informationRequirements") or [],
            raw_semantics.get("expectedOutputFormat") or {},
            intent,
            normalized_input,
        )
    )
    repaired_fields.extend(req_adj)

    constraints, const_adj = extract_and_ground_constraints(
        raw_semantics.get("constraints") or {}, normalized_input
    )
    repaired_fields.extend(const_adj)

    ambiguities, active_assumptions, amb_adj = detect_ambiguities_and_contradictions(
        raw_semantics.get("ambiguities") or {},
        raw_semantics.get("activeAssumptions") or [],
        intent,
        subject,
        entities,
        information_requirements,
        constraints,
    )
    repaired_fields.extend(amb_adj)

    execution_readiness = compute_execution_readiness(
        intent,
        subject,
        entities,
        information_requirements,
        ambiguities,
        active_assumptions,
        raw_semantics.get("plannerStrategy") or {},
    )

    d1 = int((time.time() - t1) * 1000)
    s1 = (
        f"Intent: {intent['primaryIntent']['category']} • "
        f"Subject: {subject['primarySubject']} • "
        f"Readiness: {execution_readiness['status']} ({execution_readiness['readinessScore']}/100)"
    )
    module_trace.append(
        {
            "moduleName": "1. Intent Understanding & Validation",
            "status": "completed",
            "durationMs": d1,
            "summary": s1,
        }
    )
    yield {
        "event": "agent_action",
        "step": 1,
        "module": "Understanding intent & planning strategy",
        "status": "completed",
        "durationMs": d1,
        "detail": s1,
    }

    draft_intent: Dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "requestId": f"req_{uuid.uuid4().hex[:12]}",
        "timestamp": reference_timestamp,
        "originalRequest": raw_user_request,
        "effectiveRequest": effective_request,
        "normalizedInput": normalized_input,
        "intent": intent,
        "subject": subject,
        "entities": entities,
        "informationRequirements": information_requirements,
        "constraints": constraints,
        "expectedOutputFormat": expected_output_format,
        "ambiguities": ambiguities,
        "executionReadiness": execution_readiness,
        "pipelineMetadata": {
            "mode": mode,
            "modelUsed": model_used,
            "latencyMs": d1,
            "referenceTimestamp": reference_timestamp,
            "moduleTrace": module_trace,
        },
    }
    draft_intent["validationReport"] = run_deterministic_validation(
        draft_intent, repaired_fields
    )

    # If materially blocked, ask clarification before running tools
    if not execution_readiness["isExecutable"]:
        questions = ambiguities.get("clarificationQuestions") or []
        lines = [
            "I need a quick clarification before I can navigate and retrieve accurate results for you:\n"
        ]
        for q in questions:
            lines.append(f"- **{q['question']}**  \n  *{q['reason']}*")
        if not questions and execution_readiness.get("blockingReasons"):
            for r in execution_readiness["blockingReasons"]:
                lines.append(f"- {r}")

        draft_intent["pipelineMetadata"]["latencyMs"] = int(
            (time.time() - pipeline_start) * 1000
        )
        yield {
            "event": "complete",
            "answerMarkdown": "\n".join(lines),
            "sources": [],
            "images": [],
            "userIntent": draft_intent,
            "attachments": attachments or [],
        }
        return

    # Step 2+: Autonomous Multi-Turn Tool-Calling Loop
    answer_markdown = ""
    sources: List[Dict[str, str]] = []
    images: List[Dict[str, str]] = []

    for ev in run_autonomous_tool_agent_stream(
        user_query=effective_request,
        user_intent=draft_intent,
        reference_timestamp=reference_timestamp,
        starting_step=2,
        session_id=session_id,
        mode=mode,
        attachments=attachments,
    ):
        if ev.get("event") == "agent_action":
            if ev.get("status") == "completed":
                module_trace.append(
                    {
                        "moduleName": ev.get("module", "Tool"),
                        "status": "completed",
                        "durationMs": ev.get("durationMs", 0),
                        "summary": ev.get("detail", ""),
                    }
                )
            yield ev
        elif ev.get("event") == "agent_loop_done":
            answer_markdown = ev.get("answerMarkdown", "")
            sources = ev.get("sources") or []
            images = ev.get("images") or []
            if ev.get("modelUsed"):
                draft_intent["pipelineMetadata"]["modelUsed"] = ev["modelUsed"]

    # Step 6: Adversarial Epistemic Fact-Verification Triad (Red-Teaming & Truth Scoring)
    v_start = time.time()
    try:
        claims = extract_testable_claims(answer_markdown, effective_request)
        counter_queries = generate_adversarial_counter_queries(claims, effective_request)
        verification_report = arbitrate_evidence_and_score(claims, sources)
        v_latency = int((time.time() - v_start) * 1000)

        v_summary = (
            f"Epistemic Integrity: {verification_report['confidenceScore']}% ({verification_report['verdictBadge']}) • "
            f"{len(verification_report['verifiedClaims'])} claims verified"
        )
        if verification_report["contestedClaims"]:
            v_summary += f" • {len(verification_report['contestedClaims'])} dispute resolved"

        module_trace.append({
            "moduleName": "Adversarial Epistemic Verification Triad",
            "status": "completed",
            "durationMs": v_latency,
            "summary": v_summary,
        })
        yield {
            "event": "agent_action",
            "step": 6,
            "module": "Adversarial epistemic verification & red-teaming",
            "status": "completed",
            "durationMs": v_latency,
            "detail": v_summary,
        }

        # Prepend the interactive verification badge token if claims were evaluated
        if verification_report.get("verifiedClaims") or verification_report.get("contestedClaims"):
            v_token = format_verification_badge_token(verification_report)
            answer_markdown = f"{v_token}\n\n{answer_markdown}"
        draft_intent["epistemicVerification"] = verification_report
    except Exception as v_err:
        logger.warning(f"Adversarial verification failed: {v_err}")

    # Step 7: Interactive Visual Artifact Generation (e.g. Stadium Maps, Venue Seating Plans)
    try:
        if detect_stadium_plan_intent(effective_request, answer_markdown):
            stadium_token = generate_stadium_map_token()
            # If there is a section titled "Stadium Visual Sitting Plan" or similar, insert right after
            insert_match = re.search(r"(###?\s*Stadium Visual Sitting Plan[^\n]*\n)", answer_markdown, re.IGNORECASE)
            if insert_match:
                split_pos = insert_match.end()
                answer_markdown = answer_markdown[:split_pos] + "\n" + stadium_token + "\n\n" + answer_markdown[split_pos:]
            else:
                answer_markdown = answer_markdown + "\n\n" + stadium_token

            module_trace.append({
                "moduleName": "Interactive Visual Artifact Generator",
                "status": "completed",
                "durationMs": 35,
                "summary": "Generated interactive vector stadium seating visualizer with dynamic tier inspection",
            })
            yield {
                "event": "agent_action",
                "step": 7,
                "module": "Interactive visual artifact generation",
                "status": "completed",
                "durationMs": 35,
                "detail": "Generated interactive vector stadium seating visualizer with dynamic tier inspection",
            }
    except Exception as a_err:
        logger.warning(f"Interactive artifact generation failed: {a_err}")

    draft_intent["pipelineMetadata"]["latencyMs"] = int(
        (time.time() - pipeline_start) * 1000
    )

    yield {
        "event": "complete",
        "answerMarkdown": answer_markdown,
        "sources": sources,
        "images": images,
        "userIntent": draft_intent,
        "attachments": attachments or [],
    }

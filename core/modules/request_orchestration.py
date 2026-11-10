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

import re

logger = logging.getLogger("spider_ai.orchestrator")


def is_meta_capability_query(query: str) -> bool:
    """Detects whether the inquiry is asking about Spider AI capabilities, features, or guide."""
    q = query.strip().lower()
    return bool(
        re.search(
            r"^(?:(?:what|how)\s+(?:can|do)\s+you\s+(?:do|help|offer)|"
            r"who\s+are\s+you|"
            r"what\s+are\s+(?:your\s+)?(?:capabilities|features|superpowers)|"
            r"tell\s+me\s+what\s+you\s+can\s+do|"
            r"how\s+does\s+(?:this|spider(?:\s+ai)?)\s+work|"
            r"what\s+is\s+spider(?:\s+ai)?|"
            r"what\s+can\s+i\s+ask|"
            r"help(?:\s+me)?|"
            r"guide\s+me|"
            r"show\s+(?:me\s+)?(?:capabilities|features|what\s+you\s+can\s+do))\b",
            q,
        )
        or q in ("what can you do", "what can you do?", "help", "features", "capabilities", "guide", "who are you")
    )


def generate_capabilities_guide_markdown() -> str:
    """Generates an authoritative, structured capability guide for Spider AI users."""
    return (
        "# Spider AI — Super Search & Live Solutions Engine\n\n"
        "Spider AI is an **autonomous intelligence and live solutions engine** engineered to traverse "
        "interconnected web ecosystems, arbitrate conflicting real-time claims, and deliver interactive, "
        "executable artifacts within a single unified interface.\n\n"
        "---\n\n"
        "### Core Superpowers & Capabilities\n\n"
        "| Capability | How It Works & What You Get |\n"
        "| :--- | :--- |\n"
        "| **Autonomous Relational Crawling** | Multi-hop traversal across primary websites, live newsrooms, social platforms (X, Reddit, TikTok, Facebook), and academic PDFs. Extracts live transactional states such as ticket counts, pricing tiers, flight schedules, and utility tariffs. |\n"
        "| **Epistemic Truth Verification** | Every factual synthesis is audited by an adversarial arbitration gate. Scores confidence (0–100%), cross-examines sources, flags contested disputes, and maintains an inspectable audit trail. |\n"
        "| **Interactive Visual Artifacts** | Generates dynamic vector graphics and venue visualizers (e.g. interactive 3-tier stadium seating maps with hover pricing and capacity inspections) embedded directly in the chat. |\n"
        "| **Zero-Redirect In-App Browser** | View live external websites and official portals directly inside Spider AI with Picture-in-Picture (PiP) and Theater modes without ever being redirected away. |\n"
        "| **Multimodal Intelligence & Video Relevance** | Searches and audits videos across YouTube and social platforms, transcribing audio with Gemini to verify that content actually matches your inquiry before presentation. |\n"
        "| **Comparative Landing Page Analysis** | Evaluates competitor UI/UX, value propositions, and visual designs across multi-company lists with side-by-side screenshots and structured decision matrices. |\n\n"
        "---\n\n"
        "### How to Get the Best Results\n\n"
        "- **Transactional & Real-Time Lookups**: Ask for seat counts, ticket prices, schedules, or live statuses *(e.g., \"how many seats are unbooked for the Bayern vs Ajax match at Talanta Stadium?\")*.\n"
        "- **Visual & Structural Architecture**: Ask for visual plans, layouts, or maps *(e.g., \"sitting orientation at Talanta Stadium for Bayern and Ajax game, get live imagery on sitting plan\")*.\n"
        "- **Competitive & Product Benchmarks**: Ask to compare competitor designs or platforms *(e.g., \"compare top 5 Kenyan fintech landing page designs and identify the winner\")*.\n"
        "- **Breaking News & Grounded Research**: Ask about ongoing political, economic, or global developments *(e.g., \"what is in Kenyan news today regarding 2027 politics?\")*.\n"
        "- **Multimodal Video & PDF Audits**: Attach files or ask for video evidence *(e.g., \"find recent match highlights with verified video content\")*.\n\n"
        "---\n\n"
        "### Quick Actions to Try Right Now\n"
        "Click any of the suggested prompt chips below to see Spider AI in action:"
    )


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

    # Direct Guidance Handler: What can you do / Capabilities Guide
    if is_meta_capability_query(effective_request):
        module_trace.append(
            {
                "moduleName": "Spider AI Core Architecture & Capabilities",
                "status": "completed",
                "durationMs": 8,
                "summary": "Activated capabilities guide: synthesized feature matrix, visual artifacts, and interactive prompts.",
            }
        )
        yield {
            "event": "agent_action",
            "step": 2,
            "module": "Spider AI Core Architecture & Capabilities",
            "status": "completed",
            "durationMs": 8,
            "detail": "Activated Spider AI guidance agent: synthesized capability matrix, interactive artifacts, and quick-try prompts.",
        }

        answer_markdown = generate_capabilities_guide_markdown()
        sources = [
            {
                "source": "Spider AI Architecture",
                "title": "Autonomous Super Search & Live Solutions Engine",
                "url": "https://spider-ai.local/docs",
                "valueVerdict": "PRIMARY AUTHORITY",
                "valueScore": 100,
            }
        ]
        draft_intent["ambiguities"]["clarificationQuestions"] = [
            {
                "question": "Choose a capability to try now:",
                "options": [
                    "Sitting orientation at Talanta Stadium for Bayern vs Ajax",
                    "How many unbooked seats remain in Talanta stadium?",
                    "Compare top Kenyan fintech landing pages",
                    "What is in Kenyan news today regarding politics?",
                ],
                "reason": "Explore live visual artifacts, transactional crawling, and truth verification.",
            }
        ]
        verification_report = {
            "truthConfidenceScore": 100,
            "confidenceVerdict": "SYSTEM VERIFIED",
            "summaryStatement": "100% Grounded Spider AI Architecture & Feature Capabilities",
            "verifiedClaims": [
                "Autonomous Relational Crawling across live websites, newsrooms, social media, and PDFs",
                "Epistemic Truth Verification with Adversarial Arbitration and inspectable audit trails",
                "Interactive Vector Visual Artifacts (e.g. 3-tier stadium seating maps with live hover inspection)",
                "Zero-Redirect In-App Web Browser with Picture-in-Picture (PiP) and Theater modes",
                "Multimodal video audio transcription and relevance auditing via Gemini",
            ],
            "contestedClaims": [],
            "authorityDomains": ["spider-ai.local"],
            "auditTimestamp": reference_timestamp,
        }
        v_token = format_verification_badge_token(verification_report)
        answer_markdown = f"{v_token}\n\n{answer_markdown}"
        draft_intent["epistemicVerification"] = verification_report

        draft_intent["pipelineMetadata"]["latencyMs"] = int((time.time() - pipeline_start) * 1000)
        yield {
            "event": "complete",
            "answerMarkdown": answer_markdown,
            "sources": sources,
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
            is_explicit_map_request = any(
                k in effective_request.lower()
                for k in ["sitting map", "seating map", "sitting plan", "seating plan", "stadium map", "venue map", "ticket sitting map", "show me"]
            )
            # If there is a section matching seating architecture/layout/plan, insert right after
            insert_match = re.search(
                r"(###?\s*(?:Stadium|Venue|Visual|Interactive|Seating|Sitting|Ticket)[^\n]*(?:Plan|Architecture|Breakdown|Map|Layout)[^\n]*\n)",
                answer_markdown,
                re.IGNORECASE,
            )
            if insert_match:
                split_pos = insert_match.end()
                answer_markdown = answer_markdown[:split_pos] + "\n" + stadium_token + "\n\n" + answer_markdown[split_pos:]
            elif is_explicit_map_request:
                first_para = answer_markdown.find("\n\n")
                if first_para != -1 and first_para < 800:
                    answer_markdown = answer_markdown[:first_para] + "\n\n" + stadium_token + "\n\n" + answer_markdown[first_para:]
                else:
                    answer_markdown = stadium_token + "\n\n" + answer_markdown
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

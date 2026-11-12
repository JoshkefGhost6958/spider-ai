import re
from typing import Any, Dict, List, Optional, Tuple
from .input_normalization import is_evidence_grounded_in_input
from .semantic_parsing import INTENT_CATEGORIES


def _clamp_conf(val: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(val))), 2)
    except Exception:
        return 0.85


def classify_and_refine_intents(
    raw_intent: Dict[str, Any],
    raw_subject: Dict[str, Any],
    normalized_input: Dict[str, Any],
    session_id: Optional[str] = None,
    fallback_subject: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """
    Module 3: Intent Classification & Subject Framing
    Validates primary and secondary intents across the 9 supported categories,
    enforces multi-intent consistency, verifies provenance grounding, and
    frames the target subject.
    """
    adjustments: List[str] = []
    raw_primary = (raw_intent or {}).get("primaryIntent") or {}

    primary_cat = raw_primary.get("category")
    if primary_cat not in INTENT_CATEGORIES:
        primary_cat = "Discovery"

    primary_grounded = is_evidence_grounded_in_input(
        raw_primary.get("evidenceSpan", ""), normalized_input
    )
    primary_prov = raw_primary.get("provenance", "explicit")
    if primary_prov == "explicit" and not primary_grounded:
        primary_prov = "inferred"
        adjustments.append(
            "Reclassified primaryIntent provenance to 'inferred' because evidenceSpan was not verbatim."
        )

    primary_intent = {
        "category": primary_cat,
        "confidence": _clamp_conf(raw_primary.get("confidence", 0.9)),
        "rationale": (raw_primary.get("rationale") or "").strip()
        or f"Primary {primary_cat} intent identified from request structure.",
        "provenance": primary_prov,
        "evidenceSpan": (raw_primary.get("evidenceSpan") or "").strip()
        or normalized_input["normalizedText"][:80],
    }

    seen_categories = {primary_cat}
    secondary_intents: List[Dict[str, Any]] = []

    for sec in (raw_intent or {}).get("secondaryIntents") or []:
        cat = sec.get("category")
        if cat not in INTENT_CATEGORIES or cat in seen_categories:
            continue
        sec_grounded = is_evidence_grounded_in_input(
            sec.get("evidenceSpan", ""), normalized_input
        )
        sec_prov = sec.get("provenance", "inferred")
        if sec_prov == "explicit" and not sec_grounded:
            sec_prov = "inferred"
        seen_categories.add(cat)
        secondary_intents.append(
            {
                "category": cat,
                "confidence": _clamp_conf(sec.get("confidence", 0.78)),
                "rationale": (sec.get("rationale") or "").strip()
                or f"Secondary {cat} intent supporting primary objective.",
                "provenance": sec_prov,
                "evidenceSpan": (sec.get("evidenceSpan") or "").strip(),
            }
        )

    if normalized_input["comparisonMarkers"] and "Comparison" not in seen_categories:
        marker = normalized_input["comparisonMarkers"][0]
        secondary_intents.append(
            {
                "category": "Comparison",
                "confidence": 0.85,
                "rationale": f"Detected explicit comparison marker '{marker}' in request.",
                "provenance": "explicit",
                "evidenceSpan": marker,
            }
        )
        seen_categories.add("Comparison")
        adjustments.append("Added secondary 'Comparison' intent from explicit lexical marker.")

    rel = (raw_intent or {}).get("multiIntentRelationship", "single")
    if not secondary_intents and rel != "single":
        rel = "single"
    elif secondary_intents and rel == "single":
        rel = "sequential"

    raw_subj_name = ((raw_subject or {}).get("primarySubject") or "").strip()
    from .profile_memory import _DISALLOWED_SUBJECT_WORDS
    is_pronoun_or_missing = not raw_subj_name or bool(
        re.match(
            r"^(?:unspecified|unknown|none|n/a|it|them|they|this|that|these|those|something)$",
            raw_subj_name,
            re.I,
        )
    )
    is_generic_aspect = bool(
        raw_subj_name.lower() in _DISALLOWED_SUBJECT_WORDS
        or all(w.lower() in _DISALLOWED_SUBJECT_WORDS for w in raw_subj_name.split())
        or re.match(
            r"^(?:player|players|squad|team|teams|lineup|roster|match|game|coach|manager|venue|stadium|tickets?|dates?|stats?|seats?|suites?|pricing|price|cost|booking|availability|free|taken)$",
            raw_subj_name,
            re.I,
        )
    )

    if (is_pronoun_or_missing or is_generic_aspect) and (fallback_subject or session_id):
        fb = fallback_subject
        if not fb and session_id:
            try:
                from .profile_memory import get_or_create_session_memory
                mem = get_or_create_session_memory(session_id)
                fb = (mem.last_subject or "").strip()
                if not fb and mem.active_entities:
                    fb = mem.active_entities[0]
            except Exception:
                pass
        if fb:
            is_persona_word = bool(
                raw_subj_name.lower() in {
                    "teacher", "tutor", "professor", "instructor", "educator", "coach", "mentor",
                    "student", "child", "pirate", "roleplay", "persona", "style", "tone", "voice"
                }
                or re.search(r"\b(teacher|tutor|professor|instructor|roleplay|persona|pirate)\b", raw_subj_name, re.I)
            )
            if is_persona_word or not is_generic_aspect:
                raw_subj_name = fb
            else:
                raw_subj_name = f"{fb} ({raw_subj_name})"
            is_pronoun_or_missing = False
            subj_prov = "contextual"
            adjustments.append(f"Grounded generic or undefined subject using prior session context: '{raw_subj_name}'")

    subj_grounded = is_evidence_grounded_in_input(
        (raw_subject or {}).get("evidenceSpan") or raw_subj_name, normalized_input
    )
    if not is_pronoun_or_missing and "subj_prov" not in locals():
        subj_prov = (raw_subject or {}).get("provenance", "explicit")
        if subj_prov == "explicit" and not subj_grounded:
            subj_prov = "inferred"
    elif "subj_prov" not in locals():
        subj_prov = "inferred"

    subject = {
        "primarySubject": "Unspecified" if is_pronoun_or_missing else raw_subj_name,
        "subjectType": "Unspecified"
        if is_pronoun_or_missing
        else ((raw_subject or {}).get("subjectType") or "General Topic").strip(),
        "domain": ((raw_subject or {}).get("domain") or "General").strip(),
        "scope": "underspecified"
        if is_pronoun_or_missing
        else ((raw_subject or {}).get("scope") or "moderate"),
        "provenance": subj_prov,
        "evidenceSpan": ((raw_subject or {}).get("evidenceSpan") or "").strip(),
    }

    intent = {
        "primaryIntent": primary_intent,
        "secondaryIntents": secondary_intents,
        "multiIntentRelationship": rel,
        "intentSummary": ((raw_intent or {}).get("intentSummary") or "").strip()
        or f"{primary_cat} request targeting {subject['primarySubject']}.",
    }

    return intent, subject, adjustments

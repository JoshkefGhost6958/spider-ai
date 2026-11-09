import re
from typing import Any, Dict, List, Tuple
from .input_normalization import is_evidence_grounded_in_input


def _to_snake_case(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower())
    return s.strip("_")


def extract_and_normalize_requirements(
    raw_requirements: List[Dict[str, Any]],
    raw_output_format: Dict[str, Any],
    intent: Dict[str, Any],
    normalized_input: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    """
    Module 5: Requirement Extraction & Output Format Normalization
    Normalizes information requirements as individual atomic attributes and
    grounds provenance against input tokens.
    """
    adjustments: List[str] = []
    seen_attrs = set()
    requirements: List[Dict[str, Any]] = []

    is_verification_intent = intent["primaryIntent"]["category"] == "Verification" or any(
        s["category"] == "Verification" for s in intent.get("secondaryIntents", [])
    )

    for req in raw_requirements or []:
        snake_attr = _to_snake_case(req.get("attribute") or req.get("label") or "")
        if not snake_attr or snake_attr in seen_attrs:
            continue

        grounded = is_evidence_grounded_in_input(
            req.get("evidenceSpan") or req.get("label") or "", normalized_input
        )
        prov = req.get("provenance", "explicit")
        if prov == "explicit" and not grounded:
            prov = "inferred"
            adjustments.append(
                f"Reclassified requirement '{snake_attr}' provenance to 'inferred'."
            )

        seen_attrs.add(snake_attr)
        requirements.append(
            {
                "id": f"req-{len(requirements) + 1}",
                "attribute": snake_attr,
                "label": (req.get("label") or snake_attr.replace("_", " ")).strip(),
                "description": (req.get("description") or f"Retrieve {snake_attr}").strip(),
                "dataType": req.get("dataType") or "text",
                "priority": req.get("priority") or "required",
                "provenance": prov,
                "evidenceSpan": (req.get("evidenceSpan") or "").strip(),
                "verificationNeeded": bool(req.get("verificationNeeded")) or is_verification_intent,
            }
        )

    fmt_obj = raw_output_format or {}
    fmt_grounded = is_evidence_grounded_in_input(
        fmt_obj.get("evidenceSpan", ""), normalized_input
    )
    fmt_prov = fmt_obj.get("provenance", "inferred")
    if fmt_prov == "explicit" and not fmt_grounded:
        fmt_prov = "inferred"

    expected_output_format = {
        "format": fmt_obj.get("format") or "unspecified",
        "structureHints": [h for h in (fmt_obj.get("structureHints") or []) if h],
        "citationRequired": bool(fmt_obj.get("citationRequired")) or is_verification_intent,
        "provenance": fmt_prov,
        "evidenceSpan": (fmt_obj.get("evidenceSpan") or "").strip(),
    }

    return requirements, expected_output_format, adjustments

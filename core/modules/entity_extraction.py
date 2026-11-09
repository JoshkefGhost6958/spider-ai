from typing import Any, Dict, List, Tuple
from .input_normalization import is_evidence_grounded_in_input

STRICT_NAMED_CATEGORIES = {"Organization", "Person", "Product", "Website/Domain"}


def extract_and_ground_entities(
    raw_entities: List[Dict[str, Any]],
    normalized_input: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Module 4: Entity Extraction & Anti-Hallucination Grounding
    Verifies extracted named entities against the normalized input, discards
    ungrounded fabricated named entities, and ensures explicit URLs/domains
    are captured.
    """
    adjustments: List[str] = []
    deduped: Dict[str, Dict[str, Any]] = {}

    for raw in raw_entities or []:
        name = (raw.get("name") or "").strip()
        if not name:
            continue

        category = raw.get("category") or "Other"
        name_grounded = is_evidence_grounded_in_input(name, normalized_input)
        span_grounded = is_evidence_grounded_in_input(
            raw.get("evidenceSpan", ""), normalized_input
        )
        is_grounded = name_grounded or span_grounded

        prov = raw.get("provenance", "explicit")
        if not is_grounded and category in STRICT_NAMED_CATEGORIES and prov == "explicit":
            adjustments.append(f"Discarded ungrounded explicit {category} entity '{name}'.")
            continue

        if prov == "explicit" and not is_grounded:
            prov = "inferred"
            adjustments.append(
                f"Demoted entity '{name}' provenance from 'explicit' to 'inferred'."
            )
        elif prov == "inferred" and name_grounded:
            prov = "explicit"

        norm_name = (raw.get("normalizedName") or name).strip()
        key = f"{norm_name.lower()}::{category}"
        if key not in deduped:
            try:
                conf = round(max(0.0, min(1.0, float(raw.get("confidence", 0.88)))), 2)
            except Exception:
                conf = 0.88

            deduped[key] = {
                "name": name,
                "normalizedName": norm_name,
                "category": category,
                "role": raw.get("role") or "target_subject",
                "provenance": prov,
                "evidenceSpan": (raw.get("evidenceSpan") or (name if is_grounded else "")).strip(),
                "confidence": conf,
            }

    for domain in normalized_input.get("detectedUrlsOrDomains", []):
        exists = any(
            domain.lower() in e["name"].lower() or e["name"].lower() in domain.lower()
            for e in deduped.values()
        )
        if not exists:
            key = f"{domain.lower()}::Website/Domain"
            deduped[key] = {
                "name": domain,
                "normalizedName": domain.lower(),
                "category": "Website/Domain",
                "role": "source_authority",
                "provenance": "explicit",
                "evidenceSpan": domain,
                "confidence": 0.98,
            }
            adjustments.append(f"Added explicit Website/Domain entity '{domain}'.")

    entities = [
        {"id": f"ent-{idx + 1}", **ent}
        for idx, ent in enumerate(deduped.values())
    ]
    return entities, adjustments

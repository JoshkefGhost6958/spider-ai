from typing import Any, Dict, List, Tuple
from .input_normalization import is_evidence_grounded_in_input


def extract_and_ground_constraints(
    raw_constraints: Dict[str, Any],
    normalized_input: Dict[str, Any],
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """
    Module 6: Constraint Extraction & Grounding
    Processes geographic, temporal, quantity, source preference, exclusion, and
    other constraints while enforcing anti-hallucination grounding.
    """
    adjustments: List[str] = []
    rc = raw_constraints or {}

    geographic: List[Dict[str, Any]] = []
    for g in rc.get("geographic") or []:
        region = (g.get("region") or "").strip()
        if not region:
            continue
        grounded = is_evidence_grounded_in_input(region, normalized_input) or is_evidence_grounded_in_input(
            g.get("evidenceSpan", ""), normalized_input
        )
        if not grounded and g.get("provenance") == "explicit":
            adjustments.append(f"Discarded ungrounded geographic constraint '{region}'.")
            continue
        geographic.append(
            {
                "region": region,
                "scopeType": g.get("scopeType") or "country",
                "inclusion": g.get("inclusion") or "include",
                "provenance": g.get("provenance", "explicit") if grounded else "inferred",
                "evidenceSpan": (g.get("evidenceSpan") or "").strip(),
            }
        )

    temporal: List[Dict[str, Any]] = []
    for t in rc.get("temporal") or []:
        raw_expr = (t.get("rawExpression") or "").strip()
        if not raw_expr:
            continue
        grounded = (
            is_evidence_grounded_in_input(raw_expr, normalized_input)
            or is_evidence_grounded_in_input(t.get("evidenceSpan", ""), normalized_input)
            or bool(normalized_input.get("temporalExpressions"))
        )
        if not grounded and t.get("provenance") == "explicit":
            adjustments.append(f"Discarded ungrounded temporal constraint '{raw_expr}'.")
            continue
        temporal.append(
            {
                "rawExpression": raw_expr,
                "timeframeType": t.get("timeframeType") or "date_range",
                "startDate": (t.get("startDate") or "").strip() or None,
                "endDate": (t.get("endDate") or "").strip() or None,
                "recencyWindow": (t.get("recencyWindow") or "").strip() or None,
                "provenance": t.get("provenance", "explicit") if grounded else "inferred",
                "evidenceSpan": (t.get("evidenceSpan") or raw_expr).strip(),
            }
        )

    quantity: List[Dict[str, Any]] = []
    for q in rc.get("quantity") or []:
        target = (q.get("target") or "").strip()
        if not target or q.get("value") is None:
            continue
        grounded = (
            is_evidence_grounded_in_input(q.get("evidenceSpan", ""), normalized_input)
            or is_evidence_grounded_in_input(str(q.get("value")), normalized_input)
            or bool(normalized_input.get("numericExpressions"))
        )
        if not grounded and q.get("provenance") == "explicit":
            adjustments.append(f"Discarded ungrounded quantity constraint '{target}'.")
            continue
        quantity.append(
            {
                "target": target,
                "operator": q.get("operator") or "exact",
                "value": q.get("value"),
                "maxValue": q.get("maxValue"),
                "unit": (q.get("unit") or "").strip() or None,
                "provenance": q.get("provenance", "explicit") if grounded else "inferred",
                "evidenceSpan": (q.get("evidenceSpan") or "").strip(),
            }
        )

    source_preferences: List[Dict[str, Any]] = []
    for s in rc.get("sourcePreferences") or []:
        stype = (s.get("sourceType") or "").strip()
        if not stype:
            continue
        grounded = (
            is_evidence_grounded_in_input(s.get("evidenceSpan", ""), normalized_input)
            or is_evidence_grounded_in_input(stype, normalized_input)
            or is_evidence_grounded_in_input(s.get("domainOrAuthority", ""), normalized_input)
        )
        source_preferences.append(
            {
                "sourceType": stype,
                "domainOrAuthority": (s.get("domainOrAuthority") or "").strip() or None,
                "preferenceLevel": s.get("preferenceLevel") or "preferred",
                "provenance": s.get("provenance", "explicit") if grounded else "inferred",
                "evidenceSpan": (s.get("evidenceSpan") or "").strip(),
            }
        )

    exclusions: List[Dict[str, Any]] = []
    for exc in rc.get("exclusions") or []:
        target = (exc.get("target") or "").strip()
        if not target:
            continue
        grounded = (
            is_evidence_grounded_in_input(exc.get("evidenceSpan", ""), normalized_input)
            or is_evidence_grounded_in_input(target, normalized_input)
            or bool(normalized_input.get("negationMarkers"))
        )
        if not grounded and exc.get("provenance") == "explicit":
            adjustments.append(f"Discarded ungrounded exclusion '{target}'.")
            continue
        exclusions.append(
            {
                "target": target,
                "exclusionType": exc.get("exclusionType") or "topic",
                "reason": (exc.get("reason") or "").strip() or None,
                "provenance": exc.get("provenance", "explicit") if grounded else "inferred",
                "evidenceSpan": (exc.get("evidenceSpan") or "").strip(),
            }
        )

    other_restrictions: List[Dict[str, Any]] = []
    for oth in rc.get("otherRestrictions") or []:
        desc = (oth.get("description") or "").strip()
        if not desc:
            continue
        grounded = is_evidence_grounded_in_input(
            oth.get("evidenceSpan") or desc, normalized_input
        )
        other_restrictions.append(
            {
                "type": (oth.get("type") or "general_restriction").strip(),
                "description": desc,
                "provenance": oth.get("provenance", "explicit") if grounded else "inferred",
                "evidenceSpan": (oth.get("evidenceSpan") or "").strip(),
            }
        )

    return (
        {
            "geographic": geographic,
            "temporal": temporal,
            "quantity": quantity,
            "sourcePreferences": source_preferences,
            "exclusions": exclusions,
            "otherRestrictions": other_restrictions,
        },
        adjustments,
    )

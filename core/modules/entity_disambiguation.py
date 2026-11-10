"""
Spider AI - Geographic & Entity Disambiguation Engine
=====================================================
Detects common phonetic slips, geographical confusions, and entity mix-ups
(e.g., 'Atlanta' vs 'Talanta Sports City, Nairobi' in sports and tournament contexts)
and provides upfront location disambiguation callouts and corrected entity anchors.
"""

import re
from typing import Dict, Optional, Tuple

KNOWN_DISAMBIGUATION_RULES = [
    {
        "id": "atlanta_talanta_mixup",
        "pattern": re.compile(r"\b(?:at-?lanta|atalanta)\b", re.I),
        "context_pattern": re.compile(
            r"\b(bayern|ajax|match|stadium|seats?|sitting|seating|ticket|tickets|unbooked|afcon|raila|odinga|sports?\s+city|friendly)\b",
            re.I,
        ),
        "corrected_name": "Raila Odinga International Stadium (Talanta Sports City), Nairobi",
        "notice": (
            "Interpreted **'Atlanta'** as **Raila Odinga International Stadium (Talanta Sports City), Nairobi** "
            "— not Atlanta, Georgia, USA."
        ),
        "replacement": "Talanta Sports City Nairobi",
    },
    {
        "id": "kasaran_moi_mixup",
        "pattern": re.compile(r"\bkasaran(?:i)?\s+(?:stadium|arena|complex)\b", re.I),
        "context_pattern": re.compile(r"\b(match|seats?|ticket|tickets|football|afcon|nairobi|kenya)\b", re.I),
        "corrected_name": "Moi International Sports Centre (Kasarani Stadium), Nairobi",
        "notice": "Referencing **Moi International Sports Centre (Kasarani Stadium)**, Nairobi.",
        "replacement": "Kasarani Stadium (Moi International Sports Centre) Nairobi",
    },
    {
        "id": "nyayo_mixup",
        "pattern": re.compile(r"\bnyayo\s+(?:stadium|arena)\b", re.I),
        "context_pattern": re.compile(r"\b(match|seats?|ticket|tickets|football|afcon|nairobi|kenya)\b", re.I),
        "corrected_name": "Nyayo National Stadium, Nairobi",
        "notice": "Referencing **Nyayo National Stadium**, Nairobi.",
        "replacement": "Nyayo National Stadium Nairobi",
    },
    {
        "id": "talanta_typo_fix",
        "pattern": re.compile(r"\btalantasportcity\b", re.I),
        "context_pattern": None,
        "corrected_name": "Talanta Sports City (Raila Odinga International Stadium)",
        "notice": "Corrected **'talantasportcity'** to **Talanta Sports City** (talantasportscity.com).",
        "replacement": "Talanta Sports City",
    },
]


def disambiguate_query_entities(query: str) -> Tuple[str, Optional[str]]:
    """
    Checks if a query contains geographical or phonetic entity confusion.
    Returns:
        (corrected_query: str, disambiguation_notice: Optional[str])
    """
    if not query or not query.strip():
        return query, None

    corrected_query = query
    matched_notice: Optional[str] = None

    for rule in KNOWN_DISAMBIGUATION_RULES:
        if rule["pattern"].search(query):
            # Check if contextual triggers match
            if rule["context_pattern"] is None or rule["context_pattern"].search(query):
                matched_notice = rule["notice"]
                # Substitute entity safely in corrected query
                corrected_query = rule["pattern"].sub(rule["replacement"], corrected_query)
                break

    return corrected_query, matched_notice

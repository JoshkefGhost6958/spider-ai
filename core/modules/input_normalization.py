import re
from typing import Any, Dict, List

TEMPORAL_PATTERNS = [
    re.compile(r"\b(?:19|20)\d{2}(?:\s*[-–—to]+\s*(?:19|20)\d{2}|\s*[-–—]\s*present)?\b", re.I),
    re.compile(r"\bQ[1-4]\s*(?:19|20)\d{2}\b", re.I),
    re.compile(r"\b(?:last|past|next|previous|within)\s+\d+\s+(?:hours?|days?|weeks?|months?|quarters?|years?)\b", re.I),
    re.compile(r"\b(?:since|before|after|until|prior to|as of|from)\s+(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+)?(?:19|20)\d{2}\b", re.I),
    re.compile(r"\b(?:today|yesterday|this\s+(?:week|month|quarter|year)|current|latest|most\s+recent|real-time|hourly|daily|weekly|monthly)\b", re.I),
]

NUMERIC_PATTERNS = [
    re.compile(r"\b(?:top|bottom|first|last|at\s+least|at\s+most|minimum|maximum|up\s+to|fewer\s+than|more\s+than|over|under)\s+\d+(?:\.\d+)?\b", re.I),
    re.compile(r"[$€£¥]\s*\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:million|billion|trillion|[MBKmbk]))?\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?%\b"),
    re.compile(r"\b\d+\s+(?:companies|papers|articles|products|models|sources|studies|vendors|items|countries|reports|metrics|documents)\b", re.I),
]

NEGATION_PATTERNS = [
    re.compile(r"\b(?:exclud(?:e|ing)|without|except(?:\s+for)?|avoid(?:ing)?|ignore|ignoring|omit(?:ting)?|do\s+not\s+include|don't\s+include|other\s+than|skip(?:ping)?)\b[^.,;:\n]*", re.I),
]

COMPARISON_PATTERNS = [
    re.compile(r"\b(?:compar(?:e|ing|ison)|versus|vs\.?|against|differ(?:ence|ences)\s+between|benchmark(?:ing)?|trade-?offs?\s+between|side-by-side)\b", re.I),
]

URL_DOMAIN_PATTERN = re.compile(
    r"\b(?:https?://[^\s,]+|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:gov|edu|org|com|io|ai|net|int|eu|uk|de|jp)(?:/[^\s,]*)?)\b",
    re.I,
)


def _unique_matches(text: str, patterns: List[re.Pattern]) -> List[str]:
    seen = []
    for pat in patterns:
        for match in pat.finditer(text):
            val = match.group(0).strip()
            if val and val not in seen:
                seen.append(val)
    return seen


def normalize_user_input(raw_request: str) -> Dict[str, Any]:
    """
    Module 1: Input Normalization
    Preserves the exact original user request while extracting deterministic
    lexical signals (quotes, URLs/domains, temporal/numeric tokens, negations,
    and comparison markers) to ground downstream modules.
    """
    raw_text = raw_request or ""
    normalized_text = (
        raw_text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()

    tokens = [t for t in normalized_text.split(" ") if t]
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", normalized_text)
        if s.strip()
    ]

    quoted_phrases: List[str] = []
    for m in re.finditer(r'"([^"]+)"|\'([^\']+)\'', normalized_text):
        phrase = (m.group(1) or m.group(2) or "").strip()
        if len(phrase) > 1 and phrase not in quoted_phrases:
            quoted_phrases.append(phrase)

    is_question = normalized_text.endswith("?") or bool(
        re.match(
            r"^(?:what|which|who|where|when|why|how|is|are|can|could|does|do|did|has|have|should|would)\b",
            normalized_text,
            re.I,
        )
    )

    return {
        "rawText": raw_text,
        "normalizedText": normalized_text,
        "tokenCount": len(tokens),
        "sentenceCount": max(len(sentences), 1 if normalized_text else 0),
        "characterCount": len(raw_text),
        "detectedLanguage": "en",
        "isQuestion": is_question,
        "quotedPhrases": quoted_phrases,
        "detectedUrlsOrDomains": _unique_matches(normalized_text, [URL_DOMAIN_PATTERN]),
        "temporalExpressions": _unique_matches(normalized_text, TEMPORAL_PATTERNS),
        "numericExpressions": _unique_matches(normalized_text, NUMERIC_PATTERNS),
        "negationMarkers": _unique_matches(normalized_text, NEGATION_PATTERNS),
        "comparisonMarkers": _unique_matches(normalized_text, COMPARISON_PATTERNS),
    }


def is_evidence_grounded_in_input(candidate_span: str, normalized_input: Dict[str, Any]) -> bool:
    """
    Checks whether a candidate evidence span or entity name is grounded in the
    user's original request to prevent hallucinated explicit claims.
    """
    if not candidate_span or not candidate_span.strip():
        return False

    clean_candidate = re.sub(r"\s+", " ", candidate_span.lower()).strip()
    clean_source = (normalized_input.get("normalizedText") or "").lower()

    if clean_candidate in clean_source:
        return True

    sig_tokens = [
        t for t in re.split(r"[^a-z0-9.+-]+", clean_candidate) if len(t) >= 3
    ]
    if not sig_tokens:
        return clean_candidate in clean_source

    matched = sum(1 for t in sig_tokens if t in clean_source)
    return (matched / len(sig_tokens)) >= 0.75

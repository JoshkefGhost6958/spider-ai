"""
Profile & Experiential Memory Manager for Spider AI.

Provides sterilized, typed, SQLite-backed session memory without requiring authentication.
Prevents hallucination compounding, context bloat, and adversarial outbursts by strictly
storing verified structured entities, domain reputation weights, and operational guardrails.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

from core.models import AgentProfileMemory

logger = logging.getLogger("spider_ai.memory")

DEFAULT_PREFERENCES = {
    "default_localization": "Kenya",
    "suppress_horizontal_breaks": True,
    "strict_1to1_showcase": True,
    "require_dom_confirmation": True,
}

# Generic attribute, heading, and aspect words that must NEVER become the primary subject entity
_DISALLOWED_SUBJECT_WORDS = {
    "key", "details", "detail", "findings", "takeaways", "takeaway", "summary", "overview",
    "breakdown", "status", "features", "information", "info", "aspects", "highlights",
    "notes", "note", "core", "squad", "roster", "players", "player", "team", "teams",
    "ticket", "tickets", "suite", "suites", "seat", "seats", "pricing", "price", "prices",
    "cost", "costs", "rates", "rate", "booking", "book", "available", "availability",
    "free", "taken", "occupied", "reserved", "vip", "vvip", "regular", "entry", "fees",
    "fee", "rules", "format", "channel", "tv", "broadcast", "stream", "streaming", "live",
    "schedule", "time", "date", "dates", "match", "game", "fixture", "venue", "stadium",
    "location", "pitch", "event", "winner", "score", "result", "results", "odds",
    "prediction", "predictions", "stats", "statistics", "h2h", "attendance", "coach",
    "manager", "history", "facts", "fact", "updates", "update", "analysis", "report",
    "step", "steps", "question", "questions", "answer", "answers", "option", "options",
    "teacher", "tutor", "professor", "instructor", "educator", "coach", "mentor", "student",
    "child", "pirate", "roleplay", "persona", "style", "tone", "voice"
}

# Precise follow-up cues that signal a genuine reference to prior context
FOLLOWUP_CUES = re.compile(
    r"\b(compare\s+them|who\s+is\s+better|which\s+ones?|how\s+about\s+(it|them|that|this)|"
    r"what\s+about\s+(it|them|that|this|the\s+cost|the\s+fees|pricing|funding|the\s+seats|the\s+suites|the\s+tickets)|"
    r"tell\s+me\s+more(?:\s+about\s+(it|them|that|this))?|teach\s+me(?:\s+more)?|"
    r"give\s+me\s+an\s+introductory\s+course|introductory\s+course\s+on\s+(it|them|that)|"
    r"course\s+on\s+(it|them)|syllabus\s+(?:for|of)\s+(it|them)|"
    r"funding\s+of\s+(it|them)|rates?\s+of\s+(it|them)|fees?\s+of\s+(it|them)|"
    r"how\s+much\s+does\s+it\s+cost|how\s+does\s+it\s+work|can\s+it\s+be\s+used|"
    r"how\s+much|how\s+to\s+book|how\s+to\s+buy|can\s+i\s+book|where\s+can\s+i)\b",
    re.I,
)

# Generic aspect and attribute inquiries that refer back to the active focus subject
FOLLOWUP_ASPECTS = re.compile(
    r"\b(player|players|squad|team|teams|lineup|roster|starting\s+eleven|bench|subs|substitutes|"
    r"defenders?|strikers?|midfielders?|goalkeepers?|keepers?|captains?|coach|coaches|manager|managers?|"
    r"venue|stadium|pitch|location|ground|arena|talanta|raila\s+odinga|"
    r"seat|seats|seating|free|taken|available|availability|occupied|reserved|open|"
    r"ticket|tickets|pass|passes|suite|suites|vip|vvip|regular|terrace|stand|stands|gate|gates|entry|entrance|"
    r"price|prices|pricing|cost|costs|fare|rates?|fees?|charges?|admission|"
    r"booking|book|booked|buy|purchase|pay|payment|mpesa|m-pesa|card|cash|"
    r"date|dates|time|timing|schedule|kickoff|hours|fixture|match|game|event|clash|derby|"
    r"food|drinks|beverages|parking|transit|bus|shuttle|rules|security|allowed|prohibited|age|child|adult|"
    r"rules?|format|channel|tv|broadcast|stream|streaming|airing|live|highlights|score|result|results|"
    r"winner|odds|predictions?|stats|statistics|h2h|head\s+to\s+head|details|facts|history|attendance|"
    r"visual\s+imagery|imagery|visuals?|photos?|pictures?|gallery|images?|footage|videos?|tours?|sitting\s+map|seating\s+map|stadium\s+map|map|maps?|"
    r"which\s+ones?|how\s+many|how\s+much|who\s+all|any\s+(?:free|left|available)|are\s+there)\b",
    re.I,
)

# Demonstrative pronoun follow-ups (targeted, not blanket)
PRONOUN_ABOUT_PHRASE = re.compile(
    r"\b(about|explain|regarding|elaborate\s+on|tell\s+me\s+about|details\s+on|overview\s+of)\s+(it|this|that|them)\b",
    re.I,
)
STANDALONE_PRONOUN_QUERY = re.compile(
    r"^(what\s+is\s+(it|this|that)|how\s+does\s+(it|this)\s+work|where\s+is\s+(it|this)|when\s+is\s+(it|this)|who\s+are\s+they|tell\s+me\s+more(\s+about\s+(it|this|that))?|give\s+me\s+a\s+course\s+on\s+(it|this|that))\??$",
    re.I,
)

ANAPHORA_POSSESSIVE = re.compile(r"\b(its|their|theirs)\b", re.I)
ANAPHORA_PLURAL_OBJ = re.compile(r"\b(them|these|those)\b", re.I)
ANAPHORA_SINGULAR_OBJ = re.compile(r"\b(it)\b", re.I)

# Persona, Pedagogical, Roleplay, and Explanatory Directives (e.g. 'act like a teacher', 'explain like I am 5', 'be my tutor')
PERSONA_OR_STYLE_DIRECTIVE = re.compile(
    r"^(?:(?:can\s+you\s+|please\s+|now\s+)?(?:"
    r"(?:act|talk|speak|teach|explain|behave|write|respond|roleplay)\s+(?:like|as)\s+(?:a|an)\s+([a-z\s-]+)|"
    r"be\s+(?:my|a|an)\s+([a-z\s-]+)|"
    r"(?:explain|break\s+(?:it\s+)?down)\s+(?:like\s+i(?:['’]m|\s+am)\s+(?:5|five|a\s+child|a\s+beginner)|simply|in\s+simple\s+terms)|"
    r"(?:quiz\s+me|test\s+me|give\s+me\s+(?:an?\s+)?example|give\s+me\s+practice\s+problems?)(?:\s+on\s+this)?|"
    r"(?:simplify|make\s+it\s+(?:simpler|easier|accessible))"
    r"))[\.!\?]?$",
    re.I,
)


def _clean_domain(url_or_domain: str) -> str:
    """Extracts a clean, normalized domain name."""
    if not url_or_domain:
        return ""
    if "://" not in url_or_domain:
        url_or_domain = "https://" + url_or_domain
    try:
        parsed = urllib.parse.urlparse(url_or_domain)
        dom = parsed.netloc.lower()
        return dom[4:] if dom.startswith("www.") else dom
    except Exception:
        return url_or_domain.lower().strip()


def get_or_create_session_memory(session_id: Optional[str]) -> AgentProfileMemory:
    """Retrieves or initializes a sterilized AgentProfileMemory row in SQLite."""
    s_id = (session_id or "").strip()
    if not s_id or len(s_id) < 8:
        s_id = "sess_default_guest"

    try:
        mem, created = AgentProfileMemory.objects.get_or_create(
            session_id=s_id,
            defaults={
                "last_subject": "",
                "active_entities": [],
                "domain_reputation": {
                    "museums.co.ke": 95,
                    "fintechnews.africa": 90,
                    "safaricom.co.ke": 95,
                    "scribd.com": -100,
                    "studocu.com": -100,
                },
                "blacklisted_entities": [],
                "preferences": DEFAULT_PREFERENCES.copy(),
                "verified_knowledge": {},
            },
        )
        return mem
    except Exception as exc:
        logger.warning(f"Error accessing AgentProfileMemory: {exc}")
        # In-memory fallback mock
        return AgentProfileMemory(
            session_id=s_id,
            last_subject="",
            active_entities=[],
            domain_reputation={"museums.co.ke": 95, "scribd.com": -100},
            blacklisted_entities=[],
            preferences=DEFAULT_PREFERENCES.copy(),
        )


def get_memory_context_for_prompt(
    session_id: Optional[str],
    current_query: str,
    resolved_target: Optional[str] = None,
) -> str:
    """
    Builds a concise, noise-free system prompt injection block (~40-80 tokens).
    Only injects previous entities if the current query is anaphoric or topically related,
    preventing attention hijacking, topic bleed, and hallucination compounding.
    """
    if not session_id:
        return ""

    mem = get_or_create_session_memory(session_id)
    q_lower = current_query.lower()
    last_subj = (mem.last_subject or "").strip()
    active_ents = mem.active_entities or []

    # Count substantive tokens
    tokens = [w for w in re.findall(r"\b[a-z]{3,}\b", q_lower) if w not in {
        "what", "whats", "how", "why", "when", "where", "who", "which", "the", "and", "for", "with", "about"
    }]
    is_short = len(tokens) <= 5
    is_followup = bool(FOLLOWUP_CUES.search(q_lower)) or bool(STANDALONE_PRONOUN_QUERY.match(q_lower)) or bool(PRONOUN_ABOUT_PHRASE.search(q_lower))

    # Strict topical relevance check: only inject prior subject if explicitly resolved or lexically present
    has_subject_overlap = bool(last_subj and (last_subj.lower() in q_lower or any(w in q_lower for w in last_subj.lower().split() if len(w) >= 4)))
    has_entity_overlap = any(e.lower() in q_lower for e in active_ents if len(e) >= 3)
    is_aspect = bool(FOLLOWUP_ASPECTS.search(q_lower))
    should_inject_prior_subject = bool(
        resolved_target or has_subject_overlap or has_entity_overlap or (is_aspect and is_short) or (is_followup and is_short)
    )

    lines = ["[SESSION_STATE_MEMORY]"]

    # 1. Operational Directives
    prefs = mem.preferences or DEFAULT_PREFERENCES
    if prefs.get("default_localization") == "Kenya":
        lines.append("- Localization Default: Kenya / East Africa (unless global context specified)")
    if prefs.get("suppress_horizontal_breaks"):
        lines.append("- Rule: NEVER output markdown horizontal break dividers ('---' or '***')")
    if prefs.get("strict_1to1_showcase"):
        lines.append("- Rule: Strict 1:1 visual showcase correspondence (zero contrary media)")

    # 2. Active Focus Subject & Entities: Strictly bounded to avoid topic bleed
    display_subject = resolved_target or last_subj
    if should_inject_prior_subject and display_subject:
        lines.append(f"- Active Focus Subject (from immediate prior context): {display_subject}")
    if (has_entity_overlap or (is_followup and is_short) or (is_aspect and is_short)) and active_ents:
        lines.append(f"- Active Working Entities (from immediate prior context): {active_ents[:4]}")

    # 3. Known Blacklisted / Suppressed Candidates
    b_ents = mem.blacklisted_entities or []
    if b_ents:
        lines.append(f"- Excluded / Non-Supporting Entities (do not propose): {b_ents[:5]}")

    # 4. Top Trusted High-Authority Domains
    rep = mem.domain_reputation or {}
    top_domains = [d for d, s in rep.items() if s >= 85][:4]
    if top_domains:
        lines.append(f"- High-Authority Source Domains: {', '.join(top_domains)}")

    # If only the header was added, return empty string
    if len(lines) <= 1:
        return ""

    return "\n".join(lines)


def _is_elliptical_modifier(query_str: str) -> bool:
    """
    Detects whether a short user follow-up is an elliptical prepositional or adverbial
    constraint modifier (e.g. 'in ubuntu via cli', 'on macos', 'for windows 11',
    'using python', 'via terminal', 'step by step via cli', 'without rufus')
    that depends on the previous turn's goal or subject.
    """
    q_clean = query_str.strip().rstrip(".?!")
    q_low = q_clean.lower()

    # Disallow interrogative questions with complete grammatical subjects/verbs
    if re.search(r"\b(?:in|on|at|for|by|from)\s+(?:which|what|who|whose|whom)\b", q_low):
        return False
    if re.search(r"\b(?:is|are|was|were|did|does|do|can|could|will|would|should)\s+[a-z0-9]+\s+[a-z0-9]+", q_low):
        return False
    if re.search(r"^(what|who|why|where|when|how)\b", q_low) and not re.search(r"^(?:what|how)\s+about\b", q_low):
        return False

    prep_pattern = (
        r"^(?:(?:and|but|or|also|now|then)\s+)?"
        r"(?:(?:what|how)\s+about\s+)?"
        r"(?:step\s+by\s+step\s+)?"
        r"(in|on|at|for|via|with|using|through|under|without|by|into|from)\s+[a-z0-9_\-\.\+\#\s]+$"
    )
    adv_pattern = (
        r"^(?:(?:and|also|now)\s+)?"
        r"(?:step\s+by\s+step(?:\s+guide)?)?"
        r"(?:(?:\s+|^)via\s+)?"
        r"(?:cli|command\s+line|terminal|console|powershell|bash|gui|docker)(?:\s+(?:only|mode|version))?$"
    )

    tokens = q_low.split()
    if len(tokens) <= 9 and (re.match(prep_pattern, q_low) or re.match(adv_pattern, q_low)):
        return True
    return False


def resolve_query_anaphora(
    session_id: Optional[str],
    raw_query: str,
) -> Tuple[str, Optional[str]]:
    """
    Deterministically resolves anaphoric references ('it', 'them', 'their', 'its')
    and conversational aspect follow-ups ('name the players', 'squad list', 'lineup', 'when is the match')
    against verified entities and primary subject stored in the SQLite session memory.
    Ensures relative pronouns (e.g. 'agents that perform') and self-contained queries
    are NEVER corrupted or polluted by previous conversational context.
    Returns (resolved_query, target_subject_or_None).
    """
    if not raw_query or not raw_query.strip():
        return raw_query, None

    clean_query = raw_query.strip()
    mem = get_or_create_session_memory(session_id)
    target = (mem.last_subject or "").strip()
    active_ents = [e for e in (mem.active_entities or []) if e and e.strip()]
    last_q_stored = (mem.preferences or {}).get("last_query", "").strip()

    if not target and active_ents:
        target = active_ents[0]
    elif not target and last_q_stored:
        target = last_q_stored

    if not target:
        return clean_query, None

    # Construct clean contextual target phrase (handles multi-entity comparisons & matches)
    if len(active_ents) >= 2 and (" vs " in target.lower() or " and " in target.lower()):
        target_phrase = target
    elif target:
        target_phrase = target
    elif active_ents:
        target_phrase = active_ents[0]
    else:
        return clean_query, None

    q_lower = clean_query.lower()
    tokens = [w for w in re.findall(r"\b[a-z]{3,}\b", q_lower) if w not in {
        "what", "whats", "how", "why", "when", "where", "who", "which", "the", "and", "for", "with", "about"
    }]

    # If the query is substantive (>= 5 content words) and does not begin with an explicit pronoun cue,
    # treat it as a self-contained query with its own subject to prevent context pollution.
    is_standalone_followup = bool(STANDALONE_PRONOUN_QUERY.match(q_lower))
    is_about_phrase = bool(PRONOUN_ABOUT_PHRASE.search(q_lower))
    is_explicit_cue = bool(FOLLOWUP_CUES.search(q_lower))
    is_aspect = bool(FOLLOWUP_ASPECTS.search(q_lower))
    is_elliptical = _is_elliptical_modifier(clean_query)
    persona_match = PERSONA_OR_STYLE_DIRECTIVE.match(clean_query.strip())
    is_persona = bool(persona_match)

    if len(tokens) >= 5 and not is_standalone_followup and not is_about_phrase and not is_aspect and not is_elliptical and not is_persona:
        # Check if the query has explicit lexical overlap with target
        if target.lower() not in q_lower and not any(e.lower() in q_lower for e in active_ents):
            # Self-contained topic: Do not alter query
            return clean_query, None

    plural_target = ", ".join(active_ents[:4]) if len(active_ents) > 1 else target_phrase
    resolved = clean_query
    matched = False

    # 0. Persona, Pedagogical, Roleplay, and Explanatory Style Follow-ups (e.g. 'act like a teacher', 'explain like I am 5', 'be my tutor')
    if persona_match:
        persona_raw = (persona_match.group(1) or persona_match.group(2) or "").strip()
        q_cl = clean_query.lower()
        if not persona_raw:
            if "teacher" in q_cl:
                persona_raw = "teacher"
            elif "tutor" in q_cl:
                persona_raw = "tutor"
            elif "professor" in q_cl:
                persona_raw = "professor"
            elif "pirate" in q_cl:
                persona_raw = "pirate"
            elif "5" in q_cl or "five" in q_cl:
                persona_raw = "patient 5-year-old level tutor"
            elif "quiz" in q_cl or "practice" in q_cl:
                persona_raw = "quizmaster and interactive instructor"
            else:
                persona_raw = "pedagogical instructor"

        resolved = (
            f"Teach and explain {target_phrase} step-by-step in the role of a {persona_raw}, "
            f"using intuitive real-world analogies, foundational concepts, and engaging pedagogical explanations."
        )
        matched = True
        target = target_phrase
        try:
            mem.preferences["active_persona"] = persona_raw
            mem.save(update_fields=["preferences"])
        except Exception:
            pass

    # 1. Targeted pronoun phrases: "about it", "explain this", "regarding that"
    elif is_about_phrase:
        def _rep_about(m):
            prep = m.group(1)
            pron = m.group(2).lower()
            if pron == "them" and len(active_ents) > 1:
                return f"{prep} {plural_target}"
            return f"{prep} {target_phrase}"
        resolved = PRONOUN_ABOUT_PHRASE.sub(_rep_about, resolved)
        matched = True
        target = target_phrase

    # 2. Standalone short queries: "what is it?", "how does it work?", "where is it?"
    elif is_standalone_followup:
        def _rep_standalone(m):
            full = m.group(0)
            for p in ["it", "this", "that"]:
                pattern = rf"\b{p}\b"
                if re.search(pattern, full, re.I):
                    return re.sub(pattern, target_phrase, full, flags=re.I)
            return full
        resolved = STANDALONE_PRONOUN_QUERY.sub(_rep_standalone, resolved)
        matched = True
        target = target_phrase

    # 3. Possessive pronouns in short follow-ups: its -> Target's, their -> Targets'
    elif ANAPHORA_POSSESSIVE.search(resolved) and (len(tokens) <= 6 or is_explicit_cue):
        def _rep_pos(m):
            w = m.group(1).lower()
            if w in ("their", "theirs") and len(active_ents) > 1:
                return f"{plural_target}'s"
            return f"{target_phrase}'s"
        resolved = ANAPHORA_POSSESSIVE.sub(_rep_pos, resolved)
        matched = True
        target = target_phrase

    # 4. Plural object pronouns: them -> Targets
    elif ANAPHORA_PLURAL_OBJ.search(resolved) and (len(tokens) <= 6 or is_explicit_cue):
        resolved = ANAPHORA_PLURAL_OBJ.sub(plural_target, resolved)
        matched = True
        target = target_phrase

    # 5. Singular pronoun 'it' in short follow-ups (never 'that' or 'this' to protect relative clauses)
    elif ANAPHORA_SINGULAR_OBJ.search(resolved) and (len(tokens) <= 6 or is_explicit_cue):
        resolved = ANAPHORA_SINGULAR_OBJ.sub(target_phrase, resolved)
        matched = True
        target = target_phrase

    # 6. Aspect, roster, lineup, schedule, and attribute inquiries (e.g. 'name the players', 'which seats are free', 'ticket suites for this game')
    if not matched:
        if is_aspect and (len(tokens) <= 8 or is_explicit_cue):
            clean_stripped = clean_query.rstrip(".?!")
            if re.search(r"\b(in|of|for|at|on|between)\s*$", q_lower):
                resolved = f"{clean_stripped} {target_phrase}"
            elif "both teams" in q_lower or "both clubs" in q_lower:
                resolved = f"{clean_stripped} of {target_phrase}"
            elif re.search(r"\bfor\s+(?:this\s+game|this\s+match|the\s+match|the\s+game)\b", clean_stripped, re.I):
                resolved = re.sub(r"\bfor\s+(?:this\s+game|this\s+match|the\s+match|the\s+game)\b", f"for {target_phrase}", clean_stripped, flags=re.I)
            elif re.search(r"\b(this\s+game|this\s+match|the\s+match|the\s+game)\b", clean_stripped, re.I):
                resolved = re.sub(r"\b(this\s+game|this\s+match|the\s+match|the\s+game)\b", target_phrase, clean_stripped, flags=re.I)
            else:
                resolved = f"{clean_stripped} for {target_phrase}"
            matched = True
            target = target_phrase

    # 7. Fragment follow-ups without explicit subject (e.g. 'introductory course please', 'how much?', 'syllabus')
    if not matched:
        if target.lower() not in q_lower and not any(e.lower() in q_lower for e in active_ents):
            if len(tokens) <= 4 and any(cue in q_lower for cue in [
                "course", "syllabus", "intro", "introductory", "fees", "cost", "rates",
                "pricing", "history", "origin", "overview", "admission", "requirements",
                "eligibility", "explain", "details", "visual imagery", "imagery", "images",
                "visuals", "photos", "pictures", "gallery", "sitting map", "seating map", "map"
            ]):
                resolved = f"{resolved.rstrip('.?!')} on {target_phrase}"
                matched = True
                target = target_phrase

    # 8. Elliptical Prepositional / Adverbial / Environment Modifier Follow-ups (e.g. 'in ubuntu via cli', 'on macos', 'for windows 11')
    if not matched:
        if is_elliptical:
            last_q = (mem.preferences or {}).get("last_query", "").strip()
            if not last_q:
                try:
                    from core.models import ConversationThread
                    thread = ConversationThread.objects.filter(session_id=session_id).first()
                    if thread and thread.turns:
                        last_q = (thread.turns[-1].get("query") or "").strip()
                except Exception:
                    pass

            stripped_mod = re.sub(
                r"^(?:(?:and|but|or|also|now|then)\s+)?(?:(?:what|how)\s+about\s+)?",
                "",
                clean_query,
                flags=re.I,
            ).strip().rstrip(".?!")

            if last_q:
                clean_last = last_q.rstrip(".?!")
                base_query = re.sub(
                    r"\s+\b(?:in|on|for|via|with|using|through|under)\s+[a-z0-9_\-\.\s]+$",
                    "",
                    clean_last,
                    flags=re.I,
                ).strip()
                if not base_query:
                    base_query = clean_last
                resolved = f"{base_query} {stripped_mod}"
            else:
                resolved = f"{target_phrase} {stripped_mod}"

            matched = True
            target = target_phrase

    if matched:
        logger.info(f"Resolved anaphora for session '{mem.session_id}': '{clean_query}' -> '{resolved}'")
        return resolved, target

    return clean_query, None


def record_turn_outcome(
    session_id: Optional[str],
    query: str,
    primary_subject: Optional[str] = None,
    presented_entities: Optional[List[str]] = None,
    verified_sources: Optional[List[Dict[str, Any]]] = None,
    purged_items: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Sterilizes and updates the SQLite session memory post-synthesis.
    Increases reputation of high-yield verified sources, penalizes paywalls,
    and updates active working entities, primary subject, and last query.
    Protects thread foundational topic from being overwritten by generic aspect words.
    """
    if not session_id:
        return

    try:
        mem = get_or_create_session_memory(session_id)
        dirty = False

        # 0. Persist last query and conversational goals to prevent context drift
        prefs = dict(mem.preferences or {})
        clean_q = (query or "").strip()
        if clean_q:
            prefs["last_query"] = clean_q
            q_hist = list(prefs.get("query_history") or [])
            if clean_q not in q_hist:
                q_hist.append(clean_q)
            prefs["query_history"] = q_hist[-8:]
            mem.preferences = prefs
            dirty = True

        # 1. Update primary subject (protect against generic aspect words like "Key", "Seats", "Tickets")
        clean_sub = (primary_subject or "").strip()
        is_sub_generic = (
            not clean_sub
            or clean_sub.lower() in _DISALLOWED_SUBJECT_WORDS
            or all(w.lower() in _DISALLOWED_SUBJECT_WORDS for w in clean_sub.split())
        )

        if clean_sub and len(clean_sub) >= 2 and not is_sub_generic:
            if not mem.last_subject or clean_sub != mem.last_subject:
                # If current last_subject is already substantive, only change if clean_sub introduces a new proper entity
                if not mem.last_subject or any(w[0].isupper() and w.lower() not in _DISALLOWED_SUBJECT_WORDS for w in clean_sub.split()):
                    mem.last_subject = clean_sub
                    dirty = True

        # 2. Accumulate active entities (never wipe out earlier entities with generic words)
        existing_ents = list(mem.active_entities or [])
        clean_ents = []
        for e in (presented_entities or []):
            e_str = e.strip()
            e_low = e_str.lower()
            if (
                len(e_str) >= 2
                and e_low not in _DISALLOWED_SUBJECT_WORDS
                and not all(w in _DISALLOWED_SUBJECT_WORDS for w in e_low.split())
                and e_str not in clean_ents
            ):
                clean_ents.append(e_str)

        merged_ents = []
        for e in existing_ents + clean_ents:
            if e not in merged_ents and e.lower() not in _DISALLOWED_SUBJECT_WORDS:
                merged_ents.append(e)

        if merged_ents and merged_ents != mem.active_entities:
            mem.active_entities = merged_ents[:8]
            dirty = True

        if not mem.last_subject and mem.active_entities:
            mem.last_subject = mem.active_entities[0]
            dirty = True

        # 3. Update domain reputation
        rep = dict(mem.domain_reputation or {})
        for src in (verified_sources or []):
            dom = _clean_domain(src.get("url") or src.get("domain") or "")
            if dom and len(dom) >= 4:
                val = int(src.get("valueScore") or 70)
                delta = 15 if val >= 80 else 5
                rep[dom] = min(100, rep.get(dom, 50) + delta)
                dirty = True

        # 4. Penalize or blacklist contrary / placeholder items
        b_list = list(mem.blacklisted_entities or [])
        for item in (purged_items or []):
            p_url = item.get("pageUrl") or item.get("url") or ""
            dom = _clean_domain(p_url)
            if dom:
                rep[dom] = max(-100, rep.get(dom, 50) - 25)
                dirty = True
            matched = item.get("matchedEntity") or item.get("company")
            if matched and matched not in (presented_entities or []) and matched not in b_list:
                b_list.append(matched)
                dirty = True

        mem.domain_reputation = rep
        mem.blacklisted_entities = b_list[:12]

        if dirty and hasattr(mem, "save"):
            mem.save()
            logger.info(f"Updated AgentProfileMemory for session '{mem.session_id}' in SQLite (last_subject='{mem.last_subject}').")
    except Exception as exc:
        logger.warning(f"Failed to record turn outcome to AgentProfileMemory: {exc}")

"""
Temporal Intent Understanding & Epistemic Gating Engine for Spider AI.

Analyzes user query linguistic signals (tense, aspect, modality) and knowledge volatility
to classify the epistemic half-life of requested information. Dynamically configures
tool manifests, prevents wasteful discovery calls for timeless truths (math/physics/algorithms),
and enforces canonical domain jailing for real-time transactional state.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("spider_ai.temporal_gating")


class VolatilityTier(str, Enum):
    """Epistemic volatility tiers defining information decay half-life."""
    INVARIANT = "INVARIANT"                      # Half-life: ∞ (Math, physics, algorithms, definitions)
    INSTITUTIONAL = "INSTITUTIONAL"              # Half-life: Years/Decades (Historical facts, stadium capacities)
    PERIODIC = "PERIODIC"                        # Half-life: Months/Quarters (Tax brackets, tariffs, interest rates)
    TRANSACTIONAL_STATE = "TRANSACTIONAL_STATE"  # Half-life: Real-time (Seats unbooked, tickets, inventory)
    BREAKING_NEWS = "BREAKING_NEWS"              # Half-life: Minutes/Hours (Breaking crises, live traffic, trending)


class TemporalAnchor(str, Enum):
    """Temporal reference frame extracted from grammatical tense and markers."""
    TIMELESS = "TIMELESS"                        # Gnomic present, atemporal definitions
    HISTORICAL_PAST = "HISTORICAL_PAST"          # Completed historical events
    RECENT_PAST = "RECENT_PAST"                  # Days/weeks ago
    REAL_TIME_NOW = "REAL_TIME_NOW"              # Immediate continuous present / live state


@dataclass
class TemporalIntentProfile:
    volatility_tier: VolatilityTier
    temporal_anchor: TemporalAnchor
    rationale: str
    allowed_tools: Set[str] = field(default_factory=set)
    prohibited_tools: Set[str] = field(default_factory=set)
    bypass_discovery: bool = False
    enforce_canonical_jail: bool = False
    canonical_target_domain: Optional[str] = None
    presentation_mode: str = "direct"  # "pedagogical", "archival", "transactional", "breaking"


# Known canonical entities to authoritative domains mapping
CANONICAL_ENTITY_DOMAINS: Dict[str, str] = {
    "talanta": "talantasportscity.com",
    "talanta sports city": "talantasportscity.com",
    "talanta stadium": "talantasportscity.com",
    "talantasportcity": "talantasportscity.com",
    "safaricom": "safaricom.co.ke",
    "m-pesa": "safaricom.co.ke",
    "kplc": "kplc.co.ke",
    "kra": "kra.go.ke",
    "bayern": "fcbayern.com",
    "ajax": "ajax.nl",
    "kenya airways": "kenya-airways.com",
    "ecitizen": "ecitizen.go.ke",
    "cbk": "centralbank.go.ke",
    "central bank": "centralbank.go.ke",
}

# Regex to detect timeless math, physics, computer science algorithms, definitions, and syntax
INVARIANT_PATTERNS = re.compile(
    r"\b("
    r"formula|formulae|equation|equations|theorem|theorems|algorithm|algorithms|"
    r"derivation|derivations|definition|definitions|syntax|proof|proofs|identity|"
    r"lemma|axiom|quadratic|pythagorean|fibonacci|dijkstra|binary\s+search|"
    r"quicksort|mergesort|merge\s+sort|bubble\s+sort|breadth\s+first|depth\s+first|"
    r"dynamic\s+programming|big\s+o|time\s+complexity|space\s+complexity|"
    r"photosynthesis|mitosis|meiosis|osmosis|entropy|newton's\s+law|newtonian|"
    r"calculus|derivative|integral|differential\s+equation|matrix\s+multiplication|"
    r"eigenvalues?|eigenvectors?|fourier\s+transform|bayes(?:ian)?\s+theorem|"
    r"transformer(?:\s+[a-z-]+)*\s+attention|multi-head\s+attention|attention\s+mechanism|"
    r"neural\s+network|deep\s+learning|backpropagation|gradient\s+descent|perceptron|"
    r"data\s+structure|hash\s+table|linked\s+list|binary\s+tree|graph\s+traversal|"
    r"boiling\s+point\s+of\s+water|speed\s+of\s+light|gravitational\s+constant"
    r")\b",
    re.I,
)

# Regex to detect historical past inquiries
HISTORICAL_PATTERNS = re.compile(
    r"\b("
    r"who\s+founded|when\s+was\s+(?:the\s+)?[a-z0-9\s]+\s+founded|who\s+built|"
    r"when\s+was\s+(?:the\s+)?[a-z0-9\s]+\s+built|promulgated|in\s+19\d\d|in\s+200\d|"
    r"history\s+of|origin\s+of|biography\s+of|first\s+president|first\s+secretary|"
    r"independence\s+in\s+1963|colonial\s+era|world\s+war"
    r")\b",
    re.I,
)

# Regex to detect live breaking news and real-time public sentiment
BREAKING_PATTERNS = re.compile(
    r"\b("
    r"breaking\s+news|happening\s+(?:right\s+)?now|trending\s+today|just\s+in|"
    r"developing\s+story|traffic\s+(?:right\s+)?now|protests?\s+today|"
    r"earthquake\s+today|accident\s+today|live\s+stream|live\s+updates?"
    r")\b",
    re.I,
)

# Regex to detect real-time transactional inventory and operational state
TRANSACTIONAL_STATE_PATTERNS = re.compile(
    r"\b("
    r"seats?\s+(?:not\s+booked|left|available|unbooked|taken)|"
    r"ticket\s+prices?|how\s+much\s+(?:is|for)\s+a\s+ticket|how\s+many\s+seats|"
    r"booking\s+portal|seating\s+plan|sitting\s+plan|seating\s+map|bowl\s+layout|"
    r"flight\s+status|is\s+flight\s+[a-z0-9]+\s+on\s+time|account\s+balance|"
    r"power\s+blackout\s+schedule|tokens?\s+balance"
    r")\b",
    re.I,
)

# Regex to detect periodic operational / macroeconomic indicators
PERIODIC_PATTERNS = re.compile(
    r"\b("
    r"base\s+lending\s+rate|cbr\s+rate|inflation\s+rate|statutory\s+minimum\s+wage|"
    r"fuel\s+pump\s+prices?|epra\s+prices?|tax\s+brackets?|paye\s+brackets?|"
    r"semester\s+dates?|academic\s+calendar|matatu\s+fares?"
    r")\b",
    re.I,
)


class TemporalIntentGatingEngine:
    """
    Cognitive Gatekeeper that determines what tools and subagents are permitted
    or blocked based on the epistemic half-life of requested knowledge.
    """

    def analyze_query(
        self,
        query: str,
        detected_entities: Optional[List[str]] = None,
        user_intent: Optional[Dict[str, Any]] = None,
    ) -> TemporalIntentProfile:
        q_clean = query.strip()
        q_low = q_clean.lower()

        # 1. Check for real-time temporal markers
        has_real_time_marker = bool(
            re.search(r"\b(now|today|tonight|this morning|right now|currently|live|just in)\b", q_low)
        )
        has_future_year = bool(re.search(r"\b202[5-9]\b", q_low))
        has_historical_year = bool(re.search(r"\b(?:1[7-9]\d\d|200\d|201[0-9])\b", q_low))

        # 2. Check for Transactional State & Canonical Jailing
        is_transactional = bool(TRANSACTIONAL_STATE_PATTERNS.search(q_low)) or bool(
            re.search(r"\b(ticket|tickets|seat|seats|booked|unbooked|booking|price|pricing|cost|fare)\b", q_low)
            and any(k in q_low for k in CANONICAL_ENTITY_DOMAINS)
        )
        if is_transactional:
            target_domain = None
            for ent_kw, dom in CANONICAL_ENTITY_DOMAINS.items():
                if re.search(rf"\b{re.escape(ent_kw)}\b", q_low):
                    target_domain = dom
                    break

            return TemporalIntentProfile(
                volatility_tier=VolatilityTier.TRANSACTIONAL_STATE,
                temporal_anchor=TemporalAnchor.REAL_TIME_NOW,
                rationale="Transactional inquiry requesting live seat inventory, ticket pricing, or operational status.",
                allowed_tools={
                    "browser_navigate",
                    "browser_get_interactive_snapshot",
                    "fetch_page_markdown",
                    "extract_tables_from_page",
                    "extract_images_from_page",
                    "web_search",
                },
                prohibited_tools={
                    "news_search",
                    "social_and_platform_search",
                },
                bypass_discovery=False,
                enforce_canonical_jail=bool(target_domain),
                canonical_target_domain=target_domain,
                presentation_mode="transactional",
            )

        # 3. Check for Invariant / Timeless Truths (Math, Physics, Algorithms, Definitions)
        is_invariant = bool(INVARIANT_PATTERNS.search(q_low))
        has_actionable_math_verb = bool(
            re.search(r"^(?:what\s+is\s+(?:the\s+)?|explain\s+|derive\s+|define\s+|calculate\s+|solve\s+|how\s+does\s+)", q_low)
        )
        is_coding_how_to = bool(
            re.search(r"\b(how\s+to\s+(?:code|implement|write|sort|reverse|traverse|calculate)|code\s+for|solution\s+to)\b", q_low)
        )

        # If it's a timeless formula/algorithm and NOT referencing a breaking news story or contemporary controversy
        if (is_invariant or is_coding_how_to) and not has_real_time_marker and not has_future_year:
            return TemporalIntentProfile(
                volatility_tier=VolatilityTier.INVARIANT,
                temporal_anchor=TemporalAnchor.TIMELESS,
                rationale="Invariant inquiry targeting timeless mathematical, physical, or algorithmic ground truth.",
                allowed_tools={
                    "evaluate_expression_or_convert",
                    "check_requirements_coverage",
                },
                prohibited_tools={
                    "news_search",
                    "social_and_platform_search",
                    "video_search",
                    "multi_related_site_search_and_crawl",
                },
                bypass_discovery=True,
                enforce_canonical_jail=False,
                canonical_target_domain=None,
                presentation_mode="pedagogical",
            )

        # 4. Check for Breaking News / Live Crisis
        is_breaking = bool(BREAKING_PATTERNS.search(q_low)) or (
            has_real_time_marker and re.search(r"\b(traffic|protest|fire|crash|accident|election|score|match|clash)\b", q_low)
        )
        if is_breaking:
            return TemporalIntentProfile(
                volatility_tier=VolatilityTier.BREAKING_NEWS,
                temporal_anchor=TemporalAnchor.REAL_TIME_NOW,
                rationale="Hyper-volatile inquiry targeting breaking events, live traffic, or immediate developments.",
                allowed_tools={
                    "news_search",
                    "social_and_platform_search",
                    "web_search",
                    "video_search",
                    "fetch_page_markdown",
                },
                prohibited_tools={
                    "academic_and_reference_search",
                },
                bypass_discovery=False,
                enforce_canonical_jail=False,
                canonical_target_domain=None,
                presentation_mode="breaking",
            )

        # 5. Check for Institutional / Historical Past
        is_historical = bool(HISTORICAL_PATTERNS.search(q_low)) or (
            has_historical_year and not has_real_time_marker
        )
        if is_historical:
            return TemporalIntentProfile(
                volatility_tier=VolatilityTier.INSTITUTIONAL,
                temporal_anchor=TemporalAnchor.HISTORICAL_PAST,
                rationale="Institutional/historical inquiry referencing established past events, biographies, or origins.",
                allowed_tools={
                    "web_search",
                    "academic_and_reference_search",
                    "pdf_search_and_summarize",
                    "fetch_page_markdown",
                },
                prohibited_tools={
                    "news_search",
                    "social_and_platform_search",
                    "video_search",
                },
                bypass_discovery=False,
                enforce_canonical_jail=False,
                canonical_target_domain=None,
                presentation_mode="archival",
            )

        # 6. Check for Periodic Operational Indicators (Tariffs, Taxes, Benchmark rates)
        is_periodic = bool(PERIODIC_PATTERNS.search(q_low))
        if is_periodic:
            return TemporalIntentProfile(
                volatility_tier=VolatilityTier.PERIODIC,
                temporal_anchor=TemporalAnchor.RECENT_PAST,
                rationale="Periodic operational indicator subject to monthly or quarterly regulatory gazettement.",
                allowed_tools={
                    "web_search",
                    "pdf_search_and_summarize",
                    "academic_and_reference_search",
                    "fetch_page_markdown",
                },
                prohibited_tools={
                    "social_and_platform_search",
                },
                bypass_discovery=False,
                enforce_canonical_jail=False,
                canonical_target_domain=None,
                presentation_mode="direct",
            )

        # Default fallback: General Web Discovery
        return TemporalIntentProfile(
            volatility_tier=VolatilityTier.INSTITUTIONAL,
            temporal_anchor=TemporalAnchor.RECENT_PAST,
            rationale="General knowledge inquiry with standard discovery policy.",
            allowed_tools={
                "web_search",
                "news_search",
                "academic_and_reference_search",
                "fetch_page_markdown",
                "extract_images_from_page",
                "image_search",
            },
            prohibited_tools=set(),
            bypass_discovery=False,
            enforce_canonical_jail=False,
            canonical_target_domain=None,
            presentation_mode="direct",
        )

    def is_tool_permitted(
        self,
        tool_name: str,
        profile: TemporalIntentProfile,
    ) -> Tuple[bool, str]:
        """Validates whether a specific tool execution complies with the temporal policy."""
        if tool_name in profile.prohibited_tools:
            return (
                False,
                f"Tool '{tool_name}' is PROHIBITED for {profile.volatility_tier.value} volatility inquiries ({profile.rationale}).",
            )
        return True, "Permitted"

    def filter_tool_declarations(
        self,
        tool_declarations: List[Dict[str, Any]],
        profile: TemporalIntentProfile,
    ) -> List[Dict[str, Any]]:
        """Prunes prohibited tool declarations so the model cannot even contemplate invoking them."""
        if not profile.prohibited_tools:
            return tool_declarations

        approved = []
        for decl in tool_declarations:
            t_name = decl.get("name", "")
            if t_name not in profile.prohibited_tools:
                approved.append(decl)
            else:
                logger.debug(f"Temporally gated tool declaration '{t_name}' out of model context.")
        return approved

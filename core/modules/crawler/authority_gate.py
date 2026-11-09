import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spider_ai.crawler.authority")


@dataclass
class AuthorityVerdict:
    tier: int  # 1 = Primary Official, 2 = Verified News, 3 = Informal/Vlog
    is_transactional_authority: bool
    verdict: str  # "OFFICIAL_PRIMARY", "REPUTABLE_NEWS", "INFORMAL_SPECULATIVE"
    domain: str
    rationale: str


class EpistemicAuthorityGate:
    """
    Epistemic Source Authority Engine.
    Enforces strict tiering on factual claims:
    - Tier 1 (Primary Official): Allowed to assert pricing, seat counts, operational policies.
    - Tier 2 (Verified News): Allowed for corroboration and reporting.
    - Tier 3 (Informal / Speculative): Forbidden from overriding or asserting official pricing/inventory.
    """

    def __init__(self, canonical_target_domain: Optional[str] = None):
        self.canonical_domain = (canonical_target_domain or "").lower().replace("www.", "").strip()

    def evaluate_source(self, url: str, query: str = "") -> AuthorityVerdict:
        if not url:
            return AuthorityVerdict(
                tier=3,
                is_transactional_authority=False,
                verdict="INFORMAL_SPECULATIVE",
                domain="",
                rationale="Missing URL.",
            )

        parsed = urllib.parse.urlparse(url)
        dom = parsed.netloc.lower().replace("www.", "")

        # 1. Tier 1: Canonical Primary Domain or Government / Official Portals
        is_canonical = bool(self.canonical_domain and (dom == self.canonical_domain or dom.endswith(f".{self.canonical_domain}")))
        is_gov = bool(re.search(r"\b(gov|go\.ke|gc\.ca|gov\.uk)\b", dom))
        is_known_primary = any(kd in dom for kd in ("talantasportscity.com", "talantasportcity.com", "fcbayern.com", "ajax.nl", "safaricom.co.ke"))

        if is_canonical or is_gov or is_known_primary:
            return AuthorityVerdict(
                tier=1,
                is_transactional_authority=True,
                verdict="OFFICIAL_PRIMARY",
                domain=dom,
                rationale=f"Primary verified official portal ({dom}) with direct transactional authority.",
            )

        # 2. Tier 3: Informal video vlogs, social media, user-generated content
        is_informal = any(
            sd in dom
            for sd in (
                "youtube.com", "youtu.be", "tiktok.com", "facebook.com", "instagram.com",
                "twitter.com", "x.com", "reddit.com", "blogspot.com", "wordpress.com",
            )
        )
        if is_informal:
            return AuthorityVerdict(
                tier=3,
                is_transactional_authority=False,
                verdict="INFORMAL_SPECULATIVE",
                domain=dom,
                rationale=f"Informal / community platform ({dom}); speculative for official transactional figures.",
            )

        # 3. Tier 2: Mainstream News & Sports Journalism
        is_news = bool(
            re.search(
                r"\b(news|standardmedia|nation\.africa|the-star|capitalfm|kbc\.co\.ke|"
                r"pulsesports|mozzartsport|michezoafrika|reuters|bbc|apnews|bloomberg|bundesliga)\b",
                dom,
            )
        )
        if is_news:
            return AuthorityVerdict(
                tier=2,
                is_transactional_authority=False,
                verdict="REPUTABLE_NEWS",
                domain=dom,
                rationale=f"Verified journalistic outlet ({dom}) suitable for secondary corroboration.",
            )

        # Default fallback: Tier 2 (General Web)
        return AuthorityVerdict(
            tier=2,
            is_transactional_authority=False,
            verdict="GENERAL_WEB",
            domain=dom,
            rationale=f"General web reference ({dom}).",
        )

    def filter_factual_claims(
        self,
        extracted_facts: List[Dict[str, Any]],
        has_primary_sources: bool,
    ) -> List[Dict[str, Any]]:
        """
        Guarantees that if Tier 1 sources are present, speculative Tier 3 claims
        (e.g. vlog numbers) regarding pricing and seat availability are pruned.
        """
        if not has_primary_sources:
            return extracted_facts

        approved = []
        for fact in extracted_facts:
            src_url = fact.get("sourceUrl", "")
            verdict = self.evaluate_source(src_url)
            is_pricing_or_seat_count = bool(
                re.search(
                    r"\b(price|prices|pricing|cost|costs|fees?|seats?|tickets?|ksh|kes|\$|\d+\s+remaining)\b",
                    str(fact),
                    re.I,
                )
            )
            if is_pricing_or_seat_count and verdict.tier > 1:
                logger.info(f"Purging unverified non-primary Tier {verdict.tier} pricing/seat claim from {verdict.domain}")
                continue
            approved.append(fact)
        return approved

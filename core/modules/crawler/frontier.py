import hashlib
import logging
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("spider_ai.crawler.frontier")

# Universal path noise blacklist (never crawl administrative or privacy boilerplates)
NOISY_PATH_PATTERNS = re.compile(
    r"\b(privacy(?:[-_]?policy)?|terms(?:[-_]?(?:of[-_]?service|and[-_]?conditions))?|"
    r"cookie(?:[-_]?policy)?|disclaimer|copyright|dmca|sitemap\.xml|wp-admin|"
    r"login|signin|register|signup|auth|account|cart|checkout|password-reset)\b",
    re.I,
)

# High-intent keyword patterns that warrant exploration priority boosts
HIGH_INTENT_PATH_KEYWORDS = {
    "ticket": 40,
    "tickets": 40,
    "ticketing": 40,
    "seating": 35,
    "seat": 30,
    "seats": 35,
    "seating-map": 45,
    "seat-map": 45,
    "map": 20,
    "layout": 25,
    "tiers": 25,
    "pricing": 30,
    "price": 30,
    "prices": 30,
    "rates": 25,
    "fees": 25,
    "cost": 25,
    "booking": 35,
    "book": 35,
    "hospitality": 40,
    "suites": 35,
    "suite": 35,
    "vip": 30,
    "vvip": 30,
    "packages": 25,
    "package": 25,
    "plan-your-visit": 30,
    "visit": 20,
    "events": 20,
    "event": 20,
    "fixture": 25,
    "fixtures": 25,
    "match": 25,
    "schedule": 20,
}


@dataclass
class CrawlCandidate:
    url: str
    priority: int = 50
    depth: int = 0
    source_anchor: str = ""
    path_intent: str = "general"
    discovered_at: float = field(default_factory=time.time)

    def __lt__(self, other: "CrawlCandidate") -> bool:
        # Higher priority first
        return self.priority > other.priority


class CrawlFrontier:
    """
    Stateful Crawl Frontier & Graph Engine.
    Manages prioritized candidate URLs, enforces domain jail, prunes administrative noise,
    tracks visited URL hashes, and enforces hop/depth/time limits.
    """

    def __init__(
        self,
        target_domain: str,
        max_depth: int = 3,
        max_pages: int = 5,
        time_limit_sec: float = 12.0,
        intent_keywords: Optional[List[str]] = None,
    ):
        clean_target = target_domain.lower().replace("www.", "").strip()
        self.target_domain = clean_target
        self.allowed_domains: Set[str] = {clean_target, f"www.{clean_target}"}
        # Include canonical subdomains (e.g. hospitality.talantasportscity.com)
        self.max_depth = max(1, min(5, max_depth))
        self.max_pages = max(1, min(10, max_pages))
        self.time_limit_sec = max(3.0, min(30.0, time_limit_sec))
        self.start_time = time.time()

        self.custom_intent_keywords = [
            k.lower().strip() for k in (intent_keywords or []) if len(k.strip()) >= 3
        ]

        self.visited_urls: Set[str] = set()
        self.visited_hashes: Set[str] = set()
        self.queue: List[CrawlCandidate] = []
        self.pages_crawled_count: int = 0

    def _canonicalize_url(self, raw_url: str) -> str:
        """Strips URL fragment and tracking query parameters for clean deduplication."""
        try:
            parsed = urllib.parse.urlparse(raw_url)
            # Remove tracking params
            filtered_query = urllib.parse.parse_qsl(parsed.query)
            clean_query = [
                (k, v)
                for k, v in filtered_query
                if not k.startswith("utm_")
                and k not in ("fbclid", "gclid", "ref", "source", "trk")
            ]
            new_query = urllib.parse.urlencode(clean_query)
            canonical = urllib.parse.urlunparse(
                (parsed.scheme or "https", parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", new_query, "")
            )
            return canonical
        except Exception:
            return raw_url.strip()

    def _hash_url(self, canonical_url: str) -> str:
        return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]

    def is_domain_allowed(self, url: str) -> bool:
        """Domain jail: Ensures crawler never escapes target domain or its subdomains."""
        try:
            parsed = urllib.parse.urlparse(url)
            netloc = parsed.netloc.lower().replace("www.", "")
            if not netloc:
                return False
            if netloc == self.target_domain or netloc.endswith(f".{self.target_domain}"):
                return True
            return False
        except Exception:
            return False

    def is_noisy_path(self, url_or_path: str) -> bool:
        """Rejects administrative, login, and privacy boilerplate links."""
        return bool(NOISY_PATH_PATTERNS.search(url_or_path))

    def _compute_priority(self, url: str, anchor_text: str, depth: int) -> Tuple[int, str]:
        """
        Computes exploration priority score (0 to 100):
        Base score: 50
        High-intent path keyword matches: +20 to +45
        Anchor text intent matches: +15 to +30
        Depth penalty: -10 per hop
        """
        base_score = 50 - (depth * 10)
        combined_text = f"{url.lower()} {anchor_text.lower()}"
        detected_intents = []

        for kw, boost in HIGH_INTENT_PATH_KEYWORDS.items():
            if re.search(rf"\b{re.escape(kw)}\b", combined_text):
                base_score += boost
                detected_intents.append(kw)

        for cik in self.custom_intent_keywords:
            if cik in combined_text:
                base_score += 25
                detected_intents.append(cik)

        primary_intent = detected_intents[0] if detected_intents else "general"
        clamped_score = max(5, min(100, base_score))
        return clamped_score, primary_intent

    def add_seed(self, seed_url: str, priority: int = 100):
        """Adds starting entry points (e.g. homepage or ticketing portal) to frontier."""
        canon = self._canonicalize_url(seed_url)
        u_hash = self._hash_url(canon)
        if u_hash in self.visited_hashes:
            return

        candidate = CrawlCandidate(
            url=canon,
            priority=priority,
            depth=0,
            source_anchor="Seed Entry",
            path_intent="seed",
        )
        self.queue.append(candidate)
        self.queue.sort()

    def enqueue_discovered_links(
        self,
        base_url: str,
        links: List[Dict[str, str]],
        current_depth: int,
    ):
        """
        Evaluates, filters, scores, and enqueues newly discovered hyperlinks
        from a crawled page's DOM.
        """
        if current_depth + 1 > self.max_depth:
            return

        for link in links:
            raw_href = (link.get("href") or link.get("url") or "").strip()
            anchor = (link.get("anchor") or link.get("text") or "").strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            # Resolve relative URLs
            full_url = urllib.parse.urljoin(base_url, raw_href)
            canon = self._canonicalize_url(full_url)
            u_hash = self._hash_url(canon)

            if u_hash in self.visited_hashes:
                continue
            if not self.is_domain_allowed(canon):
                continue
            if self.is_noisy_path(canon):
                continue

            # Check if already in queue
            if any(self._hash_url(c.url) == u_hash for c in self.queue):
                continue

            priority, path_intent = self._compute_priority(canon, anchor, current_depth + 1)
            candidate = CrawlCandidate(
                url=canon,
                priority=priority,
                depth=current_depth + 1,
                source_anchor=anchor[:60],
                path_intent=path_intent,
            )
            self.queue.append(candidate)

        # Keep sorted by priority descending
        self.queue.sort()

    def pop_next(self) -> Optional[CrawlCandidate]:
        """Retrieves the highest-priority candidate from the frontier."""
        if self.is_budget_exhausted():
            return None
        if not self.queue:
            return None

        candidate = self.queue.pop(0)
        u_hash = self._hash_url(candidate.url)
        self.visited_hashes.add(u_hash)
        self.visited_urls.add(candidate.url)
        self.pages_crawled_count += 1
        return candidate

    def is_empty(self) -> bool:
        return len(self.queue) == 0

    def is_budget_exhausted(self) -> bool:
        """Checks if crawl limit or time ceiling has been hit."""
        if self.pages_crawled_count >= self.max_pages:
            return True
        if (time.time() - self.start_time) >= self.time_limit_sec:
            return True
        return False

    def get_summary(self) -> Dict[str, Any]:
        return {
            "targetDomain": self.target_domain,
            "pagesCrawled": self.pages_crawled_count,
            "maxPages": self.max_pages,
            "remainingQueue": len(self.queue),
            "elapsedSec": round(time.time() - self.start_time, 2),
            "visitedUrls": list(self.visited_urls),
        }

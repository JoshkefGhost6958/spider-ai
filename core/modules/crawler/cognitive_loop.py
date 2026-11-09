import logging
import re
import time
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Set

from .authority_gate import EpistemicAuthorityGate
from .dom_distiller import DOMDistiller, DistilledPage
from .frontier import CrawlCandidate, CrawlFrontier

logger = logging.getLogger("spider_ai.crawler.cognitive_loop")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 SpiderAI/2.0"


@dataclass
class InformationSlot:
    name: str
    description: str
    is_required: bool = True
    is_fulfilled: bool = False
    evidence: Any = None
    source_url: str = ""


@dataclass
class CrawlResult:
    target_domain: str
    is_successful: bool
    termination_reason: str  # "slots_fulfilled", "budget_exhausted", "frontier_empty"
    fulfilled_slots: Dict[str, Any]
    structured_tables: List[Dict[str, Any]]
    interactive_ctas: List[str]
    verified_images: List[Dict[str, str]]
    crawled_pages: List[DistilledPage]
    elapsed_sec: float


class CognitiveCrawlerLoop:
    """
    Autonomous Cognitive ReAct Crawler Loop.
    Executes a goal-driven Plan-Act-Observe-Reflect cycle over a stateful CrawlFrontier.
    Extracts structured tables, schemas, and images, evaluates information completeness,
    backtracks on dead ends, and terminates as soon as mandatory slots are satisfied.
    """

    def __init__(
        self,
        target_domain: str,
        user_query: str,
        max_depth: int = 3,
        max_pages: int = 5,
        time_limit_sec: float = 12.0,
        required_slots: Optional[List[str]] = None,
    ):
        clean_target = target_domain.lower().replace("www.", "").strip()
        self.target_domain = clean_target
        self.user_query = user_query
        self.time_limit_sec = time_limit_sec

        # Extract keyword cues from user query for frontier prioritization
        query_keywords = [
            w.lower()
            for w in re.findall(r"[a-z0-9]+", user_query)
            if len(w) >= 3 and w not in ("the", "and", "for", "with", "from", "fetch", "crawl")
        ]

        self.frontier = CrawlFrontier(
            target_domain=clean_target,
            max_depth=max_depth,
            max_pages=max_pages,
            time_limit_sec=time_limit_sec,
            intent_keywords=query_keywords,
        )
        self.distiller = DOMDistiller(target_domain=clean_target)
        self.authority_gate = EpistemicAuthorityGate(canonical_target_domain=clean_target)

        # Initialize Information Slots
        self.slots: Dict[str, InformationSlot] = self._initialize_slots(user_query, required_slots)
        self.crawled_pages: List[DistilledPage] = []
        self.collected_tables: List[Dict[str, Any]] = []
        self.collected_ctas: List[str] = []
        self.collected_images: List[Dict[str, str]] = []
        self.start_time = time.time()

    def _initialize_slots(
        self, query: str, custom_slots: Optional[List[str]] = None
    ) -> Dict[str, InformationSlot]:
        slots = {}
        q_low = query.lower()

        is_pricing_req = bool(re.search(r"\b(price|prices|pricing|cost|costs|fees?|ticket|tickets|rates?|how\s+much)\b", q_low))
        is_seating_req = bool(re.search(r"\b(seat|seats|seating|suites?|vip|tiers?|layout|map|occupation|assignment)\b", q_low))
        is_booking_req = bool(re.search(r"\b(book|booking|buy|purchase|pay|payment|channel|portal|ticket|tickets|how\s+to\s+book)\b", q_low))

        if is_pricing_req:
            slots["pricing_and_tiers"] = InformationSlot(
                name="pricing_and_tiers",
                description="Match ticket prices and tier categories",
                is_required=True,
            )
        if is_seating_req:
            slots["seating_layout"] = InformationSlot(
                name="seating_layout",
                description="Stadium seating layout, tier architecture, or bowl visual diagram",
                is_required=True,
            )
        if is_booking_req:
            slots["booking_channel"] = InformationSlot(
                name="booking_channel",
                description="Official booking portal URL, action buttons, or payment methods",
                is_required=True,
            )

        # Default fallback if open-ended
        if not slots:
            slots["general_overview"] = InformationSlot(
                name="general_overview",
                description="Overview of requested subject and official details",
                is_required=True,
            )

        for cs in (custom_slots or []):
            if cs not in slots:
                slots[cs] = InformationSlot(name=cs, description=cs, is_required=True)

        return slots

    def are_all_slots_fulfilled(self) -> bool:
        return all(s.is_fulfilled for s in self.slots.values() if s.is_required)

    def _fetch_html(self, url: str) -> str:
        """Lightweight HTTP fetch with timeout and realistic headers."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.read(300_000).decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug(f"HTTP fetch failed for {url}: {e}")
            return ""

    def run_autonomous_crawl(
        self, seed_url: str
    ) -> Generator[Dict[str, Any], None, CrawlResult]:
        """
        Executes the autonomous cognitive loop.
        Yields real-time step events for UI progress while executing ReAct steps.
        """
        self.frontier.add_seed(seed_url, priority=100)
        step_index = 1
        termination_reason = "frontier_empty"

        while not self.frontier.is_empty() and not self.frontier.is_budget_exhausted():
            # 1. PLAN
            candidate = self.frontier.pop_next()
            if not candidate:
                break

            yield {
                "event": "agent_action",
                "step": step_index,
                "module": "Autonomous Crawler Subagent",
                "status": "running",
                "detail": f"Navigating & inspecting '{candidate.url}' (Priority: {candidate.priority}, Intent: {candidate.path_intent})...",
            }
            t_hop = time.time()

            # 2. ACT: Fetch and Distill DOM
            raw_html = self._fetch_html(candidate.url)
            distilled = self.distiller.distill(raw_html, candidate.url)
            self.crawled_pages.append(distilled)

            # 3. OBSERVE: Evaluate Extracted Assets & Slot Fulfillment
            new_tables = distilled.tables
            new_ctas = distilled.interactive_elements
            new_images = distilled.images
            page_text = distilled.clean_markdown

            self.collected_tables.extend(new_tables)
            self.collected_ctas.extend(new_ctas)
            self.collected_images.extend(new_images)

            slots_fulfilled_in_hop = []

            # Check pricing & tiers slot
            if "pricing_and_tiers" in self.slots and not self.slots["pricing_and_tiers"].is_fulfilled:
                if new_tables or re.search(r"\b(ksh|kes|\$|usd|price|tier|regular|vip)\s*\d+", page_text, re.I):
                    self.slots["pricing_and_tiers"].is_fulfilled = True
                    self.slots["pricing_and_tiers"].evidence = new_tables or page_text[:400]
                    self.slots["pricing_and_tiers"].source_url = candidate.url
                    slots_fulfilled_in_hop.append("pricing_and_tiers")

            # Check seating layout slot
            if "seating_layout" in self.slots and not self.slots["seating_layout"].is_fulfilled:
                if new_images or re.search(r"\b(seating|tiers?|bowl|concourse|capacity|vomitory)\b", page_text, re.I):
                    self.slots["seating_layout"].is_fulfilled = True
                    self.slots["seating_layout"].evidence = new_images or page_text[:400]
                    self.slots["seating_layout"].source_url = candidate.url
                    slots_fulfilled_in_hop.append("seating_layout")

            # Check booking channel slot
            if "booking_channel" in self.slots and not self.slots["booking_channel"].is_fulfilled:
                if new_ctas or re.search(r"\b(book|booking|buy\s+tickets?|m-pesa|portal)\b", page_text, re.I):
                    self.slots["booking_channel"].is_fulfilled = True
                    self.slots["booking_channel"].evidence = new_ctas or page_text[:300]
                    self.slots["booking_channel"].source_url = candidate.url
                    slots_fulfilled_in_hop.append("booking_channel")

            if "general_overview" in self.slots and not self.slots["general_overview"].is_fulfilled:
                if len(page_text) >= 150:
                    self.slots["general_overview"].is_fulfilled = True
                    self.slots["general_overview"].evidence = page_text[:500]
                    self.slots["general_overview"].source_url = candidate.url
                    slots_fulfilled_in_hop.append("general_overview")

            # 4. REFLECT: Link Enqueueing vs. Backtracking
            self.frontier.enqueue_discovered_links(
                base_url=candidate.url,
                links=distilled.internal_links,
                current_depth=candidate.depth,
            )

            d_hop = int((time.time() - t_hop) * 1000)

            if slots_fulfilled_in_hop:
                detail_msg = f"Extracted from '{distilled.domain}': resolved {', '.join(slots_fulfilled_in_hop)} ({len(new_tables)} table(s), {len(new_images)} visual(s))."
            elif len(new_tables) == 0 and len(distilled.clean_markdown) < 100:
                detail_msg = f"Pruned low-content page '{distilled.domain}'; backtracking to frontier priority queue."
            else:
                detail_msg = f"Traversed '{distilled.domain}': queued {len(distilled.internal_links)} sub-link(s)."

            yield {
                "event": "agent_action",
                "step": step_index,
                "module": "Autonomous Crawler Subagent",
                "status": "completed",
                "durationMs": d_hop,
                "detail": detail_msg,
            }
            step_index += 1

            # Check dynamic termination on completeness
            if self.are_all_slots_fulfilled():
                termination_reason = "slots_fulfilled"
                break

        if self.frontier.is_budget_exhausted():
            termination_reason = "budget_exhausted"

        elapsed = round(time.time() - self.start_time, 2)
        return CrawlResult(
            target_domain=self.target_domain,
            is_successful=any(s.is_fulfilled for s in self.slots.values()),
            termination_reason=termination_reason,
            fulfilled_slots={
                k: {"fulfilled": v.is_fulfilled, "source": v.source_url, "evidence": v.evidence}
                for k, v in self.slots.items()
            },
            structured_tables=self.collected_tables,
            interactive_ctas=self.collected_ctas,
            verified_images=self.collected_images,
            crawled_pages=self.crawled_pages,
            elapsed_sec=elapsed,
        )

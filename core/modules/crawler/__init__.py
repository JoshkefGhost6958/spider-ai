"""
Autonomous Cognitive Crawler Sub-package for Spider AI.
Provides stateful crawl frontier management, semantic DOM distillation,
epistemic source authority gating, and the ReAct cognitive loop.
"""

from .authority_gate import AuthorityVerdict, EpistemicAuthorityGate
from .cognitive_loop import CognitiveCrawlerLoop, CrawlResult, InformationSlot
from .dom_distiller import DOMDistiller, DistilledPage
from .frontier import CrawlCandidate, CrawlFrontier

__all__ = [
    "AuthorityVerdict",
    "CognitiveCrawlerLoop",
    "CrawlCandidate",
    "CrawlFrontier",
    "CrawlResult",
    "DOMDistiller",
    "DistilledPage",
    "EpistemicAuthorityGate",
    "InformationSlot",
]

"""
Unit and integration test suite for the Temporal Intent Understanding & Epistemic Gating Engine.

Verifies:
1. Invariant queries (math formulas, algorithms, definitions) bypass external discovery
   and strictly prohibit news and social tools.
2. Historical past queries route to archival reference tools and prohibit live news/socials.
3. Transactional queries enforce canonical domain jailing and real-time state inspection.
4. Breaking news queries permit live news and social vectors.
5. Tool declaration filtering and execution policy enforcement.
"""

from django.test import TestCase
from core.modules.temporal_intent_gating import (
    TemporalIntentGatingEngine,
    TemporalIntentProfile,
    VolatilityTier,
    TemporalAnchor,
)
from core.tools import GEMINI_FUNCTION_DECLARATIONS


class TemporalIntentGatingTests(TestCase):
    def setUp(self):
        self.engine = TemporalIntentGatingEngine()

    def test_invariant_math_formulae_and_algorithms(self):
        """Invariant queries (math formulas, physics laws, algorithms) must bypass external discovery."""
        test_queries = [
            "what is the quadratic formula",
            "explain Dijkstra's shortest path algorithm time complexity",
            "derive the Pythagorean theorem proof",
            "how does Transformer multi-head attention work",
            "define photosynthesis and the Calvin cycle",
            "write code for binary search algorithm",
        ]

        for q in test_queries:
            profile = self.engine.analyze_query(q)
            self.assertEqual(
                profile.volatility_tier,
                VolatilityTier.INVARIANT,
                f"Expected INVARIANT for query: '{q}', got {profile.volatility_tier}",
            )
            self.assertEqual(profile.temporal_anchor, TemporalAnchor.TIMELESS)
            self.assertTrue(profile.bypass_discovery, f"Expected bypass_discovery=True for: '{q}'")
            # Must strictly prohibit news and social tools
            self.assertIn("news_search", profile.prohibited_tools)
            self.assertIn("social_and_platform_search", profile.prohibited_tools)
            self.assertIn("video_search", profile.prohibited_tools)
            self.assertIn("multi_related_site_search_and_crawl", profile.prohibited_tools)

    def test_historical_past_events_and_origins(self):
        """Historical inquiries must route to archival tools and prohibit live news and social scrapers."""
        test_queries = [
            "who founded Safaricom and when was M-Pesa launched in 2007",
            "who was the first secretary general of KADU in 1960",
            "when was the original Nyayo National Stadium built",
            "promulgated constitution of Kenya in 1963 history",
        ]

        for q in test_queries:
            profile = self.engine.analyze_query(q)
            self.assertEqual(
                profile.volatility_tier,
                VolatilityTier.INSTITUTIONAL,
                f"Expected INSTITUTIONAL for query: '{q}', got {profile.volatility_tier}",
            )
            self.assertEqual(profile.temporal_anchor, TemporalAnchor.HISTORICAL_PAST)
            self.assertFalse(profile.bypass_discovery)
            # Prohibit live news and social media
            self.assertIn("news_search", profile.prohibited_tools)
            self.assertIn("social_and_platform_search", profile.prohibited_tools)
            # Allow web and academic/reference
            self.assertIn("web_search", profile.allowed_tools)
            self.assertIn("academic_and_reference_search", profile.allowed_tools)

    def test_transactional_state_and_canonical_domain_jailing(self):
        """Transactional inventory queries must enforce canonical domain jailing and derate secondary news blogs."""
        query = "how many seats have not been booked in talanta for the bayern and ajax match show also stadium visual sitting plan"
        profile = self.engine.analyze_query(query)

        self.assertEqual(profile.volatility_tier, VolatilityTier.TRANSACTIONAL_STATE)
        self.assertEqual(profile.temporal_anchor, TemporalAnchor.REAL_TIME_NOW)
        self.assertTrue(profile.enforce_canonical_jail)
        self.assertEqual(profile.canonical_target_domain, "talantasportscity.com")
        # Prohibit news and social tools from asserting transactional figures
        self.assertIn("news_search", profile.prohibited_tools)
        self.assertIn("social_and_platform_search", profile.prohibited_tools)

    def test_breaking_news_and_real_time_crises(self):
        """Hyper-volatile breaking news queries must activate live news and social discovery vectors."""
        test_queries = [
            "breaking news what is happening right now along Mombasa Road",
            "traffic right now in Nairobi CBD accident today",
            "live updates on the ongoing election protest today",
        ]

        for q in test_queries:
            profile = self.engine.analyze_query(q)
            self.assertEqual(
                profile.volatility_tier,
                VolatilityTier.BREAKING_NEWS,
                f"Expected BREAKING_NEWS for query: '{q}', got {profile.volatility_tier}",
            )
            self.assertEqual(profile.temporal_anchor, TemporalAnchor.REAL_TIME_NOW)
            self.assertIn("news_search", profile.allowed_tools)
            self.assertIn("social_and_platform_search", profile.allowed_tools)

    def test_periodic_operational_indicators(self):
        """Periodic operational inquiries (tariffs, tax brackets, lending rates) classify as PERIODIC."""
        test_queries = [
            "what is the current base lending rate set by CBK",
            "EPRA fuel pump prices for super petrol this month",
            "Kenya statutory minimum wage and PAYE tax brackets",
        ]

        for q in test_queries:
            profile = self.engine.analyze_query(q)
            self.assertEqual(
                profile.volatility_tier,
                VolatilityTier.PERIODIC,
                f"Expected PERIODIC for query: '{q}', got {profile.volatility_tier}",
            )
            self.assertIn("social_and_platform_search", profile.prohibited_tools)

    def test_tool_declaration_filtering_and_permission_checks(self):
        """Validates filter_tool_declarations prunes prohibited tools from the model context."""
        math_profile = self.engine.analyze_query("what is the quadratic formula")
        filtered_decls = self.engine.filter_tool_declarations(
            GEMINI_FUNCTION_DECLARATIONS, math_profile
        )
        filtered_names = {d["name"] for d in filtered_decls}

        # News, social, video tools must be completely stripped out
        self.assertNotIn("news_search", filtered_names)
        self.assertNotIn("social_and_platform_search", filtered_names)
        self.assertNotIn("video_search", filtered_names)
        self.assertNotIn("multi_related_site_search_and_crawl", filtered_names)

        # Permission checks
        ok_math, msg1 = self.engine.is_tool_permitted("evaluate_expression_or_convert", math_profile)
        self.assertTrue(ok_math)
        ok_news, msg2 = self.engine.is_tool_permitted("news_search", math_profile)
        self.assertFalse(ok_news)
        self.assertIn("PROHIBITED", msg2)

from django.test import SimpleTestCase, TestCase
from core.modules.adversarial_verification import (
    extract_testable_claims,
    generate_adversarial_counter_queries,
    arbitrate_evidence_and_score,
    format_verification_badge_token,
)
from core.modules.stadium_artifacts import (
    detect_stadium_plan_intent,
    generate_stadium_map_token,
)
from core.modules.entity_disambiguation import disambiguate_query_entities
from core.tools.live_solution_tools import (
    generate_interactive_venue_map,
    generate_interactive_chart,
    execute_sandboxed_python,
    execute_sandboxed_sql,
    compile_research_dossier,
)


class AdversarialEpistemicVerificationTests(SimpleTestCase):
    def test_extract_testable_claims(self):
        sample_answer = """
        For the upcoming Bayern Munich vs Ajax exhibition match at the 60,000-capacity Raila Odinga International Stadium on January 5, 2027.
        Lower-tier budget tickets (KSh 2,500 to KSh 5,000) are sold out.
        Regular tickets cost KSh 10,000 with 7,987 seats left.
        VIP tickets cost KSh 35,000 with 600 seats left.
        VVIP tickets cost KSh 80,000 with 196 seats left.
        """
        claims = extract_testable_claims(sample_answer, "how many seats left in talanta")
        self.assertGreater(len(claims), 0)
        types = [c["type"] for c in claims]
        self.assertTrue(
            "QUANTITATIVE_AVAILABILITY" in types or "FINANCIAL_PRICING" in types or "AVAILABILITY_STATUS" in types
        )

    def test_counter_query_formulation(self):
        counter_queries = generate_adversarial_counter_queries([], "how many seats left in talanta for bayern ajax")
        self.assertGreater(len(counter_queries), 0)
        self.assertTrue(any("talanta" in q.lower() or "stadium" in q.lower() for q in counter_queries))

    def test_arbitrate_evidence_and_score(self):
        claims = [
            {"type": "QUANTITATIVE_AVAILABILITY", "statement": "7,987 regular seats left"},
            {"type": "AVAILABILITY_STATUS", "statement": "Lower tier budget tickets sold out within hours"},
        ]
        primary_sources = [
            {"title": "Talanta Official Tickets", "url": "https://talantasportscity.com/tickets", "platform": "Primary Discovery"},
            {"title": "BBC Sports News", "url": "https://bbc.com/sport/football", "platform": "News"},
        ]
        report = arbitrate_evidence_and_score(claims, primary_sources)
        self.assertGreaterEqual(report["confidenceScore"], 85)
        self.assertIn("HIGH CONFIDENCE", report["verdictBadge"])
        self.assertTrue(report["authorityBacked"])
        self.assertIn("talantasportscity.com", report["authorityDomains"])

    def test_verification_badge_token_formatting(self):
        report = {
            "confidenceScore": 96,
            "verdictBadge": "HIGH CONFIDENCE",
            "summary": "96% Truth Confidence • 4 Verified Claims",
            "verifiedClaims": ["60,000 capacity", "7,987 regular seats left"],
            "contestedClaims": [],
            "authorityDomains": ["talantasportscity.com"],
            "auditTimestamp": "2026-11-09T18:00:00Z",
        }
        token = format_verification_badge_token(report)
        self.assertTrue(token.startswith("[[INLINE_VERIFICATION_BADGE:96||HIGH CONFIDENCE"))


class LiveSolutionToolsTests(SimpleTestCase):
    def test_generate_interactive_venue_map(self):
        res = generate_interactive_venue_map(
            stadium_name="Raila Odinga International Stadium (Talanta Sports City)",
            match_title="Bayern Munich vs Ajax Seating Plan",
        )
        self.assertTrue(res["success"])
        self.assertGreater(res["totalCapacity"], 50000)
        self.assertGreater(res["totalUnbooked"], 10000)
        self.assertIn("[[INLINE_STADIUM_MAP:", res["inlinedToken"])

    def test_generate_interactive_chart(self):
        res = generate_interactive_chart(
            chart_type="bar",
            title="Ticket Pricing by Tier (KSh)",
            labels=["Regular", "Mid-Tier", "Business", "VIP", "VVIP"],
            datasets=[{"label": "Price KSh", "data": [10000, 17500, 22000, 35000, 80000]}],
        )
        self.assertTrue(res["success"])
        self.assertIn("[[INLINE_CHART:bar||Ticket Pricing by Tier (KSh)", res["inlinedToken"])

    def test_execute_sandboxed_python_arithmetic(self):
        code = """
total_capacity = 60000
booked_budget = 15000
unbooked_regular = 7987
unbooked_vip = 600
unbooked_vvip = 196
total_unbooked = unbooked_regular + unbooked_vip + unbooked_vvip
percent_unbooked = round((total_unbooked / total_capacity) * 100, 2)
print(f"Total unbooked: {total_unbooked}, percentage: {percent_unbooked}%")
"""
        res = execute_sandboxed_python(code)
        self.assertTrue(res["success"])
        self.assertIn("Total unbooked: 8783", res["output"])
        self.assertEqual(res["variables"]["total_unbooked"], 8783)

    def test_execute_sandboxed_python_blocks_forbidden_imports(self):
        res = execute_sandboxed_python("import os\nprint(os.listdir('.'))")
        self.assertFalse(res["success"])
        self.assertIn("Security restriction", res["error"])

    def test_execute_sandboxed_sql(self):
        query = "SELECT tier, price, available FROM tiers WHERE available > 500 ORDER BY price DESC"
        cols = ["tier", "price", "available"]
        rows = [
            ["Regular", 10000, 7987],
            ["Business", 22000, 993],
            ["VIP", 35000, 600],
            ["VVIP", 80000, 196],
        ]
        res = execute_sandboxed_sql(query, table_name="tiers", columns=cols, rows=rows)
        self.assertTrue(res["success"])
        self.assertEqual(res["rowCount"], 3)
        self.assertEqual(res["rows"][0][0], "VIP")

    def test_execute_sandboxed_sql_blocks_mutations(self):
        res = execute_sandboxed_sql("DROP TABLE test")
        self.assertFalse(res["success"])
        self.assertIn("Only read-only SELECT", res["error"])

    def test_compile_research_dossier(self):
        res = compile_research_dossier(
            title="Talanta Stadium Bayern vs Ajax Intelligence Brief",
            summary="Comprehensive breakdown of unbooked seats and visual tier structure.",
            sections=[
                {"title": "Unbooked Seat Distribution", "content": "Over 14,000 seats remain unbooked."},
                {"title": "Pricing & VIP Access", "content": "VVIP tickets priced at KSh 80,000."},
            ],
            sources=[
                {"title": "Talanta Sports City", "url": "https://talantasportscity.com", "domain": "talantasportscity.com"},
            ],
        )
        self.assertTrue(res["success"])
        self.assertIn("# Talanta Stadium Bayern vs Ajax Intelligence Brief", res["markdownDossier"])
        self.assertIn("## Executive Summary", res["markdownDossier"])
        self.assertIn("## Connected Sources & Authority Attribution", res["markdownDossier"])


class StadiumVisualizerDetectionTests(SimpleTestCase):
    def test_detect_stadium_plan_intent(self):
        q = "how many seats have not been booked in talanta for the bayern and ajax match show also stadium visual sitting plan"
        ans = "The 60,000-seater Raila Odinga International Stadium features three vertical tiers."
        self.assertTrue(detect_stadium_plan_intent(q, ans))

    def test_generate_stadium_map_token(self):
        token = generate_stadium_map_token()
        self.assertTrue(token.startswith("[[INLINE_STADIUM_MAP:Raila Odinga International Stadium"))

    def test_detect_stadium_plan_intent_with_atlanta_typo(self):
        q = "Which seats are available at Atlanta for Bayern vs ajax match show visual mapping"
        ans = "The Raila Odinga International Stadium in Nairobi has three active tiers."
        self.assertTrue(detect_stadium_plan_intent(q, ans))

    def test_disambiguate_query_entities_atlanta(self):
        q = "Which seats are available at Atlanta for Bayern vs ajax match show visual mapping"
        corrected, notice = disambiguate_query_entities(q)
        self.assertIn("Talanta Sports City Nairobi", corrected)
        self.assertIsNotNone(notice)
        self.assertIn("Raila Odinga International Stadium", notice)
        self.assertIn("not Atlanta, Georgia, USA", notice)

    def test_disambiguate_query_entities_kasarani(self):
        q = "How to get tickets for Kasarani stadium football match"
        corrected, notice = disambiguate_query_entities(q)
        self.assertIn("Moi International Sports Centre", corrected)
        self.assertIsNotNone(notice)

    def test_disambiguate_query_entities_negative(self):
        q = "Who is the mayor of Atlanta Georgia"
        corrected, notice = disambiguate_query_entities(q)
        self.assertEqual(corrected, q)
        self.assertIsNone(notice)

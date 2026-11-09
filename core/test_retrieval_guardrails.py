from django.test import TestCase
import re
from core.modules.profile_memory import (
    resolve_query_anaphora,
    record_turn_outcome,
    get_or_create_session_memory,
    _DISALLOWED_SUBJECT_WORDS,
)
from core.modules.autonomous_retrieval import (
    _is_media_relevant,
    _extract_presentation_subject,
    _evaluate_presentation_relevance,
    _build_sharp_investigative_queries,
)
from core.modules.intent_classification import classify_and_refine_intents
from core.modules.input_normalization import normalize_user_input
from core.modules.ambiguity_detection import detect_ambiguities_and_contradictions
from core.modules.deterministic_validation import compute_execution_readiness
from core.modules.relevance_discriminator import (
    RelevanceDiscriminatorSubagent,
    GENERIC_STOP_WORDS,
)


class RetrievalGuardrailsMultiScenarioTests(TestCase):
    """
    Comprehensive multi-scenario test suite verifying:
    1. Direct site crawl & typo resolution directives
    2. Explicit site visual imagery extraction
    3. Cross-venue & competing entity contamination defense
    4. Transactional authority sourcing & informal vlog derating
    5. Multi-turn contextual continuity across n-turns (thread grip)
    6. Strict session isolation against topic bleed
    """

    def test_scenario_1_canonical_domain_resolution_and_site_directives(self):
        """Scenario 1: Canonical domain resolution and site-targeted crawl directives."""
        _CANONICAL_SITE_MAP = {
            "talanta": "talantasportscity.com",
            "talanta sports city": "talantasportscity.com",
            "talanta stadium": "talantasportscity.com",
            "talantasportcity": "talantasportscity.com",
            "safaricom": "safaricom.co.ke",
            "m-pesa": "safaricom.co.ke",
            "bayern": "fcbayern.com",
            "ajax": "ajax.nl",
        }

        test_queries = [
            ("crawl talanta website for bayern vs ajax info", "talantasportscity.com"),
            ("crawl talantasportcity website for tickets", "talantasportscity.com"),
            ("fetch me details from safaricom website", "safaricom.co.ke"),
            ("scrape the bayern website for squad news", "fcbayern.com"),
        ]

        for q, expected_domain in test_queries:
            site_directive_match = re.search(
                r"\bfrom\s+(?:the\s+)?([a-zA-Z0-9\.-]+(?:\s+[a-zA-Z0-9\.-]+)?)\s+website\b",
                q,
                re.I,
            ) or re.search(
                r"\b(?:crawl|scrape|inspect|check|explore|fetch(?:\s+me)?(?:\s+[a-z]+)?)\s+(?:the\s+)?([a-zA-Z0-9\.-]+(?:\s+[a-zA-Z0-9\.-]+)?)\s+website\b",
                q,
                re.I,
            )
            self.assertIsNotNone(site_directive_match, f"Directive match failed for query: {q}")
            raw_kw = site_directive_match.group(1).strip().lower()
            raw_kw = re.sub(r"^(?:from|the|on|at|me|details\s+from|info\s+from)\s+", "", raw_kw).strip()
            resolved_dom = _CANONICAL_SITE_MAP.get(raw_kw)
            self.assertEqual(resolved_dom, expected_domain, f"Failed domain resolution for: {q}")

    def test_scenario_2_explicit_site_visual_imagery_extraction(self):
        """Scenario 2: Explicit directive to fetch imagery from website triggers image extraction."""
        query = "fetch me stadium imagery of seats occupation and assignment from talanta website"
        user_wants_site_imagery = bool(
            re.search(r"\b(imagery|images?|photos?|pictures?|seat\s+occupation|assignment|screenshots?)\b", query, re.I)
        )
        self.assertTrue(user_wants_site_imagery)

        site_directive_match = re.search(
            r"\bfrom\s+(?:the\s+)?([a-zA-Z0-9\.-]+(?:\s+[a-zA-Z0-9\.-]+)?)\s+website\b",
            query,
            re.I,
        )
        self.assertIsNotNone(site_directive_match)
        raw_kw = site_directive_match.group(1).strip().lower()
        self.assertEqual(raw_kw, "talanta")

    def test_scenario_3_cross_venue_contamination_defense(self):
        """Scenario 3: Media focusing on competing venues is rejected both at retrieval and discriminator audits."""
        # Test 3a: Talanta query must reject Kasarani and Nyayo
        talanta_query = "fetch me stadium imagery of seats occupation and assignment from talanta website"
        kasarani_media = "NTV Kenya: Puzzle of empty seats at sold-out Kasarani Stadium"
        nyayo_media = "Nyayo National Stadium prepares for international athletics trial"
        talanta_media = "Talanta Sports City Stadium Interior Seating Bowl Layout"

        # Check retrieval layer
        self.assertFalse(_is_media_relevant(kasarani_media, talanta_query))
        self.assertFalse(_is_media_relevant(nyayo_media, talanta_query))
        self.assertTrue(_is_media_relevant(talanta_media, talanta_query))

        # Check discriminator audit layer
        disc = RelevanceDiscriminatorSubagent(user_query=talanta_query)
        candidates = [
            {"title": kasarani_media, "url": "https://ntvkenya.co.ke/kasarani", "mediaType": "image"},
            {"title": nyayo_media, "url": "https://standardmedia.co.ke/nyayo", "mediaType": "image"},
            {"title": talanta_media, "url": "https://talantasportscity.com/seats", "mediaType": "image"},
        ]
        approved, p_img, _ = disc.audit_and_critique_media(candidates, presentation_subject="Talanta Sports City")
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["title"], talanta_media)
        self.assertEqual(p_img, 2)

        # Test 3b: European Stadiums (Camp Nou vs Santiago Bernabeu)
        camp_nou_q = "Barcelona Camp Nou seating plan and ticket suites"
        bernabeu_media = "Inside the new Santiago Bernabeu Stadium premium skyboxes"
        camp_nou_media = "Camp Nou Spotify Stadium seating tiers and redevelopment"
        self.assertFalse(_is_media_relevant(bernabeu_media, camp_nou_q))
        self.assertTrue(_is_media_relevant(camp_nou_media, camp_nou_q))

        # Test 3c: Premier League Stadiums (Old Trafford vs Etihad)
        old_trafford_q = "Manchester United Old Trafford hospitality tickets"
        etihad_media = "Manchester City Etihad Stadium tunnel club and seats"
        old_trafford_media = "Manchester United Old Trafford Stretford End seating guide"
        self.assertFalse(_is_media_relevant(etihad_media, old_trafford_q))
        self.assertTrue(_is_media_relevant(old_trafford_media, old_trafford_q))

    def test_scenario_4_transactional_authority_and_vlog_derating(self):
        """Scenario 4: Primary portals outrank speculative YouTube vlogs for transactional queries."""
        query = "update me on seat availability at talanta which seats are taken and which are available how much for a ticket"
        disc = RelevanceDiscriminatorSubagent(user_query=query)

        sources = [
            {
                "title": "TALANTA STADIUM TICKETS UPDATE 10,671 SEATS LEFT",
                "url": "https://youtube.com/watch?v=mockvlog1",
                "platform": "YouTube",
                "snippet": "Vlogger claims approximately 10,671 seats remain available for booking",
                "valueScore": 75,
            },
            {
                "title": "MjengoHub: Rigid plastic seats controversy at Talanta",
                "url": "https://mjengohub.co.ke/seats-controversy",
                "platform": "Web",
                "snippet": "Public debate erupts over rigid plastic bucket seats at Talanta stadium",
                "valueScore": 70,
            },
            {
                "title": "Talanta Sports City Official Match Tickets & Booking Portal",
                "url": "https://talantasportscity.com/tickets",
                "platform": "Web",
                "snippet": "Official booking portal for match tickets starting from KSh 2,500 with M-Pesa",
                "valueScore": 85,
            },
        ]

        audited, _, _ = disc.audit_and_critique_sources(sources)
        # Official portal must be ranked #1
        self.assertEqual(audited[0]["title"], "Talanta Sports City Official Match Tickets & Booking Portal")
        self.assertIn("talantasportscity.com", audited[0]["url"])

        # Speculative vlog must NOT be #1
        self.assertNotEqual(audited[0]["platform"], "YouTube")

    def test_scenario_5_multi_turn_contextual_continuity_n_turns(self):
        """Scenario 5: Multi-turn conversational continuity is preserved to the n-th turn."""
        session_id = "test_guardrails_continuity_session_001"
        mem = get_or_create_session_memory(session_id)
        mem.last_subject = ""
        mem.active_entities = []
        mem.save()

        # Turn 1: Initial query
        t1_q = "who wil be present in bayern vs ajax name the players in both teams"
        eff1, target1 = resolve_query_anaphora(session_id, t1_q)
        record_turn_outcome(
            session_id=session_id,
            query=t1_q,
            primary_subject="FC Bayern Munich vs AFC Ajax",
            presented_entities=["FC Bayern Munich", "AFC Ajax", "Raila Odinga International Stadium"],
            verified_sources=[{"url": "https://talantasportscity.com", "valueScore": 90}],
            purged_items=[],
        )
        mem = get_or_create_session_memory(session_id)
        self.assertEqual(mem.last_subject, "FC Bayern Munich vs AFC Ajax")

        # Turn 2: Follow-up pricing
        t2_q = "how much is a ticket"
        eff2, target2 = resolve_query_anaphora(session_id, t2_q)
        self.assertEqual(target2, "FC Bayern Munich vs AFC Ajax")
        self.assertIn("FC Bayern Munich vs AFC Ajax", eff2)
        record_turn_outcome(
            session_id=session_id,
            query=eff2,
            primary_subject="FC Bayern Munich vs AFC Ajax",
            presented_entities=["Tickets", "Pricing"],
            verified_sources=[{"url": "https://talantasportscity.com", "valueScore": 90}],
            purged_items=[],
        )
        mem = get_or_create_session_memory(session_id)
        self.assertEqual(mem.last_subject, "FC Bayern Munich vs AFC Ajax")

        # Turn 3: Ticket suites with markdown containing 'Key' headings
        t3_q = "n kenya find me the ticket suites for this game and how to book"
        eff3, target3 = resolve_query_anaphora(session_id, t3_q)
        self.assertEqual(target3, "FC Bayern Munich vs AFC Ajax")

        turn3_md = """# Talanta Stadium Suites
FC Bayern Munich vs AFC Ajax hospitality suites at Raila Odinga Stadium in Nairobi.

### Key Contextual Breakdown of Seat Status
- Aviation: airline flight seats...
- Political: legislative seats...

### Key Details
- VIP Corporate Box: KSh 35,000
- VVIP Presidential Box: KSh 80,000
"""
        user_intent_3 = {
            "intent": {"primary": "investigate_information"},
            "subject": {"primarySubject": "FC Bayern Munich vs AFC Ajax"},
            "entities": [{"name": "Raila Odinga Stadium"}, {"name": "VIP suites"}],
            "constraints": {"geographic": [{"region": "Kenya"}]},
        }
        pres3 = _extract_presentation_subject(turn3_md, eff3, user_intent_3)
        self.assertNotEqual(pres3["primaryEntity"], "Key")
        self.assertNotIn(pres3["primaryEntity"].lower(), _DISALLOWED_SUBJECT_WORDS)
        self.assertEqual(pres3["primaryEntity"], "FC Bayern Munich vs AFC Ajax")

        record_turn_outcome(
            session_id=session_id,
            query=eff3,
            primary_subject=pres3["primaryEntity"],
            presented_entities=pres3.get("presentedEntities", []),
            verified_sources=[{"url": "https://talantasportscity.com", "valueScore": 90}],
            purged_items=[],
        )
        mem = get_or_create_session_memory(session_id)
        self.assertEqual(mem.last_subject, "FC Bayern Munich vs AFC Ajax")

        # Turn 4: The previously failing prompt
        t4_q = "which seats are free and which ones have been taken"
        eff4, target4 = resolve_query_anaphora(session_id, t4_q)
        self.assertEqual(target4, "FC Bayern Munich vs AFC Ajax")
        self.assertIn("FC Bayern Munich vs AFC Ajax", eff4)

        norm4 = normalize_user_input(eff4)
        intent4, subj4, _ = classify_and_refine_intents(
            {"primary": "investigate_information"},
            {"primarySubject": "seats"},
            norm4,
            session_id=session_id,
            fallback_subject=target4,
        )
        self.assertEqual(subj4.get("primarySubject"), "FC Bayern Munich vs AFC Ajax (seats)")

        ambig, assump, _ = detect_ambiguities_and_contradictions(
            raw_ambiguities={"items": [{"description": "Missing venue", "impact": "Ambiguous"}]},
            raw_assumptions=[],
            intent=intent4,
            subject=subj4,
            entities=[{"name": target4}],
            requirements=[{"label": "seat availability", "field": "seat_status"}],
            constraints={},
        )
        readiness = compute_execution_readiness(
            intent=intent4,
            subject=subj4,
            entities=[{"name": target4}],
            requirements=[{"label": "seat availability", "field": "seat_status"}],
            ambiguities=ambig,
            active_assumptions=assump,
            raw_planner_strategy={},
        )
        self.assertTrue(readiness["isExecutable"])

        intent_pkg = {
            "intent": intent4,
            "subject": subj4,
            "entities": [{"name": target4}],
            "constraints": {"geographic": []},
        }
        sharp = _build_sharp_investigative_queries(eff4, intent_pkg)
        self.assertNotIn("airline", sharp["web"].lower())
        self.assertNotIn("political", sharp["web"].lower())
        self.assertTrue(any(k in sharp["web"].lower() for k in ["bayern", "ajax", "talanta", "stadium"]))

    def test_scenario_6_session_isolation_against_topic_bleed(self):
        """Scenario 6: Fresh guest session query remains completely unpolluted by prior match queries."""
        fresh_session = "test_guardrails_fresh_isolation_session_002"
        fresh_q = "whats the biggest limmityation to scaling ai agents that perfor autonomous navigation and information gathering"
        eff_fresh, target_fresh = resolve_query_anaphora(fresh_session, fresh_q)

        self.assertIsNone(target_fresh)
        self.assertEqual(eff_fresh, fresh_q)
        self.assertNotIn("bayern", eff_fresh.lower())
        self.assertNotIn("ajax", eff_fresh.lower())
        self.assertNotIn("talanta", eff_fresh.lower())
        self.assertNotIn("pacific", eff_fresh.lower())

    def test_scenario_7_autonomous_cognitive_crawler_slot_fulfillment(self):
        """Scenario 7: CognitiveCrawlerLoop initializes required slots and executes autonomous frontier prioritization."""
        from core.modules.crawler import CognitiveCrawlerLoop, CrawlFrontier

        query = "crawl talanta website for tickets pricing tiers and seating layout"
        loop = CognitiveCrawlerLoop(
            target_domain="talantasportscity.com",
            user_query=query,
            max_depth=2,
            max_pages=3,
        )

        self.assertIn("pricing_and_tiers", loop.slots)
        self.assertIn("seating_layout", loop.slots)
        self.assertIn("booking_channel", loop.slots)

        frontier = loop.frontier
        frontier.add_seed("https://www.talantasportscity.com", priority=100)
        frontier.enqueue_discovered_links(
            "https://www.talantasportscity.com",
            [
                {"href": "/plan-your-visit/seating-map", "anchor": "Interactive Seating Plan"},
                {"href": "/tickets/hospitality", "anchor": "VIP Hospitality Suites"},
                {"href": "/privacy", "anchor": "Privacy Policy"},
            ],
            current_depth=0,
        )

        # Candidate 1: Seed
        c1 = frontier.pop_next()
        self.assertEqual(c1.url, "https://www.talantasportscity.com/")

        # Candidate 2: High-intent subpath
        c2 = frontier.pop_next()
        self.assertTrue("seating-map" in c2.url or "tickets" in c2.url)
        self.assertGreaterEqual(c2.priority, 75)

        # Privacy link should have been pruned
        remaining_urls = [c.url for c in frontier.queue]
        self.assertFalse(any("privacy" in u for u in remaining_urls))

    def test_scenario_8_dom_distiller_and_authority_gate(self):
        """Scenario 8: DOMDistiller extracts structured tables and CTAs; AuthorityGate enforces tiering."""
        from core.modules.crawler import DOMDistiller, EpistemicAuthorityGate

        distiller = DOMDistiller(target_domain="talantasportscity.com")
        sample_html = """
        <html>
        <head><title>Talanta Sports City Seating & Tickets</title></head>
        <body>
            <div class="cookie-modal">Cookies</div>
            <main>
                <h1>Raila Odinga Stadium Tiers</h1>
                <table>
                    <tr><th>Tier</th><th>Price</th></tr>
                    <tr><td>General Admission</td><td>KSh 2,500</td></tr>
                    <tr><td>VVIP Presidential</td><td>KSh 80,000</td></tr>
                </table>
                <button class="btn booking-btn">Book Regular KSh 2,500</button>
                <img src="/brand/seating-bowl.jpg" alt="Seating Bowl Mosaic" />
            </main>
        </body>
        </html>
        """
        page = distiller.distill(sample_html, "https://www.talantasportscity.com")
        self.assertEqual(len(page.tables), 1)
        self.assertEqual(page.tables[0]["rows"][0], ["General Admission", "KSh 2,500"])
        self.assertTrue(any("Book Regular" in cta for cta in page.interactive_elements))
        self.assertEqual(len(page.images), 1)

        # AuthorityGate validation
        gate = EpistemicAuthorityGate(canonical_target_domain="talantasportscity.com")
        primary_verdict = gate.evaluate_source("https://talantasportscity.com/tickets")
        vlog_verdict = gate.evaluate_source("https://youtube.com/watch?v=speculativevlog")
        self.assertEqual(primary_verdict.tier, 1)
        self.assertEqual(vlog_verdict.tier, 3)

        facts = [
            {"claim": "Official General Admission: KSh 2,500", "sourceUrl": "https://talantasportscity.com/tickets"},
            {"claim": "Speculative seat count: 10,671 remaining", "sourceUrl": "https://youtube.com/watch?v=speculativevlog"},
            {"claim": "Blog speculative tiers: Regular KSh 10,000", "sourceUrl": "https://kenya-today.com/talanta-prices"},
        ]
        clean_facts = gate.filter_factual_claims(facts, has_primary_sources=True)
        self.assertEqual(len(clean_facts), 1)
        self.assertIn("talantasportscity.com", clean_facts[0]["sourceUrl"])

    def test_scenario_9_canonical_portal_guaranteed_rank_one(self):
        """Scenario 9: Canonical official portal (talantasportscity.com) ALWAYS ranks #1 over keyword-stuffed news blogs."""
        query = "how many seats have not been booked in talanta for the bayern and ajax match show also stadium visual sitting plan"
        disc = RelevanceDiscriminatorSubagent(user_query=query)

        sources = [
            {
                "title": "Bayern Munich vs Ajax Raila Odinga Talanta Stadium Tickets Seats Booking Kenya Unbooked Breakdown",
                "url": "https://eastleighvoice.co.ke/sports/bayern-ajax-talanta",
                "source": "eastleighvoice.co.ke",
                "platform": "Related Site",
                "snippet": "Analysis of seats and ticket bookings for Bayern vs Ajax exhibition match at Talanta Raila Odinga stadium",
                "valueScore": 75,
            },
            {
                "title": "Unbooked seats breakdown by tier: Regular, Business, VIP, VVIP at Talanta",
                "url": "https://kenya-today.com/sports/unbooked-seats-talanta",
                "source": "kenya-today.com",
                "platform": "Web",
                "snippet": "Speculative breakdown claiming regular KSh 10,000 and business KSh 22,000",
                "valueScore": 70,
            },
            {
                "title": "Bayern Munich vs Ajax Tickets — Talanta Ticket",
                "url": "https://talantasportscity.com/tickets",
                "source": "talantasportscity.com",
                "platform": "Web",
                "snippet": "Official booking portal for Raila Odinga International Stadium match tickets starting from KSh 2,500",
                "valueScore": 85,
            },
        ]

        audited, _, _ = disc.audit_and_critique_sources(sources)
        self.assertEqual(len(audited), 3)
        # Primary official portal MUST be #1, beating the keyword-stuffed blog!
        self.assertEqual(audited[0]["source"], "talantasportscity.com")
        self.assertIn("talantasportscity.com", audited[0]["url"])
        # Blogs must be placed below the official portal
        self.assertNotEqual(audited[0]["source"], "eastleighvoice.co.ke")
        self.assertNotEqual(audited[0]["source"], "kenya-today.com")

    def test_scenario_10_implicit_canonical_domain_resolution_without_website_keyword(self):
        """Scenario 10: Transactional / seating queries implicitly resolve canonical domain without saying 'from website'."""
        _CANONICAL_SITE_MAP = {
            "talanta": "talantasportscity.com",
            "talanta sports city": "talantasportscity.com",
            "talanta stadium": "talantasportscity.com",
            "talantasportcity": "talantasportscity.com",
            "safaricom": "safaricom.co.ke",
            "m-pesa": "safaricom.co.ke",
            "bayern": "fcbayern.com",
            "ajax": "ajax.nl",
        }

        query = "how many seats have not been booked in talanta for the bayern and ajax match show also stadium visual sitting plan"
        q_low = query.lower()
        target_site_domain = ""
        is_transactional_or_lookup = bool(
            re.search(
                r"\b(ticket|tickets|seat|seats|booked|unbooked|booking|price|prices|pricing|cost|visual|sitting\s+plan|seating\s+plan|seating\s+map|bill|balance|portal|schedule|fixture)\b",
                q_low,
            )
        )
        self.assertTrue(is_transactional_or_lookup)
        if is_transactional_or_lookup:
            for ent_kw, dom in _CANONICAL_SITE_MAP.items():
                if re.search(rf"\b{re.escape(ent_kw)}\b", q_low):
                    target_site_domain = dom
                    break

        self.assertEqual(target_site_domain, "talantasportscity.com")

    def test_scenario_11_stadium_visual_seating_plan_retrieval_and_filtering(self):
        """Scenario 11: Seating plan queries generate layout searches and do NOT discard Raila Odinga stadium diagrams."""
        query = "how many seats have not been booked in talanta for the bayern and ajax match show also stadium visual sitting plan"
        pres_info = _extract_presentation_subject("Talanta Sports City Stadium", query, {})

        # Visual search queries must target seating layout and diagrams, not generic photos
        self.assertIn("seating plan", pres_info["searchQueryImage"].lower())
        self.assertIn("layout", pres_info["searchQueryImage"].lower())

        # Test media evaluation
        valid_seating_map = {
            "title": "Talanta Sports City (Raila Odinga International Stadium) Seating Plan Layout",
            "imageUrl": "https://talantasportscity.com/img/seating-map.png",
            "pageUrl": "https://talantasportscity.com/plan-your-visit/seating-map",
        }
        atlanta_false_positive = {
            "title": "Mercedes-Benz Stadium Atlanta Seating Chart and Suite Levels",
            "imageUrl": "https://mercedesbenzstadium.com/img/atlanta-map.png",
            "pageUrl": "https://mercedesbenzstadium.com/seating-map",
        }

        # Valid Raila Odinga Stadium seating map must be relevant
        is_rel, sc = _evaluate_presentation_relevance(valid_seating_map, pres_info)
        self.assertTrue(is_rel)
        self.assertGreaterEqual(sc, 50)

        # Atlanta Mercedes-Benz Stadium auto-correction must be REJECTED
        is_rel_atlanta, sc_atlanta = _evaluate_presentation_relevance(atlanta_false_positive, pres_info)
        self.assertFalse(is_rel_atlanta)

    def test_scenario_12_elliptical_modifier_drift_prevention(self):
        """Scenario 12: Elliptical prepositional/adverbial modifiers ('in ubuntu via cli') do NOT drift context."""
        session_id = "test_sess_elliptical_drift"
        mem = get_or_create_session_memory(session_id)
        mem.last_subject = ""
        mem.active_entities = []
        mem.preferences = {}
        mem.save()

        # Turn 1: "how do i prepare a bootable drive"
        t1_q = "how do i prepare a bootable drive"
        eff1, target1 = resolve_query_anaphora(session_id, t1_q)
        self.assertEqual(eff1, t1_q)
        record_turn_outcome(
            session_id=session_id,
            query=t1_q,
            primary_subject="bootable drive",
            presented_entities=["bootable drive", "USB drive", "Rufus", "balenaEtcher"],
            verified_sources=[{"url": "https://ubuntu.com", "valueScore": 95}],
            purged_items=[],
        )

        mem = get_or_create_session_memory(session_id)
        self.assertEqual(mem.last_subject, "bootable drive")
        self.assertEqual(mem.preferences.get("last_query"), t1_q)

        # Turn 2: "in ubuntu via cli" -> must resolve to bootable drive preparation, NOT generic ubuntu cli!
        t2_q = "in ubuntu via cli"
        eff2, target2 = resolve_query_anaphora(session_id, t2_q)
        self.assertEqual(eff2, "how do i prepare a bootable drive in ubuntu via cli")
        self.assertTrue("bootable drive" in target2)

        record_turn_outcome(
            session_id=session_id,
            query=eff2,
            primary_subject="bootable drive in Ubuntu CLI",
            presented_entities=["bootable drive", "Ubuntu CLI", "dd command"],
            verified_sources=[{"url": "https://ubuntu.com/tutorials", "valueScore": 98}],
            purged_items=[],
        )

        # Turn 3: "what about on macos using terminal?" -> replace previous platform constraint cleanly
        t3_q = "what about on macos using terminal?"
        eff3, target3 = resolve_query_anaphora(session_id, t3_q)
        self.assertIn("how do i prepare a bootable drive", eff3)
        self.assertIn("on macos using terminal", eff3)

        # Turn 4: "without rufus" -> adverbial exclusion modifier
        t4_q = "without rufus"
        eff4, target4 = resolve_query_anaphora(session_id, t4_q)
        self.assertIn("how do i prepare a bootable drive", eff4)
        self.assertIn("without rufus", eff4)

        # Turn 5: Independent non-elliptical question with complete predicate -> zero context pollution
        t5_q = "In what year was Linux invented?"
        eff5, target5 = resolve_query_anaphora(session_id, t5_q)
        self.assertEqual(eff5, t5_q)
        self.assertIsNone(target5)

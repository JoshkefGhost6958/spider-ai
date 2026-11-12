"""
Tests for Spider AI Authentication, Signup, Login, and Chat Tracking.
"""

import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from core.models import ConversationThread, AgentProfileMemory


class AuthAndChatTrackingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.username = "researcher_test"
        self.password = "Secur3P@ssword"

    def test_signup_successful(self):
        response = self.client.post(
            "/api/auth/register/",
            data=json.dumps({
                "username": self.username,
                "password": self.password,
                "password_confirm": self.password,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["username"], self.username)
        self.assertTrue(data["isAuthenticated"])
        self.assertTrue(User.objects.filter(username=self.username).exists())

    def test_signup_password_mismatch(self):
        response = self.client.post(
            "/api/auth/register/",
            data=json.dumps({
                "username": "mismatch_user",
                "password": "Password123",
                "password_confirm": "PasswordDifferent",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Passwords do not match", data["error"])

    def test_signup_password_too_short(self):
        response = self.client.post(
            "/api/auth/register/",
            data=json.dumps({
                "username": "short_user",
                "password": "12",
                "password_confirm": "12",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("at least 4 characters", data["error"])

    def test_signup_duplicate_username(self):
        User.objects.create_user(username=self.username, password=self.password)
        response = self.client.post(
            "/api/auth/register/",
            data=json.dumps({
                "username": self.username,
                "password": self.password,
                "password_confirm": self.password,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("already taken", data["error"])

    def test_login_successful(self):
        User.objects.create_user(username=self.username, password=self.password)
        response = self.client.post(
            "/api/auth/login/",
            data=json.dumps({"username": self.username, "password": self.password}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["username"], self.username)
        self.assertTrue(data["isAuthenticated"])

    def test_login_invalid_credentials(self):
        User.objects.create_user(username=self.username, password=self.password)
        response = self.client.post(
            "/api/auth/login/",
            data=json.dumps({"username": self.username, "password": "WrongPassword"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn("Invalid username or password", data["error"])

    def test_auth_status_and_logout(self):
        # 1. Status when unauthenticated
        res_status = self.client.get("/api/auth/status/")
        self.assertFalse(res_status.json()["isAuthenticated"])

        # 2. Login
        User.objects.create_user(username=self.username, password=self.password)
        self.client.login(username=self.username, password=self.password)
        res_status2 = self.client.get("/api/auth/status/")
        self.assertTrue(res_status2.json()["isAuthenticated"])
        self.assertEqual(res_status2.json()["username"], self.username)

        # 3. Logout
        res_logout = self.client.post("/api/auth/logout/")
        self.assertEqual(res_logout.status_code, 200)
        self.assertFalse(res_logout.json()["isAuthenticated"])

    def test_thread_save_and_tracking(self):
        user = User.objects.create_user(username=self.username, password=self.password)
        self.client.login(username=self.username, password=self.password)

        session_id = "sess_user_test_99"
        turns = [
            {"query": "Which seats are available at Talanta?", "answerMarkdown": "2,636 seats remaining."},
            {"query": "How much are VIP tickets?", "answerMarkdown": "VIP seats are KSh 35,000."},
        ]

        # Save thread
        res_save = self.client.post(
            "/api/threads/save/",
            data=json.dumps({
                "sessionId": session_id,
                "title": "Seats Availability at Talanta",
                "turns": turns,
            }),
            content_type="application/json",
        )
        self.assertEqual(res_save.status_code, 200)
        data = res_save.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["turnCount"], 2)

        # Retrieve thread details
        res_detail = self.client.get(f"/api/threads/{session_id}/")
        self.assertEqual(res_detail.status_code, 200)
        detail = res_detail.json()
        self.assertEqual(detail["sessionId"], session_id)
        self.assertEqual(detail["title"], "Seats Availability at Talanta")
        self.assertEqual(len(detail["turns"]), 2)

        # List user threads
        res_list = self.client.get("/api/threads/")
        self.assertEqual(res_list.status_code, 200)
        threads = res_list.json()["threads"]
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]["sessionId"], session_id)
        self.assertEqual(threads[0]["turnCount"], 2)

        # Delete thread
        res_del = self.client.post(f"/api/threads/{session_id}/delete/")
        self.assertEqual(res_del.status_code, 200)
        self.assertFalse(ConversationThread.objects.filter(session_id=session_id).exists())

    def test_guest_session_clear(self):
        guest_sess = "sess_guest_temp_123"
        ConversationThread.objects.create(session_id=guest_sess, title="Guest Chat", turns=[{"q": "test"}])
        AgentProfileMemory.objects.create(session_id=guest_sess, last_subject="Talanta")

        self.assertTrue(ConversationThread.objects.filter(session_id=guest_sess).exists())
        self.assertTrue(AgentProfileMemory.objects.filter(session_id=guest_sess).exists())

        res = self.client.post(
            "/api/session/clear-guest/",
            data=json.dumps({"sessionId": guest_sess}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(ConversationThread.objects.filter(session_id=guest_sess).exists())
        self.assertFalse(AgentProfileMemory.objects.filter(session_id=guest_sess).exists())

    def test_pedagogical_persona_drift_prevention(self):
        from core.modules.profile_memory import (
            get_or_create_session_memory,
            resolve_query_anaphora,
            PERSONA_OR_STYLE_DIRECTIVE,
        )
        from core.modules.intent_classification import classify_and_refine_intents
        from core.modules.autonomous_retrieval import _build_sharp_investigative_queries

        # Verify persona regex matches common user phrasing
        for phrase in [
            "act like a teacher",
            "Act like a teacher",
            "be my tutor",
            "explain like I'm 5",
            "quiz me",
            "talk like a pirate",
        ]:
            self.assertTrue(bool(PERSONA_OR_STYLE_DIRECTIVE.match(phrase)))

        # Turn 1: Establish subject
        test_sess = "sess_kinematics_pedagogy_test"
        mem = get_or_create_session_memory(test_sess)
        mem.last_subject = "Kinematics"
        mem.active_entities = ["Kinematics"]
        mem.save()

        # Turn 2: 'act like a teacher'
        resolved_q, target = resolve_query_anaphora(test_sess, "act like a teacher")
        self.assertEqual(target, "Kinematics")
        self.assertIn("Kinematics", resolved_q)
        self.assertIn("teacher", resolved_q.lower())

        # Subject framing & intent refinement must preserve Kinematics, not 'Teacher'
        raw_intent = {"primaryIntent": {"category": "Discovery", "confidence": 0.9, "evidenceSpan": "teacher"}}
        raw_subject = {"primarySubject": "Teacher"}
        norm_in = {"rawRequest": "act like a teacher", "comparisonMarkers": [], "quantities": []}

        _, ref_subj, _ = classify_and_refine_intents(
            raw_intent=raw_intent,
            raw_subject=raw_subject,
            normalized_input=norm_in,
            session_id=test_sess,
            fallback_subject=target,
        )
        self.assertEqual(ref_subj.get("primarySubject"), "Kinematics")

        # Retrieval query building must search for kinematics lessons, not 'act like a teacher'
        sharp = _build_sharp_investigative_queries(
            "act like a teacher",
            {"subject": ref_subj, "constraints": {}, "entities": []},
        )
        self.assertIn("kinematics", sharp["web"].lower())
        self.assertIn("kinematics", sharp["video"].lower())
        self.assertNotIn("scary teacher", sharp["video"].lower())

    def test_chat_page_route_renders_chats_template(self):
        session_id = "sess_reload_test_abc"
        res = self.client.get(f"/chat/{session_id}/")
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "chats.html")
        self.assertEqual(res.context["initial_session_id"], session_id)
        self.assertFalse(res.context["has_initial_thread"])

    def test_chats_alias_route_renders_chats_template(self):
        session_id = "sess_reload_alias_xyz"
        res = self.client.get(f"/chats/{session_id}/")
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "chats.html")
        self.assertEqual(res.context["initial_session_id"], session_id)

    def test_chat_page_with_existing_thread_prehydrates_turns(self):
        session_id = "sess_existing_kinematics_thread"
        sample_turn = {
            "query": "introduce me to kinematics",
            "answerMarkdown": "Kinematics is the branch of mechanics...",
            "sources": [{"title": "Kinematics Physics", "source": "PhysicsWeb", "url": "https://example.com"}],
        }
        ConversationThread.objects.create(
            session_id=session_id,
            title="Introduce me to kinematics",
            turns=[sample_turn],
        )

        res = self.client.get(f"/chat/{session_id}/")
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "chats.html")
        self.assertEqual(res.context["initial_session_id"], session_id)
        self.assertTrue(res.context["has_initial_thread"])
        turns_data = json.loads(res.context["initial_thread_turns_json"])
        self.assertEqual(len(turns_data), 1)
        self.assertEqual(turns_data[0]["query"], "introduce me to kinematics")

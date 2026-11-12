"""
Unit and integration tests for Spider AI Site Monitoring Tools & Surveillance Suite.
Tests uptime health checks, page change diffing, RSS/sitemap discovery, DNS inspection,
monitor persistence, and alert dispatch to the notification system.
"""

import socket
from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User
from django.test import TestCase, Client
from core.models import SiteWatchTarget, SiteNotificationAlert
from core.tools import execute_agent_tool
from core.tools.site_monitoring_tools import (
    monitor_site_health_and_uptime,
    track_page_changes_and_diff,
    monitor_feed_and_sitemap_updates,
    monitor_domain_dns_and_security,
    create_site_watch_target,
    poll_active_site_monitors,
    list_site_notification_alerts,
    mark_notifications_as_read,
)


class SiteMonitoringToolsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="watch_tester", password="pass_secret_123")
        self.client = Client()

    @patch("requests.Session.get")
    def test_monitor_site_health_and_uptime_healthy(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.history = []
        mock_resp.headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Server": "cloudflare",
            "strict-transport-security": "max-age=31536000",
        }
        mock_resp.text = "<html><head><title>Official Portal</title></head><body>Welcome</body></html>"
        mock_get.return_value = mock_resp

        result = monitor_site_health_and_uptime("https://example.com/portal")
        self.assertTrue(result["isUp"])
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["healthVerdict"], "HEALTHY")
        self.assertEqual(result["pageTitle"], "Official Portal")
        self.assertTrue(result["securityHeaders"]["hasHsts"])

    @patch("requests.Session.get")
    def test_monitor_site_health_and_uptime_down(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.history = []
        mock_resp.headers = {"Content-Type": "text/plain"}
        mock_resp.text = "Service Unavailable"
        mock_get.return_value = mock_resp

        result = monitor_site_health_and_uptime("https://example.com/api")
        self.assertFalse(result["isUp"])
        self.assertEqual(result["statusCode"], 503)
        self.assertEqual(result["healthVerdict"], "DOWN")

    @patch("requests.get")
    def test_track_page_changes_and_diff(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = (
            "<html><head><title>Ticket Store</title></head><body>"
            "<h1>Match Tickets Available</h1>"
            "<p>Tickets for the event start from KSh 2,500 up to KSh 12,000 for VIP boxes.</p>"
            "<p>Gates open at 3:00 PM on match day.</p>"
            "</body></html>"
        )
        mock_get.return_value = mock_resp

        baseline = "Tickets for the event start from KSh 1,000 up to KSh 5,000."
        result = track_page_changes_and_diff(
            url="https://tickets.example.com",
            baseline_text=baseline,
            keyword_filter="VIP",
        )

        self.assertEqual(result["title"], "Ticket Store")
        self.assertTrue(result["hasChanged"])
        self.assertIn("KSh 2,500", result["detectedPrices"])
        self.assertTrue(result["keywordAudit"]["found"])
        self.assertEqual(result["keywordAudit"]["keyword"], "VIP")
        self.assertIsNotNone(result["contentHash"])

    @patch("requests.get")
    def test_monitor_feed_and_sitemap_updates_rss(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<?xml version="1.0" encoding="UTF-8" ?>
        <rss version="2.0">
        <channel>
            <title>Tech Announcements</title>
            <item>
                <title>Spider AI 2.0 Released</title>
                <link>https://spider.ai/news/2.0</link>
                <pubDate>Wed, 11 Nov 2026 12:00:00 GMT</pubDate>
                <description>Autonomous web retrieval engine update.</description>
            </item>
        </channel>
        </rss>"""
        mock_get.return_value = mock_resp

        result = monitor_feed_and_sitemap_updates("https://spider.ai/rss")
        self.assertTrue(result["hasLiveFeed"])
        self.assertEqual(result["feedType"], "rss")
        self.assertEqual(result["totalItemsFound"], 1)
        self.assertEqual(result["latestUpdates"][0]["title"], "Spider AI 2.0 Released")

    @patch("socket.getaddrinfo")
    def test_monitor_domain_dns_and_security(self, mock_addr):
        mock_addr.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.21.55.10", 80)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::6815:370a", 80)),
        ]
        result = monitor_domain_dns_and_security("cloudflare.com")
        self.assertIn("104.21.55.10", result["dnsRecords"]["A"])
        self.assertTrue(result["isDualStack"])
        self.assertIn("Cloudflare", result["cdnProvider"])

    @patch("core.tools.site_monitoring_tools.monitor_site_health_and_uptime")
    @patch("core.tools.site_monitoring_tools.track_page_changes_and_diff")
    def test_create_and_poll_site_watch_targets(self, mock_diff, mock_health):
        mock_health.return_value = {
            "isUp": True,
            "statusCode": 200,
            "latencyMs": 145.2,
            "healthVerdict": "HEALTHY",
            "verdictReason": "HTTP 200 OK",
        }
        mock_diff.return_value = {
            "title": "Nairobi Sports Arena",
            "contentHash": "abc123sha256",
            "shortHash": "abc123sh",
            "hasChanged": False,
            "detectedPrices": ["KSh 1,500"],
        }

        # 1. Create target
        res = create_site_watch_target(
            url="https://arena.nairobi.go.ke",
            label="Nairobi Sports Arena",
            watch_type="health_and_content",
            session_id="sess_test_1",
            user=self.user,
        )
        self.assertEqual(res["tool"], "create_site_watch_target")
        self.assertEqual(res["label"], "Nairobi Sports Arena")
        self.assertEqual(SiteWatchTarget.objects.count(), 1)
        self.assertEqual(SiteNotificationAlert.objects.count(), 1)

        # 2. Simulate site down during poll
        mock_health.return_value = {
            "isUp": False,
            "statusCode": 500,
            "latencyMs": 3500.0,
            "healthVerdict": "DOWN",
            "verdictReason": "Internal Server Error 500",
        }
        poll_res = poll_active_site_monitors(user=self.user, force_check=True)
        self.assertEqual(poll_res["targetsChecked"], 1)
        self.assertGreaterEqual(poll_res["newAlertsGenerated"], 1)

        # 3. Verify notification alert exists in DB
        alerts = list_site_notification_alerts(user=self.user)
        self.assertGreaterEqual(alerts["totalAlerts"], 2)
        self.assertGreaterEqual(alerts["unreadCount"], 2)

        # 4. Mark notifications read
        read_res = mark_notifications_as_read(user=self.user)
        self.assertGreaterEqual(read_res["markedReadCount"], 2)
        unread_after = list_site_notification_alerts(user=self.user, unread_only=True)
        self.assertEqual(unread_after["unreadCount"], 0)

    @patch("core.tools.site_monitoring_tools.monitor_site_health_and_uptime")
    def test_execute_agent_tool_dispatch(self, mock_health):
        mock_health.return_value = {
            "isUp": True,
            "statusCode": 200,
            "latencyMs": 95.0,
            "healthVerdict": "HEALTHY",
        }
        tool_out = execute_agent_tool(
            "monitor_site_health_and_uptime",
            {"url": "https://example.org"},
        )
        self.assertEqual(tool_out["statusCode"], 200)
        self.assertEqual(tool_out["healthVerdict"], "HEALTHY")

    def test_api_monitors_and_notifications_endpoints(self):
        self.client.force_login(self.user)

        # 1. Test POST /api/monitors/create/
        with patch("core.tools.site_monitoring_tools.monitor_site_health_and_uptime") as m_h, \
             patch("core.tools.site_monitoring_tools.track_page_changes_and_diff") as m_d:
            m_h.return_value = {"isUp": True, "statusCode": 200, "latencyMs": 80.0, "healthVerdict": "HEALTHY"}
            m_d.return_value = {"title": "Portal", "contentHash": "h123", "shortHash": "h12", "hasChanged": False}

            resp = self.client.post(
                "/api/monitors/create/",
                data='{"url": "https://portal.kenya.go.ke", "label": "eCitizen Kenya"}',
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 201)

        # 2. Test GET /api/monitors/
        resp_list = self.client.get("/api/monitors/")
        self.assertEqual(resp_list.status_code, 200)
        data = resp_list.json()
        self.assertEqual(len(data["monitors"]), 1)
        self.assertEqual(data["monitors"][0]["label"], "eCitizen Kenya")

        # 3. Test GET /api/notifications/
        resp_notifs = self.client.get("/api/notifications/")
        self.assertEqual(resp_notifs.status_code, 200)
        notifs_data = resp_notifs.json()
        self.assertGreaterEqual(notifs_data["unreadCount"], 1)

        # 4. Test POST /api/notifications/read/
        resp_read = self.client.post(
            "/api/notifications/read/",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(resp_read.status_code, 200)

        # Verify unread is now 0
        resp_unread = self.client.get("/api/notifications/?unreadOnly=true")
        self.assertEqual(resp_unread.json()["unreadCount"], 0)

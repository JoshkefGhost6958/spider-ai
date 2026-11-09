"""
Unit and Integration Tests for Video Content Relevance Verification
and Multimodal Audio Transcription in Spider AI.
"""

from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase

from core.tools import GEMINI_FUNCTION_DECLARATIONS, execute_agent_tool
from core.tools.video_tools import (
    _extract_topics_from_text,
    transcribe_media_audio,
    verify_video_content_relevance,
)


class VideoVerificationTestCase(SimpleTestCase):
    def test_tool_declarations_registered(self):
        """Verifies that verify_video_content_relevance and transcribe_media_audio are declared."""
        tool_names = [d["name"] for d in GEMINI_FUNCTION_DECLARATIONS]
        self.assertIn("verify_video_content_relevance", tool_names)
        self.assertIn("transcribe_media_audio", tool_names)

        verif_decl = next(d for d in GEMINI_FUNCTION_DECLARATIONS if d["name"] == "verify_video_content_relevance")
        self.assertIn("video_url", verif_decl["parameters"]["properties"])
        self.assertIn("topic_query", verif_decl["parameters"]["properties"])
        self.assertIn("min_relevance_score", verif_decl["parameters"]["properties"])

    def test_extract_topics_from_text(self):
        """Verifies extraction of non-generic topic keywords."""
        sample = (
            "Welcome to Talanta Sports City and Raila Odinga Stadium. "
            "Today we are reviewing tickets, seating layout, and pricing in Kenya Shillings."
        )
        topics = _extract_topics_from_text(sample)
        self.assertTrue(any("Talanta" in t or "Stadium" in t or "Seating" in t or "Tickets" in t for t in topics))

    @patch("core.tools.video_tools._fetch_youtube_transcript")
    def test_transcribe_media_audio_from_captions(self, mock_fetch):
        """Verifies transcribe_media_audio extracts captions when available."""
        mock_fetch.return_value = [
            {"timestamp": "00:05", "seconds": 5.0, "text": "Welcome to Talanta Sports City Stadium."},
            {"timestamp": "00:35", "seconds": 35.0, "text": "Here is the VVIP and regular seating breakdown."},
        ]
        res = transcribe_media_audio("https://www.youtube.com/watch?v=TESTVID1234")
        self.assertEqual(res["tool"], "transcribe_media_audio")
        self.assertTrue(res["hasTranscript"])
        self.assertIn("Talanta Sports City Stadium", res["transcript"])
        self.assertEqual(res["method"], "youtube_captions")
        self.assertEqual(len(res["timestamps"]), 2)

    @patch("core.tools.video_tools._fetch_youtube_transcript")
    @patch("core.tools.video_tools._extract_audio_snippet")
    @patch("core.tools.video_tools.call_gemini_resilient")
    def test_transcribe_media_audio_gemini_multimodal_fallback(
        self, mock_gemini, mock_snippet, mock_fetch
    ):
        """Verifies fallback to multimodal audio extraction when captions are unavailable."""
        mock_fetch.return_value = []
        mock_snippet.return_value = (b"FAKE_MP3_BYTES", "audio/mp3")
        mock_gemini.return_value = (
            {
                "parts": [
                    {
                        "text": (
                            "TRANSCRIPT: [00:10] The match tickets are sold exclusively cashless via eCitizen.\n"
                            "TOPICS: Tickets, Cashless Payment, eCitizen, Raila Odinga Stadium"
                        )
                    }
                ]
            },
            "gemini-2.5-flash",
            210,
        )

        res = transcribe_media_audio("https://www.youtube.com/watch?v=NOCAPTS1234")
        self.assertEqual(res["tool"], "transcribe_media_audio")
        self.assertTrue(res["hasTranscript"])
        self.assertIn("cashless via eCitizen", res["transcript"])
        self.assertIn("gemini_multimodal_audio", res["method"])

    @patch("core.tools.video_tools._extract_video_metadata_ytdlp")
    @patch("core.tools.video_tools.transcribe_media_audio")
    def test_verify_video_content_relevance_positive(self, mock_transcribe, mock_metadata):
        """Verifies high relevance score and SUGGEST verdict for topically aligned video."""
        mock_metadata.return_value = {
            "title": "Talanta Sports City Stadium Seating & Ticket Guide",
            "channel": "Sports Tour Kenya",
            "description": "Full walkthrough of seats, prices, and booking portal for Raila Odinga Stadium.",
        }
        mock_transcribe.return_value = {
            "hasTranscript": True,
            "transcript": (
                "Hello everyone, today we are visiting Raila Odinga Stadium in Talanta Sports City. "
                "Ticket prices start at 500 KSh for regular and 10000 KSh for VVIP lounge. "
                "All seating is numbered."
            ),
            "spokenTopics": ["Talanta", "Stadium", "Tickets", "Seating", "Prices"],
            "method": "youtube_captions",
        }

        verif = verify_video_content_relevance(
            video_url="https://www.youtube.com/watch?v=GOODVID1234",
            topic_query="Talanta Sports City Stadium ticket prices and seating guide",
            min_relevance_score=65,
        )

        self.assertEqual(verif["tool"], "verify_video_content_relevance")
        self.assertTrue(verif["isRelevant"])
        self.assertGreaterEqual(verif["relevanceScore"], 65)
        self.assertEqual(verif["recommendationVerdict"], "SUGGEST")
        self.assertFalse(verif["isClickbait"])
        self.assertIn("GOODVID1234", verif["videoUrl"])

    @patch("core.tools.video_tools._extract_video_metadata_ytdlp")
    @patch("core.tools.video_tools.transcribe_media_audio")
    def test_verify_video_content_relevance_clickbait_rejection(
        self, mock_transcribe, mock_metadata
    ):
        """Verifies clickbait detection when title promises topic but residing speech is totally unrelated."""
        mock_metadata.return_value = {
            "title": "Talanta Sports City Stadium Match Highlights and Ticket Secrets",
            "channel": "Clickbait Channel",
            "description": "Click to watch shocking footage.",
        }
        mock_transcribe.return_value = {
            "hasTranscript": True,
            "transcript": (
                "In today's recipe we prepare traditional beef stew with onions, garlic, and ginger. "
                "First heat the vegetable oil in a large pan and add finely chopped rosemary herbs. "
                "Cook on medium flame for thirty minutes until tender."
            ),
            "spokenTopics": ["Recipe", "Stew", "Cooking", "Kitchen"],
            "method": "youtube_captions",
        }

        verif = verify_video_content_relevance(
            video_url="https://www.youtube.com/watch?v=BAITVID1234",
            topic_query="Talanta Sports City Stadium tickets",
            min_relevance_score=65,
        )

        self.assertFalse(verif["isRelevant"])
        self.assertTrue(verif["isClickbait"])
        self.assertLess(verif["relevanceScore"], 60)
        self.assertEqual(verif["recommendationVerdict"], "DO_NOT_SUGGEST")
        self.assertIsNotNone(verif["clickbaitReason"])

    @patch("core.tools.video_tools.transcribe_media_audio")
    @patch("core.tools.video_tools._extract_video_metadata_ytdlp")
    def test_verify_video_content_relevance_noise_pattern_immediate_rejection(
        self, mock_metadata, mock_transcribe
    ):
        """Verifies immediate rejection of generic entertainment drama/soap opera noise."""
        mock_metadata.return_value = {
            "title": "Cheated on Her Husband Episode 44 Drama Full Movie",
            "channel": "DramaTV",
            "description": "Episode 44 drama series.",
        }
        mock_transcribe.return_value = {
            "hasTranscript": True,
            "transcript": "Episode 44 drama full movie streaming online.",
            "spokenTopics": ["Drama", "Episode"],
            "method": "youtube_captions",
        }
        verif = verify_video_content_relevance(
            video_url="https://www.youtube.com/watch?v=DRAMA123456",
            topic_query="Kenyan FinTech companies market share",
        )
        self.assertFalse(verif["isRelevant"])
        self.assertTrue(verif["isClickbait"])
        self.assertEqual(verif["recommendationVerdict"], "DO_NOT_SUGGEST")

    def test_execute_agent_tool_dispatcher(self):
        """Verifies tool dispatching via execute_agent_tool."""
        with patch("core.tools.verify_video_content_relevance") as mock_verif:
            mock_verif.return_value = {
                "tool": "verify_video_content_relevance",
                "isRelevant": True,
                "relevanceScore": 88,
                "recommendationVerdict": "SUGGEST",
            }
            res = execute_agent_tool(
                "verify_video_content_relevance",
                {"video_url": "https://www.youtube.com/watch?v=TESTVID1234", "topic_query": "Talanta Stadium"},
            )
            self.assertEqual(res["tool"], "verify_video_content_relevance")
            self.assertEqual(res["relevanceScore"], 88)
            mock_verif.assert_called_once()

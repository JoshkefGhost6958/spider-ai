import io
import os
import wave
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from pypdf import PdfWriter


class FileUploadAndAttachmentTestCase(TestCase):
    def setUp(self):
        self.client = Client()

    def test_upload_missing_file_fails(self):
        resp = self.client.post("/api/upload/")
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn("error", data)

    def test_upload_unsupported_file_fails(self):
        bad_file = SimpleUploadedFile("malicious.exe", b"binarycontent", content_type="application/octet-stream")
        resp = self.client.post("/api/upload/", {"file": bad_file})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn("Unsupported file type", data.get("error", ""))

    def test_upload_text_file_success(self):
        text_content = b"Talanta Sports City official construction specifications: Raila Odinga International Stadium capacity 60000."
        txt_file = SimpleUploadedFile("talanta_specs.txt", text_content, content_type="text/plain")
        resp = self.client.post("/api/upload/", {"file": txt_file})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        file_info = data.get("file", {})
        self.assertEqual(file_info.get("name"), "talanta_specs.txt")
        self.assertEqual(file_info.get("mediaType"), "document")
        self.assertTrue(file_info.get("url", "").startswith("/media/uploads/"))
        self.assertIn("Raila Odinga International Stadium", file_info.get("extractedText", ""))

    def test_upload_image_file_success(self):
        # 1x1 transparent png bytes
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        img_file = SimpleUploadedFile("stadium_plan.png", png_bytes, content_type="image/png")
        resp = self.client.post("/api/upload/", {"file": img_file})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        file_info = data.get("file", {})
        self.assertEqual(file_info.get("name"), "stadium_plan.png")
        self.assertEqual(file_info.get("mediaType"), "image")
        self.assertTrue(file_info.get("url", "").startswith("/media/uploads/"))

    def test_upload_pdf_file_extracts_content(self):
        # Create an in-memory PDF using pypdf
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        pdf_stream = io.BytesIO()
        writer.write(pdf_stream)
        pdf_bytes = pdf_stream.getvalue()

        pdf_file = SimpleUploadedFile("talanta_seating_tiers.pdf", pdf_bytes, content_type="application/pdf")
        resp = self.client.post("/api/upload/", {"file": pdf_file})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        file_info = data.get("file", {})
        self.assertEqual(file_info.get("name"), "talanta_seating_tiers.pdf")
        self.assertEqual(file_info.get("mediaType"), "pdf")
        self.assertTrue(file_info.get("url", "").startswith("/media/uploads/"))

    def test_transcribe_empty_audio_returns_empty(self):
        resp = self.client.post("/api/transcribe/", {})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("text"), "")

    def test_transcribe_audio_file_upload(self):
        # Generate valid silent WAV audio
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 8000)
        uploaded = SimpleUploadedFile("speech.wav", buf.getvalue(), content_type="audio/wav")
        resp = self.client.post("/api/transcribe/", {"audio": uploaded})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("text", data)

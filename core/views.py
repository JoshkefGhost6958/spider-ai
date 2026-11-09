import base64
import json
import logging
import os
import re
import uuid
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import ConversationThread, AgentProfileMemory
from .modules.gemini_client import call_gemini_resilient
from .modules.request_orchestration import stream_user_intent_orchestration

logger = logging.getLogger("spider_ai.views")


def landing_page(request):
    """Serves the minimalist chatbox landing page with authentication state and headers."""
    context = {
        "is_authenticated": request.user.is_authenticated,
        "username": request.user.username if request.user.is_authenticated else "",
    }
    resp = render(request, "index.html", context)
    resp["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp


@csrf_exempt
@require_http_methods(["POST"])
def api_upload_file(request):
    """
    Handles uploading of images, PDFs, and documents for autonomous agent analysis.
    Extracts text from PDFs, text files, markdown, CSVs, JSON, and DOCX files.
    Saves file to media/uploads/ and returns file metadata + extracted text.
    """
    if "file" not in request.FILES:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    uploaded_file = request.FILES["file"]
    max_bytes = 25 * 1024 * 1024  # 25 MB limit
    if uploaded_file.size > max_bytes:
        return JsonResponse({"error": "File size exceeds 25MB limit."}, status=400)

    orig_name = uploaded_file.name
    ext = os.path.splitext(orig_name)[1].lower()

    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"}
    doc_exts = {".pdf", ".txt", ".md", ".csv", ".json", ".log", ".docx", ".xml", ".tsv", ".html"}

    if ext not in image_exts and ext not in doc_exts:
        return JsonResponse(
            {
                "error": f"Unsupported file type: {ext}. Please upload images (PNG, JPG, WEBP) or documents (PDF, TXT, DOCX, CSV, JSON)."
            },
            status=400,
        )

    is_image = ext in image_exts
    media_type = "image" if is_image else ("pdf" if ext == ".pdf" else "document")

    safe_token = uuid.uuid4().hex[:10]
    safe_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", os.path.splitext(orig_name)[0])[:40]
    saved_filename = f"{safe_stem}_{safe_token}{ext}"

    upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, saved_filename)

    with open(file_path, "wb+") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    extracted_text = ""
    page_count = 1

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            page_count = len(reader.pages)
            pages = []
            for idx, p in enumerate(reader.pages[:30]):
                txt = (p.extract_text() or "").strip()
                if txt:
                    pages.append(f"--- Page {idx + 1} ---\n{txt[:2500]}")
            extracted_text = "\n\n".join(pages)
        except Exception as exc:
            logger.warning(f"Failed to extract text from PDF {orig_name}: {exc}")
            extracted_text = f"[PDF file: {orig_name}]"
    elif ext in {".txt", ".md", ".csv", ".json", ".log", ".tsv", ".xml", ".html"}:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                extracted_text = f.read(15000)
        except Exception as exc:
            logger.warning(f"Failed reading text file {orig_name}: {exc}")
    elif ext == ".docx":
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(file_path) as z:
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                paragraphs = []
                for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                    texts = [
                        node.text
                        for node in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                        if node.text
                    ]
                    if texts:
                        paragraphs.append("".join(texts))
                extracted_text = "\n".join(paragraphs)[:15000]
        except Exception as exc:
            logger.warning(f"Failed extracting text from docx {orig_name}: {exc}")

    file_url = f"{settings.MEDIA_URL.rstrip('/')}/uploads/{saved_filename}"

    return JsonResponse(
        {
            "success": True,
            "file": {
                "name": orig_name,
                "savedName": saved_filename,
                "url": file_url,
                "size": uploaded_file.size,
                "mediaType": media_type,
                "extension": ext,
                "pageCount": page_count,
                "extractedText": extracted_text[:10000],
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def api_transcribe_audio(request):
    """
    Universal speech-to-text audio transcription endpoint for all browsers (including Firefox).
    Receives recorded audio (via multipart upload or base64 JSON payload) and transcribes
    using Gemini multimodal audio models.
    """
    try:
        audio_bytes = None
        mime_type = "audio/webm"

        if "audio" in request.FILES:
            f = request.FILES["audio"]
            audio_bytes = f.read()
            mime_type = f.content_type or "audio/webm"
        elif "file" in request.FILES:
            f = request.FILES["file"]
            audio_bytes = f.read()
            mime_type = f.content_type or "audio/webm"
        else:
            try:
                body = json.loads(request.body.decode("utf-8"))
                b64_data = body.get("audio") or body.get("data") or ""
                mime_type = body.get("mimeType") or "audio/webm"
                if b64_data:
                    if "," in b64_data:
                        header, b64_data = b64_data.split(",", 1)
                        if "ogg" in header:
                            mime_type = "audio/ogg"
                        elif "wav" in header:
                            mime_type = "audio/wav"
                    audio_bytes = base64.b64decode(b64_data)
            except Exception:
                pass

        if not audio_bytes or len(audio_bytes) < 80:
            return JsonResponse({"success": True, "text": ""})

        lower_mime = mime_type.lower()
        if "ogg" in lower_mime:
            gemini_mime = "audio/ogg"
        elif "wav" in lower_mime:
            gemini_mime = "audio/wav"
        elif "mp3" in lower_mime:
            gemini_mime = "audio/mp3"
        elif "mp4" in lower_mime or "m4a" in lower_mime:
            gemini_mime = "audio/mp4"
        else:
            gemini_mime = "audio/webm"

        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": gemini_mime,
                                "data": b64_audio,
                            }
                        },
                        {
                            "text": (
                                "Transcribe the spoken audio with 100% accuracy word-for-word in English or the spoken language. "
                                "Return ONLY the transcribed text. Do NOT add any preamble, explanation, notes, timestamps, or quotes. "
                                "If the audio is silent or contains no human speech, return an empty string."
                            )
                        },
                    ],
                }
            ]
        }

        content, model_used, latency_ms = call_gemini_resilient(payload, timeout_per_call=10)
        parts = content.get("parts") or []
        transcription = ""
        for p in parts:
            if p.get("text"):
                transcription += p["text"]

        transcription = transcription.strip().strip('"').strip("'")
        if transcription.upper() in ("[SILENCE]", "[NO SPEECH]", "SILENCE", "EMPTY"):
            transcription = ""

        return JsonResponse({
            "success": True,
            "text": transcription,
            "latencyMs": latency_ms,
            "model": model_used
        })
    except Exception as exc:
        logger.warning(f"Voice transcription failed: {exc}")
        return JsonResponse({"success": False, "error": str(exc), "text": ""}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def analyze_intent_stream(request):
    """
    Streaming SSE endpoint that streams each autonomous agent module's action in real time.
    Persists and retrieves sterilized session memory via SQLite without requiring authentication.
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
        user_query = (body.get("query") or body.get("request") or "").strip()
        raw_mode = (body.get("mode") or "direct").strip().lower()
        attachments = body.get("attachments") or []
        if raw_mode in ("compound", "learn", "learning"):
            mode = "compound"
        else:
            mode = "direct"
        session_id = (
            request.headers.get("X-Session-ID")
            or body.get("sessionId")
            or (request.session.session_key if hasattr(request, "session") else None)
            or "sess_guest"
        ).strip()
    except Exception:
        return JsonResponse({"error": "Invalid JSON request body."}, status=400)

    if not user_query:
        if attachments:
            first_att = attachments[0].get("name", "uploaded file")
            user_query = f"Analyze the attached file: {first_att}"
        else:
            return JsonResponse({"error": "Please enter a research request or attach a document."}, status=400)

    def event_generator():
        try:
            for item in stream_user_intent_orchestration(
                user_query, session_id=session_id, mode=mode, attachments=attachments
            ):
                yield f"data: {json.dumps(item)}\n\n"
        except Exception as exc:
            err_payload = {"event": "error", "error": str(exc)}
            yield f"data: {json.dumps(err_payload)}\n\n"

    response = StreamingHttpResponse(
        event_generator(), content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["X-Accel-Buffering"] = "no"
    return response


@csrf_exempt
@require_http_methods(["POST"])
def analyze_intent_json(request):
    """
    JSON endpoint that returns all agent actions and final intelligence payload
    utilizing sterilized SQLite profile memory.
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
        user_query = (body.get("query") or body.get("request") or "").strip()
        raw_mode = (body.get("mode") or "direct").strip().lower()
        attachments = body.get("attachments") or []
        if raw_mode in ("compound", "learn", "learning"):
            mode = "compound"
        else:
            mode = "direct"
        session_id = (
            request.headers.get("X-Session-ID")
            or body.get("sessionId")
            or (request.session.session_key if hasattr(request, "session") else None)
            or "sess_guest"
        ).strip()
    except Exception:
        return JsonResponse({"error": "Invalid JSON request body."}, status=400)

    if not user_query:
        if attachments:
            first_att = attachments[0].get("name", "uploaded file")
            user_query = f"Analyze the attached file: {first_att}"
        else:
            return JsonResponse({"error": "Please enter a research request."}, status=400)

    actions = []
    final_payload = {}
    try:
        for item in stream_user_intent_orchestration(
            user_query, session_id=session_id, mode=mode, attachments=attachments
        ):
            if item.get("event") == "agent_action" and item.get("status") == "completed":
                actions.append(item)
            elif item.get("event") == "complete":
                final_payload = item
        return JsonResponse(
            {
                "agentActions": actions,
                "answerMarkdown": final_payload.get("answerMarkdown", ""),
                "sources": final_payload.get("sources", []),
                "images": final_payload.get("images", []),
                "userIntent": final_payload.get("userIntent"),
                "attachments": final_payload.get("attachments", attachments),
            },
            status=200,
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


# ==============================================================================
# Thread Tracking & History Management Endpoints
# ==============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def api_threads_list(request):
    """
    Returns the list of saved conversation threads for sidebar display.
    For authenticated users, retrieves all threads associated with the user account.
    For unauthenticated guests, retrieves threads only if sessionId matches.
    """
    try:
        if request.user.is_authenticated:
            threads = ConversationThread.objects.filter(user=request.user).order_by("-updated_at")[:50]
        else:
            session_id = request.headers.get("X-Session-ID") or request.GET.get("sessionId") or ""
            if session_id:
                threads = ConversationThread.objects.filter(session_id=session_id.strip()).order_by("-updated_at")
            else:
                threads = []

        data = [
            {
                "sessionId": t.session_id,
                "title": t.title,
                "updatedAt": t.updated_at.isoformat(),
                "turnCount": len(t.turns or []),
            }
            for t in threads
        ]
        return JsonResponse({"threads": data, "isAuthenticated": request.user.is_authenticated}, status=200)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_thread_detail(request, session_id):
    """Retrieves full turns and state for a specific thread."""
    try:
        thread = ConversationThread.objects.filter(session_id=session_id.strip()).first()
        if not thread:
            return JsonResponse({"error": "Thread not found"}, status=404)

        if thread.user and request.user.is_authenticated and thread.user != request.user:
            return JsonResponse({"error": "Unauthorized access to thread"}, status=403)

        return JsonResponse(
            {
                "sessionId": thread.session_id,
                "title": thread.title,
                "turns": thread.turns or [],
                "updatedAt": thread.updated_at.isoformat(),
            },
            status=200,
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_thread_save(request):
    """
    Saves or appends turns to a conversation thread.
    Links to the logged-in user if authenticated.
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
        session_id = (body.get("sessionId") or request.headers.get("X-Session-ID") or "").strip()
        if not session_id:
            return JsonResponse({"error": "Missing sessionId."}, status=400)

        title = (body.get("title") or "").strip()
        turns = body.get("turns", [])

        user = request.user if request.user.is_authenticated else None

        thread, created = ConversationThread.objects.get_or_create(
            session_id=session_id,
            defaults={"title": title or "New Conversation", "turns": turns, "user": user},
        )
        if not created:
            if title:
                thread.title = title
            if turns:
                thread.turns = turns
            if user and not thread.user:
                thread.user = user
            thread.save()

        return JsonResponse(
            {
                "status": "ok",
                "sessionId": thread.session_id,
                "title": thread.title,
                "turnCount": len(thread.turns or []),
            },
            status=200,
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
def api_thread_delete(request, session_id):
    """Deletes a conversation thread and purges its profile memory."""
    try:
        s_id = session_id.strip()
        ConversationThread.objects.filter(session_id=s_id).delete()
        AgentProfileMemory.objects.filter(session_id=s_id).delete()
        return JsonResponse({"status": "ok", "deletedSessionId": s_id}, status=200)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_clear_guest_session(request):
    """
    Purges guest session state on reload or explicit clear.
    Guarantees zero context pollution for guest users across page reloads.
    """
    try:
        body = {}
        if request.body:
            try:
                body = json.loads(request.body.decode("utf-8"))
            except Exception:
                pass
        session_id = (
            body.get("sessionId")
            or request.headers.get("X-Session-ID")
            or request.GET.get("sessionId")
            or ""
        ).strip()

        if session_id:
            AgentProfileMemory.objects.filter(session_id=session_id).delete()
            ConversationThread.objects.filter(session_id=session_id, user__isnull=True).delete()

        # Also purge any dangling guest records older than today
        AgentProfileMemory.objects.filter(session_id__startswith="sess_guest").delete()
        ConversationThread.objects.filter(session_id__startswith="sess_guest", user__isnull=True).delete()

        return JsonResponse({"status": "ok", "cleared": True}, status=200)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


# ==============================================================================
# Authentication Endpoints
# ==============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_auth_login(request):
    """Logs in an existing user."""
    try:
        body = json.loads(request.body.decode("utf-8"))
        username = (body.get("username") or "").strip()
        password = (body.get("password") or "").strip()
        if not username or not password:
            return JsonResponse({"error": "Username and password required."}, status=400)

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({"status": "ok", "username": user.username, "isAuthenticated": True}, status=200)
        else:
            return JsonResponse({"error": "Invalid username or password."}, status=401)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_auth_register(request):
    """Registers and logs in a new user account."""
    try:
        body = json.loads(request.body.decode("utf-8"))
        username = (body.get("username") or "").strip()
        password = (body.get("password") or "").strip()
        if not username or not password:
            return JsonResponse({"error": "Username and password required."}, status=400)
        if len(password) < 4:
            return JsonResponse({"error": "Password must be at least 4 characters."}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already taken."}, status=400)

        user = User.objects.create_user(username=username, password=password)
        login(request, user)
        return JsonResponse({"status": "ok", "username": user.username, "isAuthenticated": True}, status=201)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_auth_logout(request):
    """Logs out the active user session."""
    try:
        logout(request)
        return JsonResponse({"status": "ok", "isAuthenticated": False}, status=200)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_auth_status(request):
    """Returns current authentication state."""
    return JsonResponse(
        {
            "isAuthenticated": request.user.is_authenticated,
            "username": request.user.username if request.user.is_authenticated else None,
        },
        status=200,
    )

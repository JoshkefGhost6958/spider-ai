import base64
import html
import json
import mimetypes
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from core.modules.gemini_client import MODEL_FALLBACK_CHAIN, _get_api_key, call_gemini_resilient

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _format_seconds(seconds: float) -> str:
    total = max(0, int(seconds or 0))
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _extract_youtube_id(url: str) -> Optional[str]:
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url or "")
        if m:
            return m.group(1)
    return None


_GENERIC_NOISE_RE = re.compile(
    r"\b(ep\s*\d+|episode\s*\d+|first\s+love|pregnant\s+wife|cheated\s+on\s+her|drama|movie|full\s+movie)\b",
    re.I,
)

_GENERIC_QUALIFIERS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "what", "about",
    "news", "latest", "trending", "today", "video", "broadcast", "explanation",
    "happening", "report", "updates", "story", "stories", "people", "world",
    "channel", "live", "watch", "breakdown", "analysis", "here", "there",
    "africa", "african", "documentary", "political", "politics", "party",
    "parties", "country", "national", "region", "regional", "update", "brief",
    "leadership", "leader", "leaders", "general", "court", "state", "federal",
    "democratic", "union", "republic", "society", "association", "kenya",
    "kenyan", "east", "west", "north", "south",
}


def _is_video_topically_relevant(title: str, snippet: str, query: str) -> bool:
    """
    Verifies that a video title or snippet strictly fits the specific question and entity
    presented, rejecting videos that only match broad geographic/qualifier terms.
    """
    t_text = f"{title} {snippet}".lower()
    if _GENERIC_NOISE_RE.search(title):
        if not re.search(r"\b(movie|episode|ep|drama)\b", query, re.I):
            return False

    q_words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", query) if len(w) >= 3]
    primary_entity_tokens = [w for w in q_words if w not in _GENERIC_QUALIFIERS]

    # If specific non-generic entity tokens exist (e.g. 'kadu', 'gachagua', 'ebola', 'ngala'):
    # The video MUST match at least one specific entity token using word boundaries (preventing 'stripe' -> 'stripes')
    if primary_entity_tokens:
        return any(bool(re.search(r"\b" + re.escape(pt) + r"\b", t_text)) for pt in primary_entity_tokens)

    # Fallback to general tokens for open-ended queries like "trending news today"
    fallback_tokens = [w for w in q_words if w not in {"the", "and", "for", "with", "what", "about", "this", "that"}]
    if not fallback_tokens:
        return True
    return any(bool(re.search(r"\b" + re.escape(tok) + r"\b", t_text)) for tok in fallback_tokens)


def _parse_relative_age_minutes(pub_str: str, title_str: str = "") -> int:
    """Converts relative publish strings ('LIVE', '44 min ago', '14h ago', '2 days ago') into age in minutes."""
    raw = (pub_str or "").strip().lower()
    if "live" in raw or (not raw and "live" in (title_str or "").lower()):
        return 0
    if not raw:
        return 999999
    m = re.search(r"(\d+)\s*(sec|min|hour|hr|h\b|day|d\b|week|wk|w\b|month|mo|year|yr|y\b)", raw)
    if not m:
        return 500000
    val = int(m.group(1))
    unit = m.group(2)
    if unit.startswith("sec"):
        return 1
    if unit.startswith("min"):
        return val
    if unit.startswith("h"):
        return val * 60
    if unit.startswith("d"):
        return val * 1440
    if unit.startswith("w"):
        return val * 10080
    if unit.startswith("mo"):
        return val * 43200
    if unit.startswith("y"):
        return val * 525600
    return 500000


def video_search(
    query: str,
    max_results: int = 5,
    prefer_recent: bool = True,
) -> Dict[str, Any]:
    """
    Searches YouTube and web video indices for relevant video links, sorting
    results in order of newness (LIVE and most recently uploaded videos first).
    """
    max_results = max(1, min(10, int(max_results or 5)))
    results: List[Dict[str, Any]] = []
    seen_urls = set()

    # Strip conversational filler while keeping core subject/location + 'news' if trending query
    is_trending_q = bool(re.search(r"\b(trending|happening|latest|today|now)\b", query, re.I))
    cleaned_q = re.sub(
        r"\b(what'?s|what\s+is|trending|topics?|happening|right\s+now|current|currently|in|on|about|the)\b",
        " ",
        query,
        flags=re.I,
    )
    cleaned_q = re.sub(r"\s+", " ", cleaned_q).strip()
    effective_q = cleaned_q if len(cleaned_q) >= 2 else query.strip()
    if is_trending_q and len(effective_q.split()) <= 2 and "news" not in effective_q.lower():
        effective_q = f"{effective_q} news"

    # 1. Direct YouTube search via ytInitialData JSON extraction
    # Query 'This week' (EgIIAw%3D%3D) first when prefer_recent is True, then standard search if needed
    sp_filters = ["EgIIAw%3D%3D", ""] if prefer_recent else [""]
    for sp_param in sp_filters:
        if len(results) >= max_results:
            break
        yt_search_url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote(effective_q)}"
            + (f"&sp={sp_param}" if sp_param else "")
        )
        req = urllib.request.Request(
            yt_search_url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        )
        try:
            with urllib.request.urlopen(req, timeout=7) as resp:
                page_html = resp.read().decode("utf-8", errors="ignore")
            m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});</script>", page_html, re.S)
            if m:
                yt_data = json.loads(m.group(1))
                contents = (
                    yt_data.get("contents", {})
                    .get("twoColumnSearchResultsRenderer", {})
                    .get("primaryContents", {})
                    .get("sectionListRenderer", {})
                    .get("contents", [])
                )
                for section in contents:
                    items = (
                        section.get("itemSectionRenderer", {}).get("contents") or []
                    )
                    for item in items:
                        vr = item.get("videoRenderer")
                        if not vr:
                            continue
                        vid = vr.get("videoId")
                        if not vid:
                            continue
                        v_url = f"https://www.youtube.com/watch?v={vid}"
                        if v_url in seen_urls:
                            continue
                        seen_urls.add(v_url)

                        title_runs = vr.get("title", {}).get("runs") or []
                        title = "".join(r.get("text", "") for r in title_runs).strip()
                        owner_runs = vr.get("ownerText", {}).get("runs") or []
                        channel = "".join(r.get("text", "") for r in owner_runs).strip()
                        duration = vr.get("lengthText", {}).get("simpleText") or ""
                        published = vr.get("publishedTimeText", {}).get("simpleText") or ""
                        views = vr.get("viewCountText", {}).get("simpleText") or ""

                        # Detect LIVE stream badge if publishedTimeText is empty
                        if not published:
                            badges_str = json.dumps(vr.get("badges") or vr.get("thumbnailOverlays") or []).lower()
                            if "live" in badges_str or title.lower().startswith("live"):
                                published = "LIVE NOW"
                                duration = "LIVE"

                        snip_runs = []
                        for snip_item in (
                            vr.get("detailedMetadataSnippets") or []
                        ):
                            snip_runs.extend(
                                snip_item.get("snippetText", {}).get("runs") or []
                            )
                        snippet = "".join(r.get("text", "") for r in snip_runs).strip()
                        age_mins = _parse_relative_age_minutes(published, title)

                        # Strictly verify topical relevance to avoid unrelated drama/recommended spam
                        if not _is_video_topically_relevant(title, snippet, effective_q):
                            continue

                        results.append(
                            {
                                "title": f"{title} [Video]",
                                "url": v_url,
                                "videoId": vid,
                                "thumbnailUrl": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                                "source": f"YouTube ({channel})" if channel else "youtube.com",
                                "duration": duration,
                                "publishedAt": published,
                                "ageMinutes": age_mins,
                                "views": views,
                                "snippet": snippet or f"YouTube video by {channel} ({published or duration}, {views})",
                            }
                        )
                        if len(results) >= max_results + 3:
                            break
                    if len(results) >= max_results + 3:
                        break
        except Exception:
            pass

    # 2. Supplement with ddgs.videos if needed
    if len(results) < max_results:
        try:
            from ddgs import DDGS

            ddg_vids = DDGS().videos(effective_q, max_results=max_results)
            for v in ddg_vids or []:
                v_url = (v.get("content") or v.get("url") or "").strip()
                title = (v.get("title") or "").strip()
                if not v_url or not title or v_url in seen_urls:
                    continue
                if not _is_video_topically_relevant(title, "", effective_q):
                    continue
                seen_urls.add(v_url)
                pub_str = (v.get("published") or "").strip()
                results.append(
                    {
                        "title": title,
                        "url": v_url,
                        "source": (v.get("publisher") or v.get("uploader") or "video").strip(),
                        "duration": (v.get("duration") or "").strip(),
                        "publishedAt": pub_str,
                        "ageMinutes": _parse_relative_age_minutes(pub_str, title),
                        "views": "",
                        "snippet": (v.get("description") or "")[:350].strip(),
                    }
                )
                if len(results) >= max_results + 2:
                    break
        except Exception:
            pass

    # Sort strictly by newness (ageMinutes ascending)
    results.sort(key=lambda x: x.get("ageMinutes", 999999))
    results = results[:max_results]

    return {
        "tool": "video_search",
        "executedQuery": effective_q,
        "count": len(results),
        "results": results,
    }


def _fetch_youtube_transcript(video_id: str) -> List[Dict[str, Any]]:
    """Extracts timestamped transcript segments using youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        # Compatible with both youtube-transcript-api v1.x (.fetch) and v0.x (.get_transcript)
        if hasattr(YouTubeTranscriptApi, "fetch"):
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id)
            raw_list = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
        else:
            raw_list = YouTubeTranscriptApi.get_transcript(video_id)

        segments = []
        for seg in raw_list:
            if isinstance(seg, dict):
                start = float(seg.get("start", 0.0))
                text = (seg.get("text") or "").replace("\n", " ").strip()
            else:
                start = float(getattr(seg, "start", 0.0))
                text = str(getattr(seg, "text", "")).replace("\n", " ").strip()
            if text:
                segments.append(
                    {"timestamp": _format_seconds(start), "seconds": start, "text": text}
                )
        return segments
    except Exception:
        return []


def _extract_video_metadata_ytdlp(video_url: str) -> Dict[str, Any]:
    """Extracts rich video metadata, description, and chapters via yt-dlp (no video download)."""
    try:
        import yt_dlp

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False) or {}
            chapters = []
            for ch in (info.get("chapters") or [])[:25]:
                chapters.append(
                    {
                        "startTime": _format_seconds(ch.get("start_time", 0)),
                        "title": ch.get("title", ""),
                    }
                )
            return {
                "title": info.get("title") or "",
                "channel": info.get("uploader") or info.get("channel") or "",
                "uploadDate": info.get("upload_date") or "",
                "durationSeconds": info.get("duration") or 0,
                "durationFormatted": _format_seconds(info.get("duration") or 0),
                "viewCount": info.get("view_count"),
                "description": (info.get("description") or "")[:1800],
                "chapters": chapters,
                "tags": (info.get("tags") or [])[:15],
            }
    except Exception:
        return {}


def _analyze_youtube_video_with_gemini(
    youtube_url: str,
    focus_query: Optional[str],
    metadata: Dict[str, Any],
    transcript_excerpt: str,
) -> str:
    """
    Uses Gemini's multimodal YouTube video understanding (or transcript + metadata
    synthesis fallback) to extract key information, facts, and timestamps from the video.
    """
    api_key = _get_api_key()
    prompt_text = (
        f"Extract the key facts, insights, and timestamped highlights from this video "
        f"({metadata.get('title', youtube_url)})."
    )
    if focus_query:
        prompt_text += f"\nSpecifically focus on answering or extracting: {focus_query}"
    if transcript_excerpt:
        prompt_text += f"\n\nEXTRACTED_TRANSCRIPT_EXCERPT:\n{transcript_excerpt[:4000]}"
    if metadata.get("description"):
        prompt_text += f"\n\nVIDEO_DESCRIPTION:\n{metadata['description'][:1200]}"

    try:
        parts: List[Dict[str, Any]] = []
        if not transcript_excerpt and "youtube.com/watch" in youtube_url:
            parts.append(
                {
                    "fileData": {
                        "fileUri": youtube_url,
                        "mimeType": "video/mp4",
                    }
                }
            )
        parts.append({"text": prompt_text})

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.2},
        }
        content, _, _ = call_gemini_resilient(
            payload=payload, timeout_per_call=18, max_rounds=1
        )
        text = "".join(p.get("text", "") for p in (content.get("parts") or [])).strip()
        if text:
            return text
    except Exception:
        pass
    return ""


def extract_video_info(
    video_url: str,
    focus_query: Optional[str] = None,
    include_timestamps: bool = True,
) -> Dict[str, Any]:
    """
    Extracts comprehensive information from a video link (YouTube, Vimeo, or web video):
    1. Video metadata (title, channel, duration, publish date, views, description, chapters).
    2. Timestamped transcript / closed captions (via youtube-transcript-api / yt-dlp).
    3. Keyword-matched timestamped transcript segments when focus_query is provided.
    4. AI-synthesized summary & timestamped highlights via Gemini.
    """
    yt_id = _extract_youtube_id(video_url)
    canonical_url = (
        f"https://www.youtube.com/watch?v={yt_id}" if yt_id else video_url.strip()
    )

    metadata = _extract_video_metadata_ytdlp(canonical_url)
    segments = _fetch_youtube_transcript(yt_id) if yt_id else []

    # Group transcript into ~30-second readable blocks with [MM:SS] timestamps
    grouped_blocks: List[str] = []
    if segments:
        bucket_start = segments[0]["timestamp"]
        bucket_texts: List[str] = []
        last_sec = segments[0]["seconds"]
        for seg in segments:
            if seg["seconds"] - last_sec >= 30 and bucket_texts:
                prefix = f"[{bucket_start}] " if include_timestamps else ""
                grouped_blocks.append(f"{prefix}{' '.join(bucket_texts)}")
                bucket_start = seg["timestamp"]
                bucket_texts = [seg["text"]]
                last_sec = seg["seconds"]
            else:
                bucket_texts.append(seg["text"])
        if bucket_texts:
            prefix = f"[{bucket_start}] " if include_timestamps else ""
            grouped_blocks.append(f"{prefix}{' '.join(bucket_texts)}")

    full_transcript_text = "\n".join(grouped_blocks)

    # Filter matching segments if focus_query is specified
    matching_segments: List[str] = []
    if focus_query and grouped_blocks:
        keywords = [
            k for k in re.split(r"[^a-z0-9]+", focus_query.lower()) if len(k) >= 3
        ]
        for blk in grouped_blocks:
            blk_lower = blk.lower()
            if any(k in blk_lower for k in keywords):
                matching_segments.append(blk)
                if len(matching_segments) >= 10:
                    break

    ai_analysis = _analyze_youtube_video_with_gemini(
        youtube_url=canonical_url,
        focus_query=focus_query,
        metadata=metadata,
        transcript_excerpt=(
            "\n".join(matching_segments)
            if matching_segments
            else full_transcript_text[:4500]
        ),
    )

    return {
        "tool": "extract_video_info",
        "url": canonical_url,
        "videoId": yt_id,
        "title": metadata.get("title") or canonical_url,
        "channel": metadata.get("channel") or "Video Source",
        "duration": metadata.get("durationFormatted") or "",
        "uploadDate": metadata.get("uploadDate") or "",
        "viewCount": metadata.get("viewCount"),
        "chapters": metadata.get("chapters") or [],
        "descriptionExcerpt": (metadata.get("description") or "")[:900],
        "hasTranscript": len(segments) > 0,
        "transcriptBlockCount": len(grouped_blocks),
        "matchingTimestampedSegments": matching_segments[:8],
        "transcriptExcerpt": full_transcript_text[:3500],
        "aiVideoSummary": ai_analysis,
    }


def _extract_audio_snippet(
    source_url_or_path: str,
    max_duration_sec: int = 90,
) -> Tuple[Optional[bytes], str]:
    """
    Extracts a lightweight audio sample (MP3/WAV, default 90 seconds) from a
    YouTube video, web media URL, or local audio file path using yt-dlp & ffmpeg.
    Returns (audio_bytes, mime_type).
    """
    source = (source_url_or_path or "").strip()
    if not source:
        return None, ""

    # 1. Local file path check
    if os.path.exists(source) and os.path.isfile(source):
        mime, _ = mimetypes.guess_type(source)
        mime = mime or "audio/mp3"
        try:
            with open(source, "rb") as f:
                return f.read(15 * 1024 * 1024), mime
        except Exception:
            return None, ""

    # 2. Remote URL: download short audio slice using yt-dlp + ffmpeg
    temp_dir = tempfile.mkdtemp(prefix="spider_audio_")
    try:
        import yt_dlp

        out_template = os.path.join(temp_dir, "sample.%(ext)s")
        duration_limit = max(10, min(180, int(max_duration_sec or 90)))
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "max_filesize": 15 * 1024 * 1024,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "64",
                }
            ],
            "postprocessor_args": [
                "-ss",
                "00:00:00",
                "-t",
                str(duration_limit),
            ],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([source])

        # Scan for output audio file
        for fname in os.listdir(temp_dir):
            if fname.lower().endswith((".mp3", ".m4a", ".wav", ".aac", ".ogg")):
                fpath = os.path.join(temp_dir, fname)
                with open(fpath, "rb") as f:
                    b = f.read()
                return b, "audio/mp3"
    except Exception:
        pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return None, ""


def _extract_topics_from_text(text: str) -> List[str]:
    """Extracts top non-generic entity/topic phrases from transcript text."""
    if not text:
        return []
    words = re.findall(r"\b[A-Za-z]{4,}\b", text.lower())
    freq: Dict[str, int] = {}
    for w in words:
        if w in _GENERIC_QUALIFIERS:
            continue
        freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    return [w.capitalize() for w, _ in sorted_words[:5]]


def transcribe_media_audio(
    source_url_or_path: str,
    max_duration_sec: int = 90,
) -> Dict[str, Any]:
    """
    Transcribes spoken dialogue and audio content from a YouTube video URL,
    web video/audio link, or local audio file:
    1. For YouTube: checks official & community closed-captions first for instant verbatim accuracy.
    2. Fallback / raw audio: extracts a lightweight audio clip via yt-dlp & ffmpeg and transcribes
       speech with Gemini multimodal audio API.
    3. Returns verbatim transcript, timestamps, detected topics, and transcription method.
    """
    source = (source_url_or_path or "").strip()
    yt_id = _extract_youtube_id(source)
    canonical_url = f"https://www.youtube.com/watch?v={yt_id}" if yt_id else source

    # 1. Check YouTube captions first
    segments: List[Dict[str, Any]] = []
    if yt_id:
        segments = _fetch_youtube_transcript(yt_id)
        if segments:
            full_text = " ".join(s["text"] for s in segments)
            timestamps = [
                {"timestamp": s["timestamp"], "seconds": s["seconds"], "text": s["text"]}
                for s in segments[:40]
            ]
            return {
                "tool": "transcribe_media_audio",
                "source": canonical_url,
                "videoId": yt_id,
                "mediaType": "youtube",
                "hasTranscript": True,
                "transcript": full_text[:4000],
                "spokenTopics": _extract_topics_from_text(full_text),
                "timestamps": timestamps,
                "durationTranscribed": f"{len(segments)} caption blocks ({segments[-1]['timestamp'] if segments else '0:00'})",
                "method": "youtube_captions",
            }

    # 2. Multimodal Audio Extraction & Gemini Transcription Fallback
    audio_bytes, mime_type = _extract_audio_snippet(canonical_url, max_duration_sec=max_duration_sec)
    if audio_bytes:
        try:
            api_key = _get_api_key()
            b64_data = base64.b64encode(audio_bytes).decode("ascii")
            prompt = (
                "Please transcribe the speech in this audio clip accurately. "
                "Format as:\n"
                "TRANSCRIPT: <verbatim spoken dialogue with approximate timestamps>\n"
                "TOPICS: <comma-separated list of 3-5 core subjects discussed>"
            )
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": mime_type or "audio/mp3",
                                    "data": b64_data,
                                }
                            },
                            {"text": prompt},
                        ],
                    }
                ],
                "generationConfig": {"temperature": 0.1},
            }
            content, model_used, _ = call_gemini_resilient(
                payload=payload, timeout_per_call=16, max_rounds=1
            )
            resp_text = "".join(p.get("text", "") for p in (content.get("parts") or [])).strip()
            if resp_text:
                transcript_part = resp_text
                topics: List[str] = []
                if "TRANSCRIPT:" in resp_text:
                    parts = resp_text.split("TOPICS:")
                    transcript_part = parts[0].replace("TRANSCRIPT:", "").strip()
                    if len(parts) > 1:
                        topics = [t.strip() for t in parts[1].split(",") if t.strip()]
                if not topics:
                    topics = _extract_topics_from_text(transcript_part)

                return {
                    "tool": "transcribe_media_audio",
                    "source": canonical_url,
                    "videoId": yt_id,
                    "mediaType": "audio_clip" if not yt_id else "youtube_audio",
                    "hasTranscript": True,
                    "transcript": transcript_part[:4000],
                    "spokenTopics": topics,
                    "timestamps": [],
                    "durationTranscribed": f"First {max_duration_sec}s audio clip",
                    "method": f"gemini_multimodal_audio ({model_used})",
                }
        except Exception:
            pass

    # 3. Metadata fallback if audio download/transcription failed (e.g. offline or geoblocked)
    metadata = _extract_video_metadata_ytdlp(canonical_url) if (yt_id or "http" in canonical_url) else {}
    desc = (metadata.get("description") or "")[:2000]
    chapters = [c.get("title") for c in metadata.get("chapters", []) if c.get("title")]
    synthesized_notes = f"{metadata.get('title', '')}. {desc} {' '.join(chapters)}".strip()

    return {
        "tool": "transcribe_media_audio",
        "source": canonical_url,
        "videoId": yt_id,
        "mediaType": "youtube" if yt_id else "web_media",
        "hasTranscript": bool(desc or chapters),
        "transcript": desc or f"Audio transcription unavailable. Video title: {metadata.get('title', '')}",
        "spokenTopics": chapters[:5] or _extract_topics_from_text(synthesized_notes),
        "timestamps": [{"timestamp": c.get("startTime", "00:00"), "text": c.get("title", "")} for c in metadata.get("chapters", [])],
        "durationTranscribed": metadata.get("durationFormatted", "0:00"),
        "method": "metadata_and_chapters_fallback",
    }


def verify_video_content_relevance(
    video_url: str,
    topic_query: str,
    min_relevance_score: int = 65,
) -> Dict[str, Any]:
    """
    Verifies that the residing spoken content, audio transcript, and subject matter
    of a video actually match the user's research query, detecting and filtering
    clickbait, deceptive titles, and off-topic media before suggesting it to the user.
    """
    v_url = (video_url or "").strip()
    q = (topic_query or "").strip()
    yt_id = _extract_youtube_id(v_url)
    canonical_url = f"https://www.youtube.com/watch?v={yt_id}" if yt_id else v_url

    # 1. Fetch metadata & transcript
    metadata = _extract_video_metadata_ytdlp(canonical_url)
    title = metadata.get("title") or canonical_url
    channel = metadata.get("channel") or ""
    description = metadata.get("description") or ""

    tr_res = transcribe_media_audio(canonical_url, max_duration_sec=90)
    transcript_text = tr_res.get("transcript") or ""
    spoken_topics = tr_res.get("spokenTopics") or []
    method = tr_res.get("method") or "metadata_inspection"

    # 2. Check for obvious clickbait / noise patterns
    t_low = title.lower()
    full_text_low = f"{title} {description} {transcript_text}".lower()

    if _GENERIC_NOISE_RE.search(t_low) or _GENERIC_NOISE_RE.search(full_text_low):
        if not re.search(r"\b(movie|episode|ep|drama)\b", q, re.I):
            return {
                "tool": "verify_video_content_relevance",
                "videoUrl": canonical_url,
                "videoId": yt_id,
                "title": title,
                "channel": channel,
                "topicQuery": q,
                "isRelevant": False,
                "relevanceScore": 10,
                "verdict": "IRRELEVANT_OR_CLICKBAIT",
                "confidence": 0.95,
                "hasResidingTranscript": tr_res.get("hasTranscript", False),
                "spokenSummary": f"Video appears to be drama/entertainment series unrelated to research topic '{q}'.",
                "detectedTopics": spoken_topics[:4],
                "matchingExcerpts": [],
                "isClickbait": True,
                "clickbaitReason": "Matched entertainment drama/noise pattern while query sought factual information.",
                "recommendationVerdict": "DO_NOT_SUGGEST",
                "verificationMethod": "noise_pattern_filter",
            }

    # 3. AI-Assisted Semantic Verification via Gemini
    ai_verified = False
    verdict_dict: Dict[str, Any] = {}
    try:
        api_key = _get_api_key()
        analysis_prompt = (
            f"Analyze whether this video's actual residing spoken content and subject matter "
            f"strictly address the research query.\n\n"
            f"RESEARCH QUERY: {q}\n"
            f"VIDEO TITLE: {title}\n"
            f"CHANNEL: {channel}\n"
            f"RESIDING TRANSCRIPT / SPOKEN DIALOGUE (Excerpt):\n{transcript_text[:3000]}\n\n"
            f"VIDEO DESCRIPTION:\n{description[:1000]}\n\n"
            f"Respond ONLY with a JSON object containing keys:\n"
            f"- is_relevant (boolean)\n"
            f"- relevance_score (integer 0-100)\n"
            f"- verdict ('HIGHLY_RELEVANT', 'MODERATELY_RELEVANT', or 'IRRELEVANT_OR_CLICKBAIT')\n"
            f"- confidence (float 0.0-1.0)\n"
            f"- spoken_summary (short 1-2 sentence description of what the video is actually about)\n"
            f"- detected_topics (array of 3-5 strings)\n"
            f"- matching_excerpts (array of up to 3 verbatim sentences from the text matching the query)\n"
            f"- is_clickbait (boolean, true if title promises something the residing audio/content lacks)\n"
            f"- clickbait_reason (null or explanation string)"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": analysis_prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        content, model_used, _ = call_gemini_resilient(
            payload=payload, timeout_per_call=14, max_rounds=1
        )
        resp_str = "".join(p.get("text", "") for p in (content.get("parts") or [])).strip()
        verdict_dict = json.loads(resp_str)
        ai_verified = True
        method = f"gemini_epistemic_audit ({model_used})"
    except Exception:
        pass

    # 4. Deterministic Linguistic Fallback if AI verification is unavailable (e.g. offline/mock tests)
    if not ai_verified or not verdict_dict:
        q_tokens = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", q) if len(w) >= 3 and w.lower() not in _GENERIC_QUALIFIERS]
        if not q_tokens:
            q_tokens = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", q) if len(w) >= 3]

        transcript_matches = [tok for tok in q_tokens if re.search(r"\b" + re.escape(tok) + r"\b", transcript_text.lower())]
        title_matches = [tok for tok in q_tokens if re.search(r"\b" + re.escape(tok) + r"\b", t_low)]
        desc_matches = [tok for tok in q_tokens if re.search(r"\b" + re.escape(tok) + r"\b", description.lower())]

        score = 0
        if q_tokens:
            tr_ratio = len(transcript_matches) / len(q_tokens)
            t_ratio = len(title_matches) / len(q_tokens)
            d_ratio = len(desc_matches) / len(q_tokens)

            # High weight on actual spoken transcript!
            if tr_res.get("hasTranscript"):
                score = int((tr_ratio * 60) + (t_ratio * 25) + (d_ratio * 15))
            else:
                score = int((t_ratio * 60) + (d_ratio * 40))

        # Clickbait detection: title has keywords but transcript has 0 keyword overlap despite having transcript
        is_clickbait = False
        clickbait_reason = None
        if tr_res.get("hasTranscript") and len(transcript_text) > 200:
            if title_matches and not transcript_matches:
                is_clickbait = True
                clickbait_reason = "Title claims to discuss query topic, but residing spoken transcript contains zero matching subject matter."
                score = min(score, 25)

        is_rel = score >= min_relevance_score and not is_clickbait
        verdict = "HIGHLY_RELEVANT" if score >= 80 else ("MODERATELY_RELEVANT" if score >= 60 else "IRRELEVANT_OR_CLICKBAIT")

        matching_excerpts = []
        if transcript_matches:
            # Pick sentences containing matching tokens
            sentences = re.split(r"(?<=[.!?])\s+", transcript_text)
            for s in sentences:
                if any(m in s.lower() for m in transcript_matches):
                    matching_excerpts.append(s.strip()[:180])
                    if len(matching_excerpts) >= 3:
                        break

        verdict_dict = {
            "is_relevant": is_rel,
            "relevance_score": score,
            "verdict": verdict,
            "confidence": 0.88 if tr_res.get("hasTranscript") else 0.70,
            "spoken_summary": (
                f"Video discusses {', '.join(spoken_topics[:3])}."
                if spoken_topics
                else f"Content from channel '{channel}' covering '{title[:60]}'."
            ),
            "detected_topics": spoken_topics[:5],
            "matching_excerpts": matching_excerpts,
            "is_clickbait": is_clickbait,
            "clickbait_reason": clickbait_reason,
        }

    rel_score = int(verdict_dict.get("relevance_score", 0))
    is_rel = bool(verdict_dict.get("is_relevant", False)) and rel_score >= min_relevance_score and not verdict_dict.get("is_clickbait", False)
    rec_verdict = "SUGGEST" if is_rel else "DO_NOT_SUGGEST"

    return {
        "tool": "verify_video_content_relevance",
        "videoUrl": canonical_url,
        "videoId": yt_id,
        "title": title,
        "channel": channel,
        "topicQuery": q,
        "isRelevant": is_rel,
        "relevanceScore": rel_score,
        "verdict": verdict_dict.get("verdict", "IRRELEVANT_OR_CLICKBAIT"),
        "confidence": float(verdict_dict.get("confidence", 0.8)),
        "hasResidingTranscript": tr_res.get("hasTranscript", False),
        "spokenSummary": verdict_dict.get("spoken_summary") or "",
        "detectedTopics": verdict_dict.get("detected_topics") or spoken_topics[:5],
        "matchingExcerpts": verdict_dict.get("matching_excerpts") or [],
        "isClickbait": bool(verdict_dict.get("is_clickbait", False)),
        "clickbaitReason": verdict_dict.get("clickbait_reason"),
        "recommendationVerdict": rec_verdict,
        "verificationMethod": method,
    }

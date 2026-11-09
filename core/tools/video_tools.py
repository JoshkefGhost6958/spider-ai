import html
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
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

from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from .extraction_tools import extract_page_links, fetch_page_markdown, parse_document_file

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _clean_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def web_search(
    query: str,
    time_range: Optional[str] = None,
    region: str = "wt-wt",
    domain_filter: Optional[str] = None,
    exclude_domains: Optional[List[str]] = None,
    max_results: int = 6,
) -> Dict[str, Any]:
    """
    Executes a general web search with optional recency filter ('d', 'w', 'm', 'y'),
    region code, site/domain restriction, and domain exclusions.
    """
    effective_query = query.strip()
    if domain_filter:
        clean_dom = domain_filter.replace("https://", "").replace("http://", "").strip("/")
        if f"site:{clean_dom}" not in effective_query:
            effective_query = f"{effective_query} site:{clean_dom}"

    for exc in exclude_domains or []:
        clean_exc = exc.replace("https://", "").replace("http://", "").strip("/")
        if clean_exc:
            effective_query = f"{effective_query} -site:{clean_exc}"

    results: List[Dict[str, str]] = []
    max_results = max(1, min(20, int(max_results or 8)))

    # 1. Try ddgs library first
    try:
        from ddgs import DDGS

        timelimit = None
        if time_range in ("d", "day"):
            timelimit = "d"
        elif time_range in ("w", "week"):
            timelimit = "w"
        elif time_range in ("m", "month"):
            timelimit = "m"
        elif time_range in ("y", "year"):
            timelimit = "y"

        raw_hits = DDGS().text(
            effective_query,
            region=region or "wt-wt",
            timelimit=timelimit,
            max_results=max_results,
        )
        for hit in raw_hits or []:
            href = hit.get("href") or hit.get("url") or ""
            title = (hit.get("title") or "").strip()
            body = (hit.get("body") or hit.get("snippet") or "").strip()
            if href and title:
                domain = urllib.parse.urlparse(href).netloc.replace("www.", "")
                results.append(
                    {
                        "title": title,
                        "url": href,
                        "source": domain or "web",
                        "publishedAt": "",
                        "snippet": body[:450],
                    }
                )
    except Exception:
        pass

    # 2. Fallback to Yahoo web search if ddgs returned no results
    if not results:
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote(effective_query)}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=7) as resp:
                page = resp.read().decode("utf-8", errors="ignore")
            for match in re.finditer(
                r'<div class="[^"]*algo[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
                page,
                re.S,
            ):
                block = match.group(1)
                a_m = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
                s_m = re.search(r'<div class="compText[^>]*>(.*?)</div>', block, re.S)
                if not a_m:
                    continue
                href = html.unescape(a_m.group(1))
                if "RU=" in href:
                    href = urllib.parse.unquote(href.split("RU=")[1].split("/")[0])
                if not href.startswith("http") or "yahoo.com" in href:
                    continue
                title = re.sub(r"^https?://[^\s]+\s+", "", _clean_text(a_m.group(2))).strip()
                snippet = _clean_text(s_m.group(1) if s_m else "")
                domain = urllib.parse.urlparse(href).netloc.replace("www.", "")
                if title and snippet:
                    results.append(
                        {
                            "title": title[:150],
                            "url": href,
                            "source": domain,
                            "publishedAt": "",
                            "snippet": snippet[:450],
                        }
                    )
                if len(results) >= max_results:
                    break
        except Exception:
            pass

    return {
        "tool": "web_search",
        "executedQuery": effective_query,
        "count": len(results),
        "results": results,
    }


def news_search(
    query: str,
    recency: str = "w",
    region: str = "US:en",
    max_results: int = 6,
) -> Dict[str, Any]:
    """
    Searches live news indices and Google News RSS feeds for breaking events,
    trending topics, announcements, and timestamped articles.
    """
    max_results = max(1, min(20, int(max_results or 8)))
    results: List[Dict[str, str]] = []
    seen_titles = set()

    # Strip conversational meta-words so news indices match actual topic/location headlines
    cleaned_news_q = re.sub(
        r"\b(what'?s|what\s+is|trending|topics?|happening|latest|news|today|right\s+now|current|currently|in|on|about|the|updates?)\b",
        " ",
        query,
        flags=re.I,
    )
    cleaned_news_q = re.sub(r"\s+", " ", cleaned_news_q).strip()
    effective_news_q = cleaned_news_q if len(cleaned_news_q) >= 2 else query.strip()

    # 1. Try ddgs news search
    try:
        from ddgs import DDGS

        timelimit = recency if recency in ("d", "w", "m") else None
        ddg_news = DDGS().news(effective_news_q, timelimit=timelimit, max_results=max_results)
        for item in ddg_news or []:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not title or not url or title.lower()[:50] in seen_titles:
                continue
            seen_titles.add(title.lower()[:50])
            results.append(
                {
                    "title": title,
                    "url": url,
                    "source": (item.get("source") or urllib.parse.urlparse(url).netloc).strip(),
                    "publishedAt": (item.get("date") or "").strip(),
                    "snippet": (item.get("body") or "")[:400].strip(),
                }
            )
    except Exception:
        pass

    # 2. Supplement with Google News RSS via feedparser / ElementTree
    if len(results) < max_results:
        rss_url = (
            f"https://news.google.com/rss/search?"
            f"q={urllib.parse.quote(effective_news_q)}&hl=en-US&gl=US&ceid=US:en"
        )
        req = urllib.request.Request(rss_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=7) as resp:
                xml_bytes = resp.read()
            root = ET.fromstring(xml_bytes)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                if not title or not link or title.lower()[:50] in seen_titles:
                    continue
                seen_titles.add(title.lower()[:50])
                pub_date = (item.findtext("pubDate") or "").strip()
                source_el = item.find("source")
                source_name = (
                    source_el.text.strip()
                    if source_el is not None and source_el.text
                    else "Google News"
                )
                desc = _clean_text(item.findtext("description") or "")
                results.append(
                    {
                        "title": title,
                        "url": link,
                        "source": source_name,
                        "publishedAt": pub_date,
                        "snippet": desc[:400],
                    }
                )
                if len(results) >= max_results:
                    break
        except Exception:
            pass

    return {
        "tool": "news_search",
        "executedQuery": query,
        "count": len(results),
        "results": results,
    }


def academic_and_reference_search(
    query: str,
    source_type: str = "all",
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    Searches high-trust reference and scientific indices (Wikipedia and ArXiv)
    for encyclopedic definitions, technical architectures, and research papers.
    """
    max_results = max(1, min(10, int(max_results or 5)))
    results: List[Dict[str, str]] = []

    # 1. Wikipedia Search & Summary Extract
    if source_type in ("all", "wikipedia", "reference"):
        wiki_url = (
            f"https://en.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={urllib.parse.quote(query)}&utf8=&format=json&srlimit={min(3, max_results)}"
        )
        req = urllib.request.Request(
            wiki_url, headers={"User-Agent": "IntelligentWebRetrievalAgent/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("query", {}).get("search", []):
                title = item.get("title", "")
                snippet = _clean_text(item.get("snippet", ""))
                if title:
                    page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                    results.append(
                        {
                            "title": f"{title} (Wikipedia)",
                            "url": page_url,
                            "source": "wikipedia.org",
                            "publishedAt": "",
                            "snippet": snippet[:450],
                        }
                    )
        except Exception:
            pass

    # 2. ArXiv Scientific Paper API
    if source_type in ("all", "arxiv", "academic", "papers") and len(results) < max_results:
        rem = max_results - len(results)
        q_terms = [urllib.parse.quote(w) for w in re.findall(r"[A-Za-z0-9]+", query) if len(w) >= 3][:4]
        arxiv_q = "+AND+".join(f"all:{w}" for w in q_terms) if q_terms else f"all:{urllib.parse.quote(query)}"
        arxiv_url = (
            f"https://export.arxiv.org/api/query?"
            f"search_query={arxiv_q}&start=0&max_results={rem}"
        )
        req = urllib.request.Request(
            arxiv_url, headers={"User-Agent": "IntelligentWebRetrievalAgent/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=7) as resp:
                xml_bytes = resp.read()
            root = ET.fromstring(xml_bytes)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns))
                summary = _clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
                link = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
                published = (entry.findtext("atom:published", default="", namespaces=ns) or "")[:10]
                if title and link:
                    results.append(
                        {
                            "title": f"{title} [ArXiv]",
                            "url": link,
                            "source": "arxiv.org",
                            "publishedAt": published,
                            "snippet": summary[:450],
                        }
                    )
        except Exception:
            pass

    return {
        "tool": "academic_and_reference_search",
        "executedQuery": query,
        "sourceType": source_type,
        "count": len(results),
        "results": results,
    }


def site_map_and_subpath_discovery(
    domain_or_url: str,
    keyword_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Discovers key subpaths and pages on a target domain by inspecting its
    homepage navigation links and sitemap.xml/robots.txt.
    """
    if not domain_or_url.startswith("http"):
        base_url = f"https://{domain_or_url.strip('/')}"
    else:
        parsed = urllib.parse.urlparse(domain_or_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

    discovered_links: List[Dict[str, str]] = []
    seen_urls = set()
    kw = (keyword_filter or "").strip().lower()

    # 1. Inspect homepage navigation links
    try:
        from bs4 import BeautifulSoup

        req = urllib.request.Request(base_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=7) as resp:
            raw_html = resp.read(200_000).decode("utf-8", errors="ignore")
        soup = BeautifulSoup(raw_html, "lxml")
        for a in soup.find_all("a", href=True):
            full_url = urllib.parse.urljoin(base_url, a["href"]).split("#")[0]
            if not full_url.startswith(base_url) or full_url in seen_urls:
                continue
            label = _clean_text(a.get_text(" "))
            if kw and kw not in full_url.lower() and kw not in label.lower():
                continue
            seen_urls.add(full_url)
            discovered_links.append(
                {"url": full_url, "anchorText": label or full_url.replace(base_url, "") or "/"}
            )
            if len(discovered_links) >= 25:
                break
    except Exception:
        pass

    # 2. Check sitemap.xml if more links are needed
    if len(discovered_links) < 15:
        sitemap_url = f"{base_url}/sitemap.xml"
        try:
            req = urllib.request.Request(sitemap_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=5) as resp:
                xml_text = resp.read(200_000).decode("utf-8", errors="ignore")
            for loc in re.findall(r"<loc>(.*?)</loc>", xml_text):
                loc = html.unescape(loc.strip())
                if loc in seen_urls:
                    continue
                if kw and kw not in loc.lower():
                    continue
                seen_urls.add(loc)
                discovered_links.append({"url": loc, "anchorText": "sitemap_entry"})
                if len(discovered_links) >= 25:
                    break
        except Exception:
            pass

    return {
        "tool": "site_map_and_subpath_discovery",
        "baseUrl": base_url,
        "keywordFilter": keyword_filter,
        "discoveredCount": len(discovered_links),
        "subpaths": discovered_links,
    }


def _sharpen_query(raw_query: str) -> str:
    """Strips vague conversational phrasing so search engines hit concrete entities and events."""
    cleaned = re.sub(
        r"\b(what'?s|what\s+is|what\s+are|tell\s+me\s+about|can\s+you\s+find|please\s+search|trending|topics?|happening|right\s+now|currently|in\s+the\s+world|around|the|a|an|about|give\s+me)\b",
        " ",
        raw_query or "",
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if len(cleaned) >= 2 else (raw_query or "").strip()


def social_and_platform_search(
    query: str,
    platforms: Optional[List[str]] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    Actively investigates community and social media platforms (TikTok, Facebook, X/Twitter,
    Reddit, Instagram) using targeted platform-specific queries to surface viral clips,
    on-the-ground posts, public discourse, and eyewitness updates.
    """
    sharp_q = _sharpen_query(query)
    target_platforms = platforms or ["tiktok", "facebook", "x", "reddit", "instagram"]
    platform_specs = {
        "tiktok": ("TikTok", "tiktok.com", f"{sharp_q} site:tiktok.com"),
        "facebook": ("Facebook", "facebook.com", f"{sharp_q} site:facebook.com"),
        "x": ("X (Twitter)", "x.com", f"{sharp_q} (site:x.com OR site:twitter.com)"),
        "reddit": ("Reddit", "reddit.com", f"{sharp_q} site:reddit.com"),
        "instagram": ("Instagram", "instagram.com", f"{sharp_q} site:instagram.com"),
    }

    active_specs = [
        platform_specs[p.lower()]
        for p in target_platforms
        if p.lower() in platform_specs
    ] or list(platform_specs.values())

    results: List[Dict[str, Any]] = []
    seen_urls = set()

    def _search_single_platform(spec):
        plat_label, dom_match, plat_query = spec
        items = []
        # Use web_search with recency preference first, then fallback to broader if empty
        w_res = web_search(plat_query, time_range="m", max_results=3)
        raw_list = w_res.get("results") or []
        if not raw_list:
            w_res = web_search(plat_query, max_results=3)
            raw_list = w_res.get("results") or []
        for it in raw_list:
            u = it.get("url", "")
            if not u:
                continue
            title = (it.get("title") or "").strip()
            snippet = (it.get("snippet") or "").strip()
            items.append(
                {
                    "title": f"[{plat_label}] {title}" if plat_label.lower() not in title.lower() else title,
                    "url": u,
                    "source": plat_label,
                    "platform": plat_label,
                    "publishedAt": it.get("publishedAt") or "Recent",
                    "snippet": snippet[:450],
                }
            )
        return items

    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = [pool.submit(_search_single_platform, sp) for sp in active_specs]
        for f in as_completed(futs):
            try:
                for item in f.result():
                    if item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        results.append(item)
            except Exception:
                pass

    return {
        "tool": "social_and_platform_search",
        "executedQuery": sharp_q,
        "platformsChecked": [s[0] for s in active_specs],
        "count": len(results[:max_results]),
        "results": results[:max_results],
    }


def _assess_pdf_information_value(
    title: str,
    extracted_text: str,
    page_count: int,
    query: str,
) -> Dict[str, Any]:
    """
    Evaluates a parsed PDF document and computes an explicit Information Value Verdict
    ('HIGH VALUE', 'MODERATE VALUE', or 'LOW / SUPPLEMENTAL VALUE'), numerical score (0-100),
    executive summary bullets, and a transparent rationale.
    """
    text = (extracted_text or "").strip()
    # Reject paywall / raw HTML markup leaking as parsed text
    if re.search(r"<!doctype\s+html|<html\b|<head\b|<link\s+rel=|<script\b", text, re.I):
        return {
            "valueVerdict": "LOW VALUE",
            "valueScore": 10,
            "valueRationale": "Parsed content is raw web/paywall markup (e.g. Scribd wrapper) rather than substantive PDF document text.",
            "executiveSummary": "Document could not be parsed; contained web paywall markup.",
        }

    if not text or len(text) < 120:
        return {
            "valueVerdict": "LOW VALUE",
            "valueScore": 22,
            "valueRationale": "PDF contains minimal extractable text or is a scanned/empty wrapper without substantive data.",
            "executiveSummary": "Document text could not be extracted in sufficient depth.",
        }

    q_tokens = [
        w.lower()
        for w in re.findall(r"[A-Za-z0-9]+", _sharpen_query(query))
        if len(w) >= 3
    ]
    t_lower = (title + " " + text).lower()
    matched_tokens = [tok for tok in q_tokens if tok in t_lower]
    relevance_ratio = (len(matched_tokens) / max(1, len(q_tokens))) if q_tokens else 0.7

    # Count quantitative indicators (percentages, currency, years, tables/figures, numbers)
    quant_matches = re.findall(
        r"(?:\b\d+(?:\.\d+)?%|\$\s?\d+|KSh\s?\d+|\b\d{1,3}(?:,\d{3})+\b|\b202[4-7]\b)",
        text,
    )
    quant_count = len(quant_matches)

    score = 35
    score += min(30, int(relevance_ratio * 35))
    score += min(20, quant_count * 2)
    score += min(15, max(1, page_count) * 2)
    score = max(10, min(98, score))

    # Extract top informative sentences containing numbers or matched query tokens
    raw_sentences = [
        re.sub(r"\s+", " ", s).strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", text)
        if 45 <= len(s.strip()) <= 320 and not s.strip().startswith("--- Page")
    ]
    scored_sents = []
    for s in raw_sentences:
        s_low = s.lower()
        s_score = sum(3 for tok in matched_tokens if tok in s_low)
        if re.search(r"\d+(?:\.\d+)?%|\$|KSh|\b\d{2,}\b", s):
            s_score += 4
        if s_score > 0:
            scored_sents.append((s_score, s))
    scored_sents.sort(key=lambda x: x[0], reverse=True)

    top_points: List[str] = []
    for _, s in scored_sents:
        if all(s[:40].lower() not in existing.lower() for existing in top_points):
            top_points.append(s)
        if len(top_points) >= 3:
            break
    if not top_points and raw_sentences:
        top_points = raw_sentences[:2]

    exec_summary = " • ".join(top_points) if top_points else text[:400]

    if score >= 72 and relevance_ratio >= 0.4:
        verdict = "HIGH VALUE"
        rationale = (
            f"High empirical density ({quant_count} quantitative metrics/figures across {max(1, page_count)} page(s)) "
            f"with direct topical alignment ({len(matched_tokens)}/{max(1, len(q_tokens))} core terms matched)."
        )
    elif score >= 48:
        verdict = "MODERATE VALUE"
        rationale = (
            f"Contains useful background context ({max(1, page_count)} page(s), {quant_count} data points), "
            f"suitable as supporting documentation."
        )
    else:
        verdict = "LOW VALUE"
        rationale = (
            f"Low topical specificity or sparse empirical figures ({quant_count} metrics); "
            f"tangential to the primary investigation."
        )

    return {
        "valueVerdict": verdict,
        "valueScore": score,
        "valueRationale": rationale,
        "executiveSummary": exec_summary[:650],
    }


def pdf_search_and_summarize(
    query: str,
    max_results: int = 3,
) -> Dict[str, Any]:
    """
    Searches for relevant PDF reports, official filings, policy briefs, and research papers
    matching the query, downloads and parses their text via pypdf, summarizes key findings,
    and explicitly depicts whether or not each PDF's information is of value.
    """
    sharp_q = _sharpen_query(query)
    core_pdf_words = [
        w for w in sharp_q.split()
        if w.lower() not in ("economic", "update", "policy", "brief", "analysis", "data", "latest", "news", "trending")
    ][:4]
    concise_pdf_q = " ".join(core_pdf_words) if core_pdf_words else sharp_q
    pdf_query = f"{concise_pdf_q} filetype:pdf"
    w_res = web_search(pdf_query, max_results=6)
    candidates = list(w_res.get("results") or [])

    if len([c for c in candidates if ".pdf" in (c.get("url") or "").lower()]) < 2:
        w_res2 = web_search(f"{concise_pdf_q} report pdf", max_results=6)
        candidates.extend(w_res2.get("results") or [])

    pdf_candidates = []
    seen_u = set()
    landing_pages = []
    # Significant words from query to ensure PDF title relevance
    query_core_tokens = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", sharp_q) if len(w) >= 3 and w.lower() not in ("pdf", "report", "publication", "official", "data", "latest")]

    for c in candidates:
        u = c.get("url", "")
        t = c.get("title", "")
        if not u or u in seen_u:
            continue
        # Skip known paywalls / document preview wrappers that do not provide raw PDF text
        if "scribd.com" in u.lower() or "studocu.com" in u.lower() or "pdfdrive" in u.lower():
            continue
        # Verify title relevance to user inquiry
        c_meta = f"{t} {u}".lower()
        if query_core_tokens and not any(tok in c_meta for tok in query_core_tokens):
            continue

        if ".pdf" in u.lower() or "pdf" in t.lower():
            seen_u.add(u)
            pdf_candidates.append(c)
        else:
            landing_pages.append(c)
        if len(pdf_candidates) >= max(1, min(4, int(max_results or 3))):
            break

    # Follow document/PDF links on report landing pages if direct .pdf hits are scarce
    if len(pdf_candidates) < 2 and landing_pages:
        for lp in landing_pages[:2]:
            try:
                lk_res = extract_page_links(lp["url"], link_type="document")
                for lk in lk_res.get("links") or []:
                    lu = lk.get("url", "")
                    lt = lk.get("anchorText") or lp.get("title") or "PDF Report"
                    if lu and ".pdf" in lu.lower() and lu not in seen_u:
                        if "scribd.com" in lu.lower() or "studocu.com" in lu.lower():
                            continue
                        if query_core_tokens and not any(tok in f"{lt} {lu}".lower() for tok in query_core_tokens):
                            continue
                        seen_u.add(lu)
                        pdf_candidates.append(
                            {
                                "title": lt,
                                "url": lu,
                                "publishedAt": lp.get("publishedAt") or "Document",
                                "snippet": lp.get("snippet") or "",
                            }
                        )
                        if len(pdf_candidates) >= max_results:
                            break
            except Exception:
                pass

    # Only query ArXiv if the query is explicitly academic, mathematical, or scientific
    is_academic_query = bool(re.search(r"\b(arxiv|physics|mathematics|algorithm|quantum|peer-reviewed|journal|theory|experiment)\b", query, re.I))
    if is_academic_query and len(pdf_candidates) < max_results:
        primary_word = core_pdf_words[0] if core_pdf_words else sharp_q
        arxiv_res = academic_and_reference_search(primary_word, source_type="arxiv", max_results=2)
        for ar in arxiv_res.get("results") or []:
            ar_url = ar.get("url", "")
            if "/abs/" in ar_url:
                pdf_u = ar_url.replace("http://", "https://").replace("/abs/", "/pdf/")
            else:
                pdf_u = ar_url
            if pdf_u and pdf_u not in seen_u:
                seen_u.add(pdf_u)
                pdf_candidates.append(
                    {
                        "title": ar.get("title", "Research Paper").replace("[ArXiv]", "[PDF]"),
                        "url": pdf_u,
                        "publishedAt": ar.get("publishedAt") or "Research PDF",
                        "snippet": ar.get("snippet") or "",
                    }
                )
            if len(pdf_candidates) >= max(1, min(4, int(max_results or 3))):
                break

    parsed_pdfs: List[Dict[str, Any]] = []

    def _inspect_pdf(cand: Dict[str, Any]) -> Dict[str, Any]:
        u = cand["url"]
        title = (cand.get("title") or "PDF Document").strip()
        snippet = (cand.get("snippet") or "").strip()
        doc_res = parse_document_file(u, target_keywords=sharp_q, max_pages=8)
        extracted_text = (doc_res.get("extractedContent") or snippet or "").strip()
        page_count = int(doc_res.get("totalPages") or 1)
        assessment = _assess_pdf_information_value(
            title=title,
            extracted_text=extracted_text,
            page_count=page_count,
            query=sharp_q,
        )
        dom = urllib.parse.urlparse(u).netloc.replace("www.", "") or "PDF Report"
        return {
            "title": title if "[PDF]" in title else f"[PDF] {title}",
            "url": u,
            "source": f"{dom} (PDF)",
            "platform": "PDF",
            "publishedAt": cand.get("publishedAt") or "Document",
            "pageCount": page_count,
            "valueVerdict": assessment["valueVerdict"],
            "valueScore": assessment["valueScore"],
            "valueRationale": assessment["valueRationale"],
            "executiveSummary": assessment["executiveSummary"],
            "snippet": (
                f"[{assessment['valueVerdict']} • Score {assessment['valueScore']}/100] "
                f"{assessment['valueRationale']} | Summary: {assessment['executiveSummary']}"
            )[:500],
            "fullContent": (
                f"PDF DOCUMENT SUMMARY ({page_count} pages)\n"
                f"INFORMATION VALUE VERDICT: {assessment['valueVerdict']} ({assessment['valueScore']}/100)\n"
                f"VALUE RATIONALE: {assessment['valueRationale']}\n"
                f"EXECUTIVE SUMMARY: {assessment['executiveSummary']}\n\n"
                f"EXTRACTED PDF TEXT:\n{extracted_text[:2400]}"
            ),
        }

    if pdf_candidates:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(_inspect_pdf, c) for c in pdf_candidates]
            for f in as_completed(futs):
                try:
                    res = f.result()
                    # Only retain PDFs that were successfully parsed and hold genuine informational value
                    if res and int(res.get("valueScore") or 0) >= 45 and "paywall" not in res.get("valueRationale", "").lower():
                        parsed_pdfs.append(res)
                except Exception:
                    pass

    return {
        "tool": "pdf_search_and_summarize",
        "executedQuery": pdf_query,
        "count": len(parsed_pdfs),
        "results": parsed_pdfs,
    }


_NOISE_RELATION_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "youtube.com", "youtu.be", "tiktok.com", "google.com", "news.google.com",
    "apple.com", "play.google.com", "whatsapp.com", "t.me", "pinterest.com",
    "doubleclick.net", "googletagmanager.com",
}


def multi_related_site_search_and_crawl(
    query: str,
    seed_urls: Optional[List[str]] = None,
    max_related_sites: int = 10,
) -> Dict[str, Any]:
    """
    Executes a Multi-Related Site Search & Relational Cross-Domain Crawl:
    1. Fans out across multiple relational search vectors (institutional/official portals,
       investigative/specialist outlets, and independent corroborating sites).
    2. Inspects seed pages to discover outbound relational hyperlinks pointing to related
       websites, cited primary sources, and sibling reports.
    3. Crawls the discovered related sites in parallel (extracting clean Markdown or PDF text)
       so the agent investigates the entire web of related sites rather than isolated hits.
    """
    sharp_q = _sharpen_query(query)
    core_tokens = [
        w.lower()
        for w in re.findall(r"[A-Za-z0-9]+", sharp_q)
        if len(w) >= 3
    ]
    max_related_sites = max(3, min(16, int(max_related_sites or 10)))

    # 1. Multi-vector related site search fan-out
    relational_facets = [
        ("Institutional & Official Portals", f"{sharp_q} official statement authority portal report"),
        ("Investigative & Specialist Sites", f"{sharp_q} investigation analysis breakdown data"),
        ("Regional & Independent Corroboration", f"{sharp_q} latest developments coverage"),
    ]

    candidate_sites: List[Dict[str, Any]] = []
    seen_urls = set(seed_urls or [])
    seen_domains = set()
    for u in seen_urls:
        dom = urllib.parse.urlparse(u).netloc.replace("www.", "").lower()
        if dom:
            seen_domains.add(dom)

    def _run_facet_search(facet_tuple):
        rel_label, facet_q = facet_tuple
        res = web_search(facet_q, max_results=5)
        items = []
        for it in res.get("results") or []:
            u = it.get("url", "")
            if not u:
                continue
            dom = urllib.parse.urlparse(u).netloc.replace("www.", "").lower()
            items.append(
                {
                    "title": it.get("title", ""),
                    "url": u,
                    "source": dom or it.get("source", "web"),
                    "publishedAt": it.get("publishedAt", ""),
                    "snippet": it.get("snippet", ""),
                    "relationType": rel_label,
                }
            )
        return items

    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(_run_facet_search, f) for f in relational_facets]
        for fut in as_completed(futs):
            try:
                for item in fut.result():
                    u = item["url"]
                    dom = item["source"]
                    if u in seen_urls or any(nd in dom for nd in _NOISE_RELATION_DOMAINS):
                        continue
                    seen_urls.add(u)
                    candidate_sites.append(item)
            except Exception:
                pass

    # 2. Relational Outbound Link Discovery from seed URLs (or top 2 facet hits)
    crawl_seeds = list(seed_urls or [])[:3]
    if len(crawl_seeds) < 2:
        for cand in candidate_sites[:3]:
            if cand["url"] not in crawl_seeds:
                crawl_seeds.append(cand["url"])
            if len(crawl_seeds) >= 3:
                break

    filter_kw = core_tokens[0] if core_tokens else None

    def _discover_outbound_related_links(seed_u: str):
        seed_dom = urllib.parse.urlparse(seed_u).netloc.replace("www.", "").lower()
        links_res = extract_page_links(seed_u, filter_keyword=filter_kw, link_type="all")
        discovered = []
        for lk in links_res.get("links") or []:
            href = lk.get("url", "")
            anchor = (lk.get("anchorText") or "").strip()
            if not href or not href.startswith("http") or len(anchor) < 12:
                continue
            target_dom = urllib.parse.urlparse(href).netloc.replace("www.", "").lower()
            if not target_dom or any(nd in target_dom for nd in _NOISE_RELATION_DOMAINS):
                continue
            # Prefer external related domains or deep document/article paths
            is_cross_domain = target_dom != seed_dom
            anchor_low = (anchor + " " + href).lower()
            if core_tokens and not any(tok in anchor_low for tok in core_tokens[:4]):
                continue
            rel_desc = (
                f"Cross-Domain Link ({seed_dom} → {target_dom})"
                if is_cross_domain
                else f"Deep Relational Subpath on {target_dom}"
            )
            discovered.append(
                {
                    "title": anchor[:140],
                    "url": href,
                    "source": target_dom,
                    "publishedAt": "Related Site",
                    "snippet": f"[{rel_desc}] {anchor}",
                    "relationType": rel_desc,
                    "isCrossDomain": is_cross_domain,
                }
            )
            if len(discovered) >= 4:
                break
        return discovered

    if crawl_seeds:
        with ThreadPoolExecutor(max_workers=3) as link_pool:
            l_futs = [link_pool.submit(_discover_outbound_related_links, su) for su in crawl_seeds]
            for lf in as_completed(l_futs):
                try:
                    for rel_item in lf.result():
                        if rel_item["url"] not in seen_urls:
                            seen_urls.add(rel_item["url"])
                            # Prioritize cross-domain relational links
                            if rel_item.get("isCrossDomain"):
                                candidate_sites.insert(0, rel_item)
                            else:
                                candidate_sites.append(rel_item)
                except Exception:
                    pass

    # 3. Prioritize domain diversity across all candidate related sites and crawl them in parallel
    diverse_Targets: List[Dict[str, Any]] = []
    used_target_domains = set()
    for c in candidate_sites:
        dom = c.get("source", "")
        if dom not in used_target_domains:
            used_target_domains.add(dom)
            diverse_Targets.append(c)
        if len(diverse_Targets) >= max_related_sites:
            break
    if len(diverse_Targets) < max_related_sites:
        for c in candidate_sites:
            if c not in diverse_Targets:
                diverse_Targets.append(c)
            if len(diverse_Targets) >= max_related_sites:
                break

    crawled_related_sites: List[Dict[str, Any]] = []

    def _crawl_related_site(site_item: Dict[str, Any]) -> Dict[str, Any]:
        u = site_item["url"]
        rel_type = site_item.get("relationType") or "Related Site"
        if u.lower().endswith(".pdf") or ".pdf?" in u.lower():
            doc = parse_document_file(u, target_keywords=sharp_q, max_pages=6)
            extracted = (doc.get("extractedContent") or site_item.get("snippet") or "").strip()
            plat = "PDF"
        else:
            md_res = fetch_page_markdown(u, include_tables=True)
            extracted = (md_res.get("markdown") or site_item.get("snippet") or "").strip()
            plat = "Related Site"

        snippet_base = site_item.get("snippet") or extracted[:380]
        return {
            "title": site_item.get("title") or u,
            "url": u,
            "source": site_item.get("source") or urllib.parse.urlparse(u).netloc.replace("www.", ""),
            "platform": plat,
            "relationType": rel_type,
            "publishedAt": site_item.get("publishedAt") or "Related Site",
            "snippet": f"[{rel_type}] {snippet_base}"[:450],
            "fullContent": (
                f"RELATIONAL SITE CRAWL ({rel_type})\n"
                f"SOURCE DOMAIN: {site_item.get('source', '')}\n\n"
                f"{extracted[:2800]}"
            ),
        }

    if diverse_Targets:
        with ThreadPoolExecutor(max_workers=5) as crawl_pool:
            c_futs = [crawl_pool.submit(_crawl_related_site, t) for t in diverse_Targets]
            for cf in as_completed(c_futs):
                try:
                    crawled_related_sites.append(cf.result())
                except Exception:
                    pass

    unique_domains = sorted(list({s.get("source", "") for s in crawled_related_sites if s.get("source")}))
    return {
        "tool": "multi_related_site_search_and_crawl",
        "executedQuery": sharp_q,
        "count": len(crawled_related_sites),
        "uniqueDomainsCrawled": unique_domains,
        "results": crawled_related_sites,
    }

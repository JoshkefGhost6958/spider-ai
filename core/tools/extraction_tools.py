import io
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _fetch_raw_url(url: str, max_bytes: int = 400_000) -> Tuple[bytes, str, str]:
    """Helper returning (content_bytes, content_type, final_url)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=8) as resp:
        ctype = resp.headers.get("Content-Type", "text/html")
        final_url = resp.geturl() or url
        raw_bytes = resp.read(max_bytes)
    return raw_bytes, ctype, final_url


def fetch_page_markdown(
    url: str,
    include_links: bool = True,
    include_tables: bool = True,
) -> Dict[str, Any]:
    """
    Fetches a web page and extracts its main readable content as clean Markdown
    using trafilatura (with BeautifulSoup fallback), stripping boilerplate/ads.
    """
    try:
        raw_bytes, ctype, final_url = _fetch_raw_url(url)
        html_text = raw_bytes.decode("utf-8", errors="ignore")
    except Exception as exc:
        return {"tool": "fetch_page_markdown", "url": url, "error": str(exc)}

    title = ""
    markdown_content = ""

    # 1. Try trafilatura first for high-precision article & table extraction
    try:
        import trafilatura

        extracted = trafilatura.extract(
            html_text,
            include_links=include_links,
            include_tables=include_tables,
            output_format="markdown",
            url=final_url,
        )
        if extracted:
            markdown_content = extracted.strip()
        meta = trafilatura.extract_metadata(html_text)
        if meta and meta.title:
            title = meta.title
    except Exception:
        pass

    # 2. Fallback to BeautifulSoup if trafilatura returned empty
    if not markdown_content:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html_text, "lxml")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            for tag in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
                tag.decompose()
            paras = [
                re.sub(r"\s+", " ", el.get_text(" ")).strip()
                for el in soup.find_all(["h1", "h2", "h3", "p", "li"])
            ]
            markdown_content = "\n\n".join(p for p in paras if len(p) > 25)
        except Exception as exc:
            return {"tool": "fetch_page_markdown", "url": url, "error": str(exc)}

    return {
        "tool": "fetch_page_markdown",
        "url": final_url,
        "title": title,
        "contentLength": len(markdown_content),
        "markdown": markdown_content[:4500],
    }


def extract_page_links(
    url: str,
    filter_keyword: Optional[str] = None,
    link_type: str = "all",
) -> Dict[str, Any]:
    """
    Extracts hyperlinks from a web page along with anchor text and link category
    ('navigation', 'pagination', 'document', 'article') so the agent can navigate deeper.
    """
    try:
        from bs4 import BeautifulSoup

        raw_bytes, _, final_url = _fetch_raw_url(url)
        html_text = raw_bytes.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html_text, "lxml")
    except Exception as exc:
        return {"tool": "extract_page_links", "url": url, "error": str(exc)}

    kw = (filter_keyword or "").strip().lower()
    links: List[Dict[str, str]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(final_url, a["href"]).split("#")[0]
        if not href.startswith("http") or href in seen:
            continue
        anchor = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        if not anchor and not kw:
            continue

        # Classify link
        lower_href = href.lower()
        lower_anchor = anchor.lower()
        if any( lower_href.endswith(ext) for ext in (".pdf", ".csv", ".xlsx", ".json", ".xml", ".zip") ):
            ltype = "document"
        elif any(w in lower_anchor for w in ("next", "page ", "older", "more", "»", "→")):
            ltype = "pagination"
        elif len(anchor.split()) <= 3:
            ltype = "navigation"
        else:
            ltype = "article"

        if link_type != "all" and ltype != link_type:
            continue
        if kw and kw not in lower_href and kw not in lower_anchor:
            continue

        seen.add(href)
        links.append({"url": href, "anchorText": anchor[:120], "linkType": ltype})
        if len(links) >= 35:
            break

    return {
        "tool": "extract_page_links",
        "url": final_url,
        "count": len(links),
        "links": links,
    }


def extract_tables_from_page(
    url: str,
    table_keyword: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extracts HTML <table> elements from a web page into structured Markdown tables
    and row arrays, optionally filtered by a keyword.
    """
    try:
        from bs4 import BeautifulSoup

        raw_bytes, _, final_url = _fetch_raw_url(url)
        html_text = raw_bytes.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html_text, "lxml")
    except Exception as exc:
        return {"tool": "extract_tables_from_page", "url": url, "error": str(exc)}

    kw = (table_keyword or "").strip().lower()
    tables_out: List[Dict[str, Any]] = []

    for idx, table in enumerate(soup.find_all("table")):
        rows_data: List[List[str]] = []
        for tr in table.find_all("tr"):
            cells = [
                re.sub(r"\s+", " ", c.get_text(" ")).strip()
                for c in tr.find_all(["th", "td"])
            ]
            if any(cells):
                rows_data.append(cells)

        if len(rows_data) < 2:
            continue

        flat_text = " ".join(" ".join(r) for r in rows_data).lower()
        if kw and kw not in flat_text:
            continue

        # Convert to Markdown table
        max_cols = max(len(r) for r in rows_data)
        padded = [r + [""] * (max_cols - len(r)) for r in rows_data[:25]]
        header = "| " + " | ".join(padded[0]) + " |"
        sep = "| " + " | ".join(["---"] * max_cols) + " |"
        body = "\n".join("| " + " | ".join(r) + " |" for r in padded[1:])
        md_table = f"{header}\n{sep}\n{body}"

        tables_out.append(
            {
                "tableIndex": idx + 1,
                "rowCount": len(rows_data),
                "columnCount": max_cols,
                "markdownTable": md_table,
            }
        )
        if len(tables_out) >= 6:
            break

    return {
        "tool": "extract_tables_from_page",
        "url": final_url,
        "tableCount": len(tables_out),
        "tables": tables_out,
    }


def query_page_content(
    url: str,
    search_query_or_regex: str,
) -> Dict[str, Any]:
    """
    Searches within a web page for specific keywords, phrases, or regex patterns
    (like Ctrl+F with surrounding paragraph context).
    """
    page_data = fetch_page_markdown(url, include_links=False, include_tables=True)
    if "error" in page_data:
        return {"tool": "query_page_content", "url": url, "error": page_data["error"]}

    full_text = page_data.get("markdown") or ""
    blocks = [b.strip() for b in re.split(r"\n{2,}", full_text) if b.strip()]

    try:
        pattern = re.compile(search_query_or_regex, re.I)
    except re.error:
        pattern = re.compile(re.escape(search_query_or_regex), re.I)

    matches: List[str] = []
    for b in blocks:
        if pattern.search(b):
            matches.append(b[:600])
            if len(matches) >= 8:
                break

    return {
        "tool": "query_page_content",
        "url": url,
        "query": search_query_or_regex,
        "matchCount": len(matches),
        "matchingExcerpts": matches,
    }


def parse_document_file(
    url: str,
    target_keywords: Optional[str] = None,
    max_pages: int = 8,
) -> Dict[str, Any]:
    """
    Downloads and extracts text from online PDF documents (via pypdf), JSON, CSV,
    or XML files encountered during web navigation.
    """
    try:
        raw_bytes, ctype, final_url = _fetch_raw_url(url, max_bytes=4_500_000)
    except Exception as exc:
        return {"tool": "parse_document_file", "url": url, "error": str(exc)}

    kw_tokens = [
        w.lower()
        for w in re.findall(r"[A-Za-z0-9]+", target_keywords or "")
        if len(w) >= 3
    ]
    lower_ctype = ctype.lower()

    if "pdf" in lower_ctype or ".pdf" in final_url.lower():
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw_bytes))
            extracted_pages: List[str] = []
            fallback_pages: List[str] = []
            limit_pages = max(1, min(15, int(max_pages or 8)))
            for idx, page in enumerate(reader.pages[:30]):
                txt = (page.extract_text() or "").strip()
                if not txt:
                    continue
                page_block = f"--- Page {idx + 1} ---\n{txt[:1400]}"
                if len(fallback_pages) < limit_pages:
                    fallback_pages.append(page_block)
                if kw_tokens and not any(tok in txt.lower() for tok in kw_tokens):
                    continue
                extracted_pages.append(page_block)
                if len(extracted_pages) >= limit_pages:
                    break
            final_pages = extracted_pages if extracted_pages else fallback_pages
            return {
                "tool": "parse_document_file",
                "url": final_url,
                "documentType": "PDF",
                "totalPages": len(reader.pages),
                "extractedContent": "\n\n".join(final_pages)[:5500],
            }
        except Exception as exc:
            return {"tool": "parse_document_file", "url": final_url, "error": str(exc)}

    text_content = raw_bytes.decode("utf-8", errors="ignore")
    return {
        "tool": "parse_document_file",
        "url": final_url,
        "documentType": ctype,
        "extractedContent": text_content[:4000],
    }


def extract_structured_metadata(url: str) -> Dict[str, Any]:
    """
    Extracts embedded machine-readable metadata (JSON-LD, Schema.org, OpenGraph,
    meta description, canonical link, and publish date) from a web page.
    """
    try:
        from bs4 import BeautifulSoup

        raw_bytes, _, final_url = _fetch_raw_url(url)
        html_text = raw_bytes.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html_text, "lxml")
    except Exception as exc:
        return {"tool": "extract_structured_metadata", "url": url, "error": str(exc)}

    og_meta: Dict[str, str] = {}
    for m in soup.find_all("meta"):
        prop = m.get("property") or m.get("name") or ""
        content = m.get("content") or ""
        if prop and content and (
            prop.startswith("og:")
            or prop.startswith("article:")
            or prop in ("description", "author", "keywords", "publish_date")
        ):
            og_meta[prop] = content[:300]

    json_ld_blocks: List[Any] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            if script.string:
                json_ld_blocks.append(json.loads(script.string.strip()))
        except Exception:
            pass

    return {
        "tool": "extract_structured_metadata",
        "url": final_url,
        "title": soup.title.string.strip() if soup.title and soup.title.string else "",
        "metaTags": og_meta,
        "jsonLd": json_ld_blocks[:3],
    }

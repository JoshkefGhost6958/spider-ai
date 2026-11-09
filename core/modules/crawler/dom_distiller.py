import json
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spider_ai.crawler.dom_distiller")

# Elements that contain boilerplate noise and should be stripped before content extraction
BOILERPLATE_TAGS = [
    "script", "style", "noscript", "svg", "iframe", "form",
    "nav", "header", "footer", "aside",
]

# Patterns detecting cookie banners, consent modals, and ads
NOISE_CLASSES_AND_IDS = re.compile(
    r"\b(cookie|consent|banner|gdpr|advertisement|ads|popup|modal|newsletter|social-share)\b",
    re.I,
)


@dataclass
class DistilledPage:
    url: str
    domain: str
    title: str
    clean_markdown: str
    interactive_elements: List[str] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    schemas: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, str]] = field(default_factory=list)
    internal_links: List[Dict[str, str]] = field(default_factory=list)
    is_spa_shell: bool = False


class DOMDistiller:
    """
    Semantic DOM Distiller & Perception Layer.
    Transforms raw HTML into high-density structured tables, interactive CTAs,
    schema.org metadata, and clean Markdown prose.
    Detects unhydrated client-side SPA shells that require headless browser escalation.
    """

    def __init__(self, target_domain: Optional[str] = None):
        self.target_domain = (target_domain or "").lower().replace("www.", "").strip()

    def distill(self, html_content: str, base_url: str) -> DistilledPage:
        if not html_content or not html_content.strip():
            return DistilledPage(
                url=base_url,
                domain=urllib.parse.urlparse(base_url).netloc.replace("www.", ""),
                title="",
                clean_markdown="",
                is_spa_shell=True,
            )

        from bs4 import BeautifulSoup

        domain = urllib.parse.urlparse(base_url).netloc.replace("www.", "").lower()
        effective_target = self.target_domain or domain

        soup = BeautifulSoup(html_content, "lxml")

        # 1. Page Title
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        if not title:
            og_title = soup.find("meta", property="og:title")
            title = og_title["content"].strip() if og_title and og_title.get("content") else ""

        # 2. Check for empty client-side SPA shell (e.g. empty React <div id="root"></div>)
        is_spa_shell = self._is_empty_spa_shell(soup)

        # 3. Extract JSON-LD / schema.org metadata
        schemas = self._extract_schemas(soup)

        # 4. Extract Structured Tables (pricing, tiers, seating categories)
        tables = self._extract_tables(soup)

        # 5. Extract Interactive CTAs & Booking Buttons
        interactive_elements = self._extract_ctas(soup)

        # 6. Extract High-Fidelity Images and Diagrams
        images = self._extract_images(soup, base_url)

        # 7. Extract Internal Hyperlinks with Anchors for the Crawl Frontier
        internal_links = self._extract_internal_links(soup, base_url, effective_target)

        # 8. Clean Prose Extraction
        clean_markdown = self._extract_clean_markdown(soup)

        return DistilledPage(
            url=base_url,
            domain=domain,
            title=title,
            clean_markdown=clean_markdown,
            interactive_elements=interactive_elements,
            tables=tables,
            schemas=schemas,
            images=images,
            internal_links=internal_links,
            is_spa_shell=is_spa_shell,
        )

    def _is_empty_spa_shell(self, soup) -> bool:
        """Detects if body contains an unhydrated Single Page App container."""
        root_divs = soup.find_all("div", id=re.compile(r"^(root|app|__next)$", re.I))
        for r in root_divs:
            text = r.get_text(strip=True)
            if len(text) < 50:
                return True

        body = soup.find("body")
        if body:
            b_text = body.get_text(strip=True)
            # If body has virtually no text but contains bundle scripts, it's an unhydrated shell
            if len(b_text) < 100 and soup.find_all("script", src=re.compile(r"\.(?:bundle|chunk|main)\.js", re.I)):
                return True
        return False

    def _extract_schemas(self, soup) -> List[Dict[str, Any]]:
        schemas = []
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                if isinstance(data, dict):
                    schemas.append(data)
                elif isinstance(data, list):
                    schemas.extend([d for d in data if isinstance(d, dict)])
            except Exception:
                pass
        return schemas[:8]

    def _extract_tables(self, soup) -> List[Dict[str, Any]]:
        structured_tables = []
        for tbl in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in tbl.find_all("th")]
            rows = []
            for tr in tbl.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells and cells != headers:
                    rows.append(cells)

            if rows:
                structured_tables.append({
                    "headers": headers,
                    "rows": rows[:20],
                    "rowCount": len(rows),
                })
        return structured_tables[:5]

    def _extract_ctas(self, soup) -> List[str]:
        ctas = []
        # Buttons and active anchors
        elements = soup.find_all(["button", "a"], class_=re.compile(r"\b(btn|button|cta|action|booking|ticket)\b", re.I))
        for el in elements:
            text = re.sub(r"\s+", " ", el.get_text(strip=True))
            if 3 <= len(text) <= 60 and not re.search(r"\b(menu|close|search|toggle)\b", text, re.I):
                formatted = f"[Action: {text}]"
                if formatted not in ctas:
                    ctas.append(formatted)
        return ctas[:12]

    def _extract_images(self, soup, base_url: str) -> List[Dict[str, str]]:
        collected_imgs = []
        seen = set()

        # Check OpenGraph Image
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            u = urllib.parse.urljoin(base_url, og_img["content"].strip())
            if u not in seen:
                seen.add(u)
                collected_imgs.append({
                    "url": u,
                    "title": "Official Portal Showcase Banner",
                    "source": urllib.parse.urlparse(u).netloc.replace("www.", ""),
                })

        # Check <img> tags
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if not src or src.startswith("data:"):
                continue
            alt = (img.get("alt") or "").strip()
            # Skip tiny icons, tracking pixels, badges
            if re.search(r"\b(icon|avatar|logo|pixel|badge|spacer|spinner)\b", src.lower()):
                continue
            full_src = urllib.parse.urljoin(base_url, src)
            if full_src not in seen:
                seen.add(full_src)
                collected_imgs.append({
                    "url": full_src,
                    "title": alt or "Stadium Seating & Venue Layout Asset",
                    "source": urllib.parse.urlparse(full_src).netloc.replace("www.", ""),
                })
            if len(collected_imgs) >= 8:
                break

        return collected_imgs

    def _extract_internal_links(self, soup, base_url: str, target_domain: str) -> List[Dict[str, str]]:
        internal_links = []
        seen = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full_url = urllib.parse.urljoin(base_url, href)
            parsed = urllib.parse.urlparse(full_url)
            netloc = parsed.netloc.replace("www.", "").lower()

            if netloc == target_domain or netloc.endswith(f".{target_domain}"):
                anchor = re.sub(r"\s+", " ", a.get_text(strip=True))
                if full_url not in seen:
                    seen.add(full_url)
                    internal_links.append({
                        "href": full_url,
                        "anchor": anchor[:80],
                    })
        return internal_links

    def _extract_clean_markdown(self, soup) -> str:
        # Create a copy so we don't mutate soup
        from bs4 import BeautifulSoup
        clean_soup = BeautifulSoup(str(soup), "lxml")

        # Strip noisy boilerplate tags
        for tag_name in BOILERPLATE_TAGS:
            for el in clean_soup.find_all(tag_name):
                el.decompose()

        # Strip noise classes (cookie banners, popups, ads)
        for el in clean_soup.find_all(attrs={"class": NOISE_CLASSES_AND_IDS}):
            el.decompose()
        for el in clean_soup.find_all(attrs={"id": NOISE_CLASSES_AND_IDS}):
            el.decompose()

        # Extract text blocks
        paras = []
        for p in clean_soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
            txt = re.sub(r"\s+", " ", p.get_text(strip=True))
            if len(txt) >= 20:
                if p.name.startswith("h"):
                    level = int(p.name[1])
                    paras.append(f"{'#' * level} {txt}")
                elif p.name == "li":
                    paras.append(f"* {txt}")
                else:
                    paras.append(txt)

        return "\n\n".join(paras[:40])

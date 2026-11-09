import html
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_IGNORED_IMAGE_PATTERNS = re.compile(
    r"(?:[-_/](?:logo|icon|avatar|sprite|pixel|tracker|1x1|badge|button|spinner|loader|ad|ads|banner|placeholder|favicon|spacer|blank)[-_\./]|base64|og[-_]?default|default[-_]?image|placeholder[-_.]image)",
    re.I,
)


def _is_valid_content_image(img_url: str, page_url: str = "") -> bool:
    if not img_url or not img_url.startswith("http"):
        return False
    lower = img_url.lower()
    if lower.endswith(".svg") or lower.endswith(".ico") or "data:image" in lower:
        return False
    if _IGNORED_IMAGE_PATTERNS.search(lower):
        return False
    if page_url and _IGNORED_IMAGE_PATTERNS.search(page_url.lower()):
        return False
    return True


def image_search(
    query: str,
    max_results: int = 6,
) -> Dict[str, Any]:
    """
    Searches for relevant web images and news photography matching the query,
    returning image URLs, thumbnails, titles, source page URLs, and domains.
    """
    max_results = max(1, min(10, int(max_results or 6)))
    images: List[Dict[str, str]] = []
    seen_imgs = set()

    # 1. Try ddgs.images first
    try:
        from ddgs import DDGS

        raw_imgs = DDGS().images(
            query,
            region="wt-wt",
            safesearch="moderate",
            max_results=max_results + 4,
        )
        for item in raw_imgs or []:
            img_url = (item.get("image") or "").strip()
            thumb_url = (item.get("thumbnail") or img_url).strip()
            page_url = (item.get("url") or img_url).strip()
            title = (item.get("title") or "").strip()
            if not _is_valid_content_image(img_url, page_url) or img_url in seen_imgs:
                continue
            seen_imgs.add(img_url)
            domain = urllib.parse.urlparse(page_url).netloc.replace("www.", "")
            images.append(
                {
                    "imageUrl": img_url,
                    "thumbnailUrl": thumb_url or img_url,
                    "title": title[:120] or query,
                    "pageUrl": page_url,
                    "source": domain or "web",
                }
            )
            if len(images) >= max_results:
                break
    except Exception:
        pass

    # 2. Fallback: Yahoo / Bing image search or Wikimedia Commons API if ddgs returned fewer images
    if len(images) < max_results:
        wiki_img_url = (
            f"https://commons.wikimedia.org/w/api.php?action=query"
            f"&generator=search&gsrsearch=filetype:bitmap+{urllib.parse.quote(query)}"
            f"&gsrlimit={max_results}&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=640&format=json"
        )
        req = urllib.request.Request(
            wiki_img_url, headers={"User-Agent": "IntelligentWebRetrievalAgent/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            for p in pages.values():
                iinfo = (p.get("imageinfo") or [{}])[0]
                thumb = iinfo.get("thumburl") or iinfo.get("url") or ""
                full_url = iinfo.get("url") or thumb
                desc_url = iinfo.get("descriptionurl") or full_url
                title = (p.get("title") or "").replace("File:", "").rsplit(".", 1)[0]
                if thumb and thumb not in seen_imgs:
                    seen_imgs.add(thumb)
                    images.append(
                        {
                            "imageUrl": full_url,
                            "thumbnailUrl": thumb,
                            "title": title[:120],
                            "pageUrl": desc_url,
                            "source": "wikimedia.org",
                        }
                    )
                if len(images) >= max_results:
                    break
        except Exception:
            pass

    return {
        "tool": "image_search",
        "executedQuery": query,
        "count": len(images),
        "images": images,
    }


def extract_images_from_page(
    url: str,
    filter_keyword: Optional[str] = None,
    max_images: int = 6,
) -> Dict[str, Any]:
    """
    Extracts relevant article imagery (OpenGraph og:image, Twitter card image,
    <figure> images with captions, and main content <img> tags) from a web page.
    """
    max_images = max(1, min(10, int(max_images or 6)))
    images: List[Dict[str, str]] = []
    seen = set()
    kw = (filter_keyword or "").strip().lower()

    try:
        from bs4 import BeautifulSoup

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as resp:
            final_url = resp.geturl() or url
            raw_html = resp.read(250_000).decode("utf-8", errors="ignore")
        soup = BeautifulSoup(raw_html, "lxml")
        page_title = (
            soup.title.string.strip() if soup.title and soup.title.string else ""
        )
        domain = urllib.parse.urlparse(final_url).netloc.replace("www.", "")

        # 1. Check OpenGraph og:image & twitter:image (highest quality hero image for articles)
        for prop in ("og:image", "twitter:image", "twitter:image:src"):
            meta = soup.find("meta", attrs={"property": prop}) or soup.find(
                "meta", attrs={"name": prop}
            )
            if meta and meta.get("content"):
                img_u = urllib.parse.urljoin(final_url, meta["content"].strip())
                if _is_valid_content_image(img_u, final_url) and img_u not in seen:
                    if kw and kw not in page_title.lower() and kw not in img_u.lower():
                        continue
                    seen.add(img_u)
                    images.append(
                        {
                            "imageUrl": img_u,
                            "thumbnailUrl": img_u,
                            "title": page_title[:120] or domain,
                            "pageUrl": final_url,
                            "source": domain,
                        }
                    )
                    break  # Only take 1 meta hero image per page to avoid duplicate og:image + twitter:image cards

        # 2. Extract <figure> and <article>/<main> <img> elements with alt/figcaption
        container = soup.find(["article", "main"]) or soup
        for img in container.find_all("img"):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or ""
            ).strip()
            if not src:
                continue
            full_img = urllib.parse.urljoin(final_url, src)
            if not _is_valid_content_image(full_img, final_url) or full_img in seen:
                continue

            # Skip small thumbnails if width/height attributes are tiny
            try:
                w = int(re.sub(r"\D", "", str(img.get("width") or "0")) or 0)
                h = int(re.sub(r"\D", "", str(img.get("height") or "0")) or 0)
                if (w and w < 140) or (h and h < 100):
                    continue
            except Exception:
                pass

            alt = re.sub(r"\s+", " ", (img.get("alt") or "")).strip()
            fig = img.find_parent("figure")
            caption = ""
            if fig and fig.find("figcaption"):
                caption = re.sub(
                    r"\s+", " ", fig.find("figcaption").get_text(" ")
                ).strip()

            label = caption or alt or page_title or domain
            if kw and kw not in label.lower() and kw not in full_img.lower():
                continue

            seen.add(full_img)
            images.append(
                {
                    "imageUrl": full_img,
                    "thumbnailUrl": full_img,
                    "title": label[:120],
                    "pageUrl": final_url,
                    "source": domain,
                }
            )
            if len(images) >= max_images:
                break
    except Exception as exc:
        return {"tool": "extract_images_from_page", "url": url, "error": str(exc), "images": []}

    return {
        "tool": "extract_images_from_page",
        "url": url,
        "count": len(images),
        "images": images,
    }

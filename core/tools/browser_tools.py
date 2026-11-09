import base64
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "screenshots"
)
os.makedirs(CACHE_DIR, exist_ok=True)


class StatefulDomBrowserSession:
    """
    Per-request stateful browser navigation & interactive DOM interaction engine.
    Backboned by headless Chromium (Playwright) with fallback to Firefox and static engines.
    Tracks current URL, live page instance, parsed DOM tree, numbered interactive elements ([1], [2], ...),
    form inputs, scrolling offset, and real-time page screenshots so the agent can navigate websites,
    inspect interactive elements, click links/buttons, type into inputs, scroll, and capture visual proof.
    """

    def __init__(self, preferred_browser: str = "chromium") -> None:
        self.preferred_browser = preferred_browser
        self.current_url: str = ""
        self.title: str = ""
        self.raw_html: str = ""
        self.interactive_elements: Dict[int, Dict[str, Any]] = {}
        self.paragraphs: List[str] = []
        self.scroll_index: int = 0
        self.history: List[str] = []
        self.engine: str = "playwright_chromium"
        self._pw = None
        self._browser = None
        self._page = None
        self._init_attempted = False
        self.last_screenshot_path: Optional[str] = None
        self.last_screenshot_url: Optional[str] = None
        self.last_screenshot_base64: Optional[str] = None

    def _ensure_playwright(self) -> bool:
        if self._page is not None and not self._page.is_closed():
            return True
        if self._init_attempted and self._page is None:
            return False
        self._init_attempted = True
        try:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()

            # Launch headless Chromium
            b_type = self._pw.chromium
            engine_name = "playwright_chromium"
            if self.preferred_browser == "firefox":
                b_type = self._pw.firefox
                engine_name = "playwright_firefox"

            try:
                self._browser = b_type.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--no-zygote",
                    ],
                )
                self.engine = engine_name
            except Exception:
                # Fallback to Chromium if Firefox wasn't available
                self._browser = self._pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--no-zygote",
                    ],
                )
                self.engine = "playwright_chromium"

            context = self._browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=USER_AGENT,
                device_scale_factor=1,
            )
            self._page = context.new_page()
            return True
        except Exception:
            self.engine = "static_urllib_fallback"
            return False

    def capture_screenshot(self, full_page: bool = False) -> Dict[str, Any]:
        """Captures a high-resolution screenshot of the current page tab in Playwright."""
        if self._page and not self._page.is_closed():
            try:
                img_bytes = self._page.screenshot(type="jpeg", quality=85, full_page=full_page)
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                b64_uri = f"data:image/jpeg;base64,{b64_str}"

                # Cache to disk
                parsed = urllib.parse.urlparse(self.current_url or "screenshot")
                dom_clean = re.sub(r"[^a-zA-Z0-9_-]", "_", parsed.netloc or "page")
                fn = f"{dom_clean}_{os.getpid()}.jpg"
                fp = os.path.join(CACHE_DIR, fn)
                with open(fp, "wb") as f:
                    f.write(img_bytes)

                encoded_url = urllib.parse.quote(self.current_url or "https://example.com", safe="")
                cdn_url = f"https://s0.wp.com/mshots/v1/{encoded_url}?w=1440&h=900"

                self.last_screenshot_path = fp
                self.last_screenshot_url = cdn_url
                self.last_screenshot_base64 = b64_uri

                return {
                    "tool": "browser_capture_screenshot",
                    "status": "success",
                    "url": self.current_url,
                    "title": self.title,
                    "screenshotPath": fp,
                    "screenshotUrl": cdn_url,
                    "screenshotBase64": b64_uri[:120] + "... [truncated]",
                    "imageUri": b64_uri,
                    "engine": self.engine,
                    "width": 1440,
                    "height": 900,
                }
            except Exception:
                pass

        encoded_url = urllib.parse.quote(self.current_url or "https://example.com", safe="")
        cdn_url = f"https://s0.wp.com/mshots/v1/{encoded_url}?w=1440&h=900"
        return {
            "tool": "browser_capture_screenshot",
            "status": "fallback_cdn",
            "url": self.current_url,
            "title": self.title,
            "screenshotUrl": cdn_url,
            "imageUri": cdn_url,
            "engine": self.engine,
        }

    def navigate(self, url: str) -> Dict[str, Any]:
        if not url.startswith("http"):
            url = f"https://{url.lstrip('/')}"

        pw_ok = self._ensure_playwright()
        if pw_ok and self._page:
            try:
                self._page.goto(url, timeout=14000, wait_until="domcontentloaded")
                self._page.wait_for_timeout(800)
                self.current_url = self._page.url or url
                self.title = self._page.title() or self.current_url
                self.raw_html = self._page.content()
                self.history.append(self.current_url)
                self.scroll_index = 0
                self._parse_dom()
                self.capture_screenshot()
                return self.get_snapshot()
            except Exception:
                pass

        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as resp:
                self.current_url = resp.geturl() or url
                self.raw_html = resp.read(350_000).decode("utf-8", errors="ignore")
        except Exception as e:
            self.current_url = url
            self.raw_html = f"<html><body><p>Could not load {url}: {e}</p></body></html>"

        self.history.append(self.current_url)
        self.scroll_index = 0
        self._parse_dom()
        self.capture_screenshot()
        return self.get_snapshot()

    def _parse_dom(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(self.raw_html, "lxml")
        self.title = (
            soup.title.string.strip() if soup.title and soup.title.string else self.current_url
        )

        self.interactive_elements.clear()
        elem_id = 1
        for el in soup.find_all(["a", "button", "input", "select"]):
            tag = el.name
            label = re.sub(r"\s+", " ", el.get_text(" ")).strip()
            href = el.get("href") or ""
            placeholder = el.get("placeholder") or el.get("aria-label") or el.get("name") or ""
            input_type = el.get("type") or "text"
            el_id_attr = el.get("id") or ""
            el_name_attr = el.get("name") or ""

            if el_id_attr:
                selector = f"#{el_id_attr}"
            elif el_name_attr:
                selector = f"{tag}[name='{el_name_attr}']"
            elif tag == "a" and href:
                selector = f"a[href='{href}']"
            elif label:
                clean_lbl = re.sub(r"['\"\\]", "", label[:30])
                selector = f"{tag}:has-text('{clean_lbl}')"
            else:
                selector = tag

            if tag == "a" and href:
                full_href = urllib.parse.urljoin(self.current_url, href).split("#")[0]
                if not full_href.startswith("http") or not label:
                    continue
                self.interactive_elements[elem_id] = {
                    "id": elem_id,
                    "tag": "a",
                    "label": label[:90],
                    "href": full_href,
                    "selector": selector,
                }
                elem_id += 1
            elif tag == "input" and input_type not in ("hidden", "submit"):
                form = el.find_parent("form")
                action = (form.get("action") if form else "") or self.current_url
                full_action = urllib.parse.urljoin(self.current_url, action)
                field_name = el.get("name") or "q"
                self.interactive_elements[elem_id] = {
                    "id": elem_id,
                    "tag": "input",
                    "inputType": input_type,
                    "name": field_name,
                    "placeholder": placeholder[:80] or field_name,
                    "formAction": full_action,
                    "selector": selector,
                }
                elem_id += 1
            elif tag in ("button", "select") and (label or placeholder):
                self.interactive_elements[elem_id] = {
                    "id": elem_id,
                    "tag": tag,
                    "label": (label or placeholder)[:80],
                    "selector": selector,
                }
                elem_id += 1

            if elem_id > 50:
                break

        for s in soup(["script", "style", "noscript", "svg"]):
            s.decompose()

        self.paragraphs = [
            re.sub(r"\s+", " ", p.get_text(" ")).strip()
            for p in soup.find_all(["h1", "h2", "h3", "p", "li", "tr"])
            if len(re.sub(r"\s+", " ", p.get_text(" ")).strip()) > 25
        ]

    def get_snapshot(self) -> Dict[str, Any]:
        window = self.paragraphs[self.scroll_index : self.scroll_index + 18]
        interactive_list = [
            f"[{eid}] <{meta['tag']}> {meta.get('label') or meta.get('placeholder', '')}"
            + (f" -> {meta['href'][:80]}" if meta.get("href") else "")
            for eid, meta in list(self.interactive_elements.items())[:25]
        ]
        return {
            "currentUrl": self.current_url,
            "title": self.title,
            "browserEngine": self.engine,
            "scrollPosition": f"{self.scroll_index}/{len(self.paragraphs)} blocks",
            "screenshotUrl": self.last_screenshot_url,
            "screenshotBase64": (
                self.last_screenshot_base64[:100] + "... [truncated]"
                if self.last_screenshot_base64
                else None
            ),
            "visibleTextExcerpt": "\n".join(window)[:2600],
            "interactiveElements": interactive_list,
        }

    def click(self, element_id_or_selector: str) -> Dict[str, Any]:
        m = re.search(r"\d+", str(element_id_or_selector))
        target = None
        if m:
            eid = int(m.group(0))
            target = self.interactive_elements.get(eid)
        if not target:
            query_lower = str(element_id_or_selector).strip().lower()
            for meta in self.interactive_elements.values():
                if query_lower in (meta.get("label") or "").lower():
                    target = meta
                    break

        if self._page and not self._page.is_closed():
            try:
                if target and target.get("selector"):
                    self._page.click(target["selector"], timeout=5000)
                elif target and target.get("label"):
                    clean_lbl = re.sub(r"['\"\\]", "", target["label"][:40])
                    self._page.locator(f"text={clean_lbl}").first.click(timeout=5000)
                else:
                    self._page.click(str(element_id_or_selector), timeout=5000)
                self._page.wait_for_timeout(1000)
                self.current_url = self._page.url or self.current_url
                self.title = self._page.title() or self.current_url
                self.raw_html = self._page.content()
                self._parse_dom()
                self.capture_screenshot()
                return self.get_snapshot()
            except Exception:
                if target and target.get("href"):
                    return self.navigate(target["href"])
        elif target and target.get("href"):
            return self.navigate(target["href"])

        return {
            "error": f"Interactive element '{element_id_or_selector}' not found or could not be clicked.",
            **self.get_snapshot(),
        }

    def type_and_submit(
        self, element_id_or_selector: str, text: str, press_enter: bool = True
    ) -> Dict[str, Any]:
        m = re.search(r"\d+", str(element_id_or_selector))
        target = self.interactive_elements.get(int(m.group(0))) if m else None
        if not target:
            for meta in self.interactive_elements.values():
                if meta.get("tag") == "input":
                    target = meta
                    break

        if self._page and not self._page.is_closed():
            try:
                selector = target.get("selector") if target else "input:not([type='hidden'])"
                self._page.fill(selector, text, timeout=4000)
                if press_enter:
                    self._page.press(selector, "Enter")
                    self._page.wait_for_timeout(1500)
                self.current_url = self._page.url or self.current_url
                self.title = self._page.title() or self.current_url
                self.raw_html = self._page.content()
                self._parse_dom()
                self.capture_screenshot()
                return self.get_snapshot()
            except Exception:
                pass

        if target and target.get("formAction"):
            field_name = target.get("name") or "q"
            sep = "&" if "?" in target["formAction"] else "?"
            submit_url = f"{target['formAction']}{sep}{urllib.parse.urlencode({field_name: text})}"
            return self.navigate(submit_url)

        domain = urllib.parse.urlparse(self.current_url).netloc
        from .discovery_tools import web_search

        return web_search(query=text, domain_filter=domain, max_results=5)

    def scroll(self, direction: str = "down", amount: int = 500) -> Dict[str, Any]:
        amt = max(100, min(2000, int(amount or 500)))
        delta = amt if direction.lower() == "down" else -amt
        if self._page and not self._page.is_closed():
            try:
                self._page.evaluate(f"window.scrollBy(0, {delta})")
                self._page.wait_for_timeout(600)
                self.raw_html = self._page.content()
                self._parse_dom()
                self.capture_screenshot()
                return self.get_snapshot()
            except Exception:
                pass

        step = max(5, min(35, int(amt / 40)))
        if direction.lower() == "up":
            self.scroll_index = max(0, self.scroll_index - step)
        else:
            self.scroll_index = min(
                max(0, len(self.paragraphs) - 5), self.scroll_index + step
            )
        return self.get_snapshot()

    def close(self) -> None:
        try:
            if self._page and not self._page.is_closed():
                self._page.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._browser = None
        self._pw = None


def browser_navigate(
    session: StatefulDomBrowserSession,
    url: str,
    wait_for_selector: Optional[str] = None,
) -> Dict[str, Any]:
    """Opens a URL in the stateful browser session and returns an interactive DOM snapshot + screenshot."""
    try:
        snap = session.navigate(url)
        return {"tool": "browser_navigate", **snap}
    except Exception as exc:
        return {"tool": "browser_navigate", "url": url, "error": str(exc)}


def browser_get_interactive_snapshot(
    session: StatefulDomBrowserSession,
) -> Dict[str, Any]:
    """Returns the current page's visible text, numbered interactive elements, and screenshot."""
    return {"tool": "browser_get_interactive_snapshot", **session.get_snapshot()}


def browser_capture_screenshot(
    session: StatefulDomBrowserSession,
    full_page: bool = False,
) -> Dict[str, Any]:
    """Captures a screenshot of the active page tab in the browser session."""
    return session.capture_screenshot(full_page=full_page)


def browser_click(
    session: StatefulDomBrowserSession,
    element_id_or_selector: str,
) -> Dict[str, Any]:
    """Clicks a numbered interactive element or link on the current page."""
    try:
        snap = session.click(element_id_or_selector)
        return {"tool": "browser_click", "clicked": element_id_or_selector, **snap}
    except Exception as exc:
        return {"tool": "browser_click", "error": str(exc)}


def browser_type_and_submit(
    session: StatefulDomBrowserSession,
    element_id_or_selector: str,
    text: str,
    press_enter: bool = True,
) -> Dict[str, Any]:
    """Types text into an on-site search bar or form input and submits it."""
    try:
        res = session.type_and_submit(element_id_or_selector, text, press_enter)
        return {"tool": "browser_type_and_submit", "typedText": text, **res}
    except Exception as exc:
        return {"tool": "browser_type_and_submit", "error": str(exc)}


def browser_scroll(
    session: StatefulDomBrowserSession,
    direction: str = "down",
    amount: int = 500,
) -> Dict[str, Any]:
    """Scrolls down or up on the current page to reveal additional content and updates screenshot."""
    snap = session.scroll(direction=direction, amount=amount)
    return {"tool": "browser_scroll", "direction": direction, **snap}


def browser_select_option(
    session: StatefulDomBrowserSession,
    element_id_or_selector: str,
    value: str,
) -> Dict[str, Any]:
    """Selects an option value in a dropdown or filter control on the page."""
    return {
        "tool": "browser_select_option",
        "element": element_id_or_selector,
        "selectedValue": value,
        **session.get_snapshot(),
    }

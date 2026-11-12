"""
Site Monitoring & Surveillance Tools for Spider AI Autonomous Web Retrieval Agent.
Provides real-time uptime health diagnostics, SSL verification, content diffing & hash tracking,
RSS/Sitemap update discovery, DNS/security inspection, and automated site alert dispatch.
"""

import difflib
import hashlib
import json
import logging
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("spider_ai.site_monitoring")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 (SpiderAI-Monitor/2.0)"
)


def _normalize_target_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def monitor_site_health_and_uptime(url: str, timeout: int = 12) -> Dict[str, Any]:
    """
    Checks the real-time availability, latency, SSL certificate health, redirect chain,
    and security posture of a target website.
    """
    target_url = _normalize_target_url(url)
    if not target_url:
        return {"status": "error", "message": "Invalid or empty URL provided for site monitoring."}

    parsed = urlparse(target_url)
    hostname = parsed.hostname or target_url

    start_time = time.perf_counter()
    status_code = None
    ttfb_ms = None
    redirect_history = []
    headers_dict = {}
    is_up = False
    ssl_info: Dict[str, Any] = {"valid": False}
    error_msg = None

    # 1. SSL/TLS Inspection
    if parsed.scheme == "https":
        try:
            port = parsed.port or 443
            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=min(timeout, 6)) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    if cert:
                        not_after_str = cert.get("notAfter", "")
                        expire_dt = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                        now_dt = datetime.now(timezone.utc)
                        days_remaining = (expire_dt - now_dt).days
                        issuer = dict(x[0] for x in cert.get("issuer", ()))
                        ssl_info = {
                            "valid": True,
                            "expires": not_after_str,
                            "daysRemaining": days_remaining,
                            "isExpiringSoon": days_remaining < 30,
                            "issuer": issuer.get("organizationName") or issuer.get("commonName", "Unknown CA"),
                            "tlsVersion": ssock.version(),
                            "cipher": ssock.cipher()[0] if ssock.cipher() else "Unknown",
                        }
        except Exception as ssl_err:
            ssl_info = {
                "valid": False,
                "error": str(ssl_err),
                "isExpiringSoon": False,
            }

    # 2. HTTP Request & Latency Check
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"})
        resp = session.get(target_url, timeout=timeout, allow_redirects=True)
        ttfb_ms = round((time.perf_counter() - start_time) * 1000, 1)
        status_code = resp.status_code
        is_up = (200 <= status_code < 400)

        for hop in resp.history:
            redirect_history.append({
                "url": hop.url,
                "statusCode": hop.status_code,
                "redirectReason": hop.reason
            })

        # Security Headers Audit
        h = resp.headers
        headers_dict = {
            "server": h.get("Server", "Undisclosed"),
            "contentType": h.get("Content-Type", "Unknown"),
            "contentLength": h.get("Content-Length"),
            "hasHsts": "strict-transport-security" in h,
            "hasCsp": "content-security-policy" in h,
            "hasXFrameOptions": "x-frame-options" in h,
            "hasXContentTypeOptions": "x-content-type-options" in h,
            "cacheControl": h.get("Cache-Control", ""),
        }

        # Page Title extraction if HTML
        title = ""
        if "text/html" in headers_dict["contentType"].lower() and resp.text:
            soup = BeautifulSoup(resp.text[:20000], "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()

    except requests.exceptions.Timeout:
        error_msg = f"Request timed out after {timeout} seconds."
        is_up = False
        ttfb_ms = timeout * 1000
    except requests.exceptions.SSLError as e:
        error_msg = f"SSL Certificate Validation failed: {e}"
        is_up = False
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection refused or DNS resolution failed: {e}"
        is_up = False
    except Exception as exc:
        error_msg = f"Monitoring probe encountered error: {exc}"
        is_up = False

    # 3. Overall Health Verdict
    if is_up:
        if ttfb_ms and ttfb_ms > 3000:
            health_verdict = "DEGRADED"
            verdict_reason = f"Website is accessible but response latency is elevated ({ttfb_ms}ms)."
        elif ssl_info.get("isExpiringSoon"):
            health_verdict = "DEGRADED"
            verdict_reason = f"SSL certificate expires in {ssl_info.get('daysRemaining')} days."
        else:
            health_verdict = "HEALTHY"
            verdict_reason = f"Service responded with HTTP {status_code} in {ttfb_ms}ms."
    else:
        health_verdict = "DOWN" if not status_code or status_code >= 500 else "DEGRADED"
        verdict_reason = error_msg or f"HTTP status {status_code} returned."

    return {
        "tool": "monitor_site_health_and_uptime",
        "targetUrl": target_url,
        "hostname": hostname,
        "isUp": is_up,
        "statusCode": status_code,
        "latencyMs": ttfb_ms,
        "healthVerdict": health_verdict,
        "verdictReason": verdict_reason,
        "ssl": ssl_info,
        "redirectHops": redirect_history,
        "securityHeaders": headers_dict,
        "pageTitle": title if 'title' in locals() else "",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


def track_page_changes_and_diff(
    url: str,
    baseline_hash: Optional[str] = None,
    baseline_text: Optional[str] = None,
    keyword_filter: Optional[str] = None,
    timeout: int = 15,
) -> Dict[str, Any]:
    """
    Fetches the live text of a webpage, calculates cryptographic and structural content hashes,
    and computes unified semantic diffs against a previous baseline or detects keyword mutations.
    """
    target_url = _normalize_target_url(url)
    if not target_url:
        return {"status": "error", "message": "Invalid URL provided."}

    try:
        resp = requests.get(target_url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=timeout)
        if resp.status_code >= 400:
            return {
                "tool": "track_page_changes_and_diff",
                "targetUrl": target_url,
                "status": "error",
                "statusCode": resp.status_code,
                "message": f"Server returned error code {resp.status_code}",
            }

        soup = BeautifulSoup(resp.text, "html.parser")

        # Strip scripts, styles, and navigational chrome for clean semantic text
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)]

        # Extract readable body paragraphs
        body_lines = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "li", "tr"]) if len(p.get_text(strip=True)) > 15]
        normalized_content = "\n".join(body_lines)
        if not normalized_content:
            normalized_content = soup.get_text("\n", strip=True)

        content_hash = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
        short_hash = content_hash[:16]

        # Price / Numerical pattern extraction (useful for e-commerce, tickets, and financial pages)
        currency_numbers = re.findall(r"(?:KSh|Ksh|USD|\$|EUR|€|£|GBP)\s*[\d,]+(?:\.\d+)?", normalized_content)
        detected_prices = list(dict.fromkeys(currency_numbers))[:12]

        has_changed = False
        change_percentage = 0.0
        diff_summary = []
        severity = "NONE"

        if baseline_hash and baseline_hash != content_hash:
            has_changed = True
            severity = "MINOR"

        if baseline_text:
            base_lines = baseline_text.splitlines()
            curr_lines = normalized_content.splitlines()
            matcher = difflib.SequenceMatcher(None, base_lines, curr_lines)
            similarity = matcher.ratio()
            change_percentage = round((1.0 - similarity) * 100, 2)
            has_changed = change_percentage > 0.5

            diff = list(difflib.unified_diff(base_lines[:150], curr_lines[:150], lineterm="", n=1))
            added = [line[1:].strip() for line in diff if line.startswith("+") and not line.startswith("+++")]
            removed = [line[1:].strip() for line in diff if line.startswith("-") and not line.startswith("---")]

            diff_summary = {
                "linesAddedCount": len(added),
                "linesRemovedCount": len(removed),
                "sampleAdditions": added[:5],
                "sampleRemovals": removed[:5],
            }

            if change_percentage > 25.0:
                severity = "SIGNIFICANT"
            elif change_percentage > 60.0:
                severity = "CRITICAL"
            elif has_changed:
                severity = "MINOR"

        # Keyword Presence Analysis
        keyword_result = None
        if keyword_filter:
            kw = keyword_filter.strip().lower()
            matches = [line for line in body_lines if kw in line.lower()]
            keyword_result = {
                "keyword": keyword_filter,
                "found": len(matches) > 0,
                "matchCount": len(matches),
                "snippets": matches[:4],
            }

        return {
            "tool": "track_page_changes_and_diff",
            "targetUrl": target_url,
            "title": title,
            "headingsCount": len(headings),
            "topHeadings": headings[:6],
            "contentHash": content_hash,
            "shortHash": short_hash,
            "hasChanged": has_changed,
            "changePercentage": change_percentage,
            "changeSeverity": severity,
            "detectedPrices": detected_prices,
            "diffSummary": diff_summary,
            "keywordAudit": keyword_result,
            "checkedAt": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.warning(f"Error diffing {target_url}: {exc}")
        return {
            "tool": "track_page_changes_and_diff",
            "targetUrl": target_url,
            "status": "error",
            "message": str(exc),
        }


def monitor_feed_and_sitemap_updates(url: str, max_items: int = 10, timeout: int = 12) -> Dict[str, Any]:
    """
    Discovers, checks, and extracts live updates from RSS feeds, Atom feeds, or XML sitemaps
    associated with a website.
    """
    target_url = _normalize_target_url(url)
    parsed = urlparse(target_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"

    candidate_urls = [target_url]
    if not any(target_url.endswith(ext) for ext in [".xml", "/feed", "/rss", "/feed/"]):
        candidate_urls.extend([
            urljoin(base_domain, "/sitemap.xml"),
            urljoin(base_domain, "/feed"),
            urljoin(base_domain, "/rss.xml"),
            urljoin(base_domain, "/atom.xml"),
        ])

    feed_type = None
    items = []
    resolved_feed_url = None

    for candidate in candidate_urls:
        try:
            resp = requests.get(candidate, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=timeout)
            if resp.status_code != 200:
                continue

            content = resp.text.strip()
            # 1. XML Sitemap Parsing
            if "<urlset" in content or "<sitemapindex" in content:
                feed_type = "sitemap"
                resolved_feed_url = candidate
                root = ET.fromstring(content)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                for url_node in root.findall(".//sm:url", ns) or root.findall(".//url"):
                    loc = url_node.find("sm:loc", ns) or url_node.find("loc")
                    lastmod = url_node.find("sm:lastmod", ns) or url_node.find("lastmod")
                    if loc is not None and loc.text:
                        items.append({
                            "url": loc.text.strip(),
                            "lastModified": lastmod.text.strip() if lastmod is not None and lastmod.text else "Unspecified",
                        })
                break

            # 2. RSS 2.0 Feed Parsing
            elif "<rss" in content:
                feed_type = "rss"
                resolved_feed_url = candidate
                root = ET.fromstring(content)
                for item_node in root.findall(".//item"):
                    title = item_node.find("title")
                    link = item_node.find("link")
                    pub_date = item_node.find("pubDate")
                    desc = item_node.find("description")
                    if title is not None and title.text:
                        items.append({
                            "title": title.text.strip(),
                            "link": link.text.strip() if link is not None and link.text else "",
                            "publishedAt": pub_date.text.strip() if pub_date is not None and pub_date.text else "",
                            "snippet": (desc.text[:180] + "...") if desc is not None and desc.text else "",
                        })
                break

            # 3. Atom Feed Parsing
            elif "<feed" in content and "xmlns" in content:
                feed_type = "atom"
                resolved_feed_url = candidate
                root = ET.fromstring(content)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall(".//atom:entry", ns) or root.findall(".//entry"):
                    title = entry.find("atom:title", ns) or entry.find("title")
                    link = entry.find("atom:link", ns) or entry.find("link")
                    updated = entry.find("atom:updated", ns) or entry.find("updated")
                    href = link.attrib.get("href") if link is not None else ""
                    if title is not None and title.text:
                        items.append({
                            "title": title.text.strip(),
                            "link": href,
                            "publishedAt": updated.text.strip() if updated is not None and updated.text else "",
                        })
                break

        except Exception as e:
            continue

    return {
        "tool": "monitor_feed_and_sitemap_updates",
        "targetUrl": target_url,
        "resolvedFeedUrl": resolved_feed_url,
        "feedType": feed_type or "none_detected",
        "hasLiveFeed": bool(feed_type and items),
        "totalItemsFound": len(items),
        "latestUpdates": items[:max_items],
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


def monitor_domain_dns_and_security(domain_or_url: str) -> Dict[str, Any]:
    """
    Analyzes DNS resolution, CDN distribution, IP routing, and security posture for a domain.
    """
    clean_url = _normalize_target_url(domain_or_url)
    hostname = urlparse(clean_url).hostname or domain_or_url.replace("http://", "").replace("https://", "").split("/")[0]

    dns_records = {"A": [], "AAAA": [], "CNAME": [], "MX": []}
    cdn_provider = "Direct Origin / None"

    try:
        # A records (IPv4)
        addr_info = socket.getaddrinfo(hostname, 80, proto=socket.IPPROTO_TCP)
        ipv4s = list(dict.fromkeys([x[4][0] for x in addr_info if "." in x[4][0]]))
        ipv6s = list(dict.fromkeys([x[4][0] for x in addr_info if ":" in x[4][0]]))
        dns_records["A"] = ipv4s
        dns_records["AAAA"] = ipv6s

        # Cloudflare / CDN heuristics based on IP ranges and reverse lookup
        for ip in ipv4s:
            if ip.startswith(("104.", "172.64.", "172.67.", "108.162.", "198.41.")):
                cdn_provider = "Cloudflare Global Anycast Edge"
                break
            elif ip.startswith(("151.101.", "199.232.")):
                cdn_provider = "Fastly Edge CDN"
                break
            elif ip.startswith(("13.224.", "13.225.", "13.32.", "13.33.", "13.35.")):
                cdn_provider = "Amazon CloudFront"
                break
            elif ip.startswith(("76.76.21.")):
                cdn_provider = "Vercel Edge Network"
                break

    except Exception as exc:
        return {
            "tool": "monitor_domain_dns_and_security",
            "hostname": hostname,
            "status": "error",
            "message": f"DNS resolution failed: {exc}",
        }

    return {
        "tool": "monitor_domain_dns_and_security",
        "hostname": hostname,
        "cdnProvider": cdn_provider,
        "dnsRecords": dns_records,
        "isDualStack": bool(dns_records["A"] and dns_records["AAAA"]),
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


def create_site_watch_target(
    url: str,
    label: Optional[str] = None,
    watch_type: str = "health_and_content",
    keyword: Optional[str] = None,
    session_id: Optional[str] = None,
    user: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Registers a target website into the database for active surveillance and monitoring.
    Immediately conducts a baseline probe and dispatches an initialization alert.
    """
    from core.models import SiteWatchTarget, SiteNotificationAlert

    clean_url = _normalize_target_url(url)
    if not clean_url:
        return {"status": "error", "message": "Invalid URL provided."}

    # Execute immediate baseline health probe
    probe = monitor_site_health_and_uptime(clean_url)
    diff_probe = track_page_changes_and_diff(clean_url, keyword_filter=keyword)

    display_label = label or diff_probe.get("title") or urlparse(clean_url).hostname or clean_url

    target, created = SiteWatchTarget.objects.get_or_create(
        url=clean_url,
        session_id=session_id or "default_session",
        defaults={
            "user": user if (user and user.is_authenticated) else None,
            "label": display_label,
            "watch_type": watch_type,
            "keyword": keyword or "",
            "last_status_code": probe.get("statusCode"),
            "last_latency_ms": probe.get("latencyMs"),
            "last_content_hash": diff_probe.get("contentHash", ""),
            "last_title": diff_probe.get("title", ""),
            "last_checked_at": datetime.now(timezone.utc),
            "metadata": {
                "initialProbe": probe,
                "detectedPrices": diff_probe.get("detectedPrices", []),
            },
        },
    )

    if not created:
        target.label = display_label
        target.last_status_code = probe.get("statusCode")
        target.last_latency_ms = probe.get("latencyMs")
        target.last_content_hash = diff_probe.get("contentHash", "")
        target.last_title = diff_probe.get("title", "")
        target.last_checked_at = datetime.now(timezone.utc)
        target.is_active = True
        target.save()

    # Create Initial Notification Alert for the Navbar Bell!
    alert = SiteNotificationAlert.objects.create(
        user=user if (user and user.is_authenticated) else None,
        session_id=session_id or "default_session",
        target=target,
        title=f"Monitoring Activated: {display_label}",
        message=f"Live monitor online for {clean_url}. Initial status: HTTP {probe.get('statusCode')} ({probe.get('latencyMs')}ms) • Health: {probe.get('healthVerdict')}.",
        alert_level="success" if probe.get("isUp") else "warning",
        url=clean_url,
        details={
            "statusCode": probe.get("statusCode"),
            "latencyMs": probe.get("latencyMs"),
            "healthVerdict": probe.get("healthVerdict"),
            "contentHash": diff_probe.get("shortHash"),
        },
    )

    return {
        "tool": "create_site_watch_target",
        "targetId": target.id,
        "url": target.url,
        "label": target.label,
        "watchType": target.watch_type,
        "status": "active",
        "initialProbe": {
            "statusCode": probe.get("statusCode"),
            "latencyMs": probe.get("latencyMs"),
            "healthVerdict": probe.get("healthVerdict"),
        },
        "notificationAlert": {
            "id": alert.id,
            "title": alert.title,
            "alertLevel": alert.alert_level,
        },
    }


def poll_active_site_monitors(
    session_id: Optional[str] = None,
    user: Optional[Any] = None,
    force_check: bool = False,
) -> Dict[str, Any]:
    """
    Polls all registered site watch targets, checks for downtime, high latency, or content changes,
    and emits real-time alerts into the user's notification bell drawer.
    """
    from core.models import SiteWatchTarget, SiteNotificationAlert

    qs = SiteWatchTarget.objects.filter(is_active=True)
    if user and user.is_authenticated:
        qs = qs.filter(user=user)
    elif session_id:
        qs = qs.filter(session_id=session_id)

    targets = list(qs[:25])
    checked_count = 0
    new_alerts = []

    for target in targets:
        checked_count += 1
        probe = monitor_site_health_and_uptime(target.url)
        diff = track_page_changes_and_diff(
            target.url,
            baseline_hash=target.last_content_hash,
            keyword_filter=target.keyword,
        )

        previous_status = target.last_status_code
        current_status = probe.get("statusCode")
        target.last_status_code = current_status
        target.last_latency_ms = probe.get("latencyMs")
        target.last_checked_at = datetime.now(timezone.utc)

        # Trigger 1: Downtime or Failure Alert
        if not probe.get("isUp") and (previous_status is None or previous_status < 400):
            alert = SiteNotificationAlert.objects.create(
                user=target.user,
                session_id=target.session_id,
                target=target,
                title=f"Site Down: {target.label}",
                message=f"Target {target.url} is unresponsive or returned HTTP {current_status}. Failure reason: {probe.get('verdictReason')}",
                alert_level="critical",
                url=target.url,
                details=probe,
            )
            new_alerts.append({"id": alert.id, "title": alert.title, "level": alert.alert_level})

        # Trigger 2: Recovery Alert
        elif probe.get("isUp") and previous_status and previous_status >= 400:
            alert = SiteNotificationAlert.objects.create(
                user=target.user,
                session_id=target.session_id,
                target=target,
                title=f"Site Recovered: {target.label}",
                message=f"Target {target.url} is back online with HTTP {current_status} ({probe.get('latencyMs')}ms).",
                alert_level="success",
                url=target.url,
                details=probe,
            )
            new_alerts.append({"id": alert.id, "title": alert.title, "level": alert.alert_level})

        # Trigger 3: Significant Content Change Alert
        if diff.get("hasChanged") and diff.get("changeSeverity") in ("SIGNIFICANT", "CRITICAL"):
            alert = SiteNotificationAlert.objects.create(
                user=target.user,
                session_id=target.session_id,
                target=target,
                title=f"Content Updated: {target.label}",
                message=f"Detected significant content mutation on {target.url} (severity: {diff.get('changeSeverity')}, change: ~{diff.get('changePercentage')}%).",
                alert_level="warning",
                url=target.url,
                details=diff,
            )
            new_alerts.append({"id": alert.id, "title": alert.title, "level": alert.alert_level})

        target.last_content_hash = diff.get("contentHash", target.last_content_hash)
        target.save()

    return {
        "tool": "poll_active_site_monitors",
        "targetsChecked": checked_count,
        "newAlertsGenerated": len(new_alerts),
        "alerts": new_alerts,
        "polledAt": datetime.now(timezone.utc).isoformat(),
    }


def list_site_notification_alerts(
    session_id: Optional[str] = None,
    user: Optional[Any] = None,
    unread_only: bool = False,
) -> Dict[str, Any]:
    """
    Retrieves notification alerts generated by site monitors for display in the notification bell drawer.
    """
    from core.models import SiteNotificationAlert

    qs = SiteNotificationAlert.objects.all()
    if user and user.is_authenticated:
        qs = qs.filter(user=user)
    elif session_id:
        qs = qs.filter(session_id=session_id)
    else:
        qs = qs.none()

    if unread_only:
        qs = qs.filter(is_read=False)

    alerts_list = [
        {
            "id": a.id,
            "title": a.title,
            "message": a.message,
            "alertLevel": a.alert_level,
            "url": a.url,
            "isRead": a.is_read,
            "createdAt": a.created_at.isoformat(),
            "targetLabel": a.target.label if a.target else "",
        }
        for a in qs[:30]
    ]

    unread_count = qs.filter(is_read=False).count()

    return {
        "tool": "list_site_notification_alerts",
        "unreadCount": unread_count,
        "totalAlerts": len(alerts_list),
        "alerts": alerts_list,
    }


def mark_notifications_as_read(
    alert_ids: Optional[List[int]] = None,
    session_id: Optional[str] = None,
    user: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Marks one or all notification alerts as read.
    """
    from core.models import SiteNotificationAlert

    qs = SiteNotificationAlert.objects.all()
    if user and user.is_authenticated:
        qs = qs.filter(user=user)
    elif session_id:
        qs = qs.filter(session_id=session_id)

    if alert_ids:
        updated = qs.filter(id__in=alert_ids).update(is_read=True)
    else:
        updated = qs.update(is_read=True)

    return {"status": "ok", "markedReadCount": updated}

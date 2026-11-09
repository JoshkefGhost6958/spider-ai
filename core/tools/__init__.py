from typing import Any, Dict, List
from .browser_tools import (
    StatefulDomBrowserSession,
    browser_capture_screenshot,
    browser_click,
    browser_get_interactive_snapshot,
    browser_navigate,
    browser_scroll,
    browser_select_option,
    browser_type_and_submit,
)
from .discovery_tools import (
    academic_and_reference_search,
    multi_related_site_search_and_crawl,
    news_search,
    pdf_search_and_summarize,
    site_map_and_subpath_discovery,
    social_and_platform_search,
    web_search,
)
from .extraction_tools import (
    extract_page_links,
    extract_structured_metadata,
    extract_tables_from_page,
    fetch_page_markdown,
    parse_document_file,
    query_page_content,
)
from .verification_tools import (
    check_requirements_coverage,
    cross_verify_claim,
    evaluate_expression_or_convert,
    extract_schema_from_page,
)
from .video_tools import (
    extract_video_info,
    video_search,
)
from .image_tools import (
    extract_images_from_page,
    image_search,
)
from .screenshot_tools import (
    capture_page_screenshot,
    compare_website_designs,
)

# Gemini Function Calling Tool Declarations (REST API format)
GEMINI_FUNCTION_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "web_search",
        "description": "Executes a general web search with optional recency filter ('d','w','m','y'), domain restriction (site:), and exclusions.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search query string."},
                "time_range": {"type": "STRING", "description": "Optional recency: 'd', 'w', 'm', or 'y'."},
                "domain_filter": {"type": "STRING", "description": "Optional domain to restrict search to (e.g. 'sec.gov' or 'amd.com')."},
                "max_results": {"type": "INTEGER", "description": "Max results (1-10)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "news_search",
        "description": "Searches live news feeds and Google News RSS for breaking events, trending topics, and recent announcements. Use ONLY when the user inquiry specifically seeks current events, breaking news, recent updates, legal proceedings, or political/economic developments. Do NOT use for tutorials, recipes, guides, how-to instructions, scientific concepts, or general knowledge.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "News search query focused on breaking events or recent developments."},
                "recency": {"type": "STRING", "description": "Recency window: 'd', 'w', or 'm'."},
                "max_results": {"type": "INTEGER", "description": "Max news items (1-10)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "academic_and_reference_search",
        "description": "Searches Wikipedia and ArXiv for encyclopedic facts, technical architectures, and scientific research papers.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Reference or academic query."},
                "source_type": {"type": "STRING", "description": "'all', 'wikipedia', or 'arxiv'."},
                "max_results": {"type": "INTEGER", "description": "Max results (1-8)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "site_map_and_subpath_discovery",
        "description": "Inspects a domain's navigation links and sitemap.xml to discover deep subpaths (e.g., /pricing, /docs, /specs).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "domain_or_url": {"type": "STRING", "description": "Target domain or URL."},
                "keyword_filter": {"type": "STRING", "description": "Optional keyword to filter subpaths."},
            },
            "required": ["domain_or_url"],
        },
    },
    {
        "name": "fetch_page_markdown",
        "description": "Fetches a URL and converts its main readable content and tables into clean Markdown using trafilatura.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Full http/https URL to fetch."},
                "include_tables": {"type": "BOOLEAN", "description": "Whether to include HTML tables."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "extract_page_links",
        "description": "Extracts all internal and external links on a page with anchor text and link type ('navigation', 'pagination', 'document', 'article').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Page URL."},
                "filter_keyword": {"type": "STRING", "description": "Optional keyword filter for anchor text or URL."},
                "link_type": {"type": "STRING", "description": "'all', 'navigation', 'pagination', 'document', or 'article'."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "extract_tables_from_page",
        "description": "Extracts HTML <table> comparison matrices and data tables from a web page into structured Markdown tables.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Page URL containing tables."},
                "table_keyword": {"type": "STRING", "description": "Optional keyword to filter specific tables."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "query_page_content",
        "description": "Searches within a web page for specific keywords, numbers, or regex patterns (like Ctrl+F with surrounding paragraph context).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Page URL to search inside."},
                "search_query_or_regex": {"type": "STRING", "description": "Keyword, phrase, or regex pattern to locate."},
            },
            "required": ["url", "search_query_or_regex"],
        },
    },
    {
        "name": "parse_document_file",
        "description": "Downloads and extracts text from online PDF documents, datasheets, CSV, JSON, or XML files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "URL of the PDF or document file."},
                "target_keywords": {"type": "STRING", "description": "Optional keyword to filter relevant pages."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "extract_structured_metadata",
        "description": "Extracts embedded JSON-LD, Schema.org, OpenGraph tags, publish date, and author metadata from a URL.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Target page URL."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_navigate",
        "description": "Opens a URL in the stateful browser session and returns an interactive DOM snapshot with numbered clickable/typeable elements.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "URL to open in the browser session."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_get_interactive_snapshot",
        "description": "Returns the current browser page's visible text and numbered interactive elements ([1], [2], ...).",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "browser_capture_screenshot",
        "description": "Captures a high-resolution screenshot of the current page tab in the active browser session. Returns screenshot image URL and base64 preview.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "full_page": {"type": "BOOLEAN", "description": "Whether to capture the entire scrollable page (default false)."},
            },
        },
    },
    {
        "name": "browser_click",
        "description": "Clicks a numbered interactive element (e.g. '3') or link label on the current browser page to navigate deeper.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "element_id_or_selector": {"type": "STRING", "description": "Interactive element number (e.g. '3') or link text."},
            },
            "required": ["element_id_or_selector"],
        },
    },
    {
        "name": "browser_type_and_submit",
        "description": "Types text into an on-site search input or form field on the current browser page and submits it.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "element_id_or_selector": {"type": "STRING", "description": "Input element number or field name."},
                "text": {"type": "STRING", "description": "Text to type and submit."},
            },
            "required": ["element_id_or_selector", "text"],
        },
    },
    {
        "name": "browser_scroll",
        "description": "Scrolls 'down' or 'up' on the current browser page to inspect more content blocks.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "direction": {"type": "STRING", "description": "'down' or 'up'."},
                "amount": {"type": "INTEGER", "description": "Number of content blocks to scroll (default 15)."},
            },
        },
    },
    {
        "name": "browser_select_option",
        "description": "Selects an option value in a dropdown control on the current browser page.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "element_id_or_selector": {"type": "STRING", "description": "Dropdown element ID or selector."},
                "value": {"type": "STRING", "description": "Option value to select."},
            },
            "required": ["element_id_or_selector", "value"],
        },
    },
    {
        "name": "extract_schema_from_page",
        "description": "Runs a targeted extraction pass on a URL to pull specific requested attribute names with verbatim evidence.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Target page URL."},
                "target_attributes_list": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "List of attribute names to extract.",
                },
            },
            "required": ["url", "target_attributes_list"],
        },
    },
    {
        "name": "cross_verify_claim",
        "description": "Searches across multiple independent domains to fact-check and corroborate a specific claim or statistic.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "claim": {"type": "STRING", "description": "Specific claim or fact to verify."},
                "independent_domains_required": {"type": "INTEGER", "description": "Minimum independent domains required (default 2)."},
            },
            "required": ["claim"],
        },
    },
    {
        "name": "evaluate_expression_or_convert",
        "description": "Deterministic mathematical calculator for percentages, growth rates, ratios, and unit conversions.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {"type": "STRING", "description": "Mathematical expression e.g. '(325 - 192) / 192 * 100'."},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "check_requirements_coverage",
        "description": "Self-check tool verifying whether all requested attributes from the user's intent have been gathered.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "collected_facts_summary": {"type": "STRING", "description": "Summary of facts gathered so far."},
                "required_attributes": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "List of required attributes to check against.",
                },
            },
            "required": ["collected_facts_summary", "required_attributes"],
        },
    },
    {
        "name": "video_search",
        "description": "Searches YouTube and web video indices for relevant video links, returning video URLs, titles, channels, durations, and descriptions.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Video search query."},
                "max_results": {"type": "INTEGER", "description": "Max video results (1-8)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "extract_video_info",
        "description": "Extracts comprehensive information from a video link (YouTube or web video): metadata, chapters, timestamped transcript/captions ([MM:SS]), keyword-filtered segments, and AI-synthesized video summary.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "video_url": {"type": "STRING", "description": "Full YouTube or video URL to inspect."},
                "focus_query": {"type": "STRING", "description": "Optional specific question or topic to extract from the video."},
                "include_timestamps": {"type": "BOOLEAN", "description": "Whether to include [MM:SS] timestamps in extracted transcript blocks."},
            },
            "required": ["video_url"],
        },
    },
    {
        "name": "image_search",
        "description": "Searches for relevant high-resolution web images and news photography matching the query.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Image search query."},
                "max_results": {"type": "INTEGER", "description": "Max images to retrieve (1-8)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "extract_images_from_page",
        "description": "Extracts relevant article imagery (OpenGraph og:image, figure images with captions, and content images) from a web page URL.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Target web page URL."},
                "filter_keyword": {"type": "STRING", "description": "Optional keyword filter for image alt/caption."},
                "max_images": {"type": "INTEGER", "description": "Max images to extract (1-8)."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "social_and_platform_search",
        "description": "Searches social and community platforms (TikTok, Facebook, X/Twitter, Reddit, Instagram) for viral clips, eyewitness posts, and public discourse.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Specific, non-vague search query."},
                "platforms": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Optional list of platforms: 'tiktok', 'facebook', 'x', 'reddit', 'instagram'.",
                },
                "max_results": {"type": "INTEGER", "description": "Max social results (1-12)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "pdf_search_and_summarize",
        "description": "Searches for PDF documents, official reports, and papers matching the query, extracts their text, summarizes key findings, and depicts whether the information is of HIGH, MODERATE, or LOW value.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Specific PDF search query."},
                "max_results": {"type": "INTEGER", "description": "Max PDFs to parse and summarize (1-4)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "multi_related_site_search_and_crawl",
        "description": "Finds and crawls multiple related websites in relation to the topic by fanning out across institutional, investigative, and corroborating search vectors AND following outbound relational links across domains.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Sharp core investigation query."},
                "seed_urls": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Optional seed URLs to crawl outbound related links from.",
                },
                "max_related_sites": {"type": "INTEGER", "description": "Max related sites to crawl (3-15)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "capture_page_screenshot",
        "description": "Captures a high-resolution viewport or full-page screenshot of any webpage or domain with universal cross-browser/CDN fallback. Returns image URL/data URI, dimensions, and visual metadata.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Webpage URL or domain to capture."},
                "viewport_width": {"type": "INTEGER", "description": "Viewport width in pixels (default: 1440)."},
                "viewport_height": {"type": "INTEGER", "description": "Viewport height in pixels (default: 900)."},
                "full_page": {"type": "BOOLEAN", "description": "Whether to capture the entire scrollable page."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "compare_website_designs",
        "description": "Compares landing pages and UI/UX design across multiple websites or competitors (e.g. top fintech companies, SaaS). Captures high-res screenshots in parallel, extracts design primitives (Hero, CTA, themes), scores UI/UX heuristics, and synthesizes an authoritative design conclusion.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "urls_or_domains": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "List of 2 to 6 website URLs or domain names to compare.",
                },
                "industry_category": {
                    "type": "STRING",
                    "description": "Optional domain or industry category (e.g. 'Fintech', 'Developer Tools', 'E-commerce').",
                },
            },
            "required": ["urls_or_domains"],
        },
    },
]


def execute_agent_tool(
    tool_name: str,
    args: Dict[str, Any],
    browser_session: StatefulDomBrowserSession,
) -> Dict[str, Any]:
    """Dispatches a Gemini function call to the corresponding tool implementation."""
    args = args or {}
    if tool_name == "web_search":
        return web_search(
            query=args.get("query", ""),
            time_range=args.get("time_range"),
            domain_filter=args.get("domain_filter"),
            max_results=args.get("max_results", 6),
        )
    if tool_name == "news_search":
        return news_search(
            query=args.get("query", ""),
            recency=args.get("recency", "w"),
            max_results=args.get("max_results", 6),
        )
    if tool_name == "academic_and_reference_search":
        return academic_and_reference_search(
            query=args.get("query", ""),
            source_type=args.get("source_type", "all"),
            max_results=args.get("max_results", 5),
        )
    if tool_name == "site_map_and_subpath_discovery":
        return site_map_and_subpath_discovery(
            domain_or_url=args.get("domain_or_url", ""),
            keyword_filter=args.get("keyword_filter"),
        )
    if tool_name == "fetch_page_markdown":
        return fetch_page_markdown(
            url=args.get("url", ""),
            include_tables=args.get("include_tables", True),
        )
    if tool_name == "extract_page_links":
        return extract_page_links(
            url=args.get("url", ""),
            filter_keyword=args.get("filter_keyword"),
            link_type=args.get("link_type", "all"),
        )
    if tool_name == "extract_tables_from_page":
        return extract_tables_from_page(
            url=args.get("url", ""),
            table_keyword=args.get("table_keyword"),
        )
    if tool_name == "query_page_content":
        return query_page_content(
            url=args.get("url", ""),
            search_query_or_regex=args.get("search_query_or_regex", ""),
        )
    if tool_name == "parse_document_file":
        return parse_document_file(
            url=args.get("url", ""),
            target_keywords=args.get("target_keywords"),
        )
    if tool_name == "extract_structured_metadata":
        return extract_structured_metadata(url=args.get("url", ""))
    if tool_name == "browser_navigate":
        return browser_navigate(browser_session, url=args.get("url", ""))
    if tool_name == "browser_get_interactive_snapshot":
        return browser_get_interactive_snapshot(browser_session)
    if tool_name == "browser_capture_screenshot":
        return browser_capture_screenshot(browser_session, full_page=args.get("full_page", False))
    if tool_name == "browser_click":
        return browser_click(
            browser_session,
            element_id_or_selector=args.get("element_id_or_selector", ""),
        )
    if tool_name == "browser_type_and_submit":
        return browser_type_and_submit(
            browser_session,
            element_id_or_selector=args.get("element_id_or_selector", ""),
            text=args.get("text", ""),
        )
    if tool_name == "browser_scroll":
        return browser_scroll(
            browser_session,
            direction=args.get("direction", "down"),
            amount=args.get("amount", 15),
        )
    if tool_name == "browser_select_option":
        if not args.get("user_permission_granted", False):
            return {
                "tool": "browser_select_option",
                "status": "permission_required",
                "requiresUserPermission": True,
                "action": f"Select '{args.get('value')}' in '{args.get('element_id_or_selector')}'",
                "message": f"User permission requested before browser DOM manipulation: Select '{args.get('value')}'.",
            }
        return browser_select_option(
            browser_session,
            element_id_or_selector=args.get("element_id_or_selector", ""),
            value=args.get("value", ""),
        )
    if tool_name == "extract_schema_from_page":
        return extract_schema_from_page(
            url=args.get("url", ""),
            target_attributes_list=args.get("target_attributes_list") or [],
        )
    if tool_name == "cross_verify_claim":
        return cross_verify_claim(
            claim=args.get("claim", ""),
            independent_domains_required=args.get("independent_domains_required", 2),
        )
    if tool_name == "evaluate_expression_or_convert":
        return evaluate_expression_or_convert(expression=args.get("expression", ""))
    if tool_name == "check_requirements_coverage":
        return check_requirements_coverage(
            collected_facts_summary=args.get("collected_facts_summary", ""),
            required_attributes=args.get("required_attributes") or [],
        )
    if tool_name == "video_search":
        return video_search(
            query=args.get("query", ""),
            max_results=args.get("max_results", 5),
        )
    if tool_name == "extract_video_info":
        return extract_video_info(
            video_url=args.get("video_url", ""),
            focus_query=args.get("focus_query"),
            include_timestamps=args.get("include_timestamps", True),
        )
    if tool_name == "image_search":
        return image_search(
            query=args.get("query", ""),
            max_results=args.get("max_results", 6),
        )
    if tool_name == "extract_images_from_page":
        return extract_images_from_page(
            url=args.get("url", ""),
            filter_keyword=args.get("filter_keyword"),
            max_images=args.get("max_images", 6),
        )
    if tool_name == "social_and_platform_search":
        return social_and_platform_search(
            query=args.get("query", ""),
            platforms=args.get("platforms"),
            max_results=args.get("max_results", 10),
        )
    if tool_name == "pdf_search_and_summarize":
        return pdf_search_and_summarize(
            query=args.get("query", ""),
            max_results=args.get("max_results", 3),
        )
    if tool_name == "multi_related_site_search_and_crawl":
        return multi_related_site_search_and_crawl(
            query=args.get("query", ""),
            seed_urls=args.get("seed_urls"),
            max_related_sites=args.get("max_related_sites", 8),
        )
    if tool_name == "capture_page_screenshot":
        return capture_page_screenshot(
            url=args.get("url", ""),
            viewport_width=args.get("viewport_width", 1440),
            viewport_height=args.get("viewport_height", 900),
            full_page=args.get("full_page", False),
        )
    if tool_name == "compare_website_designs":
        return compare_website_designs(
            urls_or_domains=args.get("urls_or_domains") or [],
            industry_category=args.get("industry_category"),
        )

    return {"error": f"Unknown tool: {tool_name}"}

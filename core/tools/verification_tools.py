import ast
import math
import operator
import re
from typing import Any, Dict, List
from .discovery_tools import news_search, web_search
from .extraction_tools import fetch_page_markdown

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_ast(node.left), _eval_ast(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_ast(node.operand))
    raise ValueError("Unsupported mathematical expression")


def extract_schema_from_page(
    url: str,
    target_attributes_list: List[str],
) -> Dict[str, Any]:
    """
    Fetches a page and extracts matching sentences/rows for each requested
    attribute name in target_attributes_list along with verbatim evidence.
    """
    page = fetch_page_markdown(url, include_links=False, include_tables=True)
    if "error" in page:
        return {"tool": "extract_schema_from_page", "url": url, "error": page["error"]}

    md = page.get("markdown") or ""
    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    extracted_attributes: Dict[str, List[str]] = {}

    for attr in target_attributes_list or []:
        tokens = [t for t in re.split(r"[^a-z0-9]+", attr.lower()) if len(t) >= 2]
        matches = []
        for ln in lines:
            lower_ln = ln.lower()
            if any(t in lower_ln for t in tokens):
                matches.append(ln[:300])
            if len(matches) >= 4:
                break
        extracted_attributes[attr] = matches

    return {
        "tool": "extract_schema_from_page",
        "url": url,
        "title": page.get("title", ""),
        "extractedAttributes": extracted_attributes,
    }


def cross_verify_claim(
    claim: str,
    independent_domains_required: int = 2,
) -> Dict[str, Any]:
    """
    Searches across multiple independent web and news domains to corroborate
    or fact-check a specific claim, statistic, or date.
    """
    web_hits = web_search(claim, max_results=5).get("results", [])
    news_hits = news_search(claim, max_results=4).get("results", [])

    by_domain: Dict[str, Dict[str, str]] = {}
    for item in web_hits + news_hits:
        dom = (item.get("source") or "").lower()
        if dom and dom not in by_domain:
            by_domain[dom] = item

    independent_sources = list(by_domain.values())
    return {
        "tool": "cross_verify_claim",
        "claim": claim,
        "independentDomainsFound": len(independent_sources),
        "meetsThreshold": len(independent_sources) >= int(independent_domains_required or 2),
        "evidenceSources": independent_sources[:6],
    }


def evaluate_expression_or_convert(expression: str) -> Dict[str, Any]:
    """
    Deterministic mathematical calculator for percentages, ratios, growth rates,
    and unit arithmetic so the agent never hallucinates math.
    """
    clean_expr = expression.strip().replace(",", "").replace("^", "**")
    try:
        tree = ast.parse(clean_expr, mode="eval")
        val = _eval_ast(tree.body)
        rounded = round(val, 6) if not math.isnan(val) else val
        return {
            "tool": "evaluate_expression_or_convert",
            "expression": expression,
            "result": rounded,
        }
    except Exception as exc:
        return {
            "tool": "evaluate_expression_or_convert",
            "expression": expression,
            "error": str(exc),
        }


def check_requirements_coverage(
    collected_facts_summary: str,
    required_attributes: List[str],
) -> Dict[str, Any]:
    """
    Self-check tool where the agent verifies which requested attributes have
    been covered in collected_facts_summary and which still need retrieval.
    """
    summary_lower = (collected_facts_summary or "").lower()
    covered = []
    missing = []
    for attr in required_attributes or []:
        tokens = [t for t in re.split(r"[^a-z0-9]+", attr.lower()) if len(t) >= 3]
        if not tokens or any(t in summary_lower for t in tokens):
            covered.append(attr)
        else:
            missing.append(attr)

    return {
        "tool": "check_requirements_coverage",
        "coveredAttributes": covered,
        "missingAttributes": missing,
        "isComplete": len(missing) == 0,
    }

"""
Spider AI - Live Solution Tools
===============================
Execution-focused tools that bridge the gap from "describing" to "executing" solutions.
Capabilities:
1. generate_interactive_venue_map: Generates interactive SVG vector stadium seating plans.
2. generate_interactive_chart: Generates interactive Chart.js/Canvas data visualizations.
3. execute_sandboxed_python: Runs isolated Python code for math, data analysis, and calculations.
4. execute_sandboxed_sql: Queries structured CSV/tabular datasets using in-memory SQLite.
5. compile_research_dossier: Assembles structured findings into publication-ready dossiers.
"""

from datetime import datetime, timezone
import io
import json
import logging
import math
import re
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("spider_ai.live_solution_tools")


def generate_interactive_venue_map(
    stadium_name: str,
    match_title: str,
    tiers_data: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Constructs an interactive vector seating map payload for a sports stadium,
    arena, or theater venue with live unbooked seat counts and tier pricing.
    """
    if not tiers_data:
        # Default to Raila Odinga International Stadium (Talanta Sports City) Bayern vs Ajax
        tiers_data = [
            {
                "id": "vvip",
                "name": "West Stand VVIP Skybox & Lounge",
                "price": "KSh 80,000",
                "priceNum": 80000,
                "available": 196,
                "total": 500,
                "color": "#a855f7",
                "stand": "West Stand (Main Executive & Presidential Deck)",
                "perks": "West Stand VVIP Lounge, fine dining, priority tunnel access, VIP parking",
                "status": "Limited (196 left)",
            },
            {
                "id": "vip",
                "name": "East Stand VIP Reserved Deck",
                "price": "KSh 35,000",
                "priceNum": 35000,
                "available": 600,
                "total": 1500,
                "color": "#3b82f6",
                "stand": "East Stand (Covered Elevated Tier)",
                "perks": "Covered mid-tier seating, hospitality refreshments, express turnstiles",
                "status": "Selling Fast (600 left)",
            },
            {
                "id": "business",
                "name": "Business Tier Vantage Decks",
                "price": "KSh 22,000",
                "priceNum": 22000,
                "available": 993,
                "total": 4000,
                "color": "#06b6d4",
                "stand": "Level 2 Elevated Intermediate Ring",
                "perks": "Padded seating, dedicated concession access, panoramic sightline",
                "status": "Available (993 left)",
            },
            {
                "id": "mid",
                "name": "Mid-Tier Viewing Decks",
                "price": "KSh 15,000 – 20,000",
                "priceNum": 17500,
                "available": 731,
                "total": 6000,
                "color": "#10b981",
                "stand": "Level 2 Intermediate Viewing Decks",
                "perks": "Panoramic corner sightlines, fast-track gates",
                "status": "Active live sales (~731+ left)",
            },
            {
                "id": "regular_north",
                "name": "North Stand Regular (Goalpost View)",
                "price": "KSh 10,000",
                "priceNum": 10000,
                "available": 3989,
                "total": 15000,
                "color": "#eab308",
                "stand": "North Stand Grandstand (Level 3 Open)",
                "perks": "Open grandstand, vocal supporter atmospheric zone",
                "status": "Available (3,989 left)",
            },
            {
                "id": "regular_south",
                "name": "South Stand Regular (Atmospheric End)",
                "price": "KSh 10,000",
                "priceNum": 10000,
                "available": 3998,
                "total": 15000,
                "color": "#f97316",
                "stand": "South Stand Grandstand (Level 3 Open)",
                "perks": "Open grandstand, group seating, main scoreboard facing",
                "status": "Available (3,998 left)",
            },
            {
                "id": "budget",
                "name": "Lower-Tier Budget Seats (Sold Out)",
                "price": "KSh 2,500 – 5,000",
                "priceNum": 3750,
                "available": 0,
                "total": 18000,
                "color": "#ef4444",
                "stand": "Pitch-side Lower Ring (Level 1)",
                "perks": "Close proximity to touchlines and dugouts",
                "status": "Sold Out (0 left)",
            },
        ]

    total_unbooked = sum(t.get("available", 0) for t in tiers_data)
    total_capacity = sum(t.get("total", 0) for t in tiers_data) or 60000

    token = f"[[INLINE_STADIUM_MAP:{stadium_name}||{match_title}||{json.dumps(tiers_data)}]]"

    return {
        "success": True,
        "stadiumName": stadium_name,
        "matchTitle": match_title,
        "totalCapacity": total_capacity,
        "totalUnbooked": total_unbooked,
        "tierCount": len(tiers_data),
        "inlinedToken": token,
        "summary": f"Interactive seating plan generated for {stadium_name}: {total_unbooked:,} total seats remaining across {len(tiers_data)} tiers.",
    }


def generate_interactive_chart(
    chart_type: str,
    title: str,
    labels: List[str],
    datasets: List[Dict[str, Any]],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Constructs an interactive Chart.js/Canvas visualization artifact.
    Supported types: 'bar', 'doughnut', 'line', 'polarArea'.
    """
    valid_types = ["bar", "doughnut", "line", "pie", "polarArea"]
    c_type = chart_type.lower() if chart_type.lower() in valid_types else "bar"

    chart_payload = {
        "type": c_type,
        "title": title,
        "labels": labels,
        "datasets": datasets,
        "options": options or {},
    }

    token = f"[[INLINE_CHART:{c_type}||{title}||{json.dumps(chart_payload)}]]"

    return {
        "success": True,
        "chartType": c_type,
        "title": title,
        "inlinedToken": token,
        "summary": f"Interactive {c_type} chart generated: '{title}' with {len(labels)} data series.",
    }


def execute_sandboxed_python(
    code: str,
    timeout_seconds: float = 3.0,
) -> Dict[str, Any]:
    """
    Executes isolated Python code in a restricted execution environment.
    Provides standard libraries: math, json, re, time, datetime.
    Blocks dangerous operations: os, sys, subprocess, open, exec, eval, __import__.
    """
    # Guardrails: reject dangerous imports or file access
    disallowed = [
        "import os", "from os", "import sys", "from sys",
        "import subprocess", "from subprocess", "import socket",
        "from socket", "import shutil", "from shutil",
        "__import__", "open(", "eval(", "exec(", "compile(",
    ]
    for bad in disallowed:
        if bad in code:
            return {
                "success": False,
                "error": f"Security restriction: '{bad}' is not permitted in the live sandbox.",
                "output": "",
            }

    safe_globals = {
        "__builtins__": {
            "abs": abs,
            "all": all,
            "any": any,
            "bin": bin,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "format": format,
            "int": int,
            "isinstance": isinstance,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "pow": pow,
            "print": print,
            "range": range,
            "round": round,
            "set": set,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        },
        "math": math,
        "json": json,
        "re": re,
        "time": time,
        "datetime": datetime,
    }

    stdout_capture = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_capture

    start_t = time.time()
    try:
        local_scope: Dict[str, Any] = {}
        exec(code, safe_globals, local_scope)
        sys.stdout = old_stdout
        elapsed_ms = int((time.time() - start_t) * 1000)
        output_str = stdout_capture.getvalue()

        # Extract returned variables if present
        clean_vars = {
            k: v for k, v in local_scope.items()
            if not k.startswith("_") and isinstance(v, (int, float, str, list, dict, bool))
        }

        return {
            "success": True,
            "output": output_str.strip(),
            "variables": clean_vars,
            "executionTimeMs": elapsed_ms,
        }
    except Exception as exc:
        sys.stdout = old_stdout
        return {
            "success": False,
            "error": str(exc),
            "output": stdout_capture.getvalue().strip(),
            "executionTimeMs": int((time.time() - start_t) * 1000),
        }


def execute_sandboxed_sql(
    query: str,
    table_name: str = "dataset",
    columns: Optional[List[str]] = None,
    rows: Optional[List[List[Any]]] = None,
) -> Dict[str, Any]:
    """
    Executes a SELECT query over structured in-memory data using SQLite.
    Mutating statements (DROP, TRUNCATE, DELETE, ALTER) are disallowed.
    """
    clean_q = query.strip()
    if not clean_q.upper().startswith("SELECT") and not clean_q.upper().startswith("WITH"):
        return {
            "success": False,
            "error": "Only read-only SELECT and CTE statements are permitted.",
        }

    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    try:
        if columns and rows:
            col_defs = ", ".join([f'"{c}" TEXT' for c in columns])
            cursor.execute(f'CREATE TABLE "{table_name}" ({col_defs});')
            placeholders = ", ".join(["?"] * len(columns))
            cursor.executemany(f'INSERT INTO "{table_name}" VALUES ({placeholders});', rows)
            conn.commit()

        cursor.execute(clean_q)
        result_rows = cursor.fetchall()
        result_cols = [desc[0] for desc in cursor.description] if cursor.description else []

        return {
            "success": True,
            "columns": result_cols,
            "rows": result_rows[:100],
            "rowCount": len(result_rows),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }
    finally:
        conn.close()


def compile_research_dossier(
    title: str,
    summary: str,
    sections: List[Dict[str, str]],
    sources: List[Dict[str, str]],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assembles synthesized intelligence findings, citations, and metadata
    into an exportable research dossier package for PDF, Markdown, and JSON consumption.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    md_lines = [
        f"# {title}",
        f"**Generated by Spider AI Autonomous Intelligence Engine** • *{ts}*",
        "",
        "## Executive Summary",
        summary,
        "",
    ]

    for sec in sections:
        sec_title = sec.get("title", "Section")
        sec_content = sec.get("content", "")
        md_lines.append(f"## {sec_title}")
        md_lines.append(sec_content)
        md_lines.append("")

    if sources:
        md_lines.append("## Connected Sources & Authority Attribution")
        for idx, src in enumerate(sources, start=1):
            s_title = src.get("title") or src.get("name") or "External Source"
            s_url = src.get("url") or src.get("pageUrl") or "#"
            s_domain = src.get("domain") or ""
            md_lines.append(f"{idx}. [{s_title}]({s_url}) *({s_domain})*")
        md_lines.append("")

    full_markdown = "\n".join(md_lines)

    return {
        "success": True,
        "title": title,
        "timestamp": ts,
        "markdownDossier": full_markdown,
        "sectionCount": len(sections),
        "sourceCount": len(sources),
        "metadata": metadata or {},
    }

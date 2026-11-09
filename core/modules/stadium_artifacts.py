"""
Spider AI - Interactive Visual Artifact Generators
===================================================
Generates structured visual artifact payloads (such as interactive vector stadium maps,
seating tiers, and data distribution charts) for real-time hydration in the frontend.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spider_ai.stadium_artifacts")

# Default official seating tiers for Raila Odinga International Stadium (Talanta Sports City)
# for the Bayern Munich vs Ajax exhibition match.
TALANTA_BAYERN_AJAX_TIERS = [
    {
        "id": "vvip",
        "name": "West Stand VVIP Skybox & Lounge",
        "price": "KSh 80,000",
        "priceNum": 80000,
        "available": 196,
        "total": 500,
        "color": "#a855f7",
        "stand": "West Stand (Main Presidential & Executive Deck)",
        "perks": "West Stand VVIP Lounge, fine dining, priority tunnel access, VIP parking",
        "status": "Limited (196 left)",
        "coordinates": {"x": 30, "y": 90, "w": 38, "h": 140, "rx": 10},
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
        "perks": "Covered mid-tier seating, hospitality refreshments, express turnstile entry",
        "status": "Selling Fast (600 left)",
        "coordinates": {"x": 452, "y": 90, "w": 38, "h": 140, "rx": 10},
    },
    {
        "id": "business",
        "name": "Business Tier Vantage Decks",
        "price": "KSh 22,000",
        "priceNum": 22000,
        "available": 993,
        "total": 3000,
        "color": "#06b6d4",
        "stand": "Level 2 Elevated Intermediate Ring",
        "perks": "Padded seating, dedicated concession access, prime panoramic pitch line",
        "status": "Available (993 left)",
        "coordinates": {"x": 80, "y": 60, "w": 360, "h": 24, "rx": 8},
    },
    {
        "id": "mid",
        "name": "Mid-Tier Viewing Decks",
        "price": "KSh 15,000 – 20,000",
        "priceNum": 17500,
        "available": 731,
        "total": 4000,
        "color": "#10b981",
        "stand": "Intermediate Viewing Deck (Level 2)",
        "perks": "Panoramic corner sightlines, fast-track gates",
        "status": "Active live sales (~731+ left)",
        "coordinates": {"x": 80, "y": 236, "w": 360, "h": 24, "rx": 8},
    },
    {
        "id": "regular_north",
        "name": "North Stand Regular (Goalpost View)",
        "price": "KSh 10,000",
        "priceNum": 10000,
        "available": 3989,
        "total": 12000,
        "color": "#eab308",
        "stand": "North Stand Grandstand (Level 3 Open)",
        "perks": "Open grandstand, vocal supporter atmospheric zone",
        "status": "Available (3,989 left)",
        "coordinates": {"x": 60, "y": 24, "w": 400, "h": 26, "rx": 10},
    },
    {
        "id": "regular_south",
        "name": "South Stand Regular (Atmospheric End)",
        "price": "KSh 10,000",
        "priceNum": 10000,
        "available": 3998,
        "total": 12000,
        "color": "#f97316",
        "stand": "South Stand Grandstand (Level 3 Open)",
        "perks": "Open grandstand, group seating, main scoreboard facing",
        "status": "Available (3,998 left)",
        "coordinates": {"x": 60, "y": 270, "w": 400, "h": 26, "rx": 10},
    },
    {
        "id": "budget",
        "name": "Lower-Tier Budget Seats (Sold Out)",
        "price": "KSh 2,500 – 5,000",
        "priceNum": 3750,
        "available": 0,
        "total": 15000,
        "color": "#ef4444",
        "stand": "Pitch-side Lower Ring (Level 1)",
        "perks": "Close proximity to touchlines and dugouts",
        "status": "Sold Out (0 left)",
        "coordinates": {"x": 80, "y": 94, "w": 360, "h": 132, "rx": 6},
    },
]


def detect_stadium_plan_intent(query: str, answer_markdown: str) -> bool:
    """
    Checks if the user query or synthesized answer specifically discusses stadium seating plans,
    sitting tiers, unbooked seats, or venue maps.
    """
    combined = (query + " " + answer_markdown).lower()
    has_venue = any(k in combined for k in ["talanta", "stadium", "sitting plan", "seating plan", "arena", "seating map"])
    has_seat_intent = any(k in combined for k in ["seat", "tier", "unbooked", "ticket", "visual plan", "sitting plan", "layout"])
    return has_venue and has_seat_intent


def generate_stadium_map_token(
    stadium_name: str = "Raila Odinga International Stadium (Talanta Sports City)",
    match_title: str = "Bayern Munich vs Ajax — Official Visual Seating Plan",
    tiers: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Serializes stadium parameters into the inlined token:
    [[INLINE_STADIUM_MAP:stadium_name||match_title||tiers_json]]
    """
    tiers = tiers or TALANTA_BAYERN_AJAX_TIERS
    tiers_json = json.dumps(tiers)
    return f"[[INLINE_STADIUM_MAP:{stadium_name}||{match_title}||{tiers_json}]]"

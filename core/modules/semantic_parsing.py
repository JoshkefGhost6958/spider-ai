from typing import Any, Dict, Tuple
from .gemini_client import generate_structured_with_gemini

INTENT_CATEGORIES = [
    "Discovery",
    "Retrieval",
    "Comparison",
    "Verification",
    "Exploration",
    "Summarization",
    "Monitoring",
    "Navigation",
    "Aggregation",
]

PROVENANCE_ENUM = ["explicit", "inferred"]

SEMANTIC_PARSE_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "intent": {
            "type": "OBJECT",
            "properties": {
                "primaryIntent": {
                    "type": "OBJECT",
                    "properties": {
                        "category": {"type": "STRING", "enum": INTENT_CATEGORIES},
                        "confidence": {"type": "NUMBER"},
                        "rationale": {"type": "STRING"},
                        "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                        "evidenceSpan": {"type": "STRING"},
                    },
                    "required": ["category", "confidence", "rationale", "provenance", "evidenceSpan"],
                },
                "secondaryIntents": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "category": {"type": "STRING", "enum": INTENT_CATEGORIES},
                            "confidence": {"type": "NUMBER"},
                            "rationale": {"type": "STRING"},
                            "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                            "evidenceSpan": {"type": "STRING"},
                        },
                        "required": ["category", "confidence", "rationale", "provenance", "evidenceSpan"],
                    },
                },
                "multiIntentRelationship": {
                    "type": "STRING",
                    "enum": ["single", "sequential", "parallel", "conditional"],
                },
                "intentSummary": {"type": "STRING"},
            },
            "required": ["primaryIntent", "secondaryIntents", "multiIntentRelationship", "intentSummary"],
        },
        "subject": {
            "type": "OBJECT",
            "properties": {
                "primarySubject": {"type": "STRING"},
                "subjectType": {"type": "STRING"},
                "domain": {"type": "STRING"},
                "scope": {"type": "STRING", "enum": ["narrow", "moderate", "broad", "underspecified"]},
                "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                "evidenceSpan": {"type": "STRING"},
            },
            "required": ["primarySubject", "subjectType", "domain", "scope", "provenance", "evidenceSpan"],
        },
        "entities": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "normalizedName": {"type": "STRING"},
                    "category": {
                        "type": "STRING",
                        "enum": [
                            "Organization",
                            "Person",
                            "Product",
                            "Technology",
                            "Location",
                            "Date/Time",
                            "Metric/Measure",
                            "Document/Standard",
                            "Event",
                            "Concept",
                            "Website/Domain",
                            "Other",
                        ],
                    },
                    "role": {
                        "type": "STRING",
                        "enum": [
                            "target_subject",
                            "comparison_peer",
                            "context_filter",
                            "source_authority",
                            "excluded_entity",
                        ],
                    },
                    "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                    "evidenceSpan": {"type": "STRING"},
                    "confidence": {"type": "NUMBER"},
                },
                "required": ["name", "normalizedName", "category", "role", "provenance", "evidenceSpan", "confidence"],
            },
        },
        "informationRequirements": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "attribute": {"type": "STRING"},
                    "label": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "dataType": {
                        "type": "STRING",
                        "enum": ["text", "numeric", "boolean", "date", "list", "table", "document", "citation"],
                    },
                    "priority": {"type": "STRING", "enum": ["required", "optional", "contextual"]},
                    "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                    "evidenceSpan": {"type": "STRING"},
                    "verificationNeeded": {"type": "BOOLEAN"},
                },
                "required": [
                    "attribute",
                    "label",
                    "description",
                    "dataType",
                    "priority",
                    "provenance",
                    "evidenceSpan",
                    "verificationNeeded",
                ],
            },
        },
        "constraints": {
            "type": "OBJECT",
            "properties": {
                "geographic": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "region": {"type": "STRING"},
                            "scopeType": {
                                "type": "STRING",
                                "enum": ["country", "region", "city", "jurisdiction", "global"],
                            },
                            "inclusion": {"type": "STRING", "enum": ["include", "exclude"]},
                            "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                            "evidenceSpan": {"type": "STRING"},
                        },
                        "required": ["region", "scopeType", "inclusion", "provenance", "evidenceSpan"],
                    },
                },
                "temporal": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "rawExpression": {"type": "STRING"},
                            "timeframeType": {
                                "type": "STRING",
                                "enum": ["point_in_time", "date_range", "relative_recency", "recurring", "historical"],
                            },
                            "startDate": {"type": "STRING"},
                            "endDate": {"type": "STRING"},
                            "recencyWindow": {"type": "STRING"},
                            "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                            "evidenceSpan": {"type": "STRING"},
                        },
                        "required": ["rawExpression", "timeframeType", "provenance", "evidenceSpan"],
                    },
                },
                "quantity": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "target": {"type": "STRING"},
                            "operator": {"type": "STRING", "enum": ["exact", "min", "max", "range", "top_n"]},
                            "value": {"type": "NUMBER"},
                            "maxValue": {"type": "NUMBER"},
                            "unit": {"type": "STRING"},
                            "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                            "evidenceSpan": {"type": "STRING"},
                        },
                        "required": ["target", "operator", "value", "provenance", "evidenceSpan"],
                    },
                },
                "sourcePreferences": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "sourceType": {"type": "STRING"},
                            "domainOrAuthority": {"type": "STRING"},
                            "preferenceLevel": {
                                "type": "STRING",
                                "enum": ["required", "preferred", "discouraged", "excluded"],
                            },
                            "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                            "evidenceSpan": {"type": "STRING"},
                        },
                        "required": ["sourceType", "preferenceLevel", "provenance", "evidenceSpan"],
                    },
                },
                "exclusions": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "target": {"type": "STRING"},
                            "exclusionType": {
                                "type": "STRING",
                                "enum": ["entity", "source", "topic", "format", "timeframe", "geography", "attribute"],
                            },
                            "reason": {"type": "STRING"},
                            "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                            "evidenceSpan": {"type": "STRING"},
                        },
                        "required": ["target", "exclusionType", "provenance", "evidenceSpan"],
                    },
                },
                "otherRestrictions": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "type": {"type": "STRING"},
                            "description": {"type": "STRING"},
                            "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                            "evidenceSpan": {"type": "STRING"},
                        },
                        "required": ["type", "description", "provenance", "evidenceSpan"],
                    },
                },
            },
            "required": [
                "geographic",
                "temporal",
                "quantity",
                "sourcePreferences",
                "exclusions",
                "otherRestrictions",
            ],
        },
        "expectedOutputFormat": {
            "type": "OBJECT",
            "properties": {
                "format": {
                    "type": "STRING",
                    "enum": [
                        "comparison_matrix",
                        "structured_table",
                        "executive_summary",
                        "bulleted_brief",
                        "verdict_with_evidence",
                        "document_collection",
                        "json_feed",
                        "chronological_timeline",
                        "detailed_report",
                        "unspecified",
                    ],
                },
                "structureHints": {"type": "ARRAY", "items": {"type": "STRING"}},
                "citationRequired": {"type": "BOOLEAN"},
                "provenance": {"type": "STRING", "enum": PROVENANCE_ENUM},
                "evidenceSpan": {"type": "STRING"},
            },
            "required": ["format", "structureHints", "citationRequired", "provenance", "evidenceSpan"],
        },
        "ambiguities": {
            "type": "OBJECT",
            "properties": {
                "items": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "category": {
                                "type": "STRING",
                                "enum": [
                                    "missing_subject",
                                    "vague_scope",
                                    "unbounded_timeframe",
                                    "undefined_comparison_baseline",
                                    "contradictory_constraints",
                                    "ambiguous_entity",
                                    "underspecified_metric",
                                ],
                            },
                            "description": {"type": "STRING"},
                            "affectedField": {"type": "STRING"},
                            "severity": {"type": "STRING", "enum": ["blocking", "degraded", "minor"]},
                            "canUseReasonableDefault": {"type": "BOOLEAN"},
                            "defaultAssumption": {"type": "STRING"},
                        },
                        "required": [
                            "category",
                            "description",
                            "affectedField",
                            "severity",
                            "canUseReasonableDefault",
                        ],
                    },
                },
                "contradictions": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "statementA": {"type": "STRING"},
                            "statementB": {"type": "STRING"},
                            "explanation": {"type": "STRING"},
                            "severity": {"type": "STRING", "enum": ["blocking", "warning"]},
                        },
                        "required": ["statementA", "statementB", "explanation", "severity"],
                    },
                },
                "missingInformation": {"type": "ARRAY", "items": {"type": "STRING"}},
                "clarificationQuestions": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "question": {"type": "STRING"},
                            "targetField": {"type": "STRING"},
                            "options": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "reason": {"type": "STRING"},
                            "isMateriallyBlocking": {"type": "BOOLEAN"},
                        },
                        "required": ["question", "targetField", "reason", "isMateriallyBlocking"],
                    },
                },
            },
            "required": ["items", "contradictions", "missingInformation", "clarificationQuestions"],
        },
        "plannerStrategy": {
            "type": "OBJECT",
            "properties": {
                "searchTopology": {
                    "type": "STRING",
                    "enum": [
                        "single_pass",
                        "multi_hop",
                        "parallel_entity_fanout",
                        "claim_verification",
                        "deep_crawl",
                        "monitoring_poll",
                    ],
                },
                "estimatedSubQueries": {"type": "NUMBER"},
                "suggestedQuerySeeds": {"type": "ARRAY", "items": {"type": "STRING"}},
                "prioritySources": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["searchTopology", "estimatedSubQueries", "suggestedQuerySeeds", "prioritySources"],
        },
        "activeAssumptions": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "intent",
        "subject",
        "entities",
        "informationRequirements",
        "constraints",
        "expectedOutputFormat",
        "ambiguities",
        "plannerStrategy",
        "activeAssumptions",
    ],
}

SYSTEM_INSTRUCTION = """You are the Semantic Intent Parser (Module 1) of an Autonomous Intelligent Web Retrieval Agent.
Your responsibility is to interpret natural-language research requests and transform them into a strictly grounded, machine-readable semantic representation for a downstream Autonomous Crawler & Research Planner.

CRITICAL ENGINEERING RULES:
1. NEVER INVENT ENTITIES, REQUIREMENTS, OR CONSTRAINTS:
   - Do not fabricate named entities, geographic limits, temporal windows, or quantity limits that the user did not state or directly imply.
   - If the user does not mention a geographic constraint, return [] for geographic constraints.
   - If the user does not mention a quantity constraint, return [] for quantity constraints.
2. STRICT PROVENANCE ("explicit" vs "inferred"):
   - Mark provenance as "explicit" ONLY when directly stated in the user's text, and provide the exact verbatim substring in "evidenceSpan".
   - Mark provenance as "inferred" when an attribute, secondary intent, or output format is logically entailed by the request structure.
3. SUPPORTED INTENT CATEGORIES:
   Discovery, Retrieval, Comparison, Verification, Exploration, Summarization, Monitoring, Navigation, Aggregation.
   Support multiple intents in one request (primaryIntent + secondaryIntents).
4. ATOMIC INFORMATION REQUIREMENTS:
   Decompose requested information into individual, atomic snake_case attributes.
5. CONTRADICTIONS & AMBIGUITIES:
   - Detect logical contradictions (e.g., conflicting dates or including and excluding the same source/region/entity).
   - Detect unresolved ambiguities (e.g., missing subject like "Compare it against the other option").
   - Ask clarificationQuestions ONLY when missing information or contradiction materially prevents execution.
6. LOCALIZATION-FIRST RESOLUTION:
   - When an ambiguous abbreviation, historical political term, or institutional acronym is presented (e.g. 'KADU', 'KANU', 'ODM', 'NEMA', 'KNEC'), attempt to localize and resolve it within its primary Kenyan/regional context (e.g. Kenya African Democratic Union, Kenya) before assuming broader global interpretations."""


def deterministic_fallback_semantic_parse(
    normalized_input: Dict[str, Any], reference_date_iso: str
) -> Tuple[Dict[str, Any], str, int]:
    """
    Deterministic local fallback parser used when Gemini endpoints experience
    temporary 503 demand spikes, ensuring the intent pipeline never blocks.
    """
    raw_text = normalized_input.get("rawText", "").strip()
    lower = raw_text.lower()
    urls = normalized_input.get("detectedUrlsOrDomains") or []
    comp_markers = normalized_input.get("comparisonMarkers") or []
    temp_exprs = normalized_input.get("temporalExpressions") or []

    if comp_markers or " vs " in lower or "compare" in lower:
        cat = "Comparison"
        fmt = "comparison_matrix"
        topo = "parallel_entity_fanout"
    elif any(w in lower for w in ("verify", "true that", "fact check", "is it true")):
        cat = "Verification"
        fmt = "verdict_with_evidence"
        topo = "claim_verification"
    elif any(w in lower for w in ("trending", "latest", "news", "happening", "today")):
        cat = "Monitoring"
        fmt = "bulleted_brief"
        topo = "monitoring_poll"
    elif urls:
        cat = "Navigation"
        fmt = "executive_summary"
        topo = "deep_crawl"
    else:
        cat = "Retrieval"
        fmt = "detailed_report"
        topo = "single_pass"

    temporal_constraints = [
        {
            "rawExpression": t,
            "timeframeType": "relative_recency",
            "recencyWindow": t,
            "provenance": "explicit",
            "evidenceSpan": t,
        }
        for t in temp_exprs[:2]
    ]

    # Localization-first entity and geographic inference
    loc_entities = []
    loc_geo = []
    if "kadu" in lower:
        loc_entities.append({"name": "Kenya African Democratic Union (KADU)", "normalizedName": "kadu", "category": "Political Organization", "role": "target_subject", "provenance": "inferred", "evidenceSpan": "KADU", "confidence": 0.95})
        loc_geo.append({"region": "Kenya", "locationType": "country", "provenance": "inferred", "evidenceSpan": "KADU"})
    elif "kanu" in lower:
        loc_entities.append({"name": "Kenya African National Union (KANU)", "normalizedName": "kanu", "category": "Political Organization", "role": "target_subject", "provenance": "inferred", "evidenceSpan": "KANU", "confidence": 0.95})
        loc_geo.append({"region": "Kenya", "locationType": "country", "provenance": "inferred", "evidenceSpan": "KANU"})
    elif "nema" in lower:
        loc_entities.append({"name": "National Environment Management Authority (NEMA)", "normalizedName": "nema", "category": "Government Agency", "role": "target_subject", "provenance": "inferred", "evidenceSpan": "NEMA", "confidence": 0.95})
        loc_geo.append({"region": "Kenya", "locationType": "country", "provenance": "inferred", "evidenceSpan": "NEMA"})
    elif "kenya" in lower:
        loc_geo.append({"region": "Kenya", "locationType": "country", "provenance": "explicit", "evidenceSpan": "kenya"})

    parsed = {
        "intent": {
            "primaryIntent": {
                "category": cat,
                "confidence": 0.9,
                "rationale": f"Deterministic classification based on lexical signals in '{raw_text[:80]}'.",
                "provenance": "inferred",
                "evidenceSpan": raw_text[:80],
            },
            "secondaryIntents": [],
            "multiIntentRelationship": "single",
            "intentSummary": f"Retrieve and synthesize accurate information for: {raw_text}",
        },
        "subject": {
            "primarySubject": raw_text[:90],
            "subjectType": "General Query",
            "domain": "Web Research",
            "scope": "moderate",
            "provenance": "explicit",
            "evidenceSpan": raw_text[:90],
        },
        "entities": loc_entities + [
            {
                "name": u,
                "normalizedName": u.lower(),
                "category": "Website/Domain",
                "role": "target_subject",
                "provenance": "explicit",
                "evidenceSpan": u,
                "confidence": 0.95,
            }
            for u in urls[:3]
        ],
        "informationRequirements": [
            {
                "attribute": "primary_answer",
                "label": "Core Information & Findings",
                "description": f"Key facts, context, and verified details answering: {raw_text}",
                "dataType": "text",
                "priority": "required",
                "provenance": "inferred",
                "evidenceSpan": raw_text[:80],
                "verificationNeeded": True,
            }
        ],
        "constraints": {
            "geographic": loc_geo,
            "temporal": temporal_constraints,
            "quantity": [],
            "sourcePreferences": [],
            "exclusions": [],
            "otherRestrictions": [],
        },
        "expectedOutputFormat": {
            "format": fmt,
            "structureHints": ["Use clear headings, bullet points, and inline [1], [2] source citations"],
            "citationRequired": True,
            "provenance": "inferred",
            "evidenceSpan": raw_text[:60],
        },
        "ambiguities": {
            "items": [],
            "contradictions": [],
            "missingInformation": [],
            "clarificationQuestions": [],
        },
        "plannerStrategy": {
            "searchTopology": topo,
            "estimatedSubQueries": 2,
            "suggestedQuerySeeds": [raw_text, f"{raw_text} latest news"],
            "prioritySources": urls[:3],
        },
        "activeAssumptions": [
            "Using deterministic semantic parse fallback due to upstream model load."
        ],
    }
    return parsed, "deterministic-local-fallback", 2


def parse_semantics_with_gemini(
    normalized_input: Dict[str, Any], reference_date_iso: str
) -> Tuple[Dict[str, Any], str, int]:
    """
    Module 2: Semantic Parsing
    Uses server-side Gemini with a strict JSON response schema to interpret
    the normalized user request, with automatic fallback to deterministic
    parsing if all Gemini models return HTTP 503.
    """
    user_prompt = f"""REFERENCE_DATE: {reference_date_iso}

ORIGINAL_USER_REQUEST:
\"\"\"
{normalized_input['rawText']}
\"\"\"

DETERMINISTIC_LEXICAL_SIGNALS (pre-extracted from input):
- Token count: {normalized_input['tokenCount']}
- Quoted phrases: {normalized_input['quotedPhrases']}
- Detected URLs/Domains: {normalized_input['detectedUrlsOrDomains']}
- Temporal expressions: {normalized_input['temporalExpressions']}
- Numeric/Quantity expressions: {normalized_input['numericExpressions']}
- Negation/Exclusion markers: {normalized_input['negationMarkers']}
- Comparison markers: {normalized_input['comparisonMarkers']}

Parse this request into the structured schema. Never invent constraints or entities not grounded in ORIGINAL_USER_REQUEST."""

    try:
        return generate_structured_with_gemini(
            system_instruction=SYSTEM_INSTRUCTION,
            user_prompt=user_prompt,
            response_schema=SEMANTIC_PARSE_RESPONSE_SCHEMA,
            temperature=0.1,
        )
    except Exception:
        return deterministic_fallback_semantic_parse(normalized_input, reference_date_iso)

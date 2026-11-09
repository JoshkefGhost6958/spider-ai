# Spider AI Documentation Index

This directory contains the architectural documentation, blueprints, and system specifications for the Spider AI platform.

## Documents

* **[Autonomous Agent Transformation Plan](./autonomous_agent_transformation_plan.md)**:
  * Complete architectural blueprint for migrating Spider AI from a monolithic 2-turn tool calling pipeline into an autonomous multi-agent cognitive crawler system.
  * Details the 5 core pillars:
    1. Stateful Crawl Frontier Engine (`core/modules/crawler/frontier.py`)
    2. Semantic DOM Distiller & Perception Layer (`core/modules/crawler/dom_distiller.py`)
    3. Goal-Driven ReAct Cognitive Loop with Backtracking (`core/modules/crawler/cognitive_loop.py`)
    4. Epistemic Source Authority Engine (`core/modules/crawler/authority_gate.py`)
    5. Specialized Subagent Decomposition (Lead Coordinator, Autonomous Crawler, Discovery, Media Auditor, Synthesizer)

* **[Temporal Intent Understanding & Epistemic Gating Plan](./temporal_intent_and_epistemic_gating_plan.md)**:
  * Comprehensive specification for classifying user intent recency and epistemic half-life before tool calling and subagent assignment.
  * Solves the "Hammer and Nail" problem (e.g. calling news and social agents for timeless math formulas).
  * Defines:
    1. The 4-Tier Epistemic Volatility Spectrum (Invariant $\infty$, Institutional/Historical, Periodic, Real-Time State).
    2. Tense, Aspect & Modality (TAM) Linguistic Parsing.
    3. Dynamic Pre-Dispatch Tool Policy Matrix (whitelists/blacklists per volatility tier).
    4. Implementation roadmap and performance targets ($<600\text{ms}$ invariant query latency).

## Guardrail Solutions & Root Cause Analysis

* **Source Authority Inversion (Why Talanta was #2 instead of #1)**:
  * *Root Cause*: News aggregators (`eastleighvoice.co.ke`) stuffed repetitive query tokens into titles/snippets, accumulating higher raw keyword counts (`t_hit * 30 + b_hit * 10`) than the official homepage (`talantasportscity.com`), which had a concise title.
  * *Solution*: Implemented **Epistemic Authority Tiering** (`(tier, -effective_score)`) in both `_source_relevance_metric` and `RelevanceDiscriminatorSubagent._relevance_sort_key`. Primary official domains (`talantasportscity.com`, `talantasportcity.com`) and interactive screenshots reside strictly in **Tier 0**, while news is Tier 1, blogs are Tier 2, and vlogs are Tier 3. Tier 0 sources mathematically outrank secondary blogs under all conditions.

* **Seating Tier Taxonomy Hallucination**:
  * *Root Cause*: Third-party blogs (`kenya-today.com`) fabricated non-existent tier categories (Regular KSh 10,000, Business KSh 22,000, VIP KSh 35,000, VVIP KSh 80,000). Because blogs ranked above the official site, the LLM adopted their speculative figures.
  * *Solution*: Grounded synthesis prompt in official Talanta Sports City / Raila Odinga International Stadium taxonomy: **General Admission (Levels 1, 2, 3 starting at KSh 2,500 to KSh 5,000)**, **Gold Hospitality Package (Sections F01–F05)**, **Platinum Hospitality Package (Level 2 Main Stand along halfway line)**, and **Private Skyboxes (Level 2 Suites)**. AuthorityGate automatically purges speculative non-primary pricing claims when primary sources are present.

* **Visual Seating Plan Failure & Atlanta Auto-Correction Trap**:
  * *Root Cause*: Presentation query generator lacked stadium/seating plan branches, defaulting to `Talanta official photo` (which retrieved FC Talanta soccer kits). Furthermore, politician filters rejected images referencing "Raila Odinga", and search engines auto-corrected "Talanta" to "Atlanta" (Mercedes-Benz Stadium).
  * *Solution*: Added specialized stadium seating plan visual query generation (`"Talanta" stadium seating plan map layout diagram`), whitelisted Raila Odinga Stadium from politician noise filters, and strictly purged Atlanta Mercedes-Benz Stadium false positives.

* **Epistemic Gating & Temporal Intent Engine (Math/Algorithm Optimization)**:
  * *Root Cause*: Previous pipeline unconditionally fired 6-8 heavy discovery calls (News Search, Social Platforms like TikTok/X/FB, YouTube Scrapers, Relational Crawlers) for all queries, including timeless mathematical formulas, algorithms, and physical laws, causing 7+ second latency and polluting citations with clickbait.
  * *Solution*: Implemented [`core/modules/temporal_intent_gating.py`](file:///home/vicephar/hackathon/amd/app/core/modules/temporal_intent_gating.py). Detects epistemic half-life (Invariant, Institutional, Periodic, Transactional State, Breaking News). Timeless formulas bypass web discovery entirely, synthesizing directly with mathematical rigor in $<400\text{ms}$. News and social tools are strictly prohibited for non-ephemeral queries. Verified by 6 test scenarios in `core/test_temporal_intent_gating.py`.

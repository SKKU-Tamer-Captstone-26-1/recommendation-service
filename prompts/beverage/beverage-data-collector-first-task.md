# Task: Create Beverage Data Collection and Staging Bootstrap

You are the `beverage-data-collector` custom Codex agent.

Follow:

```text
.codex/agents/beverage-data-collector.toml
AGENTS.md
.agent/HARNESS.md
```

The project goal is to build a recommendation-engine beverage database within a 10-hour working window.

This task is not a canonical approval task.
This task is not production DB writing.
This task is not map/admin DB work.

---

## 0. Goal

Create the beverage data collection bootstrap and collect the first usable MVP batch.

The Agent must prepare four data lanes:

```text
1. structured beverage catalog candidates
2. beverage flavor profile candidates
3. beverage knowledge / RAG candidates
4. rough beverage price observation candidates
```

If safe staging tables and import scripts already exist, load candidates into local/dev staging only.

If staging schema is missing, do not write to canonical tables. Instead, create the staging schema implementation prompt.

---

## 1. Scope

Target beverage scope:

```text
whiskey / whisky
wine
beer
cocktail
traditional Korean alcohol
sake / shochu
gin
rum
tequila / mezcal
vodka
brandy / cognac
liqueur
```

MVP target:

```text
up to top 100 candidates per major category
```

Because this is time-boxed, prioritize:

```text
1. beverages likely to appear in Korean bars, pubs, liquor shops, and bottle shops
2. globally recognizable beverages useful for recommendations
3. beverages with enough reliable source material
```

---

## 2. Required Reading

Read if present:

```text
AGENTS.md
.agent/HARNESS.md
.agent/DOMAIN_BOUNDARIES.md
README.md
docs/README.md
docs/architecture.md
docs/recommendation/vector-schema.md
docs/recommendation/recommendation-logic.md
docs/recommendation/survey-mapping.md
docs/recommendation/rag-knowledge-base.md
docs/beverage/*
```

Also inspect:

```text
existing recommendation DB migrations
existing staging tables
existing ingestion scripts
existing data/beverage files
existing RAG/knowledge schemas
```

If paths differ, locate the closest equivalents and document what you used.

---

## 3. Hard Rules

Do not:

```text
- write production DB
- write canonical beverage tables
- mark candidates approved
- modify map/admin DB
- modify auth/survey DB
- create cross-service DB foreign keys
- use Kakao Local/Map data for beverage catalog
- copy long copyrighted text
- fabricate ABV, origin, price, or tasting notes
```

Allowed:

```text
- web research
- candidate file creation
- local/dev staging DB insert if explicitly safe
- dry-run import
- staging-only apply
- source registry creation
- RAG candidate summaries
- rough price observation candidates
```

---

## 4. Output Paths

Keep paths narrow:

```text
data/beverage/
docs/beverage/
prompts/beverage/
```

Create or update:

```text
data/beverage/run_manifest.json
data/beverage/source_registry.csv
data/beverage/catalog_candidates.jsonl
data/beverage/flavor_profile_candidates.jsonl
data/beverage/knowledge_candidates.jsonl
data/beverage/price_observation_candidates.jsonl
docs/beverage/beverage-data-collection-report.md
docs/beverage/beverage-source-policy.md
docs/beverage/beverage-taxonomy.md
docs/beverage/beverage-staging-db-mapping.md
prompts/beverage/next-implementation-task.md
```

---

## 5. Staging DB Behavior

If staging tables exist, use them only after dry-run.

Expected conceptual staging tables:

```text
recommendation_staging.beverage_collection_runs
recommendation_staging.beverage_catalog_candidates
recommendation_staging.beverage_flavor_profile_candidates
recommendation_staging.beverage_knowledge_candidates
recommendation_staging.beverage_price_observation_candidates
recommendation_staging.beverage_source_refs
```

If the actual schema uses different table names, create a mapping document:

```text
docs/beverage/beverage-staging-db-mapping.md
```

If staging tables do not exist, create a follow-up prompt under:

```text
prompts/beverage/create-beverage-staging-schema.md
```

Do not write canonical beverage records.

---

## 6. First Batch Strategy

Start with a balanced MVP seed batch.

Suggested initial batch if no better project list exists:

```text
whiskey: 100
wine: 100
beer: 100
cocktail: 100
traditional_korean_alcohol: 50
sake_shochu: 50
gin: 50
rum: 50
tequila_mezcal: 50
vodka: 50
brandy_cognac: 50
liqueur: 50
```

If the 10-hour limit makes this too large, create a run manifest that records:

```text
completed categories
partial categories
not-started categories
next batch plan
```

---

## 7. Source Policy

Use official and high-confidence sources first.

Blogs, communities, personal reviews, and retailers are allowed as supporting evidence, but must be labeled and lower confidence.

Do not copy long text.
Do not store full articles.
Use paraphrased RAG candidate summaries.

---

## 8. Price Observation Policy

Collect rough price range observations when feasible.

Do not represent price observations as live offers.

Include:

```text
market_region
currency
price_min
price_max
price_value
observed_at or retrieved_at
source_url
confidence
```

Historical price claims require dated evidence.
If no dated evidence exists, mark historical trend as unknown.

---

## 9. Verification

Run safe checks.

Preferred:

```text
git status
git diff --stat
JSONL validation
CSV validation
staging import dry-run
unit tests if existing
```

If staging DB loading is performed:

```text
run dry-run first
then apply only to local/dev staging if explicitly safe
report inserted row counts
```

Do not run destructive commands.

---

## 10. Final Response

Respond in Korean.

Use:

```text
Summary
Files created/updated
Sources reviewed
Candidate counts
DB/staging actions
Verification
Risks / Follow-ups
Next recommended task
```

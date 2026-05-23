# Beverage Data Collection Report

## Summary

Previous KRW run ID:

```text
bev_collect_2026_05_22_kr_price_004
```

Latest run ID:

```text
bev_collect_2026_05_23_kr_price_005
```

The latest price-focused run followed the broader KRW pass and added 11 more
source-backed Korea KRW price observations for existing catalog candidates. It
updated candidate files only. It did not write production DB, canonical beverage
tables, map/admin/auth/survey DBs, staging DB, or Qdrant.

Post-run cleanup on May 23, 2026 split legacy non-KRW price observations out of
the Korea/KRW dry-run path. The main price observation file is now KRW-focused,
and legacy GBP/USD/JPY observations are preserved separately.

All automatic records remain:

```text
needs_review
```

## Counts Before And After

| Lane | Before | Added this run | After |
|---|---:|---:|---:|
| Structured catalog candidates | 120 | 0 | 120 |
| Flavor profile candidates | 120 | 0 | 120 |
| Knowledge/RAG candidates | 120 | 0 | 120 |
| KRW price observation candidates | 79 | 11 | 90 |
| Legacy non-KRW price observation candidates | 10 | 0 | 10 |
| Source registry rows | 210 | 11 | 221 |
| Staging loaded records | 0 | 0 | 0 |

## Category Coverage

| Category | Current count |
|---|---:|
| `beer` | 10 |
| `brandy_cognac` | 10 |
| `cocktail` | 10 |
| `gin` | 10 |
| `liqueur` | 10 |
| `rum` | 10 |
| `sake_shochu` | 10 |
| `tequila_mezcal` | 10 |
| `traditional_korean_alcohol` | 10 |
| `vodka` | 10 |
| `whiskey` | 10 |
| `wine` | 10 |

The catalog remains at 10 candidates in each requested category.

## Expansion Strategy

The added candidates prioritize globally recognizable products and drinks that are
realistically likely to appear in Korean bars, pubs, restaurants, bottle shops,
and liquor shops. Each new catalog candidate has a matching flavor profile
candidate and Korean knowledge candidate.

The KRW price passes focused on source-backed Korea retailer/pickup observations
for products already present in the candidate catalog. The first KRW pass added
35 records; the broad pass added 43 more; the May 23 follow-up added 11 more
source-backed observations. The data now has 90 KRW observations in the main
price observation file, with 10 legacy non-KRW records preserved in
`price_observation_legacy_non_kr_candidates.jsonl`. All KRW records remain
explicitly non-live and non-canonical.

Unique KRW price coverage is now 89 of 120 catalog candidates. The remaining 31
unpriced catalog candidates are concentrated in cocktails, wine, rum,
sake/shochu, brandy/cognac, tequila/mezcal, traditional Korean alcohol, and
vodka. Cocktail and venue/menu price evidence remains intentionally excluded
until map/place-owned snapshot semantics are modeled.

## Key Decisions

### Candidate Files Instead Of DB Writes

No staging schema or safe beverage staging importer exists in the repository.
The expansion was therefore written only as candidate files under
`data/beverage/`.

Canonical tables such as `beverage_items`, `flavor_profiles`, and
`recommendation_vectors` were not written.

### RAG Separation

Knowledge candidates are separate from structured catalog and flavor candidate
records. Knowledge text is paraphrased and must not be used as recommendation
ranking logic.

### Flavor Candidate Confidence

Flavor values are candidate estimates based on sourced identity, style,
ingredient, and recipe context. They are not canonical recommendation vectors.
Low-confidence or market-variable details are represented with null fields,
medium confidence, and review notes rather than invented precision.

### Price Treatment

Price observations are rough point-in-time, historical, suggested-retail, Korea
retailer/pickup, search-result, review-card, package, or overseas-direct KRW
references. They are not live offers, venue prices, store inventory truth, or
strict budget-filter evidence. KRW records are intended for reviewer-facing
display and normalization only.

## Source Mix

The source registry favors official producer, official importer/distributor,
official association, and public product catalog sources for catalog/flavor
facts. The KRW price passes added retailer sources for price observation only.
Some lower-confidence rows use Dailyshot search-result or review-card pages when
a direct item page was not quickly available; those rows require SKU and package
review before any importer use.

The May 23 follow-up also corrected source/product URL alignment while adding
rows. For example, Kihya item URLs were checked against visible product titles
before use rather than trusting stale item IDs from earlier notes.

No Kakao Local/Map API source was used.

## Skipped Due Source Uncertainty

| Area | Count | Reason |
|---|---:|---|
| Catalog candidates | 0 | No duplicate/source-uncertain catalog candidate was intentionally added. |
| Price observations | 0 in this follow-up | Only visible source-backed KRW observations were added; products without clear Korea price evidence were left unchanged. Cocktail and venue/menu prices were intentionally skipped because live menu pricing belongs to map/place ownership. |

## Dry-Run Cleanup

The Korea/KRW dry-run validator now reads:

```text
data/beverage/price_observation_candidates.jsonl
```

as the KRW-focused price candidate file. Legacy non-KRW observations are retained
at:

```text
data/beverage/price_observation_legacy_non_kr_candidates.jsonl
```

The Stoli Vodka row now preserves the original Dailyshot search-result price
observation and adds a Dailyshot item-page source for 700ml package-size
evidence. This remains reviewer-facing evidence only, not canonical price truth.

The final warning cleanup aligned two tequila/mezcal candidate IDs with their
slugs and normalized cocktail knowledge candidate `document_type` values. After
the May 23 follow-up, the Korea/KRW dry-run reports 671 accepted rows, 0
warnings, and 0 rejected rows.

## Current Usefulness

This expanded batch is useful for:

- category-breadth review across the 12 requested categories
- staging schema/importer validation with 120 catalog rows
- reviewer triage of flavor vectors and Korean explanation chunks
- reviewer-facing KRW price display experiments for Korea market candidates
- future canonical seed selection after human approval

This batch is not yet sufficient for:

- production recommendation ranking
- strict Korea-specific SKU normalization
- strict price/budget features
- Qdrant indexing
- canonical beverage approval

## Residual Risks

| Risk | Mitigation |
|---|---|
| ABV and bottle size may vary by market | Confirm Korea SKU/import label before canonical import |
| Some source URLs are official broad product/brand pages | Reviewer should confirm exact product page URL before approval |
| Flavor values are candidate estimates | Human review and deterministic import validation required |
| KRW price data is point-in-time retailer data | Normalize package size, SKU, and freshness before UI or scoring use |
| Some KRW sources are search-result or review-card observations | Treat as low-confidence display evidence until direct item page or receipt/source proof is reviewed |
| Cocktail and venue/menu prices are absent | Model map/place-owned snapshot semantics before collecting live menu prices |
| Cocktail ABV depends on recipe and dilution | Keep cocktail ABV null until normalized recipe model exists |
| Staging schema is absent | Implement `recommendation_staging` before DB import |

## Follow-Up Plan

1. Implement beverage staging schema and dry-run importer.
2. Dry-run the expanded 120-candidate batch into local/dev staging only.
3. Human-review candidate identity, ABV, Korea SKU, aliases, and flavor vectors.
4. Promote a reviewed seed subset through a separate canonical import workflow.
5. Continue filling Korea KRW gaps with non-Dailyshot and direct item sources after staging validation exists.

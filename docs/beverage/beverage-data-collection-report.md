# Beverage Data Collection Report

## Summary

Current run ID:

```text
bev_collect_2026_05_22_kr_price_003
```

This price-focused run followed the expanded beverage candidate batch and added
Korea-focused KRW price observations. It updated candidate files only. It did
not write production DB, canonical beverage tables, map/admin/auth/survey DBs,
staging DB, or Qdrant.

All automatic records remain:

```text
needs_review
```

## Counts Before And After

| Lane | Before | Added this run | After |
|---|---:|---:|---:|
| Structured catalog candidates | 25 | 95 | 120 |
| Flavor profile candidates | 25 | 95 | 120 |
| Knowledge/RAG candidates | 25 | 95 | 120 |
| Price observation candidates | 11 | 35 | 46 |
| Source registry rows | 131 | 35 | 166 |
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

The KRW price pass focused on source-backed Korea retailer/pickup observations
for products already present in the candidate catalog. It added 35 new KRW price
records and kept them explicitly non-live and non-canonical.

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

Price observations are rough point-in-time, historical, suggested-retail, or
Korea retailer/pickup references. They are not live offers, venue prices, store
inventory truth, or strict budget-filter evidence. KRW records are intended for
reviewer-facing display and normalization only.

## Source Mix

The source registry favors official producer, official importer/distributor,
official association, and public product catalog sources for catalog/flavor
facts. The KRW price pass added retailer sources for price observation only.

No Kakao Local/Map API source was used.

## Skipped Due Source Uncertainty

| Area | Count | Reason |
|---|---:|---|
| Catalog candidates | 0 | No duplicate/source-uncertain catalog candidate was intentionally added. |
| Price observations | 0 in this KRW pass | Only source-backed KRW observations were added; products without a clear Korea price source were left unchanged. |

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
| Cocktail ABV depends on recipe and dilution | Keep cocktail ABV null until normalized recipe model exists |
| Staging schema is absent | Implement `recommendation_staging` before DB import |

## Follow-Up Plan

1. Implement beverage staging schema and dry-run importer.
2. Dry-run the expanded 120-candidate batch into local/dev staging only.
3. Human-review candidate identity, ABV, Korea SKU, aliases, and flavor vectors.
4. Promote a reviewed seed subset through a separate canonical import workflow.
5. Add more Korea KRW observations for sake/shochu, rum, cognac, and liqueur gaps after staging validation exists.

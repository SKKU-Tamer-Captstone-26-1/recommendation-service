# Beverage Data Collection Report

## Summary

Current run ID:

```text
bev_collect_2026_05_22_mvp_expansion_002
```

This expansion run continued the beverage data collector output because the
first batch was too small for useful recommendation catalog breadth. It expanded
candidate files only. It did not write production DB, canonical beverage tables,
map/admin/auth/survey DBs, staging DB, or Qdrant.

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
| Price observation candidates | 10 | 1 | 11 |
| Source registry rows | 36 | 95 | 131 |
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

The expansion reached 10 candidates in each requested category.

## Expansion Strategy

The added candidates prioritize globally recognizable products and drinks that are
realistically likely to appear in Korean bars, pubs, restaurants, bottle shops,
and liquor shops. Each new catalog candidate has a matching flavor profile
candidate and Korean knowledge candidate.

Price collection was intentionally conservative. Only one additional price
observation was added, for `Kuro Kirishima`, where the official producer page
provided suggested retail context. Other candidate prices were skipped instead of
using unstable live retailer prices or unsourced estimates.

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

Price observations are rough point-in-time, historical, or suggested-retail
references. They are not live offers, venue prices, store inventory truth, or
strict budget-filter evidence.

## Source Mix

The source registry favors official producer, official importer/distributor,
official association, and public product catalog sources. Retailer sources were
not expanded in this run.

No Kakao Local/Map API source was used.

## Skipped Due Source Uncertainty

| Area | Count | Reason |
|---|---:|---|
| Catalog candidates | 0 | No duplicate/source-uncertain catalog candidate was intentionally added. |
| Price observations | 94 | Skipped rather than creating unstable live-retailer or unsourced price records. |

## Current Usefulness

This expanded batch is useful for:

- category-breadth review across the 12 requested categories
- staging schema/importer validation with 120 catalog rows
- reviewer triage of flavor vectors and Korean explanation chunks
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
| Price data is sparse | Add dated retailer/official price observations in a separate price-focused batch |
| Cocktail ABV depends on recipe and dilution | Keep cocktail ABV null until normalized recipe model exists |
| Staging schema is absent | Implement `recommendation_staging` before DB import |

## Follow-Up Plan

1. Implement beverage staging schema and dry-run importer.
2. Dry-run the expanded 120-candidate batch into local/dev staging only.
3. Human-review candidate identity, ABV, Korea SKU, aliases, and flavor vectors.
4. Promote a reviewed seed subset through a separate canonical import workflow.
5. Run a price-focused collection pass only with dated, source-backed price evidence.

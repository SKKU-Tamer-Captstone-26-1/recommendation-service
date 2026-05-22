# Beverage Source Policy

## Purpose

This document defines the source policy for beverage candidate collection under
`data/beverage/`.

The files created by the beverage data collector are candidate artifacts, not
canonical approval records. Canonical import must use a separate review and
staging workflow.

## Source Priority

Use sources in this order:

| Priority | Source type | Allowed use |
|---:|---|---|
| 1 | `official_producer` | Identity, ABV, origin, producer tasting context, serving guidance |
| 2 | `official_importer_or_distributor` | Market-specific SKU, ABV, bottle size, Korea availability hints |
| 3 | `official_institution_or_association` | Cocktail definitions, appellation/category context, public price lists |
| 4 | `public_data` | Supporting metadata when usage rights are clear |
| 5 | `retailer` | Rough price observation and package-size support only |
| 6 | `blog_review` | Low-confidence flavor support only after stronger source exists |
| 7 | `community_review` | Exploratory hints only; never authoritative alone |

## Candidate Status

Automatically collected records must use:

```text
needs_review
```

Use `collected` only when a record is incomplete and not ready for reviewer
triage.

Never mark a candidate as:

```text
approved
```

without a human/operator approval workflow.

## Copyright Rules

Do not store full source pages, full articles, or long copied source text.

Allowed:

- source URL
- source title
- short paraphrased summary
- short factual metadata such as ABV, country, producer, and bottle size

Disallowed:

- long product descriptions copied from producer pages
- review text copied from blogs or communities
- full cocktail recipe pages copied into RAG candidates
- retailer page text copied into price records

## Flavor Candidate Rules

Flavor vectors are candidate estimates.

Rules:

- Use 0.0 to 1.0 values.
- Keep weakly evidenced dimensions at lower confidence.
- Use lower `flavor_confidence_overall` when source notes are generic.
- Preserve `source_urls` and an `evidence_summary`.
- Do not treat candidate vectors as canonical recommendation vectors.

## Price Observation Rules

Price observations are not live offers.

Rules:

- Store `market_region`, `currency`, `price_type`, `observed_at`, and
  `retrieved_at`.
- Prefer official price lists or dated press references when available.
- Retailers are allowed only as point-in-time rough observations.
- Do not compare budgets strictly from these records.
- Do not store venue/menu/live store prices as beverage catalog truth.

## Kakao Rule

Do not use Kakao Local/Map API data for beverage catalog collection.

Kakao data may support realtime place display or linking in approved map/place
flows, but it must not become beverage catalog source material.

## RAG Boundary

Beverage knowledge candidates may support explanations and education.

They must not be used as:

- recommendation ranking logic
- current inventory truth
- live price truth
- venue existence truth
- map/place status truth

Recommendation ranking must use structured catalog data, structured flavor
profiles, versioned scoring configuration, and deterministic reason codes.

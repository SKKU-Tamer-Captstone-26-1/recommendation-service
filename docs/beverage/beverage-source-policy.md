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
- After human review, KR/KRW observations may populate broad
  `beverage_items.price_min_krw`, `beverage_items.price_max_krw`, and traceable
  catalog metadata for promoted seed beverages.
- Do not compare budgets strictly from these records.
- Do not store venue/menu/live store prices as beverage catalog truth.

## Image Candidate Rules

Beverage display images are catalog display metadata, not recommendation scoring
evidence.

Rules:

- Store only `image_url`, source URL, license, attribution, display policy, and
  review status.
- Do not copy binary image files into this repository.
- Do not use random search-result thumbnails or unlicensed retailer images.
- Do not rely on third-party hotlinking as the production app-display strategy.
  Use the ONTHEBLOCK-managed image cache/CDN when available.
- Prefer public-domain, CC0, or clearly licensed Wikimedia Commons assets for
  MVP representative images.
- A direct product or cocktail representative image may replace the category
  fallback only when the source page provides explicit reusable license,
  attribution, source URL, and review metadata.
- Official marketing packshots, retailer thumbnails, bottle labels, or images
  without clear reusable license still require operator/legal review before
  replacing category representative images.
- Images MUST NOT influence recommendation rank, score, flavor vector, price
  logic, availability, or venue inventory truth.
- If an image license requires attribution, Flutter must preserve a detail or
  credits surface that can show attribution and license metadata.
- Release gate MUST keep active beverage image URL coverage and image license
  metadata coverage at `1.0`. It MUST also keep image cache metadata coverage at
  `1.0`, even when local development still displays the licensed source URL. An
  active beverage without display image metadata is a catalog audit failure, not
  a Flutter fallback responsibility.
- The seed importer MUST reject image candidates that use unapproved source
  types, non-HTTPS URLs, unsupported image kinds, missing attribution metadata,
  unknown `beverage_candidate_id` values, direct image category mismatches, or
  duplicate category/direct image mappings.
- Before releases that expose beverage images in Flutter, operators SHOULD run
  the optional beverage image URL smoke to verify third-party image hosts still
  return an `image/*` response. This check is intentionally not part of the
  deterministic default release gate because external hosts can be temporarily
  unavailable.
- Before using a managed image CDN URL, operators SHOULD generate the beverage
  image cache export manifest. The manifest preserves original image URL,
  source URL, license, attribution, cache key, and connected beverage catalog
  keys so the CDN object tree remains traceable to reviewed source metadata.

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

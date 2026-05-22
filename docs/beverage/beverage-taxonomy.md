# Beverage Taxonomy

## Purpose

This document defines the candidate taxonomy used by beverage data collection.

It is a staging taxonomy for review and import planning. It does not change the
canonical database schema.

## Category Values

Use these category values in candidate files:

| Category | Meaning | Current coverage |
|---|---|---:|
| `whiskey` | Whisky and whiskey across Scotch, bourbon, Irish, Japanese, and other major styles | 10 |
| `wine` | Still, sparkling, fortified, and dessert wine | 10 |
| `beer` | Lager, ale, stout, wheat beer, IPA, and related beer styles | 10 |
| `cocktail` | Standardized drink archetypes, not one bar's live menu item | 10 |
| `traditional_korean_alcohol` | Korean soju, makgeolli, yakju, cheongju, fruit wine, and related traditional alcohol | 10 |
| `sake_shochu` | Japanese sake, shochu, awamori, and adjacent styles | 10 |
| `gin` | Distilled gin, London dry gin, contemporary gin | 10 |
| `rum` | White, aged, dark, agricole, and spiced rum | 10 |
| `tequila_mezcal` | Tequila, mezcal, and agave spirits | 10 |
| `vodka` | Neutral and flavored vodka | 10 |
| `brandy_cognac` | Brandy, Cognac, Armagnac, Calvados, and related aged fruit spirits | 10 |
| `liqueur` | Sweetened liqueurs, cream liqueurs, coffee liqueurs, amari, orange liqueurs | 10 |

## Style and Substyle Guidance

`category` is broad and stable. Use `style` and `substyle` for recommendation
or filter detail.

Examples:

| Category | Style | Substyle |
|---|---|---|
| `whiskey` | `single malt scotch whisky` | `peated Islay whisky` |
| `whiskey` | `bourbon` | `Kentucky straight bourbon` |
| `wine` | `white wine` | `Sauvignon Blanc` |
| `beer` | `stout` | `Irish dry stout` |
| `cocktail` | `classic cocktail` | `bitter stirred aperitif` |
| `traditional_korean_alcohol` | `makgeolli` | `fresh rice wine` |
| `sake_shochu` | `sake` | `junmai daiginjo` |
| `gin` | `London dry gin` | `juniper-forward dry gin` |
| `rum` | `aged rum` | `Jamaican blended rum` |
| `tequila_mezcal` | `mezcal` | `Espadin mezcal` |
| `vodka` | `vodka` | `French wheat vodka` |
| `brandy_cognac` | `cognac` | `VSOP cognac` |
| `liqueur` | `coffee liqueur` | `rum-based coffee liqueur` |

## Naming Rules

Canonical display name:

- Use English proper noun as `canonical_name_en`.
- Use Korean localized display as `display_name_ko`.
- Keep Korean brand names as canonical when the beverage itself is Korean.
- Preserve common menu spelling variants in aliases.
- Do not invent aliases without a normalization reason.

Slug rule:

```text
lowercase ASCII words joined by underscores
```

Candidate ID rule:

```text
bev_cand_<category>_<beverage_slug>
```

## Vector Relationship

Candidate flavor files use:

```text
beverage_vector_v1_candidate
```

This extends `taste_v1` but does not replace it.

The required `taste_v1` compatibility dimensions are:

```text
sweet
fruity
dried_fruit
woody
smoky
nutty
floral
spicy
herbal
body
acidity
carbonation
alcohol_intensity
bitterness
tannin
roasted
```

Extended beverage dimensions are:

```text
citrus
tropical_fruit
red_fruit
vanilla
caramel
earthy
mineral
savory
salinity
peat
oak
creaminess
finish_length
complexity
beginner_friendly
serving_versatility
```

Canonical `recommendation_vectors` must still follow the repository's versioned
`taste_v1` contract unless a future reviewed migration adds a new vector schema.

## Review Checklist

Before canonical import:

- Confirm category, style, and substyle.
- Confirm primary English and Korean display names.
- Confirm ABV and bottle size for the target Korea SKU when available.
- Check aliases against realistic Korean menu/store spellings.
- Review flavor vector values and dimension confidence.
- Decide whether price observations are excluded, stored as source evidence, or
  transformed into broad non-live price ranges.

from dataclasses import dataclass


@dataclass(frozen=True)
class VectorDimension:
    index: int
    name: str
    meaning: str


# Keep this aligned with docs/recommendation/vector-schema.md.
TASTE_V1_NAME = "taste_v1"
TASTE_V1_DISTANCE_METRIC = "cosine"
TASTE_V1_VALUE_MIN = 0.0
TASTE_V1_VALUE_MAX = 1.0

TASTE_V1_DIMENSIONS: tuple[VectorDimension, ...] = (
    VectorDimension(0, "sweet", "Sweetness, dessert-like notes, sugar impression"),
    VectorDimension(1, "fruity", "Fresh fruit, citrus, berry, tropical fruit"),
    VectorDimension(2, "dried_fruit", "Raisin, fig, date, jam, dark fruit"),
    VectorDimension(3, "woody", "Oak, barrel, cedar, wood spice"),
    VectorDimension(4, "smoky", "Smoke, peat, char, roasted smoke"),
    VectorDimension(5, "nutty", "Almond, hazelnut, walnut, grain nuttiness"),
    VectorDimension(6, "floral", "Flowers, perfume, delicate aromatics"),
    VectorDimension(7, "spicy", "Baking spice, pepper, warm spice"),
    VectorDimension(8, "herbal", "Mint, herbs, botanical notes"),
    VectorDimension(9, "body", "Weight, richness, mouthfeel"),
    VectorDimension(10, "acidity", "Tartness, sourness, brightness"),
    VectorDimension(11, "carbonation", "Sparkle, fizz, effervescence"),
    VectorDimension(12, "alcohol_intensity", "Heat, spirit-forward strength"),
    VectorDimension(13, "bitterness", "Hop bitterness, bitter finish"),
    VectorDimension(14, "tannin", "Drying grip, wine structure"),
    VectorDimension(15, "roasted", "Coffee, cocoa, toast, roasted malt"),
)

TASTE_V1_DIMENSION_COUNT = len(TASTE_V1_DIMENSIONS)


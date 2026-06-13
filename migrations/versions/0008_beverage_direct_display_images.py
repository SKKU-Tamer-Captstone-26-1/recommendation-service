"""beverage direct display image metadata

Revision ID: 0008_beverage_direct_images
Revises: 0007_scoring_v3
Create Date: 2026-06-07

Title: beverage direct display image metadata
Reason: Backfill license-aware direct image metadata for selected canonical
beverages where Wikimedia Commons has a source-checked product or cocktail
representative asset. Remaining beverages keep the existing category fallback.
Affected tables: beverage_items.
Affected docs: docs/recommendation/beverage-catalog.md,
docs/beverage/beverage-source-policy.md, docs/api/flutter-handoff.md,
docs/plans/035.md.
Backward compatibility: metadata_json-only update; protobuf and recommendation
ranking semantics remain unchanged.
Backfill required: yes. Selected active beverage rows receive direct image
metadata based on metadata_json.source_candidate_id.
Rollback strategy: restore beverage_image_v1 category representative image
metadata for rows touched by this migration.
Rebuild impact: none for vectors or scoring.
Qdrant impact: none.
Operational risk: low. Some direct images require attribution in app details or
credits surfaces.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op

revision: str = "0008_beverage_direct_images"
down_revision: str | None = "0007_scoring_v3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DIRECT_IMAGE_BY_CANDIDATE_ID: dict[str, dict[str, object]] = {
    "bev_cand_whiskey_buffalo_trace_bourbon": {
        "image_candidate_id": "bev_image_whiskey_buffalo_trace_bourbon_product_001",
        "category": "whiskey",
        "image_kind": "licensed_product_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Buffalo_Trace_bourbon_whiskey.jpg",
        "alt_text_ko": "버팔로 트레이스 버번 병 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Buffalo_Trace_bourbon_whiskey.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY 2.0",
        "license_url": "https://creativecommons.org/licenses/by/2.0/",
        "attribution": "Rick Audet / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons product representative image.",
    },
    "bev_cand_whiskey_jameson_irish_whiskey": {
        "image_candidate_id": "bev_image_whiskey_jameson_irish_whiskey_product_001",
        "category": "whiskey",
        "image_kind": "licensed_product_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Glass_of_Jamesons.jpg",
        "alt_text_ko": "제임슨 위스키 잔 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Glass_of_Jamesons.jpg",
        "source_type": "wikimedia_commons",
        "license": "Public Domain",
        "license_url": "https://commons.wikimedia.org/wiki/File:Glass_of_Jamesons.jpg",
        "attribution": "Chris huh / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons product representative image.",
    },
    "bev_cand_beer_guinness_draught": {
        "image_candidate_id": "bev_image_beer_guinness_draught_product_001",
        "category": "beer",
        "image_kind": "licensed_product_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Guinness_Draught.jpg",
        "alt_text_ko": "기네스 드래프트 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Guinness_Draught.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "attribution": "FakirNL / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons product representative image.",
    },
    "bev_cand_beer_asahi_super_dry": {
        "image_candidate_id": "bev_image_beer_asahi_super_dry_product_001",
        "category": "beer",
        "image_kind": "licensed_product_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Asahi_Super_Dry.jpg",
        "alt_text_ko": "아사히 슈퍼 드라이 병 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Asahi_Super_Dry.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "attribution": "Uttamstef12 / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons product representative image.",
    },
    "bev_cand_beer_heineken_original": {
        "image_candidate_id": "bev_image_beer_heineken_original_product_001",
        "category": "beer",
        "image_kind": "licensed_product_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Heineken_Bottle.jpg",
        "alt_text_ko": "하이네켄 병 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Heineken_Bottle.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "attribution": "Uttamstef12 / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons product representative image.",
    },
    "bev_cand_beer_corona_extra": {
        "image_candidate_id": "bev_image_beer_corona_extra_product_001",
        "category": "beer",
        "image_kind": "licensed_product_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Corona_Extra_bottle.jpg",
        "alt_text_ko": "코로나 엑스트라 병 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Corona_Extra_bottle.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "attribution": "Kimjon12 / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons product representative image.",
    },
    "bev_cand_liqueur_cointreau": {
        "image_candidate_id": "bev_image_liqueur_cointreau_product_001",
        "category": "liqueur",
        "image_kind": "licensed_product_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Liqueur_cointreau.jpg",
        "alt_text_ko": "코앵트로 리큐르 병 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Liqueur_cointreau.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 3.0 / GFDL",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "attribution": "Christian Horvat / VisualBeo / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons product representative image.",
    },
    "bev_cand_cocktail_negroni": {
        "image_candidate_id": "bev_image_cocktail_negroni_drink_001",
        "category": "cocktail",
        "image_kind": "licensed_cocktail_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Negroni_with_ingredients.jpg",
        "alt_text_ko": "네그로니 칵테일 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Negroni_with_ingredients.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 3.0 DE",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en",
        "attribution": "Achim Schleuning / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons cocktail representative image.",
    },
    "bev_cand_cocktail_margarita": {
        "image_candidate_id": "bev_image_cocktail_margarita_drink_001",
        "category": "cocktail",
        "image_kind": "licensed_cocktail_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Margarita.jpg",
        "alt_text_ko": "마가리타 칵테일 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Margarita.jpg",
        "source_type": "wikimedia_commons",
        "license": "Public Domain",
        "license_url": "https://commons.wikimedia.org/wiki/File:Margarita.jpg",
        "attribution": "Jon Sullivan / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons cocktail representative image.",
    },
    "bev_cand_cocktail_dry_martini": {
        "image_candidate_id": "bev_image_cocktail_dry_martini_drink_001",
        "category": "cocktail",
        "image_kind": "licensed_cocktail_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Dry_martini.jpg",
        "alt_text_ko": "드라이 마티니 칵테일 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Dry_martini.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "attribution": "Arnaud 25 / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons cocktail representative image.",
    },
    "bev_cand_cocktail_mojito": {
        "image_candidate_id": "bev_image_cocktail_mojito_drink_001",
        "category": "cocktail",
        "image_kind": "licensed_cocktail_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Standard_version_of_Mojito_Cocktail.jpg",
        "alt_text_ko": "모히토 칵테일 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Standard_version_of_Mojito_Cocktail.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY 2.0",
        "license_url": "https://creativecommons.org/licenses/by/2.0/",
        "attribution": "soyculto / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons cocktail representative image.",
    },
    "bev_cand_cocktail_daiquiri": {
        "image_candidate_id": "bev_image_cocktail_daiquiri_drink_001",
        "category": "cocktail",
        "image_kind": "licensed_cocktail_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Daiquiri_drink.jpg",
        "alt_text_ko": "다이키리 칵테일 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Daiquiri_drink.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 2.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/2.0/",
        "attribution": "Aaron Gustafson / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Licensed Commons cocktail representative image.",
    },
}

CATEGORY_IMAGE_BY_CATEGORY: dict[str, dict[str, object]] = {
    "whiskey": {
        "image_candidate_id": "bev_image_whiskey_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Glass_of_whisky.jpg",
        "alt_text_ko": "위스키 잔 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Glass_of_whisky.jpg",
        "source_type": "wikimedia_commons",
        "license": "Public Domain",
        "license_url": "https://commons.wikimedia.org/wiki/File:Glass_of_whisky.jpg",
        "attribution": "Chris huh / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image; not product-specific bottle art.",
    },
    "beer": {
        "image_candidate_id": "bev_image_beer_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Pint_Glass_%28Pub%29.svg",
        "alt_text_ko": "맥주 잔 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Pint_Glass_(Pub).svg",
        "source_type": "wikimedia_commons",
        "license": "CC0 1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/deed.en",
        "attribution": "Will Murray / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": (
            "Category representative image; not product-specific can or bottle art."
        ),
    },
    "cocktail": {
        "image_candidate_id": "bev_image_cocktail_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Margarita.jpg",
        "alt_text_ko": "칵테일 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Margarita.jpg",
        "source_type": "wikimedia_commons",
        "license": "Public Domain",
        "license_url": "https://commons.wikimedia.org/wiki/File:Margarita.jpg",
        "attribution": "Jon Sullivan / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image for cocktail recommendations.",
    },
    "liqueur": {
        "image_candidate_id": "bev_image_liqueur_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Liqueur_glass_MET_69747.jpg",
        "alt_text_ko": "리큐르 잔 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Liqueur_glass_MET_69747.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC0 1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/deed.en",
        "attribution": "Metropolitan Museum of Art / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image; not product-specific bottle art.",
    },
}


def upgrade() -> None:
    for candidate_id, image in DIRECT_IMAGE_BY_CANDIDATE_ID.items():
        payload = _image_payload(image)
        _update_image_for_candidate(
            candidate_id=candidate_id,
            image_candidate_id=str(image["image_candidate_id"]),
            payload=payload,
            protect_operator_approved=True,
        )


def downgrade() -> None:
    for candidate_id, image in DIRECT_IMAGE_BY_CANDIDATE_ID.items():
        category_image = CATEGORY_IMAGE_BY_CATEGORY[str(image["category"])]
        _update_image_for_candidate(
            candidate_id=candidate_id,
            image_candidate_id=str(image["image_candidate_id"]),
            payload=_image_payload(category_image),
            protect_operator_approved=False,
        )


def _update_image_for_candidate(
    *,
    candidate_id: str,
    image_candidate_id: str,
    payload: dict[str, object],
    protect_operator_approved: bool,
) -> None:
    payload_json = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ": "),
    )
    if protect_operator_approved:
        review_guard = (
            "AND COALESCE(metadata_json->'image'->>'review_status', '') "
            "<> 'operator_approved'"
        )
    else:
        review_guard = (
            "AND metadata_json->'image'->>'image_candidate_id' = "
            f"'{image_candidate_id}'"
        )
    op.execute(
        f"""
        UPDATE beverage_items
        SET metadata_json = COALESCE(metadata_json, '{{}}'::jsonb)
            || $${payload_json}$$::jsonb,
            updated_at = now()
        WHERE active IS TRUE
          AND metadata_json->>'source_candidate_id' = '{candidate_id}'
          AND (
            metadata_json->>'image_policy_version' IS NULL
            OR metadata_json->>'image_policy_version' = 'beverage_image_v1'
          )
          {review_guard}
        """
    )


def _image_payload(image: dict[str, object]) -> dict[str, object]:
    nested = {
        "policy_version": "beverage_image_v1",
        **{key: value for key, value in image.items() if key != "category"},
    }
    return {
        "image": nested,
        "image_url": image["image_url"],
        "image_alt_text_ko": image["alt_text_ko"],
        "image_source_url": image["source_url"],
        "image_license": image["license"],
        "image_attribution": image["attribution"],
        "image_display_policy": image["display_policy"],
        "image_kind": image["image_kind"],
        "image_review_status": image["review_status"],
        "image_policy_version": "beverage_image_v1",
    }

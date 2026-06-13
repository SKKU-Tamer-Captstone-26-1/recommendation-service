"""beverage display image metadata

Revision ID: 0006_beverage_images
Revises: 0005_scoring_v2
Create Date: 2026-06-07

Title: beverage display image metadata
Reason: Add traceable, license-aware representative image metadata to active
beverage catalog rows so Flutter can display recommendation cards without
changing the protobuf schema.
Affected tables: beverage_items.
Affected docs: docs/recommendation/beverage-catalog.md,
docs/beverage/beverage-source-policy.md, docs/api/recommendation-api.md,
docs/api/flutter-handoff.md, docs/plans/017.md.
Backward compatibility: metadata_json-only backfill; existing columns and
recommendation ranking semantics remain unchanged.
Backfill required: yes. Active beverage rows receive category representative
image metadata when no newer image policy is present.
Rollback strategy: remove beverage_image_v1 metadata keys from beverage_items.
Rebuild impact: none for vectors or scoring. Re-running the beverage importer
will restore the same image metadata from image_candidates.jsonl.
Qdrant impact: none.
Operational risk: low. Some image licenses require app-level attribution in
details or credits surfaces.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op

revision: str = "0006_beverage_images"
down_revision: str | None = "0005_scoring_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


IMAGE_BY_CATEGORY: dict[str, dict[str, object]] = {
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
    "wine": {
        "image_candidate_id": "bev_image_wine_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/White_Wine_Glass.jpg",
        "alt_text_ko": "와인 잔 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:White_Wine_Glass.jpg",
        "source_type": "wikimedia_commons",
        "license": "Public Domain",
        "license_url": "https://commons.wikimedia.org/wiki/File:White_Wine_Glass.jpg",
        "attribution": "Jon Sullivan / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image; not vintage-specific bottle art.",
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
        "notes": "Category representative image; not product-specific can or bottle art.",
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
    "brandy_cognac": {
        "image_candidate_id": "bev_image_brandy_cognac_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Cognac_glass.jpg",
        "alt_text_ko": "코냑 잔 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Cognac_glass.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "attribution": "Didier Descouens / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image; attribution should be visible in app credits.",
    },
    "gin": {
        "image_candidate_id": "bev_image_gin_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Gin_Tonic_4.jpg",
        "alt_text_ko": "진 토닉 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Gin_Tonic_4.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 3.0 DE",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/de/deed.en",
        "attribution": "Achim Schleuning / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image; contains a branded gin bottle.",
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
    "rum": {
        "image_candidate_id": "bev_image_rum_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/A_glass_of_rum.jpg",
        "alt_text_ko": "럼 잔 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:A_glass_of_rum.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY 2.0",
        "license_url": "https://creativecommons.org/licenses/by/2.0/",
        "attribution": "Linus Bohman / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image; attribution should be visible in app credits.",
    },
    "sake_shochu": {
        "image_candidate_id": "bev_image_sake_shochu_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Japanese_sake_glass_and_flask.jpg",
        "alt_text_ko": "사케 잔과 도쿠리 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Japanese_sake_glass_and_flask.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "attribution": "Wikimedia Commons contributor / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image for sake/shochu recommendations.",
    },
    "tequila_mezcal": {
        "image_candidate_id": "bev_image_tequila_mezcal_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Tequila_shot.jpg",
        "alt_text_ko": "데킬라 샷 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Tequila_shot.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 2.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/2.0/",
        "attribution": "Kim S / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image for tequila/mezcal recommendations.",
    },
    "traditional_korean_alcohol": {
        "image_candidate_id": "bev_image_traditional_korean_alcohol_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Korean_rice_wine_Makgeori01.jpg",
        "alt_text_ko": "막걸리 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Korean_rice_wine_Makgeori01.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "attribution": "Mar del Este / Wikimedia Commons",
        "attribution_required": True,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image for traditional Korean alcohol recommendations.",
    },
    "vodka": {
        "image_candidate_id": "bev_image_vodka_category_representative_001",
        "image_kind": "category_representative",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Vodka_bottle.jpg",
        "alt_text_ko": "보드카 병 대표 이미지",
        "source_url": "https://commons.wikimedia.org/wiki/File:Vodka_bottle.jpg",
        "source_type": "wikimedia_commons",
        "license": "CC0 1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/deed.en",
        "attribution": "Tetzemann / Wikimedia Commons",
        "attribution_required": False,
        "display_policy": "allowed_mvp_display_with_license_metadata",
        "review_status": "source_checked_mvp_seed",
        "notes": "Category representative image; not brand-specific for catalog candidates.",
    },
}


def upgrade() -> None:
    for category, image in IMAGE_BY_CATEGORY.items():
        payload = _image_payload(image)
        payload_json = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ": "),
        )
        op.execute(
            f"""
            UPDATE beverage_items
            SET metadata_json = metadata_json || $${payload_json}$$::jsonb,
                updated_at = now()
            WHERE category = '{category}'
              AND active IS TRUE
              AND (
                metadata_json->>'image_policy_version' IS NULL
                OR metadata_json->>'image_policy_version' = 'beverage_image_v1'
              )
            """
        )


def downgrade() -> None:
    op.execute(
        """
        UPDATE beverage_items
        SET metadata_json = metadata_json
            - 'image'
            - 'image_url'
            - 'image_alt_text_ko'
            - 'image_source_url'
            - 'image_license'
            - 'image_attribution'
            - 'image_display_policy'
            - 'image_kind'
            - 'image_review_status'
            - 'image_policy_version',
            updated_at = now()
        WHERE metadata_json->>'image_policy_version' = 'beverage_image_v1'
        """
    )


def _image_payload(image: dict[str, object]) -> dict[str, object]:
    nested = {
        "policy_version": "beverage_image_v1",
        **image,
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

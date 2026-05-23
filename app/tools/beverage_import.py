"""Import beverage candidates into staging and promote the MVP seed subset."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.db.session import SessionLocal
from app.services.beverage_import import BeverageCandidateImporter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/beverage"))
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--promote-seed", action="store_true")
    args = parser.parse_args()

    if not args.stage and not args.promote_seed:
        parser.error("choose at least one of --stage or --promote-seed")

    with SessionLocal() as session:
        importer = BeverageCandidateImporter(session, args.data_dir)
        if args.stage:
            counts = importer.stage_candidates()
            print(
                "staged "
                f"catalog={counts.catalog_candidates} "
                f"flavor={counts.flavor_candidates} "
                f"knowledge={counts.knowledge_candidates} "
                f"price={counts.price_candidates} "
                f"sources={counts.source_refs}",
            )
        if args.promote_seed:
            counts = importer.promote_seed_subset()
            print(
                "promoted "
                f"beverages={counts.canonical_beverages} "
                f"flavor_profiles={counts.canonical_flavor_profiles} "
                f"vectors={counts.canonical_vectors}",
            )
        session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

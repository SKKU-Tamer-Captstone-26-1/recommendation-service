"""Export recommendation-owned logs into an offline ML training dataset."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from app.db.session import SessionLocal
from app.services.training_dataset_export import (
    export_training_dataset,
    write_training_dataset_export,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_time", default=None)
    parser.add_argument("--to", dest="to_time", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", choices=("jsonl",), default="jsonl")
    args = parser.parse_args()

    with SessionLocal() as session:
        export = export_training_dataset(
            session,
            from_time=_parse_time(args.from_time),
            to_time=_parse_time(args.to_time),
        )
    output_dir = Path(args.output)
    write_training_dataset_export(export, output_dir)
    print(
        "training dataset export "
        f"records={export.record_count} "
        f"dataset_hash={export.dataset_hash} "
        f"format={export.format} "
        f"output={output_dir}",
    )
    return 0


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())

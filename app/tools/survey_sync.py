"""Run one survey-service sync page into derived recommendation profiles."""

from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.services.survey_sync import HttpSurveySyncClient, SurveySyncService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-name", default="survey-service")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    with SessionLocal() as session:
        sync = SurveySyncService(session, HttpSurveySyncClient())
        try:
            result = sync.sync_once(source_name=args.source_name, limit=args.limit)
            session.commit()
        except Exception:
            session.rollback()
            raise

    print(
        "survey sync "
        f"source={result.source_name} "
        f"previous_cursor={result.previous_cursor} "
        f"next_cursor={result.next_cursor} "
        f"has_more={result.has_more} "
        f"watermark={result.event_watermark} "
        f"events={result.events_received} "
        f"processed={result.events_processed} "
        f"duplicates={result.duplicate_events} "
        f"profiles={result.profiles_processed} "
        f"revoked={result.revoked_events} "
        f"schema={result.schema_events} "
        f"dead_letters={result.dead_letter_events} "
        f"retries={result.retry_events}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

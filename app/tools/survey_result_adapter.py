"""Generate a derived profile from the deployed survey-service result RPC."""

from __future__ import annotations

import argparse
import os

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.profile_generation import ProfileGenerationService, SurveyProfileInput
from app.services.survey_sync import SurveyResultGrpcAdapterClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-user-id")
    parser.add_argument("--survey-response-id")
    parser.add_argument(
        "--grpc-addr",
        default=os.environ.get("SURVEY_SERVICE_GRPC_ADDR"),
    )
    parser.add_argument(
        "--bearer-token",
        default=os.environ.get("SURVEY_SERVICE_GRPC_AUTH_BEARER_TOKEN"),
    )
    parser.add_argument(
        "--plaintext",
        action="store_true",
        help="Use plaintext gRPC. Defaults to TLS for :443 targets.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.grpc_addr:
        raise SystemExit("SURVEY_SERVICE_GRPC_ADDR or --grpc-addr is required")
    if bool(args.external_user_id) == bool(args.survey_response_id):
        raise SystemExit(
            "set exactly one of --external-user-id or --survey-response-id",
        )

    settings = get_settings()
    client = SurveyResultGrpcAdapterClient(
        address=args.grpc_addr,
        use_tls=False if args.plaintext else None,
        bearer_token=args.bearer_token,
        timeout_seconds=settings.survey_request_timeout_seconds,
    )
    if args.external_user_id:
        response = client.get_survey_result_by_user(
            external_user_id=args.external_user_id,
        )
    else:
        response = client.get_survey_result(
            survey_response_id=args.survey_response_id,
        )

    survey_input = SurveyProfileInput(
        survey_response_id=response.survey_response_id,
        external_user_id=response.external_user_id,
        survey_version=response.survey_version,
        response_revision=response.response_revision,
        completed_at=response.completed_at,
        answers=response.answers,
    )

    if args.dry_run:
        print(
            "survey result adapter dry_run "
            f"survey_response_id={survey_input.survey_response_id} "
            f"external_user_id={survey_input.external_user_id} "
            f"categories={','.join(survey_input.answers.get('categories') or [])} "
            f"keywords={','.join(survey_input.answers.get('global_keywords') or [])}",
        )
        return 0

    with SessionLocal() as session:
        try:
            profile = ProfileGenerationService(session).generate_from_survey_input(
                survey_input,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

    print(
        "survey result adapter "
        f"survey_response_id={survey_input.survey_response_id} "
        f"external_user_id={survey_input.external_user_id} "
        f"profile_revision={profile.profile_revision}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

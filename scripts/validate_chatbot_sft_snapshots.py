"""Validate chatbot SFT snapshot fixtures without external dependencies."""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

BASE_DIR = Path("data/chatbot-sft-snapshots")
FIXTURE_DIR = BASE_DIR / "fixtures"
ALLOWED_DATA_TYPES = {
    "beverage_recommendation_explanation",
    "venue_recommendation_explanation",
    "tradeoff_explanation",
    "profile_missing_insufficient_data",
    "out_of_scope_refusal",
}
RECOMMENDATION_DATA_TYPES = {
    "beverage_recommendation_explanation",
    "venue_recommendation_explanation",
    "tradeoff_explanation",
}
TRADEOFF_TYPES = {
    "closer_but_more_expensive",
    "farther_but_cheaper",
    "similar_price_different_atmosphere",
    "better_atmosphere_but_stale_price",
}
SNAPSHOT_ID_PATTERN = re.compile(
    r"^sft_snap_"
    r"(beverage_recommendation_explanation|venue_recommendation_explanation|"
    r"tradeoff_explanation|profile_missing_insufficient_data|"
    r"out_of_scope_refusal)_\d{3}$",
)


class ValidationError(Exception):
    """Raised when a snapshot fixture violates the package contract."""


def main() -> int:
    fixtures = sorted(FIXTURE_DIR.glob("*/*.json"))
    if not fixtures:
        raise ValidationError(f"no fixture JSON files found under {FIXTURE_DIR}")

    counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for path in fixtures:
        payload = _load_json(path)
        data_type = _validate_common(path, payload)
        counts[data_type] += 1
        snapshot_id = payload["snapshot_id"]
        if snapshot_id in seen_ids:
            raise ValidationError(f"{path}: duplicate snapshot_id={snapshot_id}")
        seen_ids.add(snapshot_id)

        if data_type == "beverage_recommendation_explanation":
            _validate_beverage_fixture(path, payload)
        if data_type in RECOMMENDATION_DATA_TYPES:
            _validate_recommendation_fixture(path, payload)
        if data_type == "tradeoff_explanation":
            _validate_tradeoff_fixture(path, payload)
        if data_type == "profile_missing_insufficient_data":
            _validate_insufficient_data_fixture(path, payload)
        if data_type == "out_of_scope_refusal":
            _validate_out_of_scope_fixture(path, payload)

    missing_types = ALLOWED_DATA_TYPES - set(counts)
    if missing_types:
        raise ValidationError(f"missing fixture data types: {sorted(missing_types)}")
    too_few = {data_type: count for data_type, count in counts.items() if count < 5}
    if too_few:
        raise ValidationError(f"fixture count below minimum: {too_few}")

    print("chatbot SFT snapshot validation passed")
    for data_type in sorted(counts):
        print(f"{data_type}: {counts[data_type]}")
    return 0


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fp:
            payload = json.load(fp)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError(f"{path}: fixture must be a JSON object")
    return payload


def _validate_common(path: Path, payload: dict[str, Any]) -> str:
    required = {
        "schema_version",
        "snapshot_id",
        "data_type",
        "created_at",
        "language",
        "fixture_policy",
        "source_policy",
        "user_request",
        "grounded_context",
        "expected_assistant_behavior",
        "human_review",
    }
    missing = required - set(payload)
    if missing:
        raise ValidationError(f"{path}: missing top-level fields {sorted(missing)}")
    if payload["schema_version"] != "chatbot_sft_snapshot_v1":
        raise ValidationError(f"{path}: schema_version must be chatbot_sft_snapshot_v1")
    if payload["language"] != "ko":
        raise ValidationError(f"{path}: language must be ko")
    data_type = payload["data_type"]
    if data_type not in ALLOWED_DATA_TYPES:
        raise ValidationError(f"{path}: invalid data_type={data_type}")
    expected_prefix = f"sft_snap_{data_type}_"
    snapshot_id = payload["snapshot_id"]
    if not SNAPSHOT_ID_PATTERN.match(snapshot_id):
        raise ValidationError(f"{path}: unstable snapshot_id={snapshot_id}")
    if not snapshot_id.startswith(expected_prefix):
        raise ValidationError(f"{path}: snapshot_id does not match data_type")

    policy = payload["fixture_policy"]
    if policy.get("is_synthetic_fixture") is not True:
        raise ValidationError(f"{path}: fixture must be synthetic")
    if policy.get("is_training_example") is not False:
        raise ValidationError(f"{path}: fixture must not be marked training data")
    if policy.get("human_review_required") is not True:
        raise ValidationError(f"{path}: human review must be required")

    review = payload["human_review"]
    if review.get("status") != "draft":
        raise ValidationError(f"{path}: human_review.status must be draft")
    if review.get("reviewer") != "":
        raise ValidationError(f"{path}: human_review.reviewer must be empty")

    context = payload["grounded_context"]
    for field in ("profile", "recommendations", "missing_facts", "used_sources"):
        if field not in context:
            raise ValidationError(f"{path}: grounded_context missing {field}")
    if not isinstance(context["recommendations"], list):
        raise ValidationError(f"{path}: grounded_context.recommendations must be list")
    if not isinstance(context["missing_facts"], list):
        raise ValidationError(f"{path}: grounded_context.missing_facts must be list")
    if not isinstance(context["used_sources"], list):
        raise ValidationError(f"{path}: grounded_context.used_sources must be list")

    behavior = payload["expected_assistant_behavior"]
    for field in (
        "answer_ko",
        "refused",
        "refusal_reason",
        "must_include",
        "must_not_include",
        "preserve_recommendation_order",
        "notes",
    ):
        if field not in behavior:
            raise ValidationError(
                f"{path}: expected_assistant_behavior missing {field}"
            )
    return data_type


def _validate_beverage_fixture(path: Path, payload: dict[str, Any]) -> None:
    for recommendation in payload["grounded_context"]["recommendations"]:
        if recommendation.get("type") != "beverage":
            continue
        for field in ("name_en", "display_name_ko", "canonical_name"):
            if not recommendation.get(field):
                raise ValidationError(
                    f"{path}: beverage recommendation missing {field}"
                )


def _validate_recommendation_fixture(path: Path, payload: dict[str, Any]) -> None:
    recommendations = payload["grounded_context"]["recommendations"]
    if not recommendations:
        raise ValidationError(f"{path}: recommendation fixture must include candidates")
    ranks = []
    for recommendation in recommendations:
        rank = recommendation.get("rank")
        if not isinstance(rank, int) or rank < 1:
            raise ValidationError(f"{path}: recommendation missing valid rank")
        ranks.append(rank)
    if ranks != sorted(ranks):
        raise ValidationError(f"{path}: recommendations must be sorted by rank")
    if ranks != list(range(1, len(ranks) + 1)):
        raise ValidationError(f"{path}: ranks must be contiguous from 1")
    behavior = payload["expected_assistant_behavior"]
    if behavior.get("preserve_recommendation_order") is not True:
        raise ValidationError(f"{path}: expected answer must preserve ranking")


def _validate_tradeoff_fixture(path: Path, payload: dict[str, Any]) -> None:
    tradeoff_types = {
        recommendation.get("tradeoff_type")
        for recommendation in payload["grounded_context"]["recommendations"]
    }
    if not tradeoff_types & TRADEOFF_TYPES:
        raise ValidationError(
            f"{path}: tradeoff fixture missing supported tradeoff_type"
        )


def _validate_insufficient_data_fixture(path: Path, payload: dict[str, Any]) -> None:
    if not payload["grounded_context"]["missing_facts"]:
        raise ValidationError(f"{path}: insufficient-data fixture needs missing_facts")
    behavior = payload["expected_assistant_behavior"]
    if behavior.get("refused") is not True:
        raise ValidationError(f"{path}: insufficient-data fixture must refuse")
    if not behavior.get("refusal_reason"):
        raise ValidationError(f"{path}: insufficient-data refusal_reason required")


def _validate_out_of_scope_fixture(path: Path, payload: dict[str, Any]) -> None:
    if payload["grounded_context"]["recommendations"]:
        raise ValidationError(
            f"{path}: out-of-scope fixture must not include recommendations"
        )
    behavior = payload["expected_assistant_behavior"]
    if behavior.get("refused") is not True:
        raise ValidationError(f"{path}: out-of-scope fixture must refuse")
    if not behavior.get("refusal_reason"):
        raise ValidationError(f"{path}: out-of-scope refusal_reason required")


if __name__ == "__main__":
    raise SystemExit(main())

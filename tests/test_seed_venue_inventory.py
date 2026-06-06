import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from scripts.seed_venue_inventory import resolve_beverage_names


def test_resolve_beverage_names_uses_active_catalog_ids() -> None:
    beverage_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    session = MagicMock(spec=Session)
    session.scalars.return_value = [
        SimpleNamespace(
            name_en="The Macallan 12 Years Double Cask",
            id=beverage_id,
        ),
    ]
    event = {
        "inventory": [
            {
                "inventory_revision": "inv_rev_1",
                "beverage_name_en": "The Macallan 12 Years Double Cask",
                "availability_status": "available",
                "confidence": 0.9,
            },
        ],
    }

    resolved = resolve_beverage_names(session, event)

    assert resolved["inventory"][0]["beverage_item_id"] == str(beverage_id)
    assert resolved["inventory"][0]["source_beverage_id"] == (
        "The Macallan 12 Years Double Cask"
    )
    assert "beverage_item_id" not in event["inventory"][0]


def test_resolve_beverage_names_rejects_unknown_fixture_name() -> None:
    session = MagicMock(spec=Session)
    session.scalars.return_value = []

    with pytest.raises(ValueError, match="active beverage not found"):
        resolve_beverage_names(
            session,
            {
                "inventory": [
                    {
                        "inventory_revision": "inv_rev_1",
                        "beverage_name_en": "Missing Bottle",
                        "availability_status": "available",
                        "confidence": 0.9,
                    },
                ],
            },
        )

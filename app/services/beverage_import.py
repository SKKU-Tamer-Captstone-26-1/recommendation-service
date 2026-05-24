from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.vector_schema import TASTE_V1_DIMENSIONS, TASTE_V1_NAME
from app.models.catalog import BeverageItem, FlavorProfile
from app.models.enums import FlavorProfileOwnerType, VectorOwnerType
from app.models.staging import (
    BeverageCatalogCandidate,
    BeverageCollectionRun,
    BeverageFlavorProfileCandidate,
    BeverageKnowledgeCandidate,
    BeveragePriceObservationCandidate,
    BeverageSourceRef,
)
from app.models.vector import RecommendationVector
from app.models.versioning import VectorSchemaVersion

SEED_VERSION = "canonical_beverage_seed_v1"
SEED_NAMESPACE = uuid.UUID("6ad0a869-203c-56cb-95b9-c11a9416eb35")
STAGING_NAMESPACE = uuid.UUID("2020c0be-0d4a-53b0-a6cd-37e85f7bffcf")

MVP_SEED_CANDIDATE_IDS: tuple[str, ...] = (
    "bev_cand_beer_guinness_draught",
    "bev_cand_beer_asahi_super_dry",
    "bev_cand_beer_heineken_original",
    "bev_cand_beer_corona_extra",
    "bev_cand_beer_hoegaarden_original_white_ale",
    "bev_cand_brandy_cognac_hennessy_vsop",
    "bev_cand_brandy_cognac_remy_martin_vsop",
    "bev_cand_brandy_cognac_courvoisier_vsop",
    "bev_cand_brandy_cognac_martell_cordon_bleu",
    "bev_cand_brandy_cognac_camus_vsop_cognac",
    "bev_cand_cocktail_negroni",
    "bev_cand_cocktail_margarita",
    "bev_cand_cocktail_dry_martini",
    "bev_cand_cocktail_mojito",
    "bev_cand_cocktail_daiquiri",
    "bev_cand_gin_tanqueray_london_dry_gin",
    "bev_cand_gin_hendricks_gin",
    "bev_cand_gin_beefeater_london_dry_gin",
    "bev_cand_gin_bombay_sapphire_gin",
    "bev_cand_gin_gordon_s_london_dry_gin",
    "bev_cand_liqueur_baileys_original_irish_cream",
    "bev_cand_liqueur_kahlua_original_coffee_liqueur",
    "bev_cand_liqueur_cointreau",
    "bev_cand_liqueur_grand_marnier_cordon_rouge",
    "bev_cand_liqueur_aperol",
    "bev_cand_rum_bacardi_carta_blanca",
    "bev_cand_rum_appleton_estate_signature",
    "bev_cand_rum_havana_club_3_year_old",
    "bev_cand_rum_captain_morgan_original_spiced_gold",
    "bev_cand_rum_mount_gay_eclipse",
    "bev_cand_sake_shochu_dassai_45",
    "bev_cand_sake_shochu_iichiko_silhouette",
    "bev_cand_sake_shochu_kubota_senju",
    "bev_cand_sake_shochu_hakkaisan_tokubetsu_junmai",
    "bev_cand_sake_shochu_hakutsuru_sayuri_nigori",
    "bev_cand_tequila_mezcal_patron_silver_tequila",
    "bev_cand_tequila_mezcal_del_maguey_vida_puebla_mezcal",
    "bev_cand_tequila_mezcal_don_julio_blanco",
    "bev_cand_tequila_mezcal_don_julio_1942",
    "bev_cand_tequila_mezcal_jose_cuervo_especial_silver",
    "bev_cand_traditional_korean_alcohol_hwayo_25",
    "bev_cand_traditional_korean_alcohol_kooksoondang_draft_makgeolli",
    "bev_cand_traditional_korean_alcohol_jinro_chamisul_fresh",
    "bev_cand_traditional_korean_alcohol_jinro_is_back",
    "bev_cand_traditional_korean_alcohol_chum_churum_original",
    "bev_cand_vodka_absolut_vodka",
    "bev_cand_vodka_grey_goose_vodka",
    "bev_cand_vodka_smirnoff_no_21_vodka",
    "bev_cand_vodka_belvedere_vodka",
    "bev_cand_vodka_ketel_one_vodka",
    "bev_cand_whiskey_the_macallan_12_years_double_cask",
    "bev_cand_whiskey_buffalo_trace_bourbon",
    "bev_cand_whiskey_laphroaig_10_year_old",
    "bev_cand_whiskey_jameson_irish_whiskey",
    "bev_cand_whiskey_glenfiddich_12_year_old",
    "bev_cand_wine_kim_crawford_sauvignon_blanc",
    "bev_cand_wine_cloudy_bay_sauvignon_blanc",
    "bev_cand_wine_louis_jadot_beaujolais_villages",
    "bev_cand_wine_santa_margherita_pinot_grigio",
    "bev_cand_wine_robert_mondavi_private_selection_cabernet_sauvignon",
)


class BeverageImportError(ValueError):
    """Raised when candidate artifacts cannot be safely promoted."""


@dataclass(frozen=True)
class CandidateArtifacts:
    manifest: dict[str, Any]
    catalog_rows: dict[str, dict[str, Any]]
    flavor_rows: dict[str, dict[str, Any]]
    knowledge_rows: dict[str, dict[str, Any]]
    price_rows: dict[str, dict[str, Any]]
    source_rows: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class ImportCounts:
    collection_runs: int = 0
    catalog_candidates: int = 0
    flavor_candidates: int = 0
    knowledge_candidates: int = 0
    price_candidates: int = 0
    source_refs: int = 0
    canonical_beverages: int = 0
    canonical_flavor_profiles: int = 0
    canonical_vectors: int = 0


@dataclass(frozen=True)
class CanonicalSeedRecord:
    beverage: BeverageItem
    flavor_profile: FlavorProfile
    vector: RecommendationVector


class BeverageCandidateImporter:
    """Stages reviewed artifacts and promotes the fixed MVP seed subset."""

    def __init__(self, session: Session, data_dir: Path) -> None:
        self._session = session
        self._data_dir = data_dir

    def load_artifacts(self) -> CandidateArtifacts:
        return load_candidate_artifacts(self._data_dir)

    def stage_candidates(self) -> ImportCounts:
        artifacts = self.load_artifacts()
        run_id = artifacts.manifest["run_id"]
        run_uuid = _stable_uuid("collection_run", run_id, namespace=STAGING_NAMESPACE)
        run = BeverageCollectionRun(
            id=run_uuid,
            run_id=run_id,
            agent=artifacts.manifest.get("agent"),
            task_prompt=artifacts.manifest.get("task_prompt"),
            collected_at=_parse_datetime(artifacts.manifest.get("collected_at")),
            source_manifest_json=artifacts.manifest,
            import_status="staged",
            imported_at=datetime.now(UTC),
        )
        self._session.merge(run)

        for row in artifacts.catalog_rows.values():
            self._session.merge(_catalog_candidate_model(run_uuid, row))
        for row in artifacts.flavor_rows.values():
            self._session.merge(_flavor_candidate_model(run_uuid, row))
        for row in artifacts.knowledge_rows.values():
            self._session.merge(_knowledge_candidate_model(run_uuid, row))
        for row in artifacts.price_rows.values():
            self._session.merge(_price_candidate_model(run_uuid, row))
        for row in artifacts.source_rows.values():
            self._session.merge(_source_ref_model(run_uuid, row))

        return ImportCounts(
            collection_runs=1,
            catalog_candidates=len(artifacts.catalog_rows),
            flavor_candidates=len(artifacts.flavor_rows),
            knowledge_candidates=len(artifacts.knowledge_rows),
            price_candidates=len(artifacts.price_rows),
            source_refs=len(artifacts.source_rows),
        )

    def promote_seed_subset(self) -> ImportCounts:
        artifacts = self.load_artifacts()
        vector_schema = self._session.scalar(
            select(VectorSchemaVersion).where(
                VectorSchemaVersion.version == TASTE_V1_NAME,
                VectorSchemaVersion.status == "active",
            ),
        )
        if vector_schema is None:
            raise BeverageImportError("active taste_v1 vector schema is missing")

        records = build_canonical_seed_records(
            artifacts=artifacts,
            vector_schema_version_id=vector_schema.id,
        )
        for record in records:
            self._session.merge(record.beverage)
            self._session.merge(record.flavor_profile)
            self._session.merge(record.vector)

        return ImportCounts(
            canonical_beverages=len(records),
            canonical_flavor_profiles=len(records),
            canonical_vectors=len(records),
        )


def load_candidate_artifacts(data_dir: Path) -> CandidateArtifacts:
    manifest = _read_json(data_dir / "run_manifest.json")
    catalog = _index_by(
        _read_jsonl(data_dir / "catalog_candidates.jsonl"),
        "beverage_candidate_id",
    )
    flavor = _index_by(
        _read_jsonl(data_dir / "flavor_profile_candidates.jsonl"),
        "beverage_candidate_id",
    )
    knowledge = _index_by(
        _read_jsonl(data_dir / "knowledge_candidates.jsonl"),
        "beverage_candidate_id",
    )
    price = _index_by(
        _read_jsonl(data_dir / "price_observation_candidates.jsonl"),
        "price_observation_id",
    )
    source = _index_by(_read_csv(data_dir / "source_registry.csv"), "source_id")
    return CandidateArtifacts(
        manifest=manifest,
        catalog_rows=catalog,
        flavor_rows=flavor,
        knowledge_rows=knowledge,
        price_rows=price,
        source_rows=source,
    )


def build_canonical_seed_records(
    *,
    artifacts: CandidateArtifacts,
    vector_schema_version_id: uuid.UUID,
) -> tuple[CanonicalSeedRecord, ...]:
    source_urls = {row["url"] for row in artifacts.source_rows.values()}
    records: list[CanonicalSeedRecord] = []
    for candidate_id in MVP_SEED_CANDIDATE_IDS:
        catalog = _required_row(artifacts.catalog_rows, candidate_id, "catalog")
        flavor = _required_row(artifacts.flavor_rows, candidate_id, "flavor")
        knowledge = _required_row(artifacts.knowledge_rows, candidate_id, "knowledge")
        _validate_source_coverage(catalog, flavor, knowledge, source_urls)
        _validate_seed_vector(flavor)

        catalog_key = f"{catalog['category']}.{catalog['beverage_slug']}"
        beverage_id = _stable_uuid("beverage", catalog_key)
        flavor_profile_id = _stable_uuid("flavor_profile", catalog_key)
        dimensions = flavor["taste_v1_dimension_values"]
        dimension_confidence = _normalize_dimension_confidence(flavor)
        source_hash = _source_hash(
            {
                "catalog": catalog,
                "flavor": flavor,
                "vector_schema_version_id": str(vector_schema_version_id),
                "seed_version": SEED_VERSION,
            },
        )
        vector_id = _stable_uuid(
            "recommendation_vector",
            f"{catalog_key}:{source_hash}",
        )
        vector_values = [
            float(dimensions[dimension.name]) for dimension in TASTE_V1_DIMENSIONS
        ]
        reason_hints = _reason_code_hints(catalog, flavor)
        metadata = _catalog_metadata(
            catalog,
            flavor,
            knowledge,
            catalog_key,
            reason_hints,
        )

        beverage = BeverageItem(
            id=beverage_id,
            category=catalog["category"],
            name_ko=catalog["display_name_ko"],
            name_en=catalog["canonical_name_en"],
            brand=catalog.get("brand_or_producer"),
            country=catalog.get("country"),
            region=catalog.get("region"),
            abv=catalog.get("abv"),
            price_min_krw=None,
            price_max_krw=None,
            active=True,
            description=knowledge.get("summary_text"),
            search_document=None,
            metadata_json=metadata,
        )
        flavor_profile = FlavorProfile(
            id=flavor_profile_id,
            owner_type=FlavorProfileOwnerType.BEVERAGE_ITEM.value,
            owner_id=beverage_id,
            flavor_tags=_flavor_tags(catalog, flavor),
            profile_json={
                "vector_schema": TASTE_V1_NAME,
                "dimension_values": dimensions,
                "dimension_confidence": dimension_confidence,
                "extended_dimension_values": flavor.get(
                    "extended_dimension_values",
                    {},
                ),
                "reason_code_hints": reason_hints,
                "evidence_summary": flavor.get("evidence_summary"),
                "seed_version": SEED_VERSION,
                "source_candidate_id": candidate_id,
            },
            curation_confidence=flavor.get("flavor_confidence_overall"),
            source=SEED_VERSION,
            notes=(
                "Promoted from reviewed MVP seed subset; source artifacts retained "
                "in staging."
            ),
        )
        vector = RecommendationVector(
            id=vector_id,
            owner_type=VectorOwnerType.BEVERAGE_ITEM.value,
            owner_id=beverage_id,
            vector_schema_version_id=vector_schema_version_id,
            vector=vector_values,
            vector_json=dimensions,
            confidence_json=dimension_confidence,
            source_hash=source_hash,
            source_metadata_json={
                "seed_version": SEED_VERSION,
                "catalog_key": catalog_key,
                "source_candidate_id": candidate_id,
                "source_urls": sorted(set(catalog.get("source_urls", []))),
                "reason_code_basis": reason_hints,
            },
        )
        records.append(
            CanonicalSeedRecord(
                beverage=beverage,
                flavor_profile=flavor_profile,
                vector=vector,
            ),
        )
    return tuple(records)


def _catalog_candidate_model(
    collection_run_id: uuid.UUID,
    row: dict[str, Any],
) -> BeverageCatalogCandidate:
    candidate_id = row["beverage_candidate_id"]
    return BeverageCatalogCandidate(
        id=_stable_uuid("stage_catalog", candidate_id, namespace=STAGING_NAMESPACE),
        collection_run_id=collection_run_id,
        candidate_id=candidate_id,
        beverage_candidate_id=candidate_id,
        canonical_name_en=row.get("canonical_name_en"),
        category=row.get("category"),
        candidate_status=row.get("candidate_status", "needs_review"),
        validation_status="accepted",
        validation_errors_json={},
        raw_json=row,
    )


def _flavor_candidate_model(
    collection_run_id: uuid.UUID,
    row: dict[str, Any],
) -> BeverageFlavorProfileCandidate:
    candidate_id = row["flavor_candidate_id"]
    return BeverageFlavorProfileCandidate(
        id=_stable_uuid("stage_flavor", candidate_id, namespace=STAGING_NAMESPACE),
        collection_run_id=collection_run_id,
        candidate_id=candidate_id,
        beverage_candidate_id=row.get("beverage_candidate_id"),
        canonical_name_en=None,
        category=None,
        candidate_status=row.get("candidate_status", "needs_review"),
        validation_status="accepted",
        validation_errors_json={},
        raw_json=row,
    )


def _knowledge_candidate_model(
    collection_run_id: uuid.UUID,
    row: dict[str, Any],
) -> BeverageKnowledgeCandidate:
    candidate_id = row["knowledge_candidate_id"]
    return BeverageKnowledgeCandidate(
        id=_stable_uuid("stage_knowledge", candidate_id, namespace=STAGING_NAMESPACE),
        collection_run_id=collection_run_id,
        candidate_id=candidate_id,
        beverage_candidate_id=row.get("beverage_candidate_id"),
        canonical_name_en=None,
        category=None,
        candidate_status=row.get("candidate_status", "needs_review"),
        validation_status="accepted",
        validation_errors_json={},
        raw_json=row,
        language=row.get("language"),
        document_type=row.get("document_type"),
    )


def _price_candidate_model(
    collection_run_id: uuid.UUID,
    row: dict[str, Any],
) -> BeveragePriceObservationCandidate:
    candidate_id = row["price_observation_id"]
    return BeveragePriceObservationCandidate(
        id=_stable_uuid("stage_price", candidate_id, namespace=STAGING_NAMESPACE),
        collection_run_id=collection_run_id,
        candidate_id=candidate_id,
        beverage_candidate_id=row.get("beverage_candidate_id"),
        canonical_name_en=row.get("canonical_name_en"),
        category=None,
        candidate_status="needs_review",
        validation_status="accepted",
        validation_errors_json={},
        raw_json=row,
        market_region=row.get("market_region"),
        currency=row.get("currency"),
        price_value=row.get("price_value"),
        observed_at=_parse_date(row.get("observed_at")),
    )


def _source_ref_model(
    collection_run_id: uuid.UUID,
    row: dict[str, Any],
) -> BeverageSourceRef:
    source_id = row["source_id"]
    return BeverageSourceRef(
        id=_stable_uuid("stage_source", source_id, namespace=STAGING_NAMESPACE),
        collection_run_id=collection_run_id,
        source_id=source_id,
        title=row.get("title"),
        url=row["url"],
        source_type=row["source_type"],
        usage_lanes=row.get("usage_lanes"),
        source_confidence=row.get("source_confidence"),
        retrieved_at=_parse_date(row.get("retrieved_at")),
        raw_json=row,
    )


def _read_json(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise BeverageImportError(f"{path} must contain a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise BeverageImportError(f"{path} contains a non-object row")
                rows.append(value)
    return rows


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _index_by(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_key = row.get(key)
        if not isinstance(row_key, str) or not row_key:
            raise BeverageImportError(f"missing required key {key}")
        if row_key in indexed:
            raise BeverageImportError(f"duplicate key {key}={row_key}")
        indexed[row_key] = row
    return indexed


def _required_row(
    rows: dict[str, dict[str, Any]],
    key: str,
    lane: str,
) -> dict[str, Any]:
    row = rows.get(key)
    if row is None:
        raise BeverageImportError(f"missing {lane} row for {key}")
    return row


def _validate_seed_vector(flavor: dict[str, Any]) -> None:
    dimensions = flavor.get("taste_v1_dimension_values")
    if not isinstance(dimensions, dict):
        raise BeverageImportError("flavor row is missing taste_v1_dimension_values")
    expected = [dimension.name for dimension in TASTE_V1_DIMENSIONS]
    if set(dimensions) != set(expected):
        raise BeverageImportError("flavor row dimension names do not match taste_v1")
    for name in expected:
        value = dimensions[name]
        if not isinstance(value, int | float) or not 0 <= float(value) <= 1:
            raise BeverageImportError(f"invalid taste_v1 value for {name}")


def _validate_source_coverage(
    catalog: dict[str, Any],
    flavor: dict[str, Any],
    knowledge: dict[str, Any],
    source_urls: set[str],
) -> None:
    urls = set(catalog.get("source_urls", []))
    urls.update(flavor.get("source_urls", []))
    source_url = knowledge.get("source_url")
    if isinstance(source_url, str):
        urls.add(source_url)
    missing = sorted(url for url in urls if url not in source_urls)
    if missing:
        raise BeverageImportError(f"source URLs missing from registry: {missing}")


def _normalize_dimension_confidence(flavor: dict[str, Any]) -> dict[str, float]:
    confidence = flavor.get("dimension_confidence_json") or {}
    fallback = float(confidence.get("all_other_dimensions", 0.45))
    return {
        dimension.name: float(confidence.get(dimension.name, fallback))
        for dimension in TASTE_V1_DIMENSIONS
    }


def _reason_code_hints(
    catalog: dict[str, Any],
    flavor: dict[str, Any],
) -> list[str]:
    dimensions = flavor["taste_v1_dimension_values"]
    extended = flavor.get("extended_dimension_values", {})
    hints: list[str] = []
    if dimensions.get("sweet", 0) >= 0.45 and (
        extended.get("vanilla", 0) >= 0.45 or extended.get("caramel", 0) >= 0.45
    ):
        hints.append("MATCHES_VANILLA_CARAMEL")
    if dimensions.get("smoky", 0) >= 0.45:
        hints.append("MATCHES_SMOKY_PROFILE")
    if catalog.get("beginner_friendly_score", 0) >= 0.7:
        hints.append("BEGINNER_FRIENDLY")
    if dimensions.get("fruity", 0) >= 0.55 or dimensions.get("acidity", 0) >= 0.55:
        hints.append("MATCHES_FRUITY_BRIGHT_PROFILE")
    if dimensions.get("herbal", 0) >= 0.5 or dimensions.get("bitterness", 0) >= 0.5:
        hints.append("MATCHES_HERBAL_BITTER_PROFILE")
    if dimensions.get("woody", 0) >= 0.5 and dimensions.get("body", 0) >= 0.5:
        hints.append("MATCHES_RICH_OAK_PROFILE")
    if dimensions.get("body", 0) >= 0.55 and (
        dimensions.get("sweet", 0) >= 0.45
        or dimensions.get("fruity", 0) >= 0.45
        or dimensions.get("spicy", 0) >= 0.45
    ):
        hints.append("MATCHES_ROUNDED_BODY")
    if dimensions.get("roasted", 0) >= 0.5:
        hints.append("MATCHES_ROASTED_PROFILE")
    if extended.get("earthy", 0) >= 0.5:
        hints.append("MATCHES_EARTHY_AGAVE_PROFILE")
    if _clean_light_profile(catalog, dimensions):
        hints.append("MATCHES_CLEAN_LIGHT_PROFILE")
    return sorted(set(hints))


def _clean_light_profile(
    catalog: dict[str, Any],
    dimensions: dict[str, Any],
) -> bool:
    clean_categories = {"sake_shochu", "traditional_korean_alcohol", "vodka"}
    if catalog.get("category") in clean_categories:
        expressive_dimensions = (
            "sweet",
            "fruity",
            "dried_fruit",
            "woody",
            "smoky",
            "nutty",
            "floral",
            "spicy",
            "herbal",
            "body",
            "acidity",
            "bitterness",
            "tannin",
            "roasted",
        )
        return all(
            float(dimensions.get(name, 0.0)) < 0.45
            for name in expressive_dimensions
        )
    return False


def _catalog_metadata(
    catalog: dict[str, Any],
    flavor: dict[str, Any],
    knowledge: dict[str, Any],
    catalog_key: str,
    reason_hints: list[str],
) -> dict[str, Any]:
    return {
        "catalog_key": catalog_key,
        "source_candidate_id": catalog["beverage_candidate_id"],
        "style": catalog.get("style"),
        "substyle": catalog.get("substyle"),
        "source_type": "operator_reviewed_candidate_seed",
        "source_version": SEED_VERSION,
        "curation_status": "approved_mvp_seed",
        "aliases_en": _aliases(catalog, "aliases_en", "canonical_name_en"),
        "aliases_ko": _aliases(catalog, "aliases_ko", "display_name_ko"),
        "serving_context": catalog.get("serving_style", []),
        "popularity_hint": catalog.get("popularity_hint"),
        "korea_availability_hint": catalog.get("korea_availability_hint"),
        "beginner_friendly_score": catalog.get("beginner_friendly_score"),
        "source_urls": catalog.get("source_urls", []),
        "knowledge_source_url": knowledge.get("source_url"),
        "reason_code_hints": reason_hints,
        "extended_dimension_values": flavor.get("extended_dimension_values", {}),
        "price_policy": "candidate_price_observations_not_live_truth",
    }


def _aliases(
    catalog: dict[str, Any],
    aliases_key: str,
    fallback_key: str,
) -> list[str]:
    aliases = [
        alias
        for alias in catalog.get(aliases_key, [])
        if isinstance(alias, str) and alias
    ]
    fallback = catalog.get(fallback_key)
    if isinstance(fallback, str) and fallback and fallback not in aliases:
        aliases.append(fallback)
    return aliases


def _flavor_tags(catalog: dict[str, Any], flavor: dict[str, Any]) -> list[str]:
    dimensions = flavor["taste_v1_dimension_values"]
    tags = [
        name
        for name, value in dimensions.items()
        if isinstance(value, int | float) and float(value) >= 0.5
    ]
    tags.append(catalog["category"])
    style = catalog.get("style")
    if isinstance(style, str) and style:
        tags.append(style.lower().replace(" ", "_"))
    return sorted(set(tags))


def _source_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _stable_uuid(
    kind: str,
    key: str,
    *,
    namespace: uuid.UUID = SEED_NAMESPACE,
) -> uuid.UUID:
    return uuid.uuid5(namespace, f"{kind}:{key}")


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    return date.fromisoformat(value[:10])

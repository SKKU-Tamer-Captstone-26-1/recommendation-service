# Acceptance Checklist

Use this checklist before Codex reports completion.

## General

```text
- [ ] Task scope was restated.
- [ ] Required docs were read.
- [ ] Ownership boundary was checked.
- [ ] Changes stayed inside scope.
- [ ] No speculative infrastructure was added.
- [ ] Final response includes Summary / Changed files / Verification / Risks.
```

## Service Boundary

```text
- [ ] No service directly writes another service's DB.
- [ ] Admin Page writes through APIs only.
- [ ] Recommendation service consumes map data as snapshot/read model only.
- [ ] Chatbot uses map-service API for live place data.
```

## Map / Place

```text
- [ ] map-service/place-service remains canonical owner.
- [ ] Places use lifecycle status instead of hard delete.
- [ ] Operator overrides are represented.
- [ ] Owner changes that require approval use change requests.
- [ ] Audit trail exists for admin/operator/owner writes.
```

## Inventory / Price

```text
- [ ] Inventory has freshness or TTL.
- [ ] Price has validity period or confidence.
- [ ] Stale inventory/price can be penalized or excluded.
```

## Kakao API

```text
- [ ] Kakao API is not treated as canonical bulk-ingestion source.
- [ ] Stored external data has source_type and source_policy.
- [ ] Closed/archived/merged places cannot be automatically reactivated.
```

## Recommendation

```text
- [ ] Ranking uses structured data and versioned scoring.
- [ ] RAG is not used as ranking engine.
- [ ] Recommendation logs include snapshot revisions.
- [ ] Reason codes are deterministic.
```

## RAG

```text
- [ ] Knowledge chunks are separated from structured ranking data.
- [ ] Low-confidence retrieval can produce "unknown" response.
- [ ] Live price/inventory/status is not answered from RAG.
```

## Assistant

```text
- [ ] User identity is derived from authenticated context, not request body.
- [ ] LLM does not rank recommendations.
- [ ] Beverage, venue, price, inventory, and distance claims are grounded.
- [ ] No retrieved evidence produces refusal or insufficient-data response.
- [ ] used_sources metadata is preserved internally.
- [ ] Out-of-scope requests are refused.
```

## Database

```text
- [ ] Migration is additive unless explicitly approved.
- [ ] Indexes exist for expected query paths.
- [ ] Constraints protect ownership and lifecycle assumptions.
- [ ] Rollback or mitigation is documented.
```

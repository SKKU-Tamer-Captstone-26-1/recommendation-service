# Codex Task Template

Use this prompt when assigning work to Codex.

## Task

`<Describe the exact task.>`

## Target Service

```text
map-service | recommendation-service | admin-page | chatbot-service | docs | shared
```

## Required Reading

Read first:

```text
AGENTS.md
.agent/HARNESS.md
.agent/DOMAIN_BOUNDARIES.md
```

Then read:

```text
<task-specific docs>
```

## Scope

Allowed:

```text
- ...
- ...
```

Not allowed:

```text
- ...
- ...
```

## Ownership Rules

Follow these rules:

```text
- Admin Page is not a data owner.
- map-service/place-service owns canonical place/menu/inventory/price data.
- recommendation-service consumes map snapshots only.
- Kakao API must not be used as canonical bulk-ingestion source.
- RAG must not be used as recommendation ranking logic.
```

## Required Harness

Apply:

```text
.agent/HARNESS.md
```

If this task is complex, create an ExecPlan using:

```text
.agent/EXEC_PLAN_TEMPLATE.md
```

## Acceptance Criteria

```text
- [ ] ...
- [ ] ...
- [ ] ...
```

## Verification

Run or explain:

```text
- tests
- lint/typecheck
- migration dry-run
- boundary verification
```

## Final Response

Return:

```text
Summary
Changed files
Verification
Risks / Follow-ups
```


# ExecPlan: <task title>

## 1. Goal

Describe the user-visible or system-visible goal.

## 2. Non-Goals

List what must not be changed.

## 3. Context

Relevant documents:

- `AGENTS.md`
- `.agent/HARNESS.md`
- `docs/implementation-readiness.md`
- `<domain docs>`

Relevant existing files:

- `<file>`
- `<file>`

## 4. Ownership Analysis

Canonical data affected:

| Data | Owner | This task writes? | This task reads? | Allowed? |
|---|---|---:|---:|---|
| Example | map-service | yes | yes | yes |

Boundary decision:

```text
API / event / snapshot / migration / documentation only
```

## 5. Proposed Change

Describe the smallest scoped change.

Implementation readiness gate:

```text
service boundary | API contract | database contract | sync contract |
recommendation contract | assistant contract | verification contract
```

## 6. Database Plan

Only if schema is affected.

```text
Tables:
Indexes:
Constraints:
Audit:
Lifecycle:
Rollback:
```

## 7. API Plan

Only if API is affected.

```text
Endpoint/RPC:
Caller:
Auth:
Role:
Request:
Response:
Errors:
Idempotency:
Audit:
```

## 8. Migration Plan

Only if migration is affected.

```text
Type: additive | destructive | backfill | data migration
Rollback:
Production risk:
```

## 9. Verification Plan

```text
- Unit:
- Integration:
- Migration:
- Permission:
- Docs:
```

## 10. Acceptance Criteria

The task is complete when:

```text
- [ ] ...
- [ ] ...
- [ ] ...
```

## 11. Risks

```text
- Risk:
  Mitigation:
```

## 12. Final Report Template

```text
Summary
Changed files
Verification
Risks / Follow-ups
```

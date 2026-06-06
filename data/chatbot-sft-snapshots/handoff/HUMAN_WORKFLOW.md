# Human Workflow For Chatbot SFT Snapshot Handoff

## Purpose

This handoff explains how humans should turn recommendation-service snapshots
into Korean chatbot SFT candidates.

This workflow does not train a model. It prepares safe examples for later human
review, evaluation, and fine-tuning in a separate training environment.

## Step 1: Collect Safe Recommendation Snapshots

Use only recommendation-service outputs or approved service API outputs already
captured in recommendation snapshots.

Allowed:

```text
profile status
derived taste profile summary
beverage recommendation results
venue recommendation results
reason codes
deterministic explanation text
score breakdown summaries when marked safe
place/menu/price/inventory snapshot metadata already stored by recommendation-service
```

Do not copy:

```text
raw survey answers
auth tokens
passwords
raw user profile PII
survey-service database rows
map-service database rows
auth-service database rows
```

## Step 2: Normalize Into Snapshot Schema

Create one JSON file per user scenario.

Use:

```text
schemas/recommendation_snapshot.schema.json
```

The snapshot should include:

- user request text
- inferred assistant intent
- profile status and safe profile summary
- ranked recommendation facts
- missing facts
- used source metadata
- expected assistant behavior
- human review status

## Step 3: Write Korean Assistant Draft

The assistant answer must:

- answer in Korean
- use only `grounded_context`
- preserve ranking order
- mention uncertainty when facts are stale or low-confidence
- refuse when facts are missing or scope is invalid
- avoid exposing raw internal IDs in user-facing text

The answer must not:

- invent alcohol, venues, prices, inventory, distances, flavors, scents, or user
  preferences
- change recommendation ranking
- claim live availability unless the context includes confirmed freshness
- use raw survey answers
- answer unrelated general questions

## Step 4: Review Grounding

Use:

```text
handoff/REVIEW_CHECKLIST.md
```

Reject a candidate if any factual phrase in the Korean answer is not present in
the grounded context.

## Step 5: Convert To SFT Candidate

After review, humans may create a candidate matching:

```text
schemas/sft_candidate.schema.json
```

Recommended system message:

```text
You are the ONTHEBLOCK recommendation assistant. Answer in Korean. Use only the
provided recommendation context. Do not invent beverages, venues, prices,
inventory, distances, flavors, scents, user preferences, or ranking. Refuse if
the request is outside ONTHEBLOCK alcohol recommendation scope or if required
facts are missing.
```

The user message may include the natural user question plus serialized grounded
context.

The assistant message should be the reviewed Korean answer.

## Step 6: Split Dataset

Use separate splits:

```text
train
eval
holdout
```

Do not evaluate on examples that were used for training.

Recommended initial size:

```text
smoke: 50-100 candidates
train v1: 500-1000 candidates
eval v1: 100-200 candidates
holdout: at least 50 candidates
```

## Step 7: Preserve Traceability

Every SFT candidate must reference:

```text
source_snapshot_id
data_type
grounding_review
split
```

Do not include raw JWTs, unhashed real user IDs, passwords, or service secrets in
any SFT candidate.

# 추천 서비스 기술 기록

## 목적

이 문서는 `recommendation-service`에서 지금까지 구현한 내용을 한국어로
정리하고, 500명에서 5,000명 규모 사용자가 추천 엔진을 호출할 때 필요한
운영/확장 전략과 MLflow 기반 ML 파이프라인 로드맵을 기록한다.

이 문서는 구현 명세를 새로 만드는 문서가 아니다. 현재 구현 상태와 다음
생산성/운영성 개선 방향을 사람이 빠르게 판단하기 위한 기술 기록이다.

## 현재 결론

현재 서비스는 **내부 베타/MVP 기준 70% 생산 준비도**라고 부를 수 있다.

정확한 의미는 다음과 같다.

- 음료 추천은 결정론적이고 설명 가능하다.
- PostgreSQL이 추천 서비스 소유 데이터의 canonical source다.
- Qdrant는 재생성 가능한 파생 인덱스다.
- 음료 카탈로그, 벡터, 평가, 감사, 릴리즈 게이트가 있다.
- survey-service와 map-service는 직접 DB 접근 없이 API/event/snapshot으로만
  연동해야 한다.
- 추천 결과에는 점수 분해, reason code, 프로필/스코어링/스냅샷 메타데이터를
  남긴다.
- ML 모델 학습 준비를 위한 feature logging은 시작했지만, 실서비스 랭킹은
  아직 deterministic scoring이 맞다.

반대로, 아래 항목이 완료되기 전까지는 완전한 public production readiness라고
부르면 안 된다.

- 배포된 survey-service smoke test
- 배포된 map-service smoke test
- auth-service JWKS/issuer/audience production metadata 확정
- 실제 운영 메트릭 export, 알림, 대시보드
- 실제 사용자 interaction label 기반 품질 검증
- 장애 대응/배포/롤백 프로세스 반복 검증

현실적인 표현:

```text
internal beta readiness: about 70%
full public production readiness: about 55-60%
```

## 지금까지 구현한 것

### 1. 서비스 경계와 아키텍처

문서와 코드에서 다음 경계를 고정했다.

| 데이터 | 소유 서비스 | recommendation-service 처리 방식 |
|---|---|---|
| 사용자/로그인/JWT | auth-service | JWT 검증/metadata에서 user 식별만 사용 |
| 원본 설문 답변 | survey-service | 직접 DB 접근 금지, API/event로 파생 프로필 생성 |
| 장소/메뉴/재고/가격/위치 | map-service/place-service | canonical 소유 금지, snapshot/read-model만 소비 |
| 음료 MVP 카탈로그 | recommendation-service | 별도 catalog-service 전까지 직접 소유 |
| taste profile | recommendation-service | survey 결과에서 파생, versioned mapper 사용 |
| recommendation vectors | recommendation-service PostgreSQL | canonical 저장 |
| Qdrant points | Qdrant derived index | 언제든 PostgreSQL에서 rebuild 가능 |
| 추천 로그/설명/interaction | recommendation-service | 재현성과 ML 학습 데이터로 보관 |

중요한 결정:

```text
Admin Page -> service API only
recommendation-service -> no survey DB direct read
recommendation-service -> no map DB direct read/write
Qdrant -> not canonical
LLM/RAG -> not ranking engine
```

### 2. PostgreSQL 모델

현재 추천 서비스가 소유하는 핵심 테이블 그룹은 다음과 같다.

| 그룹 | 목적 |
|---|---|
| `user_profile_state` | 사용자별 활성 taste profile 상태 |
| `taste_profile_revisions` | 설문 기반 프로필 revision |
| `survey_source_snapshots` | 프로필 생성 시점의 survey source snapshot |
| `vector_schema_versions` | taste vector schema version |
| `mapper_versions` | survey -> taste profile mapper version |
| `scoring_configs` | deterministic scoring version |
| `beverage_items` | MVP 음료 카탈로그 |
| `flavor_profiles` | 음료/장소/메뉴 flavor profile |
| `recommendation_vectors` | PostgreSQL canonical vector |
| `qdrant_points` | Qdrant 파생 point metadata |
| `recommendation_requests` | 추천 요청 로그 |
| `recommendation_results` | 추천 결과, score breakdown, snapshot metadata |
| `recommendation_explanations` | reason code와 설명 |
| `recommendation_interactions` | click/save/dismiss/detail 등 feedback label 후보 |
| `survey_sync_events/cursors` | survey event sync 상태 |
| `map_snapshot_sync_events/cursors` | map snapshot sync 상태 |
| `venue_*_snapshots` | 장소/메뉴/재고/가격 read model |
| `dead_letter_events` | sync 실패/재처리 추적 |

설계 의도:

- PostgreSQL은 추천 서비스 소유 상태의 canonical 저장소다.
- Qdrant 장애가 있어도 PostgreSQL 기반 deterministic recommendation은 살아야
  한다.
- 추천 결과는 나중에 왜 추천했는지 재현할 수 있어야 한다.

### 3. 음료 데이터베이스

현재 MVP seed catalog는 active beverage 60개를 사용한다.

검증된 현재 상태:

```text
active_beverages = 60
critical_audit_issues = 0
warning_count = 0
complete_vector_coverage = 1.0
confidence_coverage = 1.0
source_metadata_coverage = 1.0
reason_code_coverage >= 0.95
alias_coverage >= 0.95
style_coverage = 1.0
```

포함된 데이터 성격:

- category/style
- Korean/English display name
- alias
- ABV/region/producer 일부 metadata
- taste_v1 dimension vector
- confidence/source metadata
- reason code hint
- model-ready metadata

주의:

- 이 카탈로그는 내부 베타에는 충분하지만 public production 전체를 대표하는
  규모는 아니다.
- 가격/재고/매장 판매 여부는 map/place-service snapshot이 오기 전까지
  canonical fact로 말하면 안 된다.

### 4. 추천 로직

현재 ranking은 deterministic scoring이다.

핵심 흐름:

```text
JWT/auth context
-> active taste profile 조회
-> PostgreSQL beverage catalog/vector 후보 조회
-> scoring_v1 deterministic score 계산
-> result/explanation/log 저장
-> gRPC response 반환
```

현재 점수 구성은 대략 다음 성격을 가진다.

| 요소 | 의미 |
|---|---|
| taste similarity | 사용자 taste vector와 음료 vector 유사도 |
| category fit | 선호 카테고리와 후보 카테고리 적합도 |
| budget fit | 예산 관련 신호, 현재는 제한적 |
| experience fit | beginner/enthusiast/expert 적합도 |
| popularity/quality proxy | catalog metadata 기반 보정 |
| diversity adjustment | 같은 성향 반복 방지 후보 |

이 결과는 `recommendation_results.score_breakdown_json`과
`recommendation_explanations.reason_codes`에 저장된다.

중요:

```text
아직 learned ranking model이 production ranking을 대체하지 않는다.
현재 production path는 deterministic scoring_v1이다.
```

### 5. 평가 시스템

offline drink evaluation을 추가했다.

현재 gate:

```text
fixture_count >= 20
top_5_hit_rate >= 0.85
negative_violation_count = 0
average_category_style_match_rate >= 0.65
average_reason_code_coverage >= 0.95
positive_score_above_negative_rate >= 0.90
```

검증된 현재 결과:

```text
fixture_count = 20
top_k_hit_rate = 1.0
negative_violations = 0
average_category_style_match_rate = 0.96
average_reason_code_coverage = 1.0
positive_score_above_negative_rate = 1.0
```

이 평가는 production quality의 증명이 아니라 regression guardrail이다.
실제 품질 판단에는 real user feedback이 필요하다.

### 6. Qdrant

Qdrant는 vector 검색을 위한 derived index다.

구현된 것:

- PostgreSQL `recommendation_vectors`에서 Qdrant point 생성
- `qdrant_points` metadata 저장
- index idempotency
- rebuild command
- smoke query
- PostgreSQL 기반 serving fallback

검증된 smoke:

```text
qdrant rebuild scanned=60 indexed=60 failed=0
qdrant index scanned=60 indexed=0 skipped=60 failed=0
qdrant index smoke pass
```

중요:

```text
Qdrant를 잃어도 catalog/profile/vector canonical data는 PostgreSQL에 남는다.
Qdrant는 삭제 후 rebuild 가능해야 한다.
```

### 7. Survey sync

survey-service 원본 DB를 직접 읽지 않고 event/API 기반으로 동작하도록 설계했다.

구현된 것:

- survey sync cursor
- sync event 상태
- retry/dead letter
- survey response fetch client 구조
- fake/protocol smoke
- profile generation
- recommendation request logging

아직 필요한 것:

- 실제 배포된 survey-service URL/gRPC 주소
- auth metadata 또는 internal service credential
- 실제 event/response contract 확인
- 안전한 smoke test survey event

### 8. Map snapshot과 장소 추천

map/place-service canonical DB를 직접 읽거나 수정하지 않고 snapshot/read-model을
사용한다.

구현된 것:

- map snapshot event import
- venue/menu/inventory/price read model
- freshness/confidence/lifecycle filter
- selected beverage venue recommendation
- `nearest_reasonable`, `best_price`, `balanced_best` option type
- place/menu/inventory/price revision logging

중요:

```text
거리, 가격, 재고, 영업 상태는 LLM이 추측하면 안 된다.
structured map snapshot에서만 ranking해야 한다.
```

아직 필요한 것:

- 배포된 map-service/place-service endpoint
- auth metadata
- 실제 snapshot contract 확인
- 안전한 map snapshot smoke event

### 9. Auth

gRPC handler는 authenticated context가 있으면 client-supplied `user_id`를
신뢰하지 않도록 정리했다.

구현된 것:

- gRPC metadata에서 bearer token 처리
- JWT resolver
- subject 기반 external user id resolve
- auth metadata normalization test
- missing/invalid bearer token test

아직 필요한 것:

- production JWKS URL
- issuer
- audience
- TLS/gateway metadata 전달 방식

### 10. 운영성

구현된 것:

- local release gate
- Alembic upgrade smoke
- catalog audit
- drink evaluation threshold check
- Qdrant rebuild/index smoke
- survey sync smoke
- venue recommendation smoke
- operational metrics smoke
- structured JSON logs
- `/v1/operations/metrics`
- runbooks
- human-required external blockers 문서화

현재 release gate:

```bash
bash scripts/codex-harness/verify-release-gate.sh
```

optional full gate:

```bash
RUN_DB_SMOKE=1 RUN_QDRANT_SMOKE=1 RUN_SYNC_SMOKE=1 \
  bash scripts/codex-harness/verify-release-gate.sh
```

현재 full gate에서 확인된 것:

```text
pytest = pass
ruff = pass
compileall = pass
git diff --check = pass
catalog audit = pass
drink evaluation = pass
alembic upgrade = pass
operational metrics smoke = pass
qdrant rebuild/index/smoke = pass
beverage recommendation smoke = pass
survey sync smoke = pass
venue recommendation smoke = pass
```

## 500-5,000명 사용자가 호출할 때의 판단

먼저 숫자의 의미를 구분해야 한다.

| 표현 | 의미 | 난이도 |
|---|---|---|
| 500명 가입자 | 하루 요청은 작을 수 있음 | 낮음 |
| 5,000명 가입자 | 피크 시간 요청이 중요 | 중간 |
| 500명 동시 접속 | 순간 RPS 관리 필요 | 중간-높음 |
| 5,000명 동시 접속 | 진짜 scale/load engineering 필요 | 높음 |

현재 추천 요청은 heavy LLM inference가 아니라 PostgreSQL/Qdrant/CPU scoring 중심이다.
따라서 5,000명 "가입자" 수준은 어렵지 않을 수 있다. 하지만 5,000명이 동시에
추천 버튼을 누르면 다른 문제다.

## 트래픽 가정

초기 MVP에서 현실적인 가정:

```text
DAU: 500-5,000
사용자당 추천 요청: 3-10/day
평균 RPS: 0.02-0.6
피크 RPS: 5-50
이벤트성 피크: 100+ RPS 가능
```

즉, 가입자 5,000명 자체보다 중요한 것은 다음이다.

- 피크 RPS
- p95/p99 latency
- PostgreSQL connection 수
- Qdrant query latency
- sync worker와 API traffic 분리 여부
- 배포 중 rollback 가능 여부
- cache hit 가능성

## 확장 전략

### 1단계: 500-1,000명 베타

권장 구성:

```text
1 recommendation API/gRPC instance
1 background worker
1 PostgreSQL
1 Qdrant
local release gate
structured logs
basic metrics endpoint
```

필요한 기술:

- Docker Compose 또는 단순 container deployment
- PostgreSQL backup
- Qdrant persistent volume
- JWT 검증
- request id logging
- release gate CI 연결
- k6 또는 Locust로 smoke load test

목표:

```text
p95 latency < 300-500ms
error rate < 1%
recommendation_empty_rate monitoring
profile_missing_rate monitoring
```

### 2단계: 1,000-5,000명 베타

권장 구성:

```text
2-3 recommendation API/gRPC replicas
1-2 background workers
PostgreSQL + PgBouncer
Qdrant dedicated container/instance
centralized logs
Prometheus/Grafana or managed monitoring
Sentry or equivalent error tracking
```

필요한 기술:

- Load balancer
- horizontal scaling
- PgBouncer connection pooling
- DB index/query plan monitoring
- OpenTelemetry tracing
- Prometheus metrics export
- Grafana dashboard
- error tracking
- rate limiting at gateway
- secrets manager
- automated backup/restore test

이 규모에서는 API process와 worker process를 반드시 분리하는 것이 좋다.

```text
API process:
  user-facing recommendation request

Worker process:
  survey sync
  map snapshot sync
  Qdrant indexing
  catalog import/rebuild
```

이유:

- Qdrant rebuild가 API latency를 밀어내면 안 된다.
- survey/map sync 장애가 추천 API 장애로 번지면 안 된다.
- worker는 retry/dead-letter 중심으로 운영해야 한다.

### 3단계: 5,000명 동시성 또는 이벤트성 피크

권장 구성:

```text
API replicas: autoscaling
workers: separate queue/cron/worker deployment
PostgreSQL: PgBouncer + tuned indexes + backup + monitoring
Qdrant: managed/dedicated, snapshot/rebuild strategy
gateway: rate limit + auth + request id
observability: metrics + logs + traces + alerting
deployment: blue/green or rolling rollback
```

추가로 고려할 기술:

- Redis: short TTL cache/rate limit 용도. canonical 저장소로 사용 금지.
- CDN/API gateway: public edge 보호.
- Kubernetes/ECS/Cloud Run: autoscaling과 배포 안정성.
- managed PostgreSQL: backup, PITR, monitoring.
- managed Qdrant 또는 안정적인 VM 배포.
- message queue: sync/event volume이 커질 때만 도입.

아직 당장 넣지 말아야 할 것:

- Kafka
- Airflow
- feature store
- separate ML serving
- 복잡한 microservice 분리

이유:

```text
지금 병목은 복잡한 infra 부족이 아니라 실제 배포 연동, 관측성, real feedback,
운영 반복이다.
```

## 병목별 해결책

| 병목 | 증상 | 해결 |
|---|---|---|
| PostgreSQL connection 부족 | timeout, connection refused | PgBouncer, pool size 조정, API replica 수 제한 |
| 느린 추천 query | p95 증가 | EXPLAIN ANALYZE, index 추가, 후보 수 제한 |
| Qdrant latency | vector search 지연 | Qdrant dedicated instance, payload 최소화, rebuild window 분리 |
| profile missing 증가 | 추천 빈 결과 증가 | survey sync 상태 알림, profile regeneration worker |
| map snapshot stale | 장소 추천 품질 저하 | freshness TTL, sync lag alert, stale response 처리 |
| empty recommendation rate 증가 | 사용자에게 추천 없음 | catalog coverage 확대, filter 완화, fallback reason |
| worker가 API 방해 | API latency 증가 | worker/API process 분리 |
| 배포 후 품질 회귀 | 추천 이상 | release gate, canary, scoring rollback |

## 필수 운영 메트릭

현재 `/v1/operations/metrics`에서 시작한 항목을 production exporter로 확장해야
한다.

우선순위 높은 메트릭:

```text
recommendation_request_count
recommendation_empty_rate
recommendation_average_results_per_request
profile_missing_rate
profile_stale_count
survey_sync_max_lag_seconds
map_snapshot_sync_max_lag_seconds
catalog_audit_critical_count
qdrant_pending_point_count
qdrant_failed_point_count
runtime_*_average_latency_ms
runtime_*_max_latency_ms
```

추가해야 할 production 메트릭:

```text
request latency histogram: p50/p95/p99
gRPC status code count
DB query latency
DB pool usage
Qdrant query latency
worker retry count
dead-letter count by reason
recommendation click/save/dismiss rate
conversion proxy by recommendation source
```

추천 알림 기준 예시:

```text
5분 error_rate > 2%
10분 p95 latency > 800ms
recommendation_empty_rate > 10%
profile_missing_rate > 20%
survey_sync_lag > 10분
map_snapshot_sync_lag > 10분
qdrant_failed_point_count > 0
catalog_audit_critical_count > 0
```

## Load test 계획

Flutter integration 전에 backend 자체 load test를 먼저 해야 한다.

권장 도구:

- k6
- Locust
- ghz for gRPC

시나리오:

```text
1. GetProfileStatus
2. GetBeverageRecommendations
3. GetVenueRecommendations
4. RecordRecommendationEvent
5. mixed traffic: 70% beverage, 20% venue, 10% interaction
```

단계:

```text
smoke: 1-5 RPS, 5분
beta: 20 RPS, 10분
peak: 50 RPS, 10분
stress: 100 RPS, 10분
soak: expected peak RPS, 1-2시간
```

통과 기준 예시:

```text
p95 latency <= 500ms for beverage recommendation
p95 latency <= 800ms for venue recommendation
error rate <= 1%
DB connection saturation 없음
Qdrant failure 없음
empty recommendation spike 없음
```

## Flutter integration 순서

Flutter에서 한 번에 모든 것을 붙이면 원인 파악이 어렵다.

권장 순서:

```text
1. auth login/token 저장
2. recommendation GetProfileStatus with JWT
3. survey submit through survey-service
4. survey sync smoke or profile regeneration 확인
5. beverage recommendation
6. map/location permission + map-service smoke
7. selected beverage venue recommendation
8. chat-service -> recommendation-service orchestration
```

Flutter test screen에 있으면 좋은 항목:

- 현재 auth token 존재 여부
- token 만료 시간
- profile status
- survey submit result
- beverage recommendation result
- selected beverage id
- map lat/lng
- venue recommendation result
- request id
- last error message

중요:

```text
Flutter가 user_id를 신뢰 source로 보내면 안 된다.
backend는 JWT subject에서 user identity를 읽어야 한다.
```

## ML 파이프라인 방향

현재는 "real AI model"을 바로 넣으면 안 된다. 먼저 데이터가 쌓여야 한다.

이유:

- synthetic fixture만으로 학습하면 실제 사용자 취향을 과적합한다.
- 클릭/저장/무시/상세보기 같은 label이 부족하다.
- venue 추천에는 거리/가격/재고 freshness가 섞이므로 모델이 잘못 배우기 쉽다.
- LLM/RAG는 설명에는 쓸 수 있지만 ranking source가 되면 안 된다.

따라서 ML은 다음 순서가 맞다.

### ML 0단계: 현재 상태

```text
deterministic scoring_v1
offline evaluation fixtures
model-ready feature logging
recommendation_interactions table
structured logs
```

이 단계에서는 MLflow를 도입하지 않아도 된다.

### ML 1단계: 데이터 수집 안정화

필요한 label:

| label | source | 의미 |
|---|---|---|
| impression | 추천 카드 노출 | ranking denominator |
| click | 카드 클릭 | 약한 positive |
| save | 저장/찜 | 강한 positive |
| dismiss | 숨김/관심 없음 | negative |
| detail_view | 상세 조회 | 중간 positive |
| purchase/visit proxy | 나중에 map/order 연동 | 강한 positive 후보 |

필요한 feature:

- profile vector
- beverage vector
- category/style
- budget range
- experience level
- score breakdown
- reason codes
- catalog source version
- scoring config version
- map distance
- price
- inventory freshness
- source snapshot revision
- time context

주의:

```text
raw survey answers는 survey-service 소유다.
ML dataset은 recommendation-service가 소유한 derived profile/log/snapshot에서
만들어야 한다.
```

### ML 2단계: offline dataset builder

추가할 수 있는 구성:

```text
PostgreSQL recommendation logs
-> dataset export job
-> object storage
-> train/validation/test split
-> data quality report
```

추천 기술:

- object storage: S3, GCS, MinIO 중 하나
- data format: Parquet
- data validation: Great Expectations 또는 pandera
- versioning: DVC 또는 lakeFS는 필요할 때만

당장 필요한 최소 구현:

```text
python -m app.tools.export_training_dataset --from --to --output
```

처음에는 cron/manual job으로 충분하다.

### ML 3단계: MLflow tracking

MLflow는 다음 용도로 도입하는 것이 좋다.

```text
experiment tracking
parameter tracking
metric tracking
artifact storage
model registry
champion/challenger 기록
```

MLflow에 기록할 것:

| 항목 | 예시 |
|---|---|
| data version | dataset hash, export time range |
| feature version | feature_builder_v1 |
| vector schema | taste_v1 |
| scoring baseline | scoring_v1 |
| model type | logistic regression, LightGBM, XGBoost ranker |
| metrics | NDCG@K, MAP@K, hit rate, negative violation, calibration |
| artifacts | feature importance, eval report, model binary |

초기 모델 후보:

```text
1. logistic regression or linear model
2. LightGBM/XGBoost ranking model
3. neural/two-tower model은 훨씬 나중
```

이유:

- 데이터가 적을 때는 단순 모델이 더 안전하다.
- feature importance를 볼 수 있다.
- deterministic scoring과 비교하기 쉽다.
- rollback이 쉽다.

### ML 4단계: shadow mode

처음 ML 모델은 사용자에게 영향 주면 안 된다.

흐름:

```text
production ranking = deterministic scoring_v1
shadow model = same candidates에 점수만 계산
log = deterministic rank vs model rank 비교
```

저장해야 할 것:

```text
request_id
candidate_id
deterministic_score
deterministic_rank
model_name
model_version
model_score
model_rank
feature_version
created_at
```

통과 기준:

```text
model이 deterministic baseline보다 offline/online proxy에서 좋아야 함
negative violation 증가 없어야 함
특정 카테고리/가격대 bias가 심해지면 안 됨
```

### ML 5단계: canary/A-B test

shadow mode가 충분히 좋을 때만 작은 traffic에 적용한다.

권장:

```text
1% traffic canary
5% traffic
10% traffic
roll back if guardrail fails
```

guardrail:

```text
error rate
latency
empty result rate
save/click rate
dismiss rate
category diversity
budget violation
freshness violation
```

rollback:

```text
active ranker = deterministic scoring_v1
model result는 로그로만 유지
```

### ML 6단계: model serving

초기에는 separate ML serving을 만들지 않는 것이 좋다.

가능한 순서:

```text
1. batch-trained simple model을 app process에서 load
2. shadow scoring only
3. model registry로 version 관리
4. traffic이 커지고 모델 복잡도가 커질 때 별도 model service
```

별도 model serving이 필요한 신호:

- model inference가 API latency를 지배한다.
- model version hot-swap이 자주 필요하다.
- Python dependency가 API 안정성을 해친다.
- GPU/large embedding model이 필요하다.
- 여러 서비스가 같은 model endpoint를 공유한다.

그 전까지는 과한 분리다.

## 추천 MLflow 구성

처음 production-level로 가는 구성:

```text
MLflow Tracking Server
PostgreSQL backend store
S3/GCS/MinIO artifact store
training job container
model registry
```

주의:

```text
MLflow backend DB와 recommendation-service DB를 같은 schema로 섞지 않는다.
```

권장 artifact:

```text
dataset_manifest.json
feature_schema.json
training_config.yaml
evaluation_report.json
model.pkl or model.txt
feature_importance.json
model_card.md
```

model registry stage:

```text
candidate
shadow
canary
production
archived
```

production 승격 조건:

```text
offline metric passes
shadow comparison passes
canary guardrail passes
rollback plan exists
model version is recorded in recommendation logs
```

## 다음 implementation 추천

Flutter integration 전에 backend 쪽 다음 순서가 현실적이다.

### A. staging 환경 smoke 확정

해야 할 것:

- auth-service JWKS/issuer/audience 확정
- survey-service deployed smoke
- map-service deployed smoke
- recommendation-service deployed smoke
- chat-service가 recommendation-service 결과를 사용하는 smoke

완료 기준:

```text
실제 staging URL에서 Flutter 없이 curl/grpcurl로 end-to-end pass
```

### B. load test harness

해야 할 것:

- k6 또는 ghz script 추가
- 20/50/100 RPS 시나리오
- DB/Qdrant/latency 관측
- 결과 markdown 기록

완료 기준:

```text
현재 배포 스펙에서 안전한 RPS와 병목이 문서화됨
```

### C. production metrics exporter

해야 할 것:

- 현재 `/v1/operations/metrics`를 Prometheus format 또는 OpenTelemetry metric으로
  확장
- Grafana dashboard
- alert rule

완료 기준:

```text
recommendation_empty_rate, p95 latency, sync lag, qdrant_failed가 dashboard와
alert에 보임
```

### D. training dataset export

해야 할 것:

- recommendation logs + interactions를 Parquet으로 export
- feature schema version
- dataset manifest/hash
- privacy review

완료 기준:

```text
MLflow에 올릴 수 있는 offline dataset artifact 생성
```

### E. MLflow proof-of-concept

해야 할 것:

- deterministic baseline을 MLflow run으로 기록
- simple model 후보 하나 학습
- offline eval report 기록
- model registry에 candidate 등록

완료 기준:

```text
production ranking 변경 없이 ML experiment lifecycle만 검증
```

## 정리

지금 서비스는 "실제 AI 모델이 이미 추천한다"라고 말하면 안 된다.

정확한 표현은 다음이다.

```text
현재 추천 엔진은 production-safe deterministic recommender다.
카탈로그, 평가, 로그, Qdrant rebuild, sync smoke, operations gate가 있어
내부 베타 70% 수준까지 올라왔다.
ML 모델은 feature/label/log 기반을 만들었고, MLflow를 통해 다음 단계로
실험/검증/registry/shadow/canary 순서로 올려야 한다.
```

가장 중요한 다음 기준:

```text
실제 배포된 auth/survey/map/chat 연동 smoke + load test + monitoring.
그 다음 MLflow.
```

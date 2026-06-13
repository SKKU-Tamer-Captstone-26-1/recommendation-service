# App Gateway Handoff

## Purpose

This document defines the production handoff from `app-gateway-service` to
`recommendation-service`.

The production mobile path is:

```text
Flutter
  -> app-gateway-service
      -> recommendation-service
```

`recommendation-service` stays private at the Cloud Run IAM layer. Flutter must
not call it directly in production.

## Service Ownership

`app-gateway-service` owns:

- mobile-facing routing
- stable app API contracts
- Cloud Run server-to-server authentication
- forwarding user auth metadata
- request IDs, timeouts, and edge logging

`recommendation-service` owns:

- profile status
- beverage recommendations
- venue recommendations from map/place read-model snapshots
- recommendation result logging
- recommendation feedback event recording
- scoring, ranking, and reason codes

The gateway must not score, rank, filter, generate recommendation reasons, read
recommendation databases, read survey databases, or trust client-supplied
`user_id`.

## Downstream Endpoint

Current staging gRPC target:

```text
RECOMMENDATION_SERVICE_GRPC_ADDR=recommendation-service-vcuepibcwq-du.a.run.app:443
RECOMMENDATION_SERVICE_AUDIENCE=https://recommendation-service-vcuepibcwq-du.a.run.app
```

Use gRPC over TLS. Cloud Run must be called over HTTP/2.

## Metadata Contract

For every user-context recommendation RPC, the gateway must send both metadata
values when `recommendation-service` is private:

```text
authorization: Bearer <auth-service-access-token>
x-serverless-authorization: Bearer <google-id-token-for-recommendation-service>
```

Do not replace the user bearer token with the Google ID token.

The headers have separate purposes:

| Metadata | Purpose |
|---|---|
| `authorization` | Application authentication and user context inside recommendation-service |
| `x-serverless-authorization` | Cloud Run IAM admission for private service-to-service calls |

The user identity must come from the auth token validated through auth-service.
Flutter requests must not provide `user_id` for recommendation APIs.

## IAM Requirement

Grant the gateway runtime service account Cloud Run Invoker on
`recommendation-service`:

```bash
gcloud run services add-iam-policy-binding recommendation-service \
  --region=asia-northeast3 \
  --project=on-the-block-2026 \
  --member="serviceAccount:<APP_GATEWAY_SERVICE_ACCOUNT>" \
  --role=roles/run.invoker
```

Keep `recommendation-service` private:

```text
allUsers roles/run.invoker = not allowed for production
```

## Required RPC Routing

The gateway may proxy these recommendation RPCs for mobile UI:

```text
GetProfileStatus
GetBeverageRecommendations
GetVenueRecommendations
RecordRecommendationEvent
```

Recommended mobile call order:

```text
1. GetProfileStatus
2. GetBeverageRecommendations
3. GetVenueRecommendations when a selected beverage and location are available
4. RecordRecommendationEvent for impression/click/save/dismiss/detail events
```

The gateway must preserve recommendation order and result IDs. It must not
rerank candidates.

For selected-beverage venue flows, the gateway may pass place intent through
`GetVenueRecommendations.place_types`:

```text
store
shop
liquor_shop
bottle_shop
bar
pub
cocktail_bar
wine_bar
whiskey_bar
outdoor
outdoor_spot
```

The gateway should not filter venue results locally. It forwards user location,
selected beverage, budget mode, radius, limit, and place type filters to
recommendation-service, then returns the server-ranked response.

### User Location Forwarding

Venue recommendation distance uses WGS84 coordinates from the request:

```text
GetVenueRecommendations.lat
GetVenueRecommendations.lng
```

If auth/gateway already stores or resolves user map information, the gateway
should translate that approved location into these request fields before calling
`recommendation-service`. `recommendation-service` must not call auth-service
private storage or infer coordinates from `neighborhood`.

If no precise user coordinates are available, the gateway should return a
location-needed state to Flutter instead of calling venue recommendations with
placeholder coordinates.

Kakao map keys stay on the Flutter/map-service side. The gateway must not pass
Kakao API keys or raw Kakao lookup payloads to `recommendation-service` for
ranking.

For beverage chatbot follow-ups such as "다른 술 추천해줘", the gateway may pass
these fields through to `GetBeverageRecommendations` when chatbot-service or the
mobile API contract provides them:

```text
exclude_beverage_ids
exclude_result_ids
diversity_mode
```

The gateway must not resolve diversity behavior itself. It only forwards the
client/chatbot contract; `recommendation-service` owns exclusion, deterministic
diversity, ranking, and reason codes.

For beverage cards, the gateway should pass through recommendation metadata
without rewriting image fields:

```text
metadata.image_url
metadata.image_alt_text_ko
metadata.image
```

Image metadata is catalog display metadata from recommendation-service. The
gateway must not rewrite display URLs or infer product quality, ranking,
inventory, or availability from image presence. In staging/production,
`metadata.image_url` may already be an ONTHEBLOCK-managed cache/CDN URL while
`metadata.image.original_image_url` preserves the licensed source image URL.

For venue recommendations, the gateway must also preserve distance metadata
without relabeling it. `distance_strategy=straight_line_mvp` means approximate
straight-line distance from user lat/lng to venue snapshot coordinates. It is
not a walking, driving, or transit route estimate. Future route-aware responses
must be identified by `is_route_distance=true` and route fields supplied by the
approved map-service integration. If
`metadata.source.distance_fallback_used=true`, the route provider was attempted
but the response fell back to straight-line distance; the gateway must pass this
through unchanged.

## Error Handling

Gateway behavior should preserve recommendation-service states:

| Downstream result | Gateway behavior |
|---|---|
| `PROFILE_STATUS_MISSING` | Return survey/profile missing state to Flutter |
| `PROFILE_STATUS_PENDING_GENERATION` | Return profile generation pending state |
| Empty recommendations | Return an empty result with profile status, not a fabricated fallback |
| `UNAUTHENTICATED` | Return app auth failure |
| `UNAVAILABLE` / timeout | Return retryable service unavailable response |

## Production Smoke

Use the deployed smoke with both auth layers:

```bash
RECOMMENDATION_SMOKE_GRPC_ADDR=recommendation-service-vcuepibcwq-du.a.run.app:443 \
SMOKE_AUTH_BEARER_TOKEN=<safe-auth-service-access-token> \
SMOKE_SERVERLESS_AUTH_TOKEN=<google-id-token-for-recommendation-service> \
RECOMMENDATION_SMOKE_EXPECT_ACTIVE_PROFILE=true \
RECOMMENDATION_SMOKE_RUN_BEVERAGE=true \
SMOKE_GRPC_TLS=1 \
python3 -m app.tools.deployed_smoke --mode recommendation
```

This verifies the same metadata split that app-gateway-service must use:

```text
authorization = user/application auth
x-serverless-authorization = Cloud Run IAM
```

## Rollback

If app-gateway routing fails:

1. Keep `recommendation-service` private.
2. Disable the gateway recommendation route or feature flag.
3. Continue using internal deployed smoke with serverless auth to prove
   recommendation-service health.
4. Do not open `allUsers` invoker in production as a silent rollback.

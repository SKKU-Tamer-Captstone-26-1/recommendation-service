# Domain Boundaries

This document defines service ownership boundaries.

## System Overview

```text
Kakao API / public data / field research / owner input
        |
        v
place-ingestion / admin APIs
        |
        v
map-service or place-service DB
        |
        v
1. Map UI displays active/published places
2. Recommendation service consumes snapshots/read models
3. Chatbot calls map-service tools/APIs for live place data
```

## Admin Page

Admin Page is not a data owner.

It is a UI client for:

- platform operators
- business owners
- store managers

It must write through service APIs.

## Auth Service

`auth-service` owns:

- users
- roles
- identity
- JWT/session issuance
- login state

Other services must derive authenticated identity from auth context and must not
trust client-supplied identity fields when an authenticated context exists.

## Survey Service

`survey-service` owns raw survey answers.

Recommendation may derive taste profiles from survey outputs, but it must not
own or mutate raw survey answers.

## Map / Place Service

Owns canonical place data.

Includes:

- places
- locations
- business status
- publication status
- menus
- signature menus
- inventory
- prices
- business claims
- operator overrides
- audit logs

## Recommendation Service

Owns recommendation-specific derived state.

Includes:

- taste profile
- recommendation vectors
- scoring configs
- recommendation logs
- explanation reason codes
- map/place read-model snapshots

It must not directly mutate place/menu/inventory/price data.

Map/place snapshots are derived read models and must be rebuildable from
map-service/place-service.

## Chatbot / RAG

The ONTHEBLOCK assistant is an orchestration layer, not a canonical data owner.

Assistant runtime ownership is not approved for implementation until the
implementation-readiness assistant gate is satisfied.

It may use RAG to build grounded context and produce natural-language answers.

It must not:

- rank beverages or venues with the LLM
- invent beverage names, places, prices, inventory, distances, or route times
- read survey-service or map-service databases directly
- bypass recommendation-service for recommendation scores and reason codes

For recommendation questions, assistant calls recommendation-service.

For live place data outside recommendation snapshots, assistant must call
approved map-service APIs or tools.

If no verified facts are retrieved, assistant must say it cannot answer
reliably.

## Kakao API

Kakao API is not canonical by default.

Use it for realtime lookup, display, verification, or linking unless
legal/partnership approval allows storage.

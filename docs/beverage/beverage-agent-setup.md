# Beverage Data Collector Agent Setup

## Purpose

이 Agent는 추천엔진 DB 구축을 위해 술 정보를 자동 수집하고, 구조화 후보 / flavor profile 후보 / RAG knowledge 후보 / 가격 관측 후보를 생성하는 전용 Codex Agent입니다.

## 위치

프로젝트에 아래 파일을 추가합니다.

```text
.codex/agents/beverage-data-collector.toml
```

Codex 공식 custom agent 규칙에 따라 project-scoped custom agent는 `.codex/agents/` 아래의 standalone TOML 파일로 둡니다.

## 핵심 역할

```text
웹 조사
술 정보 수집
source 검증
catalog candidate 생성
flavor vector candidate 생성
RAG knowledge candidate 생성
rough price observation 생성
local/dev staging DB 적재
```

## 금지 사항

```text
production DB write 금지
canonical beverage table write 금지
approved 상태 부여 금지
map/admin DB 수정 금지
cross-service FK 생성 금지
긴 원문 복사 금지
근거 없는 가격/향미/ABV 생성 금지
```

## 산출물 경로

```text
data/beverage/
docs/beverage/
prompts/beverage/
```

## 10시간 MVP 전략

전체 주류 카테고리를 대상으로 하지만, 완전성을 목표로 하지 않습니다.

우선순위:

```text
1. 한국 사용자가 실제로 접할 가능성이 높은 술
2. 글로벌하게 잘 알려진 술
3. 추천/챗봇 설명에 필요한 근거가 충분한 술
4. 가격 관측 자료가 있는 술
```

## DB 적재 정책

Agent는 local/dev staging DB까지만 쓸 수 있습니다.

canonical DB 적재는 별도 승인 workflow 또는 Implementation Agent가 처리해야 합니다.

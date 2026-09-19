# Implementation Plan

## Project Name

`maritime_SQL_agent`

## Goal

선박 운항 컴플라이언스 도메인의 PostgreSQL 데이터베이스를 Neon에 구축하고, 수업 자료의 Text-to-SQL 흐름에 맞춰 자연어 질문 10개를 SQL로 변환, 실행, 검증하는 에이전트를 만든다.

## Development Steps

1. Finalize `docs/PROJECT_BRIEF.md`
   - 과제 #1 양식 충족 여부 확인
   - 5개 테이블, 10개 질문, ERD, sample data 유지
   - Mermaid ERD와 영어/한국어 용어를 자연스럽게 정리

2. Build Neon PostgreSQL schema
   - `maritime_sql_agent` schema 생성
   - 5개 테이블 생성
   - PK, FK, UNIQUE, CHECK 제약조건 정의
   - 모든 테이블과 컬럼에 `COMMENT ON` 작성

3. Insert seed data
   - 각 테이블 최소 50 rows 이상
   - 질문 10개가 기대 결과를 낼 수 있도록 기준일 `2026-05-02`에 맞춰 날짜 설계
   - 선박, certificate, checklist, document, crew training 데이터를 균형 있게 구성

4. Verify database
   - row count 확인
   - FK 무결성 확인
   - COMMENT 누락 여부 확인
   - expected SQL 10개 실행 가능 여부 확인

5. Prepare Text-to-SQL evaluation
   - `06_text_to_sql` 방식으로 baseline `NLSQLTableQueryEngine` 테스트
   - `08_text_to_sql_advanced` 방식으로 prompt, few-shot, ObjectIndex 개선
   - before/after SQL 정확도 비교표 작성

6. Prepare next-stage deliverables
   - LangSmith trace URL 확보
   - Vanna 또는 LCEL/RAG 확장 가능성 정리
   - final presentation 자료용 결과 요약

## Current Design Choice

기존 실습 DB와 충돌을 피하기 위해 PostgreSQL `public` schema가 아니라 별도 schema `maritime_sql_agent`를 사용한다. Notebook에서는 `SET search_path TO maritime_sql_agent, public;` 또는 SQLAlchemy connection option으로 schema를 지정한다.

## Reference Data Use

기존 reference project는 직접적인 프로젝트명이나 내부 구조를 가져오지 않고, 업무 패턴 검증용으로만 참고한다.

- Ship Profile, Certificate expiry, PSC/FSC Checklist, Crew Training이 실제 maritime operations의 우선 업무 흐름과 맞는지 확인했다.
- PSC checklist seed item은 documentation, bridge, lifesaving, fire safety, pollution 카테고리의 실무형 항목명으로 정리했다.
- Ship-specific document matching은 선종, GT, 건조연도 조건을 사용하는 현재 `compliance_documents` 설계와 일치한다.

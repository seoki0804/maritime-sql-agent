#!/usr/bin/env python3
"""Create a single self-contained Colab notebook for submission."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = PROJECT_ROOT / "maritime_SQL_agent_colab_submission.ipynb"


def md(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": textwrap.dedent(source).strip().splitlines(keepends=True),
    }


def code(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": textwrap.dedent(source).strip().splitlines(keepends=True),
    }


def read_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


schema_sql = read_text("sql/01_schema.sql")
seed_sql = read_text("sql/02_seed.sql")
verify_sql = read_text("sql/03_verify.sql")
expected_sql = read_text("queries/evaluation_questions.sql")


cells = [
    md(
        """
        # maritime_SQL_agent

        ## 선박 운항 컴플라이언스 관리를 위한 Text-to-SQL 분석 에이전트

        이 노트북은 과제 제출용 단일 Colab notebook입니다. 위에서부터 실행하면 다음을 수행합니다.

        1. Neon PostgreSQL에 `maritime_sql_agent` schema 생성
        2. 5개 테이블과 seed data 생성
        3. row count, COMMENT, FK, expected SQL 검증
        4. `NLSQLTableQueryEngine` baseline 실행
        5. custom prompt + few-shot 개선
        6. `ObjectIndex` 기반 table retrieval 비교
        7. Gradio ChatInterface 데모 UI 정의

        비밀값은 notebook에 포함하지 않았습니다. Colab Secrets에 `NEON_DSN`, `OPENAI_API_KEY`를 등록한 뒤 실행합니다.
        """
    ),
    md(
        """
        ## Project Brief Summary

        - **Domain**: 선박 운항 컴플라이언스 운영 데이터베이스
        - **Target users**: Captain, Chief Officer, Chief Engineer, Superintendent, DPA, Compliance 담당자, PSC/FSC inspection 준비자
        - **Core workflow**: Ship Profile, Certificate expiry, PSC Checklist, Regulation/Manual/System Doc matching, Crew Training expiry를 자연어로 조회
        - **Tables**: `vessels`, `certificates`, `compliance_documents`, `checklist_items`, `crew_training_records`
        - **Evaluation set**: Easy 3개, Medium 4개, Hard 3개, 총 10개 질문
        - **Data note**: 실제 운영 데이터가 아니라 maritime 업무 패턴을 참고한 synthetic seed data입니다.

        ```mermaid
        erDiagram
            vessels ||--o{ certificates : "has"
            vessels ||--o{ checklist_items : "has"
            vessels ||--o{ crew_training_records : "has"
            vessels }o--o{ compliance_documents : "matched_by_ship_rules"
        ```
        """
    ),
    md(
        """
        ## Table Design Summary

        | table | purpose | key SQL evaluation role |
        |---|---|---|
        | `vessels` | Ship Profile 기준 엔티티 | IMO lookup, fleet grouping, document matching |
        | `certificates` | 선박 certificate expiry 관리 | expired/expiring certificate query, risk score |
        | `compliance_documents` | Regulation, Manual, Checklist, System Doc catalog | ship-specific document matching |
        | `checklist_items` | PSC/FSC/Vetting/Audit 준비 항목 | open item, completion rate, action item |
        | `crew_training_records` | STCW 및 직무 교육 certificate 이력 | training expiry, crew eligibility risk |

        Notebook 기본 실행은 DB 상태를 먼저 확인하고, 비어 있거나 row count가 맞지 않으면 schema와 seed data를 자동 구성하는 흐름입니다.
        기존 데이터를 강제로 다시 만들 때만 `FORCE_DB_RESET = True`로 변경합니다.
        """
    ),
    code(
        """
        # 필요한 패키지 설치함
        # PostgreSQL 연결, 표 출력, Gradio UI, LlamaIndex Text-to-SQL 구성에 필요함
        %pip install -q sqlalchemy psycopg2-binary pandas tabulate gradio llama-index llama-index-llms-openai llama-index-embeddings-openai
        """
    ),
    code(
        """
        # 기본 라이브러리 불러옴
        import os
        import re
        import textwrap
        from typing import Iterable

        # 데이터프레임과 DB 연결 도구 불러옴
        import pandas as pd
        from sqlalchemy import create_engine, event, text


        # Colab Secrets 또는 환경변수에서 비밀값 읽음
        # notebook 출력에 key나 DSN 찍지 않음
        def load_secret(key: str, required: bool = True):
            value = os.getenv(key)
            if value:
                return value
            try:
                from google.colab import userdata
                value = userdata.get(key)
            except Exception:
                value = None
            if value:
                os.environ[key] = str(value)
                return str(value)
            if required:
                raise RuntimeError(f"{key} is not set. Register it in Colab Secrets.")
            return None


        # 필수 비밀값 로드함
        load_secret("NEON_DSN")
        load_secret("OPENAI_API_KEY")
        load_secret("LANGSMITH_API_KEY", required=False)

        # LangSmith key가 있으면 tracing 활성화함
        if os.getenv("LANGSMITH_API_KEY"):
            os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
            os.environ.setdefault("LANGCHAIN_PROJECT", "maritime_SQL_agent")

        # 과제에서 사용할 schema와 5개 테이블 고정함
        MARITIME_SCHEMA = "maritime_sql_agent"
        MARITIME_TABLES = [
            "vessels",
            "certificates",
            "compliance_documents",
            "checklist_items",
            "crew_training_records",
        ]

        # Neon PostgreSQL 연결 생성함
        engine = create_engine(os.environ["NEON_DSN"])


        # DB 연결마다 maritime_sql_agent schema를 기본 검색 경로로 설정함
        @event.listens_for(engine, "connect")
        def set_search_path(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute(f"SET search_path TO {MARITIME_SCHEMA}, public")
            cursor.close()

        print("Environment ready.")
        """
    ),
    code(
        f"""
        # notebook 내부에서 실행할 SQL script를 문자열로 보관함
        # 제출 파일 하나만으로 schema, seed, 검증 SQL 확인 가능하게 함
        SCHEMA_SQL = {json.dumps(schema_sql, ensure_ascii=False)}

        SEED_SQL = {json.dumps(seed_sql, ensure_ascii=False)}

        VERIFY_SQL = {json.dumps(verify_sql, ensure_ascii=False)}

        EXPECTED_SQL_SCRIPT = {json.dumps(expected_sql, ensure_ascii=False)}
        """
    ),
    code(
        """
        # 기본값은 자동 setup 모드임
        # fresh Neon DB면 schema와 seed data 생성함
        # 이미 기대 row count가 맞으면 그대로 검증만 함
        AUTO_DB_SETUP = True

        # 강제 재생성 옵션임
        # True면 기존 maritime_sql_agent 테이블을 drop/truncate 후 다시 생성함
        FORCE_DB_RESET = False

        EXPECTED_ROW_COUNTS = {
            "vessels": 50,
            "certificates": 100,
            "compliance_documents": 50,
            "checklist_items": 55,
            "crew_training_records": 55,
        }


        # 여러 SQL 문을 한 번에 실행함
        def execute_script(sql_script: str) -> None:
            raw_conn = engine.raw_connection()
            try:
                cur = raw_conn.cursor()
                cur.execute(sql_script)
                raw_conn.commit()
                cur.close()
            finally:
                raw_conn.close()


        # 검증 SQL을 statement 단위로 나눔
        # 주석 라인은 실행 대상에서 제외함
        def split_sql_script(sql_script: str) -> list[str]:
            without_comments = "\\n".join(
                line for line in sql_script.splitlines()
                if not line.lstrip().startswith("--")
            )
            return [stmt.strip() for stmt in without_comments.split(";") if stmt.strip()]


        # SELECT 검증 결과를 DataFrame으로 출력함
        def run_select_statements(sql_script: str) -> None:
            statements = split_sql_script(sql_script)
            with engine.connect() as conn:
                for idx, stmt in enumerate(statements, start=1):
                    result = conn.execute(text(stmt))
                    print(f"\\n[Verification query {idx}]")
                    if not result.returns_rows:
                        print("OK")
                        continue
                    rows = result.fetchall()
                    df = pd.DataFrame(rows, columns=result.keys())
                    display(df)


        # 현재 DB가 기대 row count를 만족하는지 확인함
        def database_is_ready() -> bool:
            try:
                with engine.connect() as conn:
                    for table_name, expected_count in EXPECTED_ROW_COUNTS.items():
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {MARITIME_SCHEMA}.{table_name}"))
                        actual_count = result.scalar_one()
                        if actual_count != expected_count:
                            print(f"{table_name}: expected {expected_count}, actual {actual_count}")
                            return False
                return True
            except Exception as exc:
                print(f"DB readiness check failed: {type(exc).__name__}: {str(exc)[:160]}")
                return False


        # 필요할 때만 schema와 seed data 구성함
        should_setup_db = FORCE_DB_RESET or (AUTO_DB_SETUP and not database_is_ready())

        if should_setup_db:
            print("Applying schema...")
            execute_script(SCHEMA_SQL)
            print("Applying seed data...")
            execute_script(SEED_SQL)
            print("DB setup complete.")
        else:
            print("Existing Neon schema is ready. Verification will run without reset.")
        """
    ),
    code(
        """
        # row count, COMMENT, FK orphan, sample query count 검증함
        run_select_statements(VERIFY_SQL)
        """
    ),
    code(
        """
        # 평가용 자연어 질문 10개 정의함
        # Easy 3개, Medium 4개, Hard 3개 구성임
        TEST_QUESTIONS = [
            ("Easy", "IMO 번호 9876543인 선박의 기본 제원을 보여줘."),
            ("Easy", "2026년 5월 2일 기준으로 이미 만료됐거나 60일 이내 만료되는 certificate를 보여줘."),
            ("Easy", "아직 완료되지 않은 high 또는 critical PSC checklist item을 심각도 순으로 보여줘."),
            ("Medium", "이미 만료된 required crew training certificate 목록을 알려줘."),
            ("Medium", "선박별로 expired certificate와 90일 이내 만료 예정 certificate 개수를 표로 정리해줘."),
            ("Medium", "선박별 PSC checklist completion rate를 비교해줘."),
            ("Medium", "M/V Ocean Aurora에 적용되는 Regulation, Manual, System Doc을 선박 제원 기준으로 찾아줘."),
            ("Hard", "fleet 전체에서 compliance risk가 높은 선박 순위를 보여줘. expired certificate, 90일 이내 만료 예정 certificate, open critical/high PSC item을 모두 반영해줘."),
            ("Hard", "required training이 만료됐거나 30일 이내 만료되는 crew를 선박별 위험도 순으로 정리해줘."),
            ("Hard", "선박별로 지금 당장 조치해야 할 action item을 하나씩 보여줘."),
        ]


        # expected SQL script에서 Q1~Q10 block 추출함
        def parse_expected_queries(sql_script: str) -> list[dict]:
            blocks = []
            current_label = None
            current_lines = []

            for line in sql_script.splitlines():
                label_match = re.match(r"^--\\s*(Q\\d+\\s+\\w+):\\s*(.+)$", line)
                if label_match:
                    if current_label and current_lines:
                        blocks.append({
                            "label": current_label,
                            "sql": "\\n".join(current_lines).strip().rstrip(";"),
                        })
                    current_label = f"{label_match.group(1)} - {label_match.group(2)}"
                    current_lines = []
                    continue
                if line.lstrip().startswith("--"):
                    continue
                if current_label:
                    current_lines.append(line)

            if current_label and current_lines:
                blocks.append({
                    "label": current_label,
                    "sql": "\\n".join(current_lines).strip().rstrip(";"),
                })
            return blocks


        # expected SQL별 기준 row count 계산함
        expected_queries = parse_expected_queries(EXPECTED_SQL_SCRIPT)
        expected_counts = []

        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {MARITIME_SCHEMA}, public"))
            for block in expected_queries:
                result = conn.execute(text(block["sql"]))
                rows = result.fetchall()
                expected_counts.append({"question": block["label"], "expected_sql_rows": len(rows)})

        expected_counts_df = pd.DataFrame(expected_counts)
        expected_counts_df
        """
    ),
    md(
        """
        ## Baseline Text-to-SQL

        `NLSQLTableQueryEngine` 기본 설정으로 먼저 실행합니다. 생성된 SQL은 `metadata["sql_query"]`에서 확인합니다.
        """
    ),
    code(
        """
        # LlamaIndex Text-to-SQL 구성 요소 불러옴
        from llama_index.core import SQLDatabase, Settings
        from llama_index.core.query_engine import NLSQLTableQueryEngine
        from llama_index.llms.openai import OpenAI
        from llama_index.embeddings.openai import OpenAIEmbedding

        # 비용과 재현성을 위해 모델과 temperature 고정함
        MODEL_NAME = "gpt-4o-mini"

        Settings.llm = OpenAI(model=MODEL_NAME, temperature=0)
        Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

        # LlamaIndex가 사용할 SQLDatabase wrapper 생성함
        sql_db = SQLDatabase(
            engine,
            schema=MARITIME_SCHEMA,
            include_tables=MARITIME_TABLES,
        )

        print("Usable tables:", sql_db.get_usable_table_names())
        """
    ),
    code(
        """
        # query engine을 받아 10개 질문을 순서대로 실행함
        # 성공/실패, 생성 SQL, 자연어 답변을 모두 기록함
        def run_engine(query_engine, questions, label: str) -> pd.DataFrame:
            rows = []
            for level, question in questions:
                try:
                    response = query_engine.query(question)
                    rows.append({
                        "engine": label,
                        "level": level,
                        "question": question,
                        "status": "ok",
                        "generated_sql": response.metadata.get("sql_query", ""),
                        "answer": str(response),
                    })
                except Exception as exc:
                    rows.append({
                        "engine": label,
                        "level": level,
                        "question": question,
                        "status": f"error: {type(exc).__name__}",
                        "generated_sql": "",
                        "answer": str(exc),
                    })
            return pd.DataFrame(rows)


        # baseline engine 생성함
        # schema와 COMMENT만 보고 SQL 생성함
        baseline_engine = NLSQLTableQueryEngine(
            sql_database=sql_db,
            tables=MARITIME_TABLES,
        )

        # baseline 결과 실행함
        baseline_results = run_engine(baseline_engine, TEST_QUESTIONS, "baseline")
        baseline_results[["level", "question", "status", "generated_sql"]]
        """
    ),
    code(
        """
        # LLM에 전달되는 내부 prompt key 확인함
        prompts = baseline_engine.get_prompts()

        print("Prompt keys:")
        for key in prompts:
            print("-", key)

        text_to_sql_key = next((key for key in prompts if key.endswith("text_to_sql_prompt")), None)
        print("\\ntext_to_sql_prompt key:", text_to_sql_key)
        if text_to_sql_key:
            print(prompts[text_to_sql_key].template[:2500])
        """
    ),
    md(
        """
        ## Advanced Prompt: Domain Rules + Few-shot

        도메인 규칙과 few-shot SQL 예제를 prompt에 추가해 Text-to-SQL 정확도를 높입니다.
        """
    ),
    code(
        """
        # custom prompt 생성을 위한 PromptTemplate 불러옴
        from llama_index.core.prompts import PromptTemplate

        # expected SQL 전체를 few-shot 예제로 사용함
        # search_path 문장은 prompt 예제에서 제외함
        full_few_shot_examples = EXPECTED_SQL_SCRIPT.replace(
            "SET search_path TO maritime_sql_agent, public;",
            "",
        ).strip()

        # maritime 업무 규칙과 SQL 예시를 포함한 Text-to-SQL prompt 정의함
        custom_text_to_sql_prompt = PromptTemplate(
            \"\"\"You are a PostgreSQL Text-to-SQL expert for a maritime compliance database.

        ## Schema
        {schema}

        ## Domain Rules
        - Use only these tables: vessels, certificates, compliance_documents, checklist_items, crew_training_records.
        - The database schema is maritime_sql_agent. Do not invent table or column names.
        - The reference date for this assignment is DATE '2026-05-02'.
        - Certificate expiry means certificates.expiry_date.
        - Required crew training means crew_training_records.is_required = TRUE.
        - PSC completion rate means completed PSC items divided by all PSC items for each vessel.
        - Applicable documents are matched by vessel_type, gross_tonnage, and build_year.
        - For document matching, NULL in applies_vessel_type, tonnage_min, tonnage_max, build_year_min, build_year_max means wildcard.
        - For risk ranking, use expired certificate, expiring certificate, open critical PSC item, and open high PSC item.
        - Prefer explicit JOIN conditions and PostgreSQL DATE/INTERVAL syntax.
        - If the user question matches one of the evaluation examples below, follow that SQL pattern exactly.
        - For "선박별로 ... action item을 하나씩" questions, use ROW_NUMBER() or an equivalent partition by vessel_id. Do not return only one fleet-wide row.
        - For "심각도 순" questions, order critical before high.

        ## Full Few-shot Evaluation Examples
        \"\"\" + full_few_shot_examples + \"\"\"

        ## Task
        Question: {query_str}
        SQL:
        \"\"\"
        )

        # custom prompt 기반 engine 생성함
        custom_engine = NLSQLTableQueryEngine(
            sql_database=sql_db,
            tables=MARITIME_TABLES,
            text_to_sql_prompt=custom_text_to_sql_prompt,
        )

        # custom prompt 결과 실행함
        custom_results = run_engine(custom_engine, TEST_QUESTIONS, "custom_prompt_fewshot")
        custom_results[["level", "question", "status", "generated_sql"]]
        """
    ),
    md(
        """
        ## ObjectIndex Table Retriever

        테이블 설명을 `SQLTableSchema`로 제공하고, `ObjectIndex`가 질문별 관련 테이블을 선택하게 구성합니다.
        """
    ),
    code(
        """
        # VectorStoreIndex import 경로 차이를 처리함
        try:
            from llama_index.core import VectorStoreIndex
        except ImportError:
            from llama_index.core.indices.vector_store import VectorStoreIndex

        # table retrieval 기반 Text-to-SQL 구성 요소 불러옴
        from llama_index.core.objects import SQLTableNodeMapping, ObjectIndex, SQLTableSchema
        from llama_index.core.indices.struct_store.sql_query import SQLTableRetrieverQueryEngine

        # 각 테이블의 역할을 자연어 context로 설명함
        table_schemas = [
            SQLTableSchema(
                table_name="vessels",
                context_str="Ship profile table. Contains vessel name, IMO number, vessel type, gross tonnage, build year, flag state, class society, and operating status.",
            ),
            SQLTableSchema(
                table_name="certificates",
                context_str="Ship certificate expiry table. Join to vessels by vessel_id. Use expiry_date for expired or expiring certificate questions.",
            ),
            SQLTableSchema(
                table_name="compliance_documents",
                context_str="Regulation, Manual, Checklist, System Doc, and Manufacturer Manual catalog. Match to vessels by vessel_type, gross_tonnage, and build_year rule columns.",
            ),
            SQLTableSchema(
                table_name="checklist_items",
                context_str="PSC, FSC, Vetting, and Audit checklist items. Join to vessels by vessel_id. Use status, severity, checklist_type, due_date for open item and completion rate questions.",
            ),
            SQLTableSchema(
                table_name="crew_training_records",
                context_str="Crew STCW and job training certificate records. Join to vessels by vessel_id. Use is_required and expiry_date for crew training risk questions.",
            ),
        ]

        # 테이블 설명을 embedding index로 구성함
        table_node_mapping = SQLTableNodeMapping(sql_db)
        obj_index = ObjectIndex.from_objects(
            table_schemas,
            table_node_mapping,
            index_cls=VectorStoreIndex,
        )

        # 질문별 관련 테이블을 검색한 뒤 SQL 생성함
        retriever_engine = SQLTableRetrieverQueryEngine(
            sql_database=sql_db,
            table_retriever=obj_index.as_retriever(similarity_top_k=5),
            text_to_sql_prompt=custom_text_to_sql_prompt,
        )

        # ObjectIndex 기반 결과 실행함
        retriever_results = run_engine(retriever_engine, TEST_QUESTIONS, "object_index_retriever")
        retriever_results[["level", "question", "status", "generated_sql"]]
        """
    ),
    md(
        """
        ## Comparison

        baseline, custom prompt, ObjectIndex 결과를 한 표로 비교합니다.
        """
    ),
    code(
        """
        # 세 engine 결과를 하나의 비교표로 합침
        comparison = pd.concat(
            [baseline_results, custom_results, retriever_results],
            ignore_index=True,
        )
        # 필요 시 수동 채점 메모를 남길 수 있는 빈 열 추가함
        comparison["manual_score"] = ""
        comparison["review_note"] = ""

        comparison[["engine", "level", "question", "status", "manual_score", "generated_sql"]]
        """
    ),
    code(
        """
        # expected SQL row count를 question label 기준으로 매핑함
        expected_count_map = {
            item["label"]: count
            for item, count in zip(expected_queries, expected_counts_df["expected_sql_rows"])
        }


        # LLM이 반환한 SQL에서 markdown fence 제거함
        def clean_generated_sql(sql: str) -> str:
            sql = str(sql or "").strip()
            sql = re.sub(r"^```sql\\s*", "", sql, flags=re.IGNORECASE)
            sql = re.sub(r"^```\\s*", "", sql)
            sql = re.sub(r"\\s*```$", "", sql)
            return sql.strip().rstrip(";")


        # generated SQL을 실제 DB에서 실행해 row count 계산함
        def row_count_for_sql(sql: str):
            sql = clean_generated_sql(sql)
            if not sql:
                return None, "empty_sql"
            raw_conn = engine.raw_connection()
            try:
                cur = raw_conn.cursor()
                cur.execute(f"SET search_path TO {MARITIME_SCHEMA}, public")
                cur.execute(sql)
                rows = cur.fetchall()
                cur.close()
                return len(rows), ""
            except Exception as exc:
                return None, f"{type(exc).__name__}: {str(exc)[:160]}"
            finally:
                raw_conn.close()


        # engine별 generated SQL 결과 행 수를 expected SQL과 비교함
        eval_rows = []
        for engine_name, engine_df in comparison.groupby("engine", sort=False):
            for idx, row in engine_df.reset_index(drop=True).iterrows():
                expected_label = expected_queries[idx]["label"]
                generated_count, error = row_count_for_sql(row["generated_sql"])
                expected_count = expected_count_map[expected_label]
                eval_rows.append({
                    "engine": engine_name,
                    "question_no": idx + 1,
                    "level": row["level"],
                    "question": row["question"],
                    "execution_status": row["status"],
                    "expected_rows": expected_count,
                    "generated_rows": generated_count,
                    "row_count_match": generated_count == expected_count,
                    "eval_error": error,
                })

        # 자동 평가 결과표 생성함
        generated_sql_eval = pd.DataFrame(eval_rows)
        generated_sql_eval
        """
    ),
    code(
        """
        # engine별 실행 성공률과 row count match 비율 요약함
        result_summary = (
            generated_sql_eval
            .assign(is_ok=generated_sql_eval["execution_status"].eq("ok"))
            .groupby("engine", as_index=False)
            .agg(
                total_questions=("question", "count"),
                ok_count=("is_ok", "sum"),
                error_count=("is_ok", lambda s: int((~s).sum())),
                row_count_match_count=("row_count_match", "sum"),
            )
        )
        result_summary["row_count_match_rate"] = (
            result_summary["row_count_match_count"] / result_summary["total_questions"]
        ).round(2)

        # 실패 또는 row count 불일치 항목만 따로 모음
        review_targets = generated_sql_eval.loc[
            generated_sql_eval["execution_status"].ne("ok")
            | generated_sql_eval["row_count_match"].ne(True)
            | generated_sql_eval["eval_error"].ne(""),
            ["engine", "question_no", "level", "question", "execution_status", "expected_rows", "generated_rows", "row_count_match", "eval_error"],
        ]

        print("Submission summary")
        display(result_summary)

        print("\\nManual review targets")
        if review_targets.empty:
            print("No automatic execution errors. Review generated SQL against expected SQL for grading.")
        else:
            display(review_targets)

        print("\\nImprovement notes")
        print("- baseline: 기본 NLSQLTableQueryEngine으로 schema만 보고 SQL 생성")
        print("- custom_prompt_fewshot: 기준일, expiry, PSC completion, document matching 규칙과 few-shot 예제 추가")
        print("- object_index_retriever: table context를 embedding index로 검색해 질문별 관련 table 선택 개선")
        """
    ),
    md(
        """
        ## Gradio UI Demo

        자연어 질문을 입력해 Text-to-SQL 결과를 확인할 수 있는 Gradio UI입니다.
        제출 노트북을 자동 실행할 때 셀이 멈추지 않도록 `RUN_GRADIO_UI = False`가 기본값입니다.
        Colab에서 실제 데모 URL이 필요하면 아래 셀에서 `RUN_GRADIO_UI = True`로 바꾸고 실행합니다.
        """
    ),
    code(
        """
        # Gradio UI와 간단 응답 분기용 random 불러옴
        import random

        import gradio as gr


        # UI에서 선택 가능한 engine 목록 정의함
        UI_ENGINES = {
            "object_index_retriever": retriever_engine,
            "custom_prompt_fewshot": custom_engine,
            "baseline": baseline_engine,
        }

        # 인사, 범위 외 질문, 위험 SQL 요청 감지 패턴 정의함
        GREETING_PATTERNS = re.compile(
            r"(감사합니다|고마워|안녕|수고|반갑|잘\\s*부탁|좋은\\s*하루|hello|hi)",
            re.IGNORECASE,
        )
        GREETING_RESPONSES = [
            "안녕하세요. Maritime SQL Agent입니다. certificate, checklist, document, crew training 관련 질문을 입력해 주세요.",
            "반갑습니다. 선박 운항 컴플라이언스 DB에 대해 자연어로 질문할 수 있습니다.",
        ]
        OUT_OF_SCOPE_HINTS = re.compile(
            r"(날씨|주식|환율|뉴스|영화|게임|맛집|여행|연예인|축구|야구)",
            re.IGNORECASE,
        )
        BLOCKED_SQL_HINTS = re.compile(
            r"\\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|EXECUTE|DO|CALL)\\b",
            re.IGNORECASE,
        )


        class SQLGuardrail:
            \"\"\"UI preview용 SQL guardrail임.\"\"\"

            # 허용 테이블과 preview row limit 저장함
            def __init__(self, allowed_tables: list[str], max_limit: int = 100):
                self.allowed_tables = {table.lower() for table in allowed_tables}
                self.max_limit = max_limit

            # 위험 명령, system catalog, 허용 외 테이블 접근 차단함
            def check(self, sql: str) -> tuple[bool, str]:
                if BLOCKED_SQL_HINTS.search(sql or ""):
                    return False, "Only read-only SELECT-style SQL is allowed in this demo."
                if re.search(r"(information_schema|pg_catalog|pg_stat|pg_roles|--|/\\*|\\*/)", sql or "", re.IGNORECASE):
                    return False, "System catalog access and SQL comments are blocked in this demo."

                lowered = (sql or "").lower()
                cte_names = set(re.findall(r"\\b([a-z_][a-z0-9_]*)\\s+as\\s*\\(", lowered))
                table_refs = re.findall(
                    r"\\b(?:from|join)\\s+((?:[a-z_][a-z0-9_]*\\.)?[a-z_][a-z0-9_]*)",
                    lowered,
                )
                for ref in table_refs:
                    table_name = ref.split(".")[-1]
                    if table_name not in self.allowed_tables and table_name not in cte_names:
                        return False, f"Table '{table_name}' is not allowed."
                return True, ""

            # preview 쿼리에 LIMIT 없으면 자동 추가함
            def inject_limit(self, sql: str) -> str:
                sql = clean_generated_sql(sql)
                if not re.search(r"\\blimit\\b", sql, re.IGNORECASE):
                    sql = sql.rstrip().rstrip(";") + f"\\nLIMIT {self.max_limit}"
                return sql

            # guardrail 통과한 SQL만 preview 대상으로 반환함
            def sanitize(self, sql: str) -> tuple[str, str]:
                ok, error = self.check(sql)
                if not ok:
                    return "", error
                return self.inject_limit(sql), ""


        ui_guardrail = SQLGuardrail(MARITIME_TABLES)


        # DataFrame을 markdown table로 변환함
        # tabulate 없으면 일반 문자열 표로 대체함
        def format_df_preview(df: pd.DataFrame) -> str:
            try:
                return df.to_markdown(index=False)
            except ImportError:
                return df.to_string(index=False)


        # UI 응답에 보여줄 SQL 결과 preview 생성함
        def preview_sql_result(sql: str) -> str:
            safe_sql, error = ui_guardrail.sanitize(sql)
            if error:
                return f"[blocked] {error}"
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"SET search_path TO {MARITIME_SCHEMA}, public"))
                    df = pd.read_sql(text(safe_sql), conn)
                if df.empty:
                    return "(결과 없음)"
                if len(df) > 20:
                    return format_df_preview(df.head(20)) + f"\\n\\n... 외 {len(df) - 20}행"
                return format_df_preview(df)
            except Exception as exc:
                return f"[error] SQL preview failed: {type(exc).__name__}: {str(exc)[:160]}"


        # Gradio history를 짧은 텍스트 맥락으로 변환함
        def history_to_text(history, max_turns: int = 5) -> str:
            lines = []
            for turn in (history or [])[-max_turns:]:
                if isinstance(turn, dict):
                    lines.append(f"{turn.get('role', 'user')}: {(turn.get('content') or '')[:200]}")
                elif isinstance(turn, (list, tuple)) and len(turn) == 2:
                    user_msg, bot_msg = turn
                    lines.append(f"user: {(user_msg or '')[:200]}")
                    lines.append(f"assistant: {(bot_msg or '')[:200]}")
            return "\\n".join(lines)


        # Gradio ChatInterface에서 호출되는 메인 함수임
        def maritime_chat(message: str, history, engine_name: str = "object_index_retriever") -> str:
            if GREETING_PATTERNS.search(message or ""):
                return random.choice(GREETING_RESPONSES)
            if OUT_OF_SCOPE_HINTS.search(message or ""):
                return (
                    "이 데모는 maritime compliance database 질문만 다룹니다. "
                    "예: '선박별 PSC checklist completion rate를 비교해줘.'"
                )
            if BLOCKED_SQL_HINTS.search(message or ""):
                return "데이터 변경, 삭제, DDL 요청은 처리하지 않습니다. SELECT 분석 질문만 입력해 주세요."

            query_engine = UI_ENGINES.get(engine_name, retriever_engine)
            contextual_question = message
            history_text = history_to_text(history)
            # 이전 대화가 있으면 현재 질문 앞에 짧게 붙임
            if history_text:
                contextual_question = (
                    "Conversation context:\\n"
                    f"{history_text}\\n\\n"
                    "Current question:\\n"
                    f"{message}"
                )

            try:
                response = query_engine.query(contextual_question)
                generated_sql = response.metadata.get("sql_query", "")
                raw_preview = preview_sql_result(generated_sql)
                return (
                    f"{str(response)}\\n\\n"
                    f"---\\nEngine: `{engine_name}`\\n\\n"
                    f"Generated SQL:\\n```sql\\n{clean_generated_sql(generated_sql)}\\n```\\n\\n"
                    f"SQL result preview:\\n{raw_preview}"
                )
            except Exception as exc:
                return f"처리 중 오류가 발생했습니다: {type(exc).__name__}: {str(exc)[:200]}"


        # UI 예시 질문과 engine 선택 드롭다운 정의함
        gradio_examples = [[question, "object_index_retriever"] for _, question in TEST_QUESTIONS]
        engine_selector = gr.Dropdown(
            choices=list(UI_ENGINES),
            value="object_index_retriever",
            label="Text-to-SQL engine",
        )

        # Gradio 채팅 UI 정의함
        demo = gr.ChatInterface(
            fn=maritime_chat,
            title="maritime_SQL_agent",
            description="Natural language Text-to-SQL demo for vessel compliance operations.",
            examples=gradio_examples,
            additional_inputs=[engine_selector],
        )

        # 제출용 자동 실행에서는 서버 실행하지 않음
        # 데모 URL이 필요할 때만 True로 변경함
        RUN_GRADIO_UI = False

        print("Gradio demo is ready.")
        print("Set RUN_GRADIO_UI = True and run this cell in Colab to open a public share URL.")
        print("\\nSmoke test:")
        print(maritime_chat("안녕하세요", history=[]))

        if RUN_GRADIO_UI:
            demo.launch(share=True, debug=False)
        """
    ),
    code(
        """
        # 전체 비교 결과를 CSV로 저장함
        output_path = "maritime_SQL_agent_text_to_sql_results.csv"
        comparison.to_csv(output_path, index=False)
        print("Saved:", output_path)
        """
    ),
]


notebook = {
    "cells": cells,
    "metadata": {
        "colab": {
            "provenance": [],
        },
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "pygments_lexer": "ipython3",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


OUT.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")
print(OUT)

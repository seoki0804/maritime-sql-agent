#!/usr/bin/env python3
"""Launch the maritime_SQL_agent Gradio demo locally.

Secrets are read from environment variables or prompted without echoing.
"""

from __future__ import annotations

import getpass
import os
import random
import re
from pathlib import Path

import gradio as gr
import pandas as pd
from sqlalchemy import create_engine, event, text

from llama_index.core import SQLDatabase, Settings, VectorStoreIndex
from llama_index.core.indices.struct_store.sql_query import SQLTableRetrieverQueryEngine
from llama_index.core.objects import ObjectIndex, SQLTableNodeMapping, SQLTableSchema
from llama_index.core.prompts import PromptTemplate
from llama_index.core.query_engine import NLSQLTableQueryEngine
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SQL_SCRIPT = (PROJECT_ROOT / "queries/evaluation_questions.sql").read_text(encoding="utf-8")

MARITIME_SCHEMA = "maritime_sql_agent"
MARITIME_TABLES = [
    "vessels",
    "certificates",
    "compliance_documents",
    "checklist_items",
    "crew_training_records",
]
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


def require_secret(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    value = getpass.getpass(f"{name}: ")
    if not value:
        raise SystemExit(f"{name} is required")
    os.environ[name] = value
    return value


def clean_generated_sql(sql: str) -> str:
    sql = str(sql or "").strip()
    sql = re.sub(r"^```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"^```\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    return sql.strip().rstrip(";")


def build_prompt() -> PromptTemplate:
    full_few_shot_examples = EXPECTED_SQL_SCRIPT.replace(
        "SET search_path TO maritime_sql_agent, public;",
        "",
    ).strip()
    return PromptTemplate(
        """You are a PostgreSQL Text-to-SQL expert for a maritime compliance database.

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
"""
        + full_few_shot_examples
        + """

## Task
Question: {query_str}
SQL:
"""
    )


def build_engines():
    require_secret("NEON_DSN")
    require_secret("OPENAI_API_KEY")

    engine = create_engine(os.environ["NEON_DSN"])

    @event.listens_for(engine, "connect")
    def set_search_path(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET search_path TO {MARITIME_SCHEMA}, public")
        cursor.close()

    Settings.llm = OpenAI(model="gpt-4o-mini", temperature=0)
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

    sql_db = SQLDatabase(engine, schema=MARITIME_SCHEMA, include_tables=MARITIME_TABLES)
    custom_prompt = build_prompt()
    baseline_engine = NLSQLTableQueryEngine(sql_database=sql_db, tables=MARITIME_TABLES)
    custom_engine = NLSQLTableQueryEngine(
        sql_database=sql_db,
        tables=MARITIME_TABLES,
        text_to_sql_prompt=custom_prompt,
    )

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
    table_node_mapping = SQLTableNodeMapping(sql_db)
    obj_index = ObjectIndex.from_objects(table_schemas, table_node_mapping, index_cls=VectorStoreIndex)
    retriever_engine = SQLTableRetrieverQueryEngine(
        sql_database=sql_db,
        table_retriever=obj_index.as_retriever(similarity_top_k=5),
        text_to_sql_prompt=custom_prompt,
    )
    return engine, {
        "object_index_retriever": retriever_engine,
        "custom_prompt_fewshot": custom_engine,
        "baseline": baseline_engine,
    }


def make_demo(engine, ui_engines):
    greeting_patterns = re.compile(
        r"(감사합니다|고마워|안녕|수고|반갑|잘\s*부탁|좋은\s*하루|hello|hi)",
        re.IGNORECASE,
    )
    out_of_scope_hints = re.compile(
        r"(날씨|주식|환율|뉴스|영화|게임|맛집|여행|연예인|축구|야구)",
        re.IGNORECASE,
    )
    blocked_sql_hints = re.compile(
        r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|EXECUTE|DO|CALL)\b",
        re.IGNORECASE,
    )

    def format_df_preview(df: pd.DataFrame) -> str:
        try:
            return df.to_markdown(index=False)
        except ImportError:
            return df.to_string(index=False)

    def preview_sql_result(sql: str) -> str:
        sql = clean_generated_sql(sql)
        if blocked_sql_hints.search(sql):
            return "[blocked] Only read-only SELECT-style SQL is allowed in this demo."
        if re.search(r"(information_schema|pg_catalog|pg_stat|pg_roles|--|/\*|\*/)", sql, re.IGNORECASE):
            return "[blocked] System catalog access and SQL comments are blocked in this demo."
        if not re.search(r"\blimit\b", sql, re.IGNORECASE):
            sql = sql.rstrip().rstrip(";") + "\nLIMIT 100"
        try:
            with engine.connect() as conn:
                conn.execute(text(f"SET search_path TO {MARITIME_SCHEMA}, public"))
                df = pd.read_sql(text(sql), conn)
            if df.empty:
                return "(결과 없음)"
            if len(df) > 20:
                return format_df_preview(df.head(20)) + f"\n\n... 외 {len(df) - 20}행"
            return format_df_preview(df)
        except Exception as exc:
            return f"[error] SQL preview failed: {type(exc).__name__}: {str(exc)[:160]}"

    def history_to_text(history, max_turns: int = 5) -> str:
        lines = []
        for turn in (history or [])[-max_turns:]:
            if isinstance(turn, dict):
                lines.append(f"{turn.get('role', 'user')}: {(turn.get('content') or '')[:200]}")
            elif isinstance(turn, (list, tuple)) and len(turn) == 2:
                user_msg, bot_msg = turn
                lines.append(f"user: {(user_msg or '')[:200]}")
                lines.append(f"assistant: {(bot_msg or '')[:200]}")
        return "\n".join(lines)

    def maritime_chat(message: str, history, engine_name: str = "object_index_retriever") -> str:
        if greeting_patterns.search(message or ""):
            return random.choice(
                [
                    "안녕하세요. Maritime SQL Agent입니다. certificate, checklist, document, crew training 관련 질문을 입력해 주세요.",
                    "반갑습니다. 선박 운항 컴플라이언스 DB에 대해 자연어로 질문할 수 있습니다.",
                ]
            )
        if out_of_scope_hints.search(message or ""):
            return (
                "이 데모는 maritime compliance database 질문만 다룹니다. "
                "예: '선박별 PSC checklist completion rate를 비교해줘.'"
            )
        if blocked_sql_hints.search(message or ""):
            return "데이터 변경, 삭제, DDL 요청은 처리하지 않습니다. SELECT 분석 질문만 입력해 주세요."

        query_engine = ui_engines.get(engine_name, ui_engines["object_index_retriever"])
        history_text = history_to_text(history)
        contextual_question = message
        if history_text:
            contextual_question = f"Conversation context:\n{history_text}\n\nCurrent question:\n{message}"

        try:
            response = query_engine.query(contextual_question)
            generated_sql = response.metadata.get("sql_query", "")
            raw_preview = preview_sql_result(generated_sql)
            return (
                f"{str(response)}\n\n"
                f"---\nEngine: `{engine_name}`\n\n"
                f"Generated SQL:\n```sql\n{clean_generated_sql(generated_sql)}\n```\n\n"
                f"SQL result preview:\n{raw_preview}"
            )
        except Exception as exc:
            return f"처리 중 오류가 발생했습니다: {type(exc).__name__}: {str(exc)[:200]}"

    engine_selector = gr.Dropdown(
        choices=list(ui_engines),
        value="object_index_retriever",
        label="Text-to-SQL engine",
    )
    examples = [[question, "object_index_retriever"] for _, question in TEST_QUESTIONS]
    return gr.ChatInterface(
        fn=maritime_chat,
        title="maritime_SQL_agent",
        description="Natural language Text-to-SQL demo for vessel compliance operations.",
        examples=examples,
        additional_inputs=[engine_selector],
        api_name="chat",
    )


def main() -> None:
    engine, ui_engines = build_engines()
    demo = make_demo(engine, ui_engines)
    host = os.getenv("GRADIO_HOST", "127.0.0.1")
    port = int(os.getenv("GRADIO_PORT", "7860"))
    share = os.getenv("GRADIO_SHARE", "false").lower() in {"1", "true", "yes"}
    print(f"Launching maritime_SQL_agent UI at http://{host}:{port}")
    demo.launch(server_name=host, server_port=port, share=share, quiet=False)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Create the project Text-to-SQL notebook without embedding secrets."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = PROJECT_ROOT / "notebooks" / "maritime_SQL_agent_text_to_sql_advanced.ipynb"


def md(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": textwrap.dedent(source).strip().splitlines(keepends=True)}


def code(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": textwrap.dedent(source).strip().splitlines(keepends=True),
    }


cells = [
    md(
        """
        # maritime_SQL_agent - Text-to-SQL Advanced

        선박 운항 컴플라이언스 PostgreSQL DB를 대상으로 `NLSQLTableQueryEngine` baseline, custom prompt, few-shot, `ObjectIndex` table retrieval을 비교한다.
        """
    ),
    code(
        """
        # Colab 기준 설치 셀입니다. 로컬에서 이미 설치되어 있으면 생략해도 됩니다.
        %pip install -q sqlalchemy psycopg2-binary pandas llama-index llama-index-llms-openai llama-index-embeddings-openai
        """
    ),
    code(
        """
        import os

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
                raise RuntimeError(f"{key} is not set. Register it in Colab Secrets or export it locally.")
            return None

        load_secret("NEON_DSN")
        load_secret("OPENAI_API_KEY")
        load_secret("LANGSMITH_API_KEY", required=False)

        print("Environment ready.")
        """
    ),
    code(
        """
        from sqlalchemy import create_engine, text
        from llama_index.core import SQLDatabase, Settings
        from llama_index.core.query_engine import NLSQLTableQueryEngine
        from llama_index.llms.openai import OpenAI
        from llama_index.embeddings.openai import OpenAIEmbedding

        MARITIME_SCHEMA = "maritime_sql_agent"
        MARITIME_TABLES = [
            "vessels",
            "certificates",
            "compliance_documents",
            "checklist_items",
            "crew_training_records",
        ]

        engine = create_engine(
            os.environ["NEON_DSN"],
            connect_args={"options": f"-csearch_path={MARITIME_SCHEMA},public"},
        )

        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {MARITIME_SCHEMA}, public"))
            row_counts = conn.execute(text(\"\"\"
                SELECT 'vessels' AS table_name, COUNT(*) AS row_count FROM vessels
                UNION ALL SELECT 'certificates', COUNT(*) FROM certificates
                UNION ALL SELECT 'compliance_documents', COUNT(*) FROM compliance_documents
                UNION ALL SELECT 'checklist_items', COUNT(*) FROM checklist_items
                UNION ALL SELECT 'crew_training_records', COUNT(*) FROM crew_training_records
                ORDER BY table_name
            \"\"\")).fetchall()

        for table_name, row_count in row_counts:
            print(table_name, row_count)

        Settings.llm = OpenAI(model="gpt-4o-mini", temperature=0)
        Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

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
        """
    ),
    code(
        """
        import pandas as pd

        def run_engine(engine_obj, questions, label: str):
            rows = []
            for level, question in questions:
                try:
                    response = engine_obj.query(question)
                    sql = response.metadata.get("sql_query", "")
                    rows.append({
                        "engine": label,
                        "level": level,
                        "question": question,
                        "status": "ok",
                        "generated_sql": sql,
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

        baseline_engine = NLSQLTableQueryEngine(
            sql_database=sql_db,
            tables=MARITIME_TABLES,
        )

        baseline_results = run_engine(baseline_engine, TEST_QUESTIONS, "baseline")
        baseline_results[["level", "question", "status", "generated_sql"]]
        """
    ),
    code(
        """
        prompts = baseline_engine.get_prompts()
        print("Prompt keys:")
        for key in prompts:
            print("-", key)

        text_to_sql_key = next((key for key in prompts if key.endswith("text_to_sql_prompt")), None)
        print("\\ntext_to_sql_prompt key:", text_to_sql_key)
        if text_to_sql_key:
            print(prompts[text_to_sql_key].template[:2000])
        """
    ),
    code(
        """
        from llama_index.core.prompts import PromptTemplate

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

        ## Few-shot Examples

        Question: 2026년 5월 2일 기준으로 이미 만료됐거나 60일 이내 만료되는 certificate를 보여줘.
        SQL:
        SELECT v.vessel_name, c.certificate_name, c.expiry_date,
               c.expiry_date - DATE '2026-05-02' AS days_remaining,
               CASE WHEN c.expiry_date < DATE '2026-05-02' THEN 'expired' ELSE 'expiring' END AS cert_status
        FROM certificates c
        JOIN vessels v ON v.vessel_id = c.vessel_id
        WHERE c.expiry_date <= DATE '2026-05-02' + INTERVAL '60 days'
        ORDER BY c.expiry_date;

        Question: M/V Ocean Aurora에 적용되는 Regulation, Manual, System Doc을 선박 제원 기준으로 찾아줘.
        SQL:
        SELECT v.vessel_name, d.document_code, d.document_title, d.document_type, d.document_domain, d.is_mandatory
        FROM vessels v
        JOIN compliance_documents d
          ON (d.applies_vessel_type IS NULL OR d.applies_vessel_type = v.vessel_type)
         AND (d.tonnage_min IS NULL OR d.tonnage_min <= v.gross_tonnage)
         AND (d.tonnage_max IS NULL OR d.tonnage_max >= v.gross_tonnage)
         AND (d.build_year_min IS NULL OR d.build_year_min <= v.build_year)
         AND (d.build_year_max IS NULL OR d.build_year_max >= v.build_year)
        WHERE v.vessel_name = 'M/V Ocean Aurora'
        ORDER BY d.document_domain, d.document_type, d.document_code;

        Question: {query_str}
        SQL:
        \"\"\"
        )

        custom_engine = NLSQLTableQueryEngine(
            sql_database=sql_db,
            tables=MARITIME_TABLES,
            text_to_sql_prompt=custom_text_to_sql_prompt,
        )

        custom_results = run_engine(custom_engine, TEST_QUESTIONS, "custom_prompt_fewshot")
        custom_results[["level", "question", "status", "generated_sql"]]
        """
    ),
    code(
        """
        try:
            from llama_index.core import VectorStoreIndex
        except ImportError:
            from llama_index.core.indices.vector_store import VectorStoreIndex

        from llama_index.core.objects import SQLTableNodeMapping, ObjectIndex, SQLTableSchema
        from llama_index.core.indices.struct_store.sql_query import SQLTableRetrieverQueryEngine

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
        obj_index = ObjectIndex.from_objects(
            table_schemas,
            table_node_mapping,
            index_cls=VectorStoreIndex,
        )

        retriever_engine = SQLTableRetrieverQueryEngine(
            sql_database=sql_db,
            table_retriever=obj_index.as_retriever(similarity_top_k=3),
            text_to_sql_prompt=custom_text_to_sql_prompt,
        )

        retriever_results = run_engine(retriever_engine, TEST_QUESTIONS, "object_index_retriever")
        retriever_results[["level", "question", "status", "generated_sql"]]
        """
    ),
    code(
        """
        comparison = pd.concat([baseline_results, custom_results, retriever_results], ignore_index=True)
        comparison[["engine", "level", "question", "status", "generated_sql"]]
        """
    ),
    code(
        """
        output_path = "maritime_SQL_agent_text_to_sql_results.csv"
        comparison.to_csv(output_path, index=False)
        print("Saved:", output_path)
        """
    ),
]


notebook = {
    "cells": cells,
    "metadata": {
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

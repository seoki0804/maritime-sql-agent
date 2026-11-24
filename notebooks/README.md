# notebooks

- `maritime_SQL_agent_text_to_sql_advanced.ipynb` — 기본 설정, 도메인 규칙과 예시 SQL, 테이블 설명 검색(ObjectIndex)
  세 구성을 같은 10문항으로 비교하는 노트북. `scripts/create_project_notebook.py`로 만든다.

실행 전에 Colab Secrets(또는 환경 변수)에 `NEON_DSN`, `OPENAI_API_KEY`를 등록한다.
트레이싱을 쓰려면 `LANGSMITH_API_KEY`도 등록한다.

PostgreSQL에 연결한 직후 schema를 고정한다.

```sql
SET search_path TO maritime_sql_agent, public;
```

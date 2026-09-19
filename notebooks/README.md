# Notebook Work Area

수업 notebook을 이 폴더로 복사해서 프로젝트용으로 수정한다.

권장 순서:

1. `06_text_to_sql_ipynb의_사본.ipynb`를 복사해 baseline notebook 작성
2. `08_text_to_sql_advanced_ipynb의_사본.ipynb`를 복사해 prompt, few-shot, ObjectIndex 개선 notebook 작성
3. Colab Secrets에 다음 이름으로 key 등록
   - `NEON_DSN`
   - `OPENAI_API_KEY`
   - `LANGSMITH_API_KEY`
   - `COHERE_API_KEY`
4. PostgreSQL 연결 직후 다음 SQL을 실행해 schema를 고정

```sql
SET search_path TO maritime_sql_agent, public;
```


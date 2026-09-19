# Environment Variables

Do not commit API keys or database URLs.

Use Colab Secrets or a local `.env` file ignored by git.

Required names:

- `NEON_DSN`
- `OPENAI_API_KEY`
- `LANGSMITH_API_KEY`
- `COHERE_API_KEY`

Local execution example:

```bash
export NEON_DSN="..."
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/deploy_sql.py --verify-only
```


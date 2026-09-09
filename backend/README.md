# Backend

API simples da padaria usando FastAPI e SQLAlchemy.

## Executar

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

A documentação fica em http://127.0.0.1:8000/docs.

O banco padrão é SQLite em `backend/pao.db`. Para PostgreSQL, defina `DATABASE_URL` no `.env`.

Usuários de demonstração criados na primeira execução:

- `admin@pao.com` / `admin123`
- `cliente@pao.com` / `123456`

Troque as senhas antes de publicar a aplicação.

# Backend

Backend da padaria usando FastAPI, Flask, SQLAlchemy e PostgreSQL/Supabase via psycopg. O FastAPI fornece a API e o Flask serve o frontend no mesmo processo.

## Executar

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

O comando inicia a API e o frontend juntos. Acesse o frontend em http://127.0.0.1:8000/undex.html e a documentação em http://127.0.0.1:8000/docs.

O frontend é servido pelo Flask; não é necessário iniciar um `python -m http.server` separado.

Com `DATABASE_URL` vazio em desenvolvimento, o banco isolado é `backend/pao.db`. Em produção, `DATABASE_URL` é obrigatória. Copie a string oficial em Supabase > Connect; use a string do Session Pooler se a infraestrutura futura não alcançar o endpoint direto.

As tabelas também podem ser preparadas executando `migration_initial.sql` no SQL Editor. Crie o primeiro administrador com `python create_admin.py`. O seed demo exige explicitamente `ENVIRONMENT=development` e `SEED_DEMO_DATA=true`.

Consulte `/health`, `/health/db` e `/docs` após iniciar. Nunca coloque `DATABASE_URL`, `JWT_SECRET` ou chaves Supabase no HTML, no JavaScript ou no Git.

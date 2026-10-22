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

Em desenvolvimento, o seed habilitado cria as contas `cliente@pao.com` (`123456`) e `admin@pao.com` (`admin123`). Elas são apenas para teste local; o seed é bloqueado fora de `ENVIRONMENT=development`. Altere as variáveis `DEMO_*` no `.env` para usar outras credenciais. A sessão do navegador usa cookie `HttpOnly` com validade padrão de 30 dias; `JWT_EXPIRE_MINUTES` controla essa duração.

As tabelas também podem ser preparadas executando `migration_initial.sql` no SQL Editor. Crie o primeiro administrador com `python create_admin.py`. O seed demo exige explicitamente `ENVIRONMENT=development` e `SEED_DEMO_DATA=true`.

Em um banco vazio, a inicialização cadastra o catálogo padrão uma única vez; produtos já existentes não são substituídos. Para criar as contas iniciais em produção, configure `INITIAL_ADMIN_NAME`, `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD`, `INITIAL_CUSTOMER_NAME`, `INITIAL_CUSTOMER_EMAIL` e `INITIAL_CUSTOMER_PASSWORD` no Render. Use senhas próprias com pelo menos 6 caracteres. Após confirmar que as contas foram criadas, remova as duas variáveis de senha do Render; os usuários permanecem salvos no Supabase.

Consulte `/health`, `/health/db` e `/docs` após iniciar. Nunca coloque `DATABASE_URL`, `JWT_SECRET` ou chaves Supabase no HTML, no JavaScript ou no Git.

# Pão para Toda Obra

Site de delivery de uma padaria artesanal, com frontend em HTML/CSS/JavaScript e uma API em Python.

## Backend e Supabase

O backend usa FastAPI, Flask, SQLAlchemy e PostgreSQL via `psycopg`. O FastAPI fornece a API e o Flask serve o frontend no mesmo processo. O catálogo, autenticação e pedidos são persistidos no banco; o navegador mantém apenas sessão, carrinho e preferências auxiliares.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Esse único comando inicia a API e o frontend juntos. Abra http://127.0.0.1:8000/undex.html e a documentação em http://127.0.0.1:8000/docs.

O frontend usa automaticamente a mesma origem da API quando é servido pelo backend. O servidor separado `python -m http.server 5500` não é mais necessário.

Para desenvolvimento isolado, `DATABASE_URL` vazio usa SQLite local. Em produção, `DATABASE_URL` é obrigatória e não há fallback silencioso. Para o Supabase, abra **Connect** no painel, copie a connection string oficial PostgreSQL (direta ou Session Pooler), e coloque-a em `backend/.env` como `DATABASE_URL`, sem publicar esse arquivo. Se o Render não alcançar o endpoint direto por IPv6, use a string oficial do Session Pooler fornecida pelo próprio Supabase, sem montar o host manualmente.

As tabelas podem ser criadas pelo startup local ou aplicando `backend/migration_initial.sql` no SQL Editor do Supabase. Depois, confirme `users`, `products`, `orders` e `order_items` no Table Editor.

Defina também `JWT_SECRET` com uma chave longa e aleatória, `ENVIRONMENT=development` ou `production`, `SEED_DEMO_DATA=false` e `CORS_ORIGINS` somente quando o frontend estiver em outra origem. O arquivo `.env` é local e está no `.gitignore`; se algum segredo já tiver sido versionado, remova-o do índice com `git rm --cached backend/.env` e faça a rotação da credencial.

Para criar o primeiro administrador sem senha padrão:

```bash
cd backend
python create_admin.py
```

O seed de demonstração só roda quando `ENVIRONMENT=development` e `SEED_DEMO_DATA=true`; o padrão é não criar contas nem produtos fictícios.

Verificações disponíveis: `GET /health`, `GET /health/db` e documentação em `/docs`. Para validar persistência, cadastre um produto ou faça um pedido, reinicie a aplicação e consulte novamente o catálogo/histórico.

No Render, configure as mesmas variáveis no painel Environment, instale `backend/requirements.txt` e inicie com `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`. Não publiquei nem testei o banco remoto nesta etapa.

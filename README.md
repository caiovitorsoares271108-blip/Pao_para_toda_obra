# Pão para Toda Obra

Site de delivery de uma padaria artesanal, com frontend em HTML/CSS/JavaScript e uma API em Python.

## Backend

O backend usa FastAPI, SQLAlchemy e SQLite por padrão. Ele já possui autenticação, produtos e pedidos.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Depois, abra a documentação em http://127.0.0.1:8000/docs.

Em outro terminal, na raiz do projeto, sirva o frontend:

```bash
python -m http.server 5500
```

Abra http://127.0.0.1:5500/undex.html. O frontend está configurado para usar a API em `http://127.0.0.1:8000`.

O banco é criado automaticamente em `backend/pao.db`. Para usar PostgreSQL ou Supabase no futuro, basta trocar `DATABASE_URL` no arquivo `.env`.

Usuários de demonstração:

- Administrador: `admin@pao.com` / `admin123`
- Cliente: `cliente@pao.com` / `123456`

As credenciais são apenas para desenvolvimento e devem ser alteradas antes da publicação.

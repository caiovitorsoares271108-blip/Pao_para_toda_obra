# Pão para Toda Obra

Site de delivery de uma padaria artesanal, com frontend em HTML/CSS/JavaScript e uma API em Python.

## Backend

O backend usa FastAPI, Flask, SQLAlchemy e SQLite por padrão. O FastAPI fornece a API e o Flask serve o frontend no mesmo processo. Ele já possui autenticação, produtos e pedidos.

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

O banco é criado automaticamente em `backend/pao.db`. Para usar PostgreSQL ou Supabase no futuro, basta trocar `DATABASE_URL` no arquivo `.env`.

Usuários de demonstração:

- Administrador: `admin@pao.com` / `admin123`
- Cliente: `cliente@pao.com` / `123456`

As credenciais são apenas para desenvolvimento e devem ser alteradas antes da publicação.

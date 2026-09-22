# Backend

Backend da padaria usando FastAPI, Flask, SQLAlchemy e SQLite. O FastAPI fornece a API e o Flask serve o frontend no mesmo processo.

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

O banco padrão é SQLite em `backend/pao.db`. Para PostgreSQL, defina `DATABASE_URL` no `.env`.

Usuários de demonstração criados na primeira execução:

- `admin@pao.com` / `admin123`
- `cliente@pao.com` / `123456`

Troque as senhas antes de publicar a aplicação.

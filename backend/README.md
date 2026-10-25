# Backend

API FastAPI organizada nos módulos `API/contas.py`, `API/cardapio.py` e `API/pedidos.py`. O Flask serve o frontend no mesmo processo. SQLAlchemy/psycopg persistem dados no PostgreSQL/Supabase ou em SQLite isolado durante desenvolvimento.

## Estrutura

- `database.py`: modelos compartilhados e sessão SQLAlchemy.
- `api_schemas.py`: contratos Pydantic de entrada e saída.
- `API/contas.py`: autenticação, sessão e administração de contas.
- `API/cardapio.py`: catálogo, disponibilidade e promoções.
- `API/pedidos.py`: criação e consulta de pedidos com cálculo no backend.
- `products_seed.json`: os 21 produtos reais recuperados do frontend anterior.

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

Contas demo são opcionais e exigem `ENVIRONMENT=development`, `SEED_DEMO_DATA=true` e credenciais privadas nas variáveis `DEMO_*`. Elas nunca usam senhas publicadas no código. Sessões usam cookie `HttpOnly`; `JWT_EXPIRE_MINUTES` controla sua duração.

As contas podem ser gerenciadas por `GET/PATCH /auth/accounts`. Usuários comuns não podem alterar papel ou acesso. O primeiro administrador pode ser provisionado por `INITIAL_ADMIN_*` no ambiente privado ou pela execução interativa de `python create_admin.py`.

Em bancos não vazios, `products_seed.json` é carregado uma vez por `seed_key`. Produtos já existentes não são substituídos. Configure o ambiente de produção sem contas demo e com `INITIAL_ADMIN_*` privado. Depois da primeira inicialização, remova o segredo da senha do provedor; a conta permanece no banco.

Os produtos novos e promoções são administrados pelas rotas `/products`, `/products/admin` e `/products/{id}`. O preço enviado pelo navegador não participa do cálculo do pedido. Promoções podem ter início/fim opcionais e somente o backend aplica o valor vigente.

Aplicar `migration_initial.sql` no Supabase é uma ação manual e aditiva. Não confirme a publicação ou migração remota sem acesso autorizado ao projeto. Consulte `/health`, `/health/db` e `/docs` após iniciar. Nunca coloque `DATABASE_URL`, `JWT_SECRET` ou chaves privilegiadas no HTML, no JavaScript ou no Git.

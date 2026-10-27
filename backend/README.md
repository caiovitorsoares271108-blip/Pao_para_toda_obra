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
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

O comando inicia a API e o frontend juntos. Acesse o frontend em http://127.0.0.1:8000/ e a documentação em http://127.0.0.1:8000/docs.

O frontend é servido pelo Flask; não é necessário iniciar um `python -m http.server` separado.

Todos os ambientes de execução exigem a connection string PostgreSQL oficial do Supabase em `DATABASE_URL` ou `SUPABASE_DB_URL`; sem ela, ou se ela apontar a SQLite/outro host, o backend não inicia. Obtenha a URL em Supabase > Connect e use o Session Pooler se necessário. SQLite só é usado pelos testes automatizados com banco temporário. O endpoint `/health/db` informa o dialect efetivamente conectado em `engine`.

Contas demo são opcionais e exigem `ENVIRONMENT=development`, `SEED_DEMO_DATA=true` e credenciais privadas nas variáveis `DEMO_*`. Elas nunca usam senhas publicadas no código. Sessões usam cookie `HttpOnly`; `JWT_EXPIRE_MINUTES` controla sua duração.

## Codespaces Secrets do Supabase

Cadastre no Codespaces a connection string PostgreSQL do Supabase como `DATABASE_URL` (ou `SUPABASE_DB_URL`). `SUPABASE_URL` identifica o projeto REST e não substitui a conexão SQL.

As duas API keys não são enviadas ao navegador. Somente o backend pode usar `SUPABASE_SECRET_KEY`; o frontend recebe apenas o resultado das rotas autenticadas.

O backend usa o schema PostgreSQL/Supabase já preparado e carrega [products_seed.json](products_seed.json) uma vez por `seed_key`. Alterações feitas no painel não são sobrescritas. O esquema não é migrado automaticamente no startup.

As contas podem ser gerenciadas por `GET/PATCH /auth/accounts`. Usuários comuns não podem alterar papel ou acesso. Cada pessoa autenticada pode atualizar seu próprio endereço com `PATCH /auth/me/address`; a rota exige sessão. O primeiro administrador pode ser provisionado por `INITIAL_ADMIN_*` no ambiente privado ou pela execução interativa de `python create_admin.py`.

O botão **Acessar conta de administrador** aparece na tela de login quando `QUICK_ADMIN_EMAIL` corresponde a uma conta administrativa ativa. Ele preenche o e-mail e solicita a senha normal; não permite entrar sem senha. O login usa o cookie de sessão `HttpOnly`.

Em bancos não vazios, `products_seed.json` é carregado uma vez por `seed_key`. Produtos já existentes não são substituídos. Configure o ambiente de produção sem contas demo e com `INITIAL_ADMIN_*` privado. Depois da primeira inicialização, remova o segredo da senha do provedor; a conta permanece no banco.

Os produtos novos e promoções são administrados pelas rotas `/products`, `/products/admin` e `/products/{id}`. O preço enviado pelo navegador não participa do cálculo do pedido. Promoções podem ter início/fim opcionais e somente o backend aplica o valor vigente.

Para um banco Supabase existente que já recebeu `migration_supabase_v3.sql`, aplique `migration_profile_address.sql` no SQL Editor antes de iniciar a API; ela adiciona a coluna do endereço salvo no perfil. Em um banco novo, a coluna também é incluída em `migration_supabase_v3.sql`. A migração remota é uma ação manual: não a execute sem acesso autorizado ao projeto. Consulte `/health`, `/health/db` e `/docs` após iniciar. Nunca coloque `DATABASE_URL`, `JWT_SECRET` ou chaves privilegiadas no HTML, no JavaScript ou no Git.

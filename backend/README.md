# Backend

API FastAPI com rotas Supabase REST em `API/supabase_routes.py`; `API/contas.py`, `API/cardapio.py`, `API/pedidos.py` e `database.py` são mantidos para os testes temporários de compatibilidade. O Flask serve o frontend no mesmo processo. Dados de execução vão exclusivamente para o Supabase.

## Estrutura

- `supabase_rest.py`: cliente REST privado para o Supabase usado pela aplicação em execução.
- `database.py`: modelos SQLAlchemy usados somente pelo conjunto de testes legado.
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

Todos os ambientes de execução usam a API REST do Supabase. Configure `SUPABASE_URL` e uma credencial privada (`SUPABASE_SECRET_KEY` para `sb_secret_...`, ou `SUPABASE_SERVICE_ROLE_KEY` para o JWT legado). `SUPABASE_KEY` é somente fallback e também precisa conter uma dessas chaves privadas. Não é necessário `DATABASE_URL`. SQLite é usado somente pelos testes automatizados com banco temporário. O endpoint `/health/db` valida uma consulta REST autenticada.

Contas demo são opcionais e exigem `ENVIRONMENT=development`, `SEED_DEMO_DATA=true` e credenciais privadas nas variáveis `DEMO_*`. Elas nunca usam senhas publicadas no código. Sessões usam cookie `HttpOnly`; `JWT_EXPIRE_MINUTES` controla sua duração.

## Configuração do Render

Configure `SUPABASE_URL` e uma das chaves privadas `SUPABASE_SECRET_KEY` (`sb_secret_...`) ou `SUPABASE_SERVICE_ROLE_KEY` (JWT legado `service_role`) no Render. `SUPABASE_KEY` só é fallback se contiver uma chave privada válida; chave publishable/anon não é aceita. Em caso de conflito, as duas variáveis privadas têm prioridade na ordem indicada acima. A credencial fica somente no backend.

Nenhuma API key é enviada ao navegador. O backend usa a credencial privada selecionada para acessar o banco; a chave publishable/anon não tem permissão para acessar as tabelas sem policies.

O backend usa o schema PostgreSQL/Supabase já preparado e carrega [products_seed.json](products_seed.json) uma vez por `seed_key`. Alterações feitas no painel não são sobrescritas. O esquema não é migrado automaticamente no startup.

As contas podem ser gerenciadas por `GET/PATCH /auth/accounts`. Usuários comuns não podem alterar papel ou acesso. Cada pessoa autenticada pode atualizar seu próprio endereço com `PATCH /auth/me/address`; a rota exige sessão. O primeiro administrador pode ser provisionado por `INITIAL_ADMIN_*` no ambiente privado ou pela execução interativa de `python create_admin.py`.

O botão **Acessar conta de administrador** aparece na tela de login quando `QUICK_ADMIN_EMAIL` corresponde a uma conta administrativa ativa. Ele preenche o e-mail e solicita a senha normal; não permite entrar sem senha. O login usa o cookie de sessão `HttpOnly`.

Em bancos não vazios, `products_seed.json` é carregado uma vez por `seed_key`. Produtos já existentes não são substituídos. Configure o ambiente de produção sem contas demo e com `INITIAL_ADMIN_*` privado. Depois da primeira inicialização, remova o segredo da senha do provedor; a conta permanece no banco.

Os produtos novos e promoções são administrados pelas rotas `/products`, `/products/admin` e `/products/{id}`. O preço enviado pelo navegador não participa do cálculo do pedido. Promoções podem ter início/fim opcionais e somente o backend aplica o valor vigente.

Para um banco Supabase existente, aplique `migration_supabase_rest_orders.sql` para criar ou atualizar a função atômica de checkout; reaplique-a mesmo se uma versão anterior já foi executada. `migration_supabase_v3.sql` cria as tabelas e o histórico de status, mas não cria essa RPC. A migração libera a execução somente para `service_role` e solicita a atualização do cache PostgREST. Aplique também `migration_profile_address.sql` se `users.address` ainda não existir. Em um banco novo, aplique primeiro `migration_supabase_v3.sql` e depois as migrações necessárias. O backend não executa DDL automaticamente. Consulte `/health`, `/health/db` e `/docs` após iniciar. Nunca coloque `JWT_SECRET` ou chaves privilegiadas no HTML, no JavaScript ou no Git.

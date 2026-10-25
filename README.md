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

O frontend usa automaticamente a mesma origem da API. A API está separada em módulos de contas, cardápio e pedidos, mas mantém os caminhos públicos já usados pelo frontend. O servidor separado `python -m http.server 5500` não é necessário.

O painel administrativo e a área de pedidos consultam os pedidos persistidos a cada 5 segundos; o cardápio aberto também consulta os produtos no backend nesse intervalo, refletindo alterações feitas em outras sessões. Cada atualização é lida da API e do banco compartilhado, não simulada no navegador. Os pedidos mantêm nome e preço dos itens no momento da compra e expõem a data da última atualização de status.

Para desenvolvimento isolado, `DATABASE_URL` vazio usa SQLite local. Em produção, `DATABASE_URL` é obrigatória e não há fallback silencioso. Para o Supabase, abra **Connect** no painel, copie a connection string oficial PostgreSQL (direta ou Session Pooler), e coloque-a em `backend/.env` como `DATABASE_URL`, sem publicar esse arquivo. Se o Render não alcançar o endpoint direto por IPv6, use a string oficial do Session Pooler fornecida pelo próprio Supabase, sem montar o host manualmente.

No SQLite local, o startup cria e atualiza o esquema. No Supabase, aplique `backend/migration_supabase_v3.sql` pelo SQL Editor antes de iniciar a versão atual da API; ela prepara as tabelas e o campo `orders.updated_at` usado para exibir a última atualização do pedido. Depois, confirme `users`, `products`, `orders` e `order_items` no Table Editor.

Defina `JWT_SECRET` com uma chave longa e aleatória, `ENVIRONMENT=development` ou `production`, e `CORS_ORIGINS` somente quando o frontend estiver em outra origem. Contas demo são opcionais e exigem credenciais privadas nas variáveis `DEMO_*`; não há senha publicada no código. A autenticação fica em cookie `HttpOnly` por 30 dias por padrão. O navegador não guarda conta nem catálogo como banco de dados. O arquivo `.env` é local e está no `.gitignore`; se algum segredo já tiver sido versionado, remova-o do índice e faça a rotação da credencial.

Para criar o primeiro administrador sem senha padrão:

```bash
cd backend
python create_admin.py
```

A aplicação carrega os 21 produtos reais recuperados em `backend/products_seed.json` por uma chave `seed_key` estável. A carga é idempotente e não sobrescreve alterações feitas pelo administrador.

Contas são persistidas no banco. O admin pode criar contas, alterar dados permitidos, promover ou remover o papel administrativo e ativar/desativar acessos pela aba Contas. Um usuário comum não pode alterar seu próprio papel.

Contas demo são opcionais e exigem `ENVIRONMENT=development` com `SEED_DEMO_DATA=true` e credenciais privadas. Promoções são persistidas no banco e podem informar início/fim opcionais; o backend aplica o desconto somente no período vigente.

Verificações disponíveis: `GET /health`, `GET /health/db` e documentação em `/docs`. Para validar persistência, cadastre um produto ou faça um pedido, reinicie a aplicação e consulte novamente o catálogo/histórico.

No Render, configure as variáveis privadas no painel Environment, instale `backend/requirements.txt` e inicie com `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`. Remova as variáveis `INITIAL_*_PASSWORD` depois da primeira provisionação. A publicação e o banco remoto não foram alterados nesta etapa.

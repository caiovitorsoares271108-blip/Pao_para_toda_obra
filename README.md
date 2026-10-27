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
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Esse único comando inicia a API e o frontend juntos. Abra http://127.0.0.1:8000/ e a documentação em http://127.0.0.1:8000/docs.

O frontend usa automaticamente a mesma origem da API. A API está separada em módulos de contas, cardápio e pedidos, mas mantém os caminhos públicos já usados pelo frontend. O servidor separado `python -m http.server 5500` não é necessário.

Pedidos e cardápio são sincronizados a cada 2 segundos enquanto a página está visível. O admin também atualiza pedidos, produtos e contas nesse intervalo; assim, clientes veem mudanças de status e disponibilidade e o admin vê novos pedidos e alterações de endereço. A sincronização consulta a API e o banco compartilhado.

O projeto usa exclusivamente PostgreSQL no Supabase em todos os ambientes de execução. Configure `DATABASE_URL` (ou `SUPABASE_DB_URL`) antes de iniciar: no painel Supabase, abra **Connect**, copie a connection string PostgreSQL oficial (direta ou Session Pooler) e guarde-a em `backend/.env` ou no secret manager da hospedagem. A aplicação rejeita a inicialização se a URL estiver ausente, apontar para SQLite ou não usar um host oficial Supabase. Não publique a connection string. SQLite é permitido somente nos testes automatizados, com banco temporário.

No Supabase, aplique `backend/migration_supabase_v3.sql` pelo SQL Editor antes de iniciar a versão atual da API. Se o v3 já foi aplicado antes, execute também `backend/migration_profile_address.sql` para adicionar o endereço persistente da conta. Confirme `users`, `products`, `orders` e `order_items` no Table Editor.

Defina `JWT_SECRET` com uma chave longa e aleatória, `ENVIRONMENT=development` ou `production`, e `CORS_ORIGINS` somente quando o frontend estiver em outra origem. Contas demo são opcionais e exigem credenciais privadas nas variáveis `DEMO_*`; não há senha publicada no código. A autenticação fica em cookie `HttpOnly` por 30 dias por padrão. O navegador não guarda conta nem catálogo como banco de dados. O arquivo `.env` é local e está no `.gitignore`; se algum segredo já tiver sido versionado, remova-o do índice e faça a rotação da credencial.

Para criar o primeiro administrador sem senha padrão:

```bash
cd backend
python create_admin.py
```

A aplicação carrega os 21 produtos reais recuperados em `backend/products_seed.json` por uma chave `seed_key` estável. A carga é idempotente e não sobrescreve alterações feitas pelo administrador.

Contas são persistidas no banco. Cadastro e login usam e-mail e senha; a sessão é mantida por cookie protegido para evitar novo login a cada visita. O cliente pode salvar seu endereço na conta enquanto estiver autenticado; endereço de conta não pode ser alterado anonimamente. O admin pode criar contas, alterar dados permitidos, promover ou remover o papel administrativo e ativar/desativar acessos pela aba Contas. Um usuário comum não pode alterar seu próprio papel.

O botão **Acessar conta de administrador** no login preenche o e-mail configurado e pede a senha normalmente. Configure `QUICK_ADMIN_EMAIL` em `backend/.env` para uma conta admin ativa; o botão não concede acesso sem senha.

Contas demo são opcionais e exigem `ENVIRONMENT=development` com `SEED_DEMO_DATA=true` e credenciais privadas. Promoções são persistidas no banco e podem informar início/fim opcionais; o backend aplica o desconto somente no período vigente.

Verificações disponíveis: `GET /health`, `GET /health/db` e documentação em `/docs`. Para validar persistência, cadastre um produto ou faça um pedido, reinicie a aplicação e consulte novamente o catálogo/histórico.

No Render, configure as variáveis privadas no painel Environment, instale `backend/requirements.txt` e inicie com `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`. Remova as variáveis `INITIAL_*_PASSWORD` depois da primeira provisionação. A publicação e o banco remoto não foram alterados nesta etapa.

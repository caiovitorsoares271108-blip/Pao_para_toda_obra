# Relatório do Projeto: Pão para Toda Obra

## 1. Visão geral

Este projeto é uma aplicação de padaria online chamada **Pão para Toda Obra**. Ele combina:

- backend em Python com FastAPI
- banco de dados SQLite
- frontend em HTML, CSS e JavaScript
- autenticação com JWT
- gestão de produtos, pedidos e usuários
- painel administrativo para o dono da loja

O objetivo é permitir que o cliente navegue pelo cardápio, adicione itens ao carrinho, confirme um pedido e acompanhe o status, enquanto o administrador pode gerenciar o catálogo e os pedidos.

---

## 2. Estrutura do projeto

```text
Pao_para_toda_obra/
├── README.md
├── relatorio.md
├── backend/
│   ├── .env.example
│   ├── README.md
│   ├── __init__.py
│   ├── app.py
│   ├── main.py
│   ├── requirements.txt
│   └── pao.db
└── frontend/
    └── undex.html
```

### Principais arquivos

- `backend/main.py`: código principal da API
- `backend/app.py`: entrypoint compatível da aplicação
- `backend/requirements.txt`: dependências do backend
- `backend/.env.example`: variáveis de ambiente de exemplo
- `frontend/undex.html`: frontend completo da aplicação
- `README.md`: instruções gerais do projeto

---

## 3. Backend

O backend foi desenvolvido em Python usando **FastAPI** e **SQLAlchemy**.

### Tecnologias principais

- FastAPI: criação da API REST
- SQLAlchemy: ORM para acessar o banco
- SQLite: banco padrão do projeto
- Pydantic: validação de dados de entrada
- JWT: autenticação de usuários
- pwdlib: hash de senhas
- dotenv: carregamento de variáveis de ambiente

### Banco de dados

O banco padrão é o SQLite, armazenado em:

```text
backend/pao.db
```

As entidades principais são:

- `User`: usuários do sistema
- `Product`: produtos do cardápio
- `Order`: pedido realizado pelo cliente
- `OrderItem`: itens dentro de um pedido

### Estrutura de autenticação

O sistema usa JWT para autenticar usuários.

As rotas protegidas verificam:

- se o token foi enviado
- se o token é válido
- se o usuário existe
- se o usuário tem a permissão necessária

A função `current_user()` valida o token e retorna o usuário logado. A função `admin_user()` garante que somente administradores tenham acesso a rotas especiais.

---

## 4. Endpoints da API

A API expõe os endpoints abaixo:

### Saúde da aplicação

- `GET /health`
  - verifica se a API está ativa

### Autenticação

- `POST /auth/register`
  - cadastra um novo usuário

- `POST /auth/login`
  - faz login e retorna token e dados do usuário

### Produtos

- `GET /products`
  - lista os produtos ativos

- `POST /products`
  - cria um produto (somente admin)

- `PATCH /products/{product_id}`
  - edita um produto (somente admin)

- `DELETE /products/{product_id}`
  - desativa um produto (somente admin)

### Pedidos

- `POST /orders`
  - cria um pedido para o cliente logado

- `GET /orders`
  - lista pedidos do cliente ou de todos, dependendo do perfil

- `PATCH /orders/{order_id}/status`
  - atualiza o status do pedido (somente admin)

---

## 5. Lógica do backend

### Inicialização

Na inicialização, o backend:

1. carrega as variáveis de ambiente
2. cria a engine do banco
3. cria as tabelas, se necessário
4. insere dados iniciais no banco
5. inicia o app FastAPI

### Semeando dados iniciais

A função `seed_database()` garante que existam:

- usuários padrão
- alguns produtos iniciais

Usuários de demonstração:

- `admin@pao.com` / `admin123`
- `cliente@pao.com` / `123456`

Produtos iniciais incluem itens como:

- Pão Francês
- Pão de Queijo
- Café Espresso

### Validação de dados

Os modelos Pydantic validam campos como:

- nome do usuário
- e-mail
- senha
- preço
- quantidade
- endereço
- itens do pedido

Isso evita entradas inválidas e reduz erros no fluxo da aplicação.

---

## 6. Frontend

O frontend está em um único arquivo:

```text
frontend/undex.html
```

Ele contém:

- HTML da estrutura da página
- CSS para estilos e layout
- JavaScript para lógica da aplicação

### Objetivo do frontend

O frontend é uma SPA (Single Page Application), que oferece:

- catálogo de produtos
- filtros por categoria e pesquisa
- carrinho de compras
- checkout com endereço
- painel administrativo
- listagem de pedidos
- autenticação local para demo

---

## 7. Como a lógica do frontend funciona

### Armazenamento local

O script usa `localStorage` para salvar dados no navegador, por meio do objeto `DB`.

Ele guarda:

- usuários
- produtos
- pedidos
- carrinho
- endereço do cliente
- sessão atual

Isso permite que a aplicação funcione mesmo sem um backend em produção, o que é útil para protótipos e demonstrações.

### Estado da aplicação

O objeto `State` guarda o estado atual da sessão, como:

- usuário logado
- token
- endereço
- carrinho
- página atual
- status da API

### Fluxo de navegação

As funções `Pages.home()`, `Pages.orders()` e `Pages.admin()` renderizam diferentes telas dinamicamente, sem recarregar a página inteira.

### Carrinho

O carrinho é um array de itens com:

- produto
- quantidade

Quando o usuário confirma o pedido:

1. pega os itens do carrinho
2. calcula o valor total
3. cria um objeto pedido
4. salva o pedido em `localStorage`
5. limpa o carrinho
6. envia o usuário para a página de pedidos

### Login e cadastro

A autenticação no frontend compara e-mail e senha com usuários locais. Se o usuário é encontrado:

- cria a sessão do usuário
- salva no estado
- atualiza a interface

O admin entra em uma área especial para gerir o sistema.

---

## 8. Fluxo de uso do cliente

1. O cliente entra na página inicial
2. escolhe produtos no cardápio
3. adiciona itens ao carrinho
4. abre o checkout
5. informa o endereço de entrega
6. confirma o pedido
7. o pedido é salvo e exibido em “Meus pedidos”

---

## 9. Fluxo de uso do administrador

1. faz login com conta administrativa
2. acessa o painel administrativo
3. visualiza resumo dos pedidos
4. adiciona, edita ou remove produtos
5. altera o status do pedido
6. acompanha entrega e pedidos em andamento

---

## 10. Como o projeto é executado

### Backend

No terminal:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Depois, o frontend fica disponível em:

- `http://127.0.0.1:8000/undex.html`
- documentação da API em `http://127.0.0.1:8000/docs`

### Observação importante

O arquivo `backend/app.py` foi ajustado para funcionar como entrypoint compatível com a aplicação principal em `backend/main.py`.

---

## 11. Conclusão

O projeto é uma aplicação funcional de padaria, com foco em demonstração e prototipagem local. Ele combina backend real com interface dinâmica em navegador, criando uma solução simples e didática para gestão de produtos e pedidos.

O código está bem organizado para um projeto de estudos e demonstração, e a lógica principal é fácil de seguir:

- backend cuida da API e da autenticação
- frontend cuida da experiência do usuário
- localStorage simula persistência no cliente
- o administrador controla a operação da loja

Esse conjunto torna o projeto uma base excelente para evoluir para um sistema mais completo, com backend real em produção e frontend mais robusto.

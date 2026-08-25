# Deploy: Sofia em produção

## Variáveis obrigatórias no ambiente

- `APP_URL=https://sofia.2ads.com.br`
- `CORS_ORIGINS=https://sofia.2ads.com.br`
- `GROQ_API_KEY`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `REDIS_URL`
- Opcional: `OPENROUTER_API_KEY`, `CLICKUP_API_KEY`, `CLICKUP_TEAM_ID`, Google OAuth

## 1) Construir e publicar o backend

Atualmente em FastAPI + uvicorn. Para empacotar:

```bash
docker build -t sofia-api:latest apps/api
docker tag sofia-api:latest registry.exemplo.com/sofia-api:latest
docker push registry.exemplo.com/sofia-api:latest
```

Na VPS ou serviço de contêiner, rodar com as variáveis de ambiente injetadas e a porta `8000` exposta.

## 2) Construir e publicar o frontend

```bash
npm install
npm run install:web
npm run build
```

O build gera artefatos em `apps/web/dist`. Sirva como static site (Nginx, CDN ou Traefik) apontando para `sofia.2ads.com.br`.

## 3) Banco e filas

Provisione:
- Postgres com `pgvector`
- Redis para filas/cache

Aplique as migrations e rode o worker separado antes de ativar o tráfego.

## 4) HTTPS e rota

Configure Traefik para:
- rota principal para o static do frontend em `sofia.2ads.com.br`
- proxy reverso de `/api` para o backend em `api.sofia.2ads.com.br`
- rota de webhook `hooks.sofia.2ads.com.br` para a API

Habilite HTTPS nas três rotas com certificado válido.

## 5) Pós-deploy

- Confirme `/health` e `/api/v1/config` em `api.sofia.2ads.com.br`
- Confirme o painel em `sofia.2ads.com.br`
- Valide CORS e origem do app
- Ative webhooks e integrações gradualmente
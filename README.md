# Sofia

Secretária pessoal com IA para WhatsApp e chat web.

## Rodar localmente

Requisitos: Docker e Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

- Chat web: http://localhost:5173
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health

O webhook inicial da Evolution API está em `POST /webhooks/evolution`. Nesta primeira fundação ele apenas aceita o payload; validação, persistência e processamento entram na próxima etapa.

## Domínios de produção

- `sofia.2ads.com.br` — frontend
- `api.sofia.2ads.com.br` — API
- `hooks.sofia.2ads.com.br` — webhooks

As URLs são configuradas por ambiente e não ficam fixas no frontend.

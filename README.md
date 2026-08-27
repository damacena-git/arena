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

## Configurar IA

Copie `.env.example` para `.env` e preencha pelo menos uma chave:

```env
GROQ_API_KEY=sua-chave
OPENROUTER_API_KEY=sua-chave-opcional
```

A Sofia usa Groq por padrão e faz fallback para OpenRouter quando configurado. Para trocar o provedor ou o modelo, altere `AI_PROVIDER`, `AI_FALLBACK_PROVIDER`, `GROQ_MODEL` e `OPENROUTER_MODEL`. Nunca versione o arquivo `.env`.

A resposta da API informa `provider` e `model`, e o chat exibe essa informação abaixo da resposta. O botão de microfone permite enviar um arquivo de áudio de até 25 MB. A transcrição é feita pelo modelo `GROQ_TRANSCRIPTION_MODEL` e enviada à Sofia para gerar a resposta.

## Conectar o Google Calendar

1. No Google Cloud Console, crie um projeto e ative a **Google Calendar API**.
2. Crie credenciais OAuth 2.0 do tipo **Aplicativo da Web**.
3. Adicione este URI de redirecionamento autorizado no ambiente local:
   `http://localhost:8000/api/v1/integrations/google/callback`
4. Preencha o `.env`:

```env
GOOGLE_CLIENT_ID=seu-client-id
GOOGLE_CLIENT_SECRET=seu-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/integrations/google/callback
```

5. Reinicie a API e abra **Configuração → Conectar agenda**.

A conexão local fica temporariamente em memória nesta etapa. Ela será persistida e criptografada no PostgreSQL antes do uso em produção. O endpoint inicial de consulta é `GET /api/v1/integrations/google/events`.

## Domínios de produção

- `sofia.2ads.com.br` — frontend
- `api.sofia.2ads.com.br` — API
- `hooks.sofia.2ads.com.br` — webhooks

As URLs são configuradas por ambiente e não ficam fixas no frontend.

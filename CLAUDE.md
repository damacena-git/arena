# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Sofia — secretária pessoal com IA para WhatsApp e chat web. Usuário alvo: Diego Damacena, com Google Calendar e ClickUp como integrações principais. Idioma de interface: pt-BR.

**Nota global:** As instruções gerais de idioma, coding standards e processo estão em `~/.claude/CLAUDE.md`.

## How to Run

```bash
# Backend (FastAPI)
.\.venv\Scripts\Activate.ps1       # Windows
cd apps/api && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (Vite + React)
npm run dev                         # raiz do projeto
# ou: cd apps/web && npx vite --host 0.0.0.0
```

- Frontend fica em http://localhost:5173
- API em http://localhost:8000
- Swagger em http://localhost:8000/docs

### Docker (completo)

```bash
cp .env.example .env
docker compose up --build
```

Requer infra adicional (Postgres, Redis) definida em `infra/docker-compose.yml`.

## Configuration

Todas as variáveis estão em `.env` (não versionado). Referência: `.env.example`.
`config.py` carrega settings via `pydantic-settings` com `get_settings()` (cache `lru_cache`). O arquivo `.env` é buscado tanto na raiz do projeto quanto no diretório de trabalho.

**Variáveis importantes:**
- `TTS_DEFAULT_VOICE` — voz padrão para síntese (pt-BR-FranciscaNeural ou pt-BR-AntonioNeural)
- `AI_PROVIDER` / `AI_FALLBACK_PROVIDER` — Groq com fallback OpenRouter
- `GROQ_TRANSCRIPTION_MODEL` — Whisper para transcrição de áudio

## Architecture

### Backend (`apps/api/`)

FastAPI minimalista — **quase todo o código está em um único arquivo** (`app/main.py`). Fluxo de uma requisição de chat:

1. `POST /api/v1/chat/messages` recebe o texto
2. Tenta resolvers "built-in" em ordem: agenda Google → leitura ClickUp → criação ClickUp
3. Se nenhum resolver disparar, chama `AIClient.complete()` que faz fallback automático Groq → OpenRouter
4. Resposta retorna `provider` e `model` para exibição no frontend

Módulos:
- `main.py` — rotas, middleware CORS e toda lógica de detecção de intenção (Google Calendar, ClickUp)
- `ai.py` — `AIClient`: transcrição Groq Whisper + completion com fallback entre provedores
- `clickup.py` — `ClickUpClient`: wrapper HTTP síncrono para a API v2 do ClickUp
- `config.py` — `Settings` (Pydantic BaseSettings), carregamento de `.env`
- `tts.py` — `TTSClient`: síntese de voz usando Edge TTS (Microsoft, gratuito, sem API key)

### Frontend (`apps/web/`)

React + Vite em um único componente (`main.tsx`, ~210 linhas). CSS embutido inline. Três views: chat, ClickUp, configuração. Usa `fetch` direto para a API (sem camada de abstração).

### Estado volátil

- `conversation_histories` (dict in-memory), `google_oauth_states`, `google_tokens` e `pending_clickup_actions` vivem em memória — **não sobrevivem a restart**. A migração para Postgres é planejada (ainda não implementada).

## Key Patterns

- **IA nunca executa ações externas diretamente**: a intenção é resolvida no backend antes de chamar qualquer API externa
- **Fallback entre provedores**: `AIClient._provider_order()` monta a lista; `complete()` itera até o primeiro que responder
- **Detecção de intenção ClickUp via regex**: `normalize_text()` remove acentos e lowercase; o matching é feito com `re.search` em texto normalizado
- **Confirmação antes de ações destrutivas/criadoras**: tarefas ClickUp passam por pending → awaiting_confirmation antes de serem criadas

## Dependencies

Backend (`apps/api/requirements.txt`):
- `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `sqlalchemy[asyncio]`, `asyncpg`, `redis`, `httpx`, `python-multipart`, `itsdangerous`

Frontend (`apps/web/package.json`): React latest, Vite latest, TypeScript latest.

## Conventions

- Todo o código da API está em `apps/api/app/` — não há estrutura de pacotes multiplos ainda
- Nomes de arquivos em snake_case; classes em PascalCase
- Frontend sem TypeScript strict; codificado diretamente em JSX inline dentro de um único arquivo
- Erros do ClickUp são capturados por um `exception_handler` dedicado retornando 502
- Truncamento de respostas externas: `response.text[:200]` no ClickUp, `MAX_HISTORY_MESSAGES = 12` no chat
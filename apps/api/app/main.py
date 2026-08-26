from datetime import datetime, timezone
from secrets import token_urlsafe
from uuid import uuid4
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .ai import AIClient, AIProviderError
from .clickup import ClickUpClient, ClickUpError, get_clickup_client, require_clickup
from .config import get_settings

settings = get_settings()
ai_client = AIClient(settings)
# Memória curta temporária; será substituída pela persistência no PostgreSQL.
conversation_histories: dict[str, list[dict[str, str]]] = {}
MAX_HISTORY_MESSAGES = 12
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_URL = "https://www.googleapis.com/calendar/v3"
google_oauth_states: set[str] = set()
google_tokens: dict[str, dict] = {}


app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ClickUpError)
async def clickup_exception_handler(request: Request, exc: ClickUpError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


class ChatMessage(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    text: str
    created_at: datetime
    provider: str | None = None
    model: str | None = None
    transcription: str | None = None


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "sofia-api", "environment": settings.environment}


@app.get("/api/v1/config", tags=["system"])
async def public_config() -> dict[str, str | bool]:
    return {
        "app_name": settings.app_name,
        "user_name": settings.user_name,
        "environment": settings.environment,
        "ai_provider": settings.ai_provider,
        "groq_configured": bool(settings.groq_api_key),
        "openrouter_configured": bool(settings.openrouter_api_key),
        "groq_model": settings.groq_model,
        "openrouter_model": settings.openrouter_model,
        "groq_transcription_model": settings.groq_transcription_model,
    }


@app.post("/api/v1/chat/messages", response_model=ChatResponse, tags=["chat"])
async def send_chat_message(payload: ChatMessage) -> ChatResponse:
    conversation_id = payload.conversation_id or str(uuid4())
    provider = model = None
    try:
        history = conversation_histories.setdefault(conversation_id, [])
        ai_reply = await ai_client.complete(payload.text, history)
        reply, provider, model = ai_reply.text, ai_reply.provider, ai_reply.model
        history.extend([
            {"role": "user", "content": payload.text},
            {"role": "assistant", "content": reply},
        ])
        del history[:-MAX_HISTORY_MESSAGES]
    except AIProviderError as exc:
        reply = f"Ainda não consegui consultar minha inteligência artificial: {exc}"
    return ChatResponse(
        conversation_id=conversation_id,
        message_id=str(uuid4()),
        text=reply,
        created_at=datetime.now(timezone.utc),
        provider=provider,
        model=model,
    )


@app.post("/api/v1/chat/audio", response_model=ChatResponse, tags=["chat"])
async def send_audio_message(
    file: UploadFile = File(...), conversation_id: str | None = Form(None)
) -> ChatResponse:
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        return ChatResponse(
            conversation_id=conversation_id or str(uuid4()), message_id=str(uuid4()),
            text="O áudio é muito grande. Envie um arquivo de até 25 MB.",
            created_at=datetime.now(timezone.utc),
        )
    current_conversation_id = conversation_id or str(uuid4())
    try:
        transcript = await ai_client.transcribe(file.filename or "audio", content, file.content_type or "")
        history = conversation_histories.setdefault(current_conversation_id, [])
        ai_reply = await ai_client.complete(transcript, history)
        reply, provider, model = ai_reply.text, ai_reply.provider, ai_reply.model
        history.extend([
            {"role": "user", "content": transcript},
            {"role": "assistant", "content": reply},
        ])
        del history[:-MAX_HISTORY_MESSAGES]
    except AIProviderError as exc:
        transcript = None
        reply, provider, model = f"Não consegui processar o áudio: {exc}", None, None
    return ChatResponse(
        conversation_id=current_conversation_id,
        message_id=str(uuid4()),
        text=reply,
        created_at=datetime.now(timezone.utc),
        provider=provider,
        model=model,
        transcription=transcript,
    )


@app.get("/api/v1/integrations/google/start", tags=["integrations"])
async def google_start() -> RedirectResponse:
    if not settings.google_client_id or not settings.google_client_secret:
        return RedirectResponse(url="/api/v1/integrations/google/status?error=missing_credentials", status_code=303)
    state = token_urlsafe(32)
    google_oauth_states.add(state)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@app.get("/api/v1/integrations/google/callback", tags=["integrations"])
async def google_callback(code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    if error or not code or not state or state not in google_oauth_states:
        return RedirectResponse(url="/api/v1/integrations/google/status?connected=false", status_code=303)
    google_oauth_states.discard(state)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
    if response.status_code >= 400:
        return RedirectResponse(url="/api/v1/integrations/google/status?connected=false", status_code=303)
    token = response.json()
    token["expires_at"] = datetime.now(timezone.utc).timestamp() + token.get("expires_in", 3600)
    google_tokens["default"] = token
    return RedirectResponse(url=f"{settings.app_url}/?google=connected", status_code=303)


@app.get("/api/v1/integrations/google/status", tags=["integrations"])
async def google_status(error: str | None = None) -> dict[str, bool | str | None]:
    return {"connected": "default" in google_tokens, "error": error}


async def google_access_token() -> str | None:
    token = google_tokens.get("default")
    if not token:
        return None
    expires_at = token.get("expires_at", 0)
    if expires_at and expires_at < datetime.now(timezone.utc).timestamp() + 60 and token.get("refresh_token"):
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": token["refresh_token"],
                "grant_type": "refresh_token",
            })
        if response.status_code < 400:
            refreshed = response.json()
            refreshed["refresh_token"] = token["refresh_token"]
            refreshed["expires_at"] = datetime.now(timezone.utc).timestamp() + refreshed.get("expires_in", 3600)
            google_tokens["default"] = refreshed
    return google_tokens["default"].get("access_token")


@app.get("/api/v1/integrations/google/events", tags=["integrations"])
async def google_events() -> dict:
    access_token = await google_access_token()
    if not access_token:
        return {"connected": False, "events": []}
    now = datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{GOOGLE_CALENDAR_URL}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"timeMin": now.isoformat(), "maxResults": 20, "singleEvents": "true", "orderBy": "startTime"},
        )
    if response.status_code >= 400:
        return {"connected": True, "events": [], "error": f"Google Calendar HTTP {response.status_code}"}
    return {"connected": True, "events": response.json().get("items", [])}


@app.get("/api/v1/integrations/clickup/status", tags=["integrations"])
async def clickup_status() -> dict[str, bool | str | None]:
    client = get_clickup_client()
    if not client:
        return {"connected": False, "error": "CLICKUP_API_KEY não configurada"}
    return {"connected": True, "error": None}


@app.get("/api/v1/integrations/clickup/workspaces", tags=["integrations"])
async def clickup_workspaces() -> dict:
    client = require_clickup()
    workspaces = await client.get_workspaces()
    return {"connected": True, "workspaces": workspaces[:20]}


@app.get("/api/v1/integrations/clickup/lists", tags=["integrations"])
async def clickup_lists(workspace_id: str | None = None) -> dict:
    client = require_clickup()
    workspace_id = workspace_id or await client.get_workspace_id()
    lists = await client.get_lists(workspace_id)
    return {"connected": True, "lists": lists[:50]}


@app.get("/api/v1/integrations/clickup/tasks", tags=["integrations"])
async def clickup_tasks(list_id: str | None = None) -> dict:
    client = require_clickup()
    list_id = list_id or await client.get_default_list_id()
    tasks = await client.get_tasks(list_id)
    return {"connected": True, "list_id": list_id, "tasks": tasks[:50]}


@app.post("/api/v1/integrations/clickup/tasks", tags=["integrations"])
async def clickup_create_task(
    list_id: str | None = None,
    name: str = "",
    description: str | None = None,
    priority: int | None = None,
    due_dates: str | None = None,
    assignees: str | None = None,
    tags: str | None = None,
) -> dict:
    client = require_clickup()
    list_id = list_id or await client.get_default_list_id()
    if not name.strip():
        raise HTTPException(status_code=422, detail="name é obrigatório")
    task = await client.create_task(
        list_id=list_id,
        name=name,
        description=description,
        priority=priority,
        due_dates=due_dates,
        assignees=assignees.split(",") if assignees else None,
        tags=tags.split(",") if tags else None,
    )
    return {"connected": True, "task": task}


@app.post("/webhooks/evolution", status_code=202, tags=["webhooks"])
async def evolution_webhook(request: Request) -> dict[str, str]:
    await request.json()
    return {"status": "accepted"}
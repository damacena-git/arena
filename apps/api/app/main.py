from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re
from secrets import token_urlsafe
import unicodedata
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
from .tts import TTSClient, get_tts_client

settings = get_settings()
ai_client = AIClient(settings)
tts_client = get_tts_client()
# Memória curta temporária; será substituída pela persistência no PostgreSQL.
conversation_histories: dict[str, list[dict[str, str]]] = {}
MAX_HISTORY_MESSAGES = 12
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_URL = "https://www.googleapis.com/calendar/v3"
google_oauth_states: set[str] = set()
google_tokens: dict[str, dict] = {}
pending_clickup_actions: dict[str, dict] = {}


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
        "user_timezone": settings.user_timezone,
        "environment": settings.environment,
        "ai_provider": settings.ai_provider,
        "groq_configured": bool(settings.groq_api_key),
        "openrouter_configured": bool(settings.openrouter_api_key),
        "groq_model": settings.groq_model,
        "openrouter_model": settings.openrouter_model,
        "groq_transcription_model": settings.groq_transcription_model,
    }


def normalize_text(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(char))


def chat_response(conversation_id: str, text: str) -> ChatResponse:
    return ChatResponse(conversation_id=conversation_id, message_id=str(uuid4()), text=text, created_at=datetime.now(timezone.utc))


async def prepare_google_read(conversation_id: str, text: str) -> ChatResponse | None:
    normalized = normalize_text(text)
    if not any(word in normalized for word in ("compromisso", "agenda", "calendario")) or not any(day in normalized for day in ("hoje", "amanha", "amanhã")):
        return None
    access_token = await google_access_token()
    if not access_token:
        return chat_response(conversation_id, "Ainda não estou conectado à sua agenda. Vá em Configuração e clique em Conectar agenda para eu consultar seus compromissos.")
    try:
        local_zone = ZoneInfo(settings.user_timezone)
    except Exception:
        local_zone = timezone.utc
    now = datetime.now(local_zone)
    end = now + timedelta(days=1)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{GOOGLE_CALENDAR_URL}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"timeMin": now.isoformat(), "timeMax": end.isoformat(), "maxResults": 50, "singleEvents": "true", "orderBy": "startTime"},
        )
    if response.status_code >= 400:
        return chat_response(conversation_id, f"Não consegui consultar sua agenda agora (Google Calendar HTTP {response.status_code}).")
    events = response.json().get("items", [])
    if not events:
        return chat_response(conversation_id, "Você não tem compromissos na agenda para hoje.")
    lines = [f"Você tem {len(events)} compromisso(s) hoje:"]
    for event in events:
        start_data = event.get("start", {})
        start = start_data.get("dateTime", start_data.get("date", ""))
        if "T" in start:
            start = start.split("T", 1)[1][:5]
        lines.append(f"• {start} — {event.get('summary', 'Sem título')}")
    return chat_response(conversation_id, "\n".join(lines))


async def prepare_clickup_read(conversation_id: str, text: str) -> ChatResponse | None:
    normalized = normalize_text(text)
    if "tarefa" not in normalized or "semana passada" not in normalized:
        return None
    client = require_clickup()
    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    start = int(datetime.combine(last_monday, datetime.min.time(), timezone.utc).timestamp() * 1000)
    end = int(datetime.combine(this_monday, datetime.min.time(), timezone.utc).timestamp() * 1000)
    tasks = await client.get_filtered_tasks(
        await client.get_workspace_id(),
        date_created_gt=start,
        date_created_lt=end,
        include_closed="true",
        subtasks="false",
    )
    if not tasks:
        return chat_response(conversation_id, "Não encontrei tarefas criadas no ClickUp durante a semana passada.")
    lines = [f"Encontrei {len(tasks)} tarefa(s) criada(s) na semana passada:"]
    for task in tasks[:30]:
        status = task.get("status", {}).get("status", "")
        list_name = task.get("list", {}).get("name", "")
        suffix = f" — {list_name}" if list_name else ""
        lines.append(f"• {task.get('name', 'Sem título')}{suffix} ({status})")
    if len(tasks) > 30:
        lines.append(f"… e mais {len(tasks) - 30} tarefa(s).")
    return chat_response(conversation_id, "\n".join(lines))


async def prepare_clickup_action(conversation_id: str, text: str) -> ChatResponse | None:
    normalized = normalize_text(text)
    pending = pending_clickup_actions.get(conversation_id)
    if pending and pending.get("awaiting_confirmation") and normalized in {"sim", "s", "confirmo", "pode", "pode criar", "ok", "sim pode criar"}:
        client = require_clickup()
        task = await client.create_task(
            list_id=pending["list_id"], name=pending["name"],
            assignees=[pending["assignee_id"]], due_dates=pending.get("due_date"),
        )
        pending_clickup_actions.pop(conversation_id, None)
        return chat_response(conversation_id, f"Tarefa criada no ClickUp com sucesso: {task.get('name', pending['name'])}.\n{task.get('url', '')}")
    if pending and pending.get("awaiting_confirmation") and normalized in {"nao", "cancela", "cancelar"}:
        pending_clickup_actions.pop(conversation_id, None)
        return chat_response(conversation_id, "Tudo bem, não criei a tarefa.")

    if "tarefa" not in normalized or not re.search(r"\b(crie|criar|cria|criei)\b", normalized):
        return None
    client = require_clickup()
    lists = await client.get_lists_for_workspace()
    list_item = None
    # Procura pelo nome real da lista, evitando que o restante da frase seja confundido com o nome.
    for item in sorted(lists, key=lambda value: len(normalize_text(value.get("name", ""))), reverse=True):
        item_name = normalize_text(item.get("name", "")).strip()
        folder_name = normalize_text(item.get("folder", {}).get("name", "")).strip()
        if item_name and re.search(rf"\b{re.escape(item_name)}\b", normalized):
            if "datelha" not in normalized or folder_name == "datelha":
                list_item = item
                break
    if not list_item:
        if "tarefa" not in normalized or not re.search(r"\b(crie|criar|cria|criei)\b", normalized):
            return None
        return None

    title_match = re.search(r"(?:titulo|título)\s+(?:da\s+tarefa\s+)?(?:sera|será|e)\s+(.+?)(?=\s+(?:hoje|amanha|amanhã|as|às|e\s+(?:o\s+)?horario|e\s+coloque|coloque)|$)", text, re.IGNORECASE)
    if not title_match:
        list_position = normalized.find(normalize_text(list_item["name"]))
        after_list = normalized[list_position + len(normalize_text(list_item["name"])):] if list_position >= 0 else ""
        title_match = re.match(r"\s*(?:e\s+)?(?:o\s+titulo\s+sera\s+)?(.+?)(?=\s+(?:hoje|amanha|as|às|e\s+(?:o\s+)?horario|e\s+coloque|coloque)|$)", after_list)
    if not title_match and pending and pending.get("awaiting_title"):
        title_match = re.match(r"\s*(.+?)\s*$", text)
    if not title_match:
        pending_clickup_actions[conversation_id] = {"list_id": list_item["id"], "list_name": list_item["name"], "awaiting_title": True}
        return chat_response(conversation_id, f"Encontrei a lista {list_item['name']}. Qual deve ser o título da tarefa?")

    name = title_match.group(1).strip().rstrip(".,")
    if not name or len(name) < 3:
        return chat_response(conversation_id, f"Encontrei a lista {list_item['name']}. Qual deve ser o título da tarefa?")
    members = await client.get_members(await client.get_workspace_id())
    diego = next((item for item in members if "diego" in normalize_text(str(item.get("user", {}).get("username", "")) + " " + str(item.get("user", {}).get("email", "")) + " " + str(item.get("user", {}).get("initials", "")))), None)
    if not diego:
        return chat_response(conversation_id, "Encontrei a tarefa, mas não localizei Diego como membro do Workspace.")
    due_date = None
    time_match = re.search(r"hoje\s+(?:as|às)\s+(\d{1,2})(?:\s*:\s*(\d{2}))?", normalized)
    if time_match:
        try:
            local_now = datetime.now(ZoneInfo(settings.user_timezone))
            due = local_now.replace(hour=int(time_match.group(1)), minute=int(time_match.group(2) or 0), second=0, microsecond=0)
            due_date = str(int(due.timestamp() * 1000))
        except (ValueError, KeyError):
            pass
    assignee_id = str(diego.get("user", {}).get("id"))
    pending_clickup_actions[conversation_id] = {"list_id": list_item["id"], "name": name, "assignee_id": assignee_id, "due_date": due_date, "awaiting_confirmation": True}
    due_label = f"\nPrazo: hoje às {time_match.group(1)}:{time_match.group(2) or '00'}" if time_match else ""
    return chat_response(conversation_id, f"Encontrei:\nCliente: {list_item.get('folder', {}).get('name', 'não informado')}\nLista: {list_item['name']}\nTítulo: {name}\nResponsável: Diego Damacena{due_label}\n\nPosso criar essa tarefa?")


@app.post("/api/v1/chat/messages", response_model=ChatResponse, tags=["chat"])
async def send_chat_message(payload: ChatMessage) -> ChatResponse:
    conversation_id = payload.conversation_id or str(uuid4())
    google_response = await prepare_google_read(conversation_id, payload.text)
    if google_response:
        return google_response
    read_response = await prepare_clickup_read(conversation_id, payload.text)
    if read_response:
        return read_response
    action_response = await prepare_clickup_action(conversation_id, payload.text)
    if action_response:
        return action_response
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
        action_response = await prepare_clickup_action(current_conversation_id, transcript)
        if action_response:
            action_response.transcription = transcript
            return action_response
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


# ==================== TTS Endpoints ====================


class TTSRequest(BaseModel):
    """Requisição para síntese de voz."""
    text: str = Field(min_length=1, max_length=5000, description="Texto para sintetizar")
    voice: str | None = Field(default=None, description="Voz a usar (ex: pt-BR-FranciscaNeural)")
    rate: str = Field(default="+0%", description="Velocidade da fala (ex: +10%, -20%)")
    volume: str = Field(default="+0%", description="Volume (ex: +10%, -20%)")
    pitch: str = Field(default="+0Hz", description="Tom da voz (ex: +10Hz, -5Hz)")


class TTSResponse(BaseModel):
    """Resposta da síntese de voz."""
    success: bool
    voice: str
    format: str = "mp3"
    audio_base64: str | None = None
    error: str | None = None


@app.post("/api/v1/tts/synthesize", response_model=TTSResponse, tags=["tts"])
async def tts_synthesize(payload: TTSRequest) -> TTSResponse:
    """Sintetiza texto em áudio usando Edge TTS."""
    import base64

    try:
        reply = await tts_client.synthesize(
            text=payload.text,
            voice=payload.voice,
            rate=payload.rate,
            volume=payload.volume,
            pitch=payload.pitch,
        )
        audio_base64 = base64.b64encode(reply.audio_data).decode("utf-8")
        return TTSResponse(
            success=True,
            voice=reply.voice,
            format=reply.format,
            audio_base64=audio_base64,
        )
    except Exception as exc:
        return TTSResponse(
            success=False,
            voice=payload.voice or tts_client.default_voice,
            error=str(exc),
        )


@app.get("/api/v1/tts/voices", tags=["tts"])
async def tts_voices() -> dict:
    """Lista vozes disponíveis para TTS."""
    return {"voices": TTSClient.list_voices()}


@app.get("/api/v1/tts/voices/all", tags=["tts"])
async def tts_all_voices() -> dict:
    """Lista todas as vozes do Edge TTS (requer conexão com internet)."""
    voices = await TTSClient.list_all_edge_voices()
    return {"voices": voices}
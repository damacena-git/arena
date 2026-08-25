from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai import AIClient, AIProviderError
from .config import get_settings

settings = get_settings()
ai_client = AIClient(settings)
# Memória curta temporária; será substituída pela persistência no PostgreSQL.
conversation_histories: dict[str, list[dict[str, str]]] = {}
MAX_HISTORY_MESSAGES = 12


app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/webhooks/evolution", status_code=202, tags=["webhooks"])
async def evolution_webhook(request: Request) -> dict[str, str]:
    # O payload é aceito agora para permitir configurar a Evolution API sem bloquear o MVP.
    # Validação de assinatura, idempotência e enfileiramento serão adicionados antes do uso real.
    await request.json()
    return {"status": "accepted"}

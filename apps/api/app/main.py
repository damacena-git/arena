from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai import AIClient, AIProviderError
from .config import get_settings

settings = get_settings()
ai_client = AIClient(settings)
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


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "sofia-api", "environment": settings.environment}


@app.get("/api/v1/config", tags=["system"])
async def public_config() -> dict[str, str]:
    return {"app_name": settings.app_name, "environment": settings.environment}


@app.post("/api/v1/chat/messages", response_model=ChatResponse, tags=["chat"])
async def send_chat_message(payload: ChatMessage) -> ChatResponse:
    conversation_id = payload.conversation_id or str(uuid4())
    try:
        ai_reply = await ai_client.complete(payload.text)
        reply = ai_reply.text
    except AIProviderError as exc:
        # A mensagem permanece útil mesmo quando as chaves não foram configuradas.
        reply = f"Ainda não consegui consultar minha inteligência artificial: {exc}"
    return ChatResponse(
        conversation_id=conversation_id,
        message_id=str(uuid4()),
        text=reply,
        created_at=datetime.now(timezone.utc),
    )


@app.post("/webhooks/evolution", status_code=202, tags=["webhooks"])
async def evolution_webhook(request: Request) -> dict[str, str]:
    # O payload é aceito agora para permitir configurar a Evolution API sem bloquear o MVP.
    # Validação de assinatura, idempotência e enfileiramento serão adicionados antes do uso real.
    await request.json()
    return {"status": "accepted"}

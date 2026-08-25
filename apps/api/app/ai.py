from dataclasses import dataclass

import httpx

from .config import Settings


class AIProviderError(RuntimeError):
    """Erro seguro para retorno ao usuário, sem expor credenciais ou payloads."""


@dataclass(frozen=True)
class AIReply:
    text: str
    provider: str
    model: str


class AIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def transcribe(self, filename: str, content: bytes, content_type: str) -> str:
        if not self.settings.groq_api_key:
            raise AIProviderError("A transcrição de áudio usa o Groq; configure GROQ_API_KEY.")

        files = {"file": (filename, content, content_type or "audio/mpeg")}
        data = {"model": self.settings.groq_transcription_model, "response_format": "json"}
        headers = {"Authorization": f"Bearer {self.settings.groq_api_key}"}
        async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
            )
        if response.status_code >= 400:
            raise AIProviderError(f"transcrição Groq: resposta HTTP {response.status_code}")
        try:
            text = response.json()["text"].strip()
        except (ValueError, KeyError, TypeError) as exc:
            raise AIProviderError("transcrição inválida do Groq") from exc
        if not text:
            raise AIProviderError("o áudio não contém fala identificável")
        return text

    async def complete(self, user_text: str) -> AIReply:
        providers = self._provider_order()
        if not providers:
            raise AIProviderError("Nenhum provedor de IA está configurado.")

        errors: list[str] = []
        for provider in providers:
            try:
                return await self._complete_with(provider, user_text)
            except (httpx.HTTPError, AIProviderError) as exc:
                errors.append(f"{provider}: {exc}")

        detail = "; ".join(errors)
        raise AIProviderError(
            f"Os provedores de IA não responderam ({detail}). "
            "Verifique as chaves, o modelo e a conexão."
        )

    def _provider_order(self) -> list[str]:
        configured = [self.settings.ai_provider.lower()]
        fallback = self.settings.ai_fallback_provider.lower()
        if fallback not in configured:
            configured.append(fallback)
        return [provider for provider in configured if self._api_key(provider)]

    def _api_key(self, provider: str) -> str:
        return {
            "groq": self.settings.groq_api_key,
            "openrouter": self.settings.openrouter_api_key,
        }.get(provider, "")

    async def _complete_with(self, provider: str, user_text: str) -> AIReply:
        if provider == "groq":
            base_url = "https://api.groq.com/openai/v1/chat/completions"
            model = self.settings.groq_model
        elif provider == "openrouter":
            base_url = "https://openrouter.ai/api/v1/chat/completions"
            model = self.settings.openrouter_model
        else:
            raise AIProviderError(f"Provedor não suportado: {provider}")

        headers = {"Authorization": f"Bearer {self._api_key(provider)}"}
        if provider == "openrouter":
            if self.settings.app_url:
                headers["HTTP-Referer"] = self.settings.app_url
            headers["X-Title"] = self.settings.app_name

        payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Você é Sofia, uma secretária pessoal objetiva, cordial e confiável. "
                        "Responda em português do Brasil. Neste momento você ainda não executa "
                        "ações externas; não diga que criou tarefas ou eventos. Se faltar contexto, "
                        "faça uma pergunta clara."
                    ),
                },
                {"role": "user", "content": user_text},
            ],
        }

        async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
            response = await client.post(base_url, headers=headers, json=payload)

        if response.status_code >= 400:
            raise AIProviderError(f"resposta HTTP {response.status_code}")

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("resposta inválida do provedor") from exc

        if not text:
            raise AIProviderError("resposta vazia do provedor")
        return AIReply(text=text, provider=provider, model=model)

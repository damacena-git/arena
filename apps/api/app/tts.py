"""Edge TTS client para síntese de voz."""
import edge_tts
from typing import Optional
from dataclasses import dataclass

from .config import get_settings


@dataclass(frozen=True)
class TTSReply:
    """Resultado da síntese de voz."""
    audio_data: bytes
    voice: str
    format: str = "mp3"


class TTSClient:
    """Cliente para Edge TTS (Microsoft Edge Text-to-Speech).

    Usa as vozes neurais do Microsoft Edge, disponíveis gratuitamente
    sem necessidade de API key.
    """

    # Vozes em português do Brasil disponíveis no Edge TTS
    PT_BR_VOICES = {
        "female": "pt-BR-FranciscaNeural",
        "male": "pt-BR-AntonioNeural",
    }

    # Outras vozes populares
    OTHER_VOICES = {
        "en-US-female": "en-US-AriaNeural",
        "en-US-male": "en-US-DavisNeural",
        "es-ES-female": "es-ES-ElviraNeural",
        "es-ES-male": "es-ES-AlvaroNeural",
        "fr-FR-female": "fr-FR-DeniseNeural",
        "fr-FR-male": "fr-FR-HenriNeural",
    }

    def __init__(self) -> None:
        settings = get_settings()
        self.default_voice = settings.tts_default_voice

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
    ) -> TTSReply:
        """Sintetiza texto em áudio usando Edge TTS.

        Args:
            text: Texto para sintetizar
            voice: Voz a usar (ex: "pt-BR-FranciscaNeural"). Se None, usa a padrão.
            rate: Velocidade da fala (ex: "+10%", "-20%")
            volume: Volume (ex: "+10%", "-20%")
            pitch: Tom da voz (ex: "+10Hz", "-5Hz")

        Returns:
            TTSReply com dados de áudio e metadados

        Raises:
            RuntimeError: Se houver erro na síntese
        """
        voice = voice or self.default_voice

        # Valida se a voz existe (opcional - edge-tts lança erro se inválida)
        if not self._is_valid_voice(voice):
            # Fallback para voz padrão se a voz não for reconhecida
            voice = self.default_voice

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
        )

        audio_chunks = []
        try:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])
        except Exception as exc:
            raise RuntimeError(f"Erro na síntese de voz: {exc}") from exc

        if not audio_chunks:
            raise RuntimeError("Nenhum áudio gerado")

        audio_data = b"".join(audio_chunks)

        return TTSReply(
            audio_data=audio_data,
            voice=voice,
            format="mp3",
        )

    def _is_valid_voice(self, voice: str) -> bool:
        """Verifica se a voz é uma voz conhecida do Edge TTS."""
        all_voices = {**self.PT_BR_VOICES, **self.OTHER_VOICES}
        return voice in all_voices.values()

    @classmethod
    def list_voices(cls) -> dict[str, str]:
        """Lista todas as vozes disponíveis organizadas por idioma/gênero."""
        return {**cls.PT_BR_VOICES, **cls.OTHER_VOICES}

    @classmethod
    async def list_all_edge_voices(cls) -> list[dict]:
        """Lista todas as vozes disponíveis no Edge TTS (requer conexão)."""
        try:
            voices = await edge_tts.list_voices()
            return [
                {
                    "name": v["ShortName"],
                    "display_name": v["FriendlyName"],
                    "gender": v["Gender"],
                    "locale": v["Locale"],
                    "style_list": v.get("StyleList", []),
                }
                for v in voices
            ]
        except Exception:
            return []


# Instância global padrão
_default_client: Optional[TTSClient] = None


def get_tts_client() -> TTSClient:
    """Retorna instância singleton do TTSClient."""
    global _default_client
    if _default_client is None:
        _default_client = TTSClient()
    return _default_client
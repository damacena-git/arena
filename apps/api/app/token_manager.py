"""Gerenciador de tokens OAuth com persistência em arquivo JSON."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from cryptography.fernet import Fernet
from .config import get_settings

settings = get_settings()

# Usar arquivo JSON local por enquanto (antes de implementar DB)
TOKENS_FILE = Path(__file__).parent.parent.parent / ".tokens.json"
ENCRYPTION_KEY_FILE = Path(__file__).parent.parent.parent / ".token_key"


def _get_or_create_encryption_key() -> bytes:
    """Gera ou carrega a chave de criptografia."""
    if ENCRYPTION_KEY_FILE.exists():
        with open(ENCRYPTION_KEY_FILE, "rb") as f:
            return f.read()

    key = Fernet.generate_key()
    ENCRYPTION_KEY_FILE.write_bytes(key)
    # Proteger arquivo
    os.chmod(ENCRYPTION_KEY_FILE, 0o600)
    return key


def _get_cipher() -> Fernet:
    """Obtém cipher Fernet para criptografia."""
    key = _get_or_create_encryption_key()
    return Fernet(key)


def _load_tokens() -> dict:
    """Carrega tokens do arquivo."""
    if not TOKENS_FILE.exists():
        return {}

    try:
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_tokens(tokens: dict) -> None:
    """Salva tokens no arquivo (criptografados)."""
    cipher = _get_cipher()

    # Criptografar tokens sensíveis
    encrypted_tokens = {}
    for key, token_data in tokens.items():
        encrypted_tokens[key] = {
            "access_token": cipher.encrypt(token_data["access_token"].encode()).decode(),
            "refresh_token": cipher.encrypt(token_data["refresh_token"].encode()).decode() if token_data.get("refresh_token") else None,
            "expires_at": token_data.get("expires_at"),
            "token_type": token_data.get("token_type", "Bearer"),
        }

    with open(TOKENS_FILE, "w") as f:
        json.dump(encrypted_tokens, f, indent=2)

    # Proteger arquivo
    os.chmod(TOKENS_FILE, 0o600)


def _decrypt_tokens(encrypted_tokens: dict) -> dict:
    """Descriptografa tokens do arquivo."""
    cipher = _get_cipher()
    decrypted = {}

    for key, token_data in encrypted_tokens.items():
        try:
            decrypted[key] = {
                "access_token": cipher.decrypt(token_data["access_token"].encode()).decode(),
                "refresh_token": cipher.decrypt(token_data["refresh_token"].encode()).decode() if token_data.get("refresh_token") else None,
                "expires_at": token_data.get("expires_at"),
                "token_type": token_data.get("token_type", "Bearer"),
            }
        except Exception:
            # Se não conseguir descriptografar, ignorar
            pass

    return decrypted


def save_google_token(user_id: str = "default", token_data: dict = None) -> None:
    """Salva token do Google Calendar."""
    if token_data is None:
        return

    tokens = _load_tokens()
    tokens[f"google_{user_id}"] = {
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_at": token_data.get("expires_at"),
        "token_type": token_data.get("token_type", "Bearer"),
    }
    _save_tokens(tokens)


def load_google_token(user_id: str = "default") -> dict | None:
    """Carrega token do Google Calendar."""
    encrypted_tokens = _load_tokens()
    decrypted = _decrypt_tokens(encrypted_tokens)
    return decrypted.get(f"google_{user_id}")


def delete_google_token(user_id: str = "default") -> None:
    """Deleta token do Google Calendar."""
    encrypted_tokens = _load_tokens()
    encrypted_tokens.pop(f"google_{user_id}", None)
    _save_tokens(encrypted_tokens)


def save_clickup_token(api_key: str, user_id: str = "default") -> None:
    """Salva token/API key do ClickUp."""
    tokens = _load_tokens()
    cipher = _get_cipher()
    tokens[f"clickup_{user_id}"] = {
        "api_key": cipher.encrypt(api_key.encode()).decode(),
    }
    _save_tokens(tokens)


def load_clickup_token(user_id: str = "default") -> str | None:
    """Carrega token/API key do ClickUp."""
    encrypted_tokens = _load_tokens()
    decrypted = _decrypt_tokens(encrypted_tokens)
    token_data = decrypted.get(f"clickup_{user_id}")
    if token_data:
        cipher = _get_cipher()
        try:
            return cipher.decrypt(token_data.get("api_key", "").encode()).decode()
        except Exception:
            return None
    return None

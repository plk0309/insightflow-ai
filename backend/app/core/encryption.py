
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import dotenv_values


class EncryptionConfigurationError(RuntimeError):
    """Raised when the encryption key is missing or invalid."""


# Resolve the backend directory independently of the
# terminal's current working directory.
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


def get_encryption_key() -> str:
    # Production: prefer an explicitly configured environment variable.
    key = os.getenv("CREDENTIAL_ENCRYPTION_KEY")

    # Local development: fall back to backend/.env.
    if not key and ENV_FILE.is_file():
        key = dotenv_values(ENV_FILE).get(
            "CREDENTIAL_ENCRYPTION_KEY"
        )

    if not key:
        raise EncryptionConfigurationError(
            "CREDENTIAL_ENCRYPTION_KEY is not configured"
        )

    return key


def get_fernet() -> Fernet:
    key = get_encryption_key()

    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise EncryptionConfigurationError(
            "CREDENTIAL_ENCRYPTION_KEY is invalid"
        ) from exc


def encrypt_credential(plaintext: str) -> str:
    if not isinstance(plaintext, str):
        raise TypeError("Credential must be a string")

    encrypted = get_fernet().encrypt(
        plaintext.encode("utf-8")
    )

    return encrypted.decode("ascii")


def decrypt_credential(ciphertext: str) -> str:
    if not isinstance(ciphertext, str):
        raise TypeError("Encrypted credential must be a string")

    try:
        decrypted = get_fernet().decrypt(
            ciphertext.encode("ascii")
        )
    except (InvalidToken, UnicodeEncodeError) as exc:
        raise ValueError(
            "Credential decryption failed"
        ) from exc

    return decrypted.decode("utf-8")

"""Password hashing and session tokens, using only the standard library."""

import hashlib
import hmac
import secrets

# scrypt parameters (OWASP-recommended minimums).
_N, _R, _P = 2**14, 8, 1
_KEY_LEN = 64


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_KEY_LEN)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, key_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    key = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt_hex), n=_N, r=_R, p=_P, dklen=_KEY_LEN
    )
    return hmac.compare_digest(key.hex(), key_hex)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Only the token's hash is stored, so a leaked DB can't be used to hijack sessions."""
    return hashlib.sha256(token.encode()).hexdigest()

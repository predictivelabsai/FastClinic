"""Per-user Exa credentials, encrypted in the operational database.

Manual jobs use their requesting user's key, then the shared deployment key.
Weekly jobs use only the shared key. No secret is copied into a queued job.
"""

import os
from cryptography.fernet import Fernet, InvalidToken
from web import market

SHARED = "__scheduled_market__"


def connect():
    c = market.connect()
    c.execute(
        """CREATE TABLE IF NOT EXISTS search_provider_credentials
        (owner TEXT PRIMARY KEY, provider TEXT NOT NULL, encrypted_key TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    )
    c.commit()
    return c


def cipher():
    key = os.getenv("MARKET_CREDENTIALS_KEY") or os.getenv("BYOK_ENCRYPTION_KEY")
    if not key:
        raise ValueError(
            "Set MARKET_CREDENTIALS_KEY to a persistent Fernet key before saving credentials"
        )
    try:
        return Fernet(key.encode())
    except ValueError:
        raise ValueError("MARKET_CREDENTIALS_KEY must be a valid Fernet key") from None


def configured(owner):
    with connect() as c:
        return bool(
            c.execute(
                "SELECT owner FROM search_provider_credentials WHERE owner=?", (owner,)
            ).fetchone()
        )


def save(owner, key, provider="exa"):
    if provider != "exa":
        raise ValueError("Only Exa is enabled")
    if not key.strip() or len(key) > 512:
        raise ValueError("Enter an Exa API key")
    token = cipher().encrypt(key.strip().encode()).decode()
    with connect() as c:
        c.execute(
            """INSERT INTO search_provider_credentials (owner,provider,encrypted_key,updated_at) VALUES (?,?,?,?)
           ON CONFLICT(owner) DO UPDATE SET provider=excluded.provider,encrypted_key=excluded.encrypted_key,updated_at=excluded.updated_at""",
            (owner, provider, token, market.now()),
        )
        c.commit()


def remove(owner):
    with connect() as c:
        c.execute("DELETE FROM search_provider_credentials WHERE owner=?", (owner,))
        c.commit()


def resolve(owner=None):
    with connect() as c:
        for who in [owner, SHARED] if owner else [SHARED]:
            if not who:
                continue
            row = c.execute(
                "SELECT encrypted_key FROM search_provider_credentials WHERE owner=?",
                (who,),
            ).fetchone()
            if row:
                try:
                    return cipher().decrypt(row["encrypted_key"].encode()).decode()
                except InvalidToken:
                    raise ValueError(
                        "Stored Exa credential cannot be decrypted; re-enter the key"
                    ) from None
    return os.getenv("EXA_API_KEY", "")

import hashlib
import uuid
import time
from typing import Optional

from fastapi import HTTPException


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token() -> str:
    return str(uuid.uuid4())


def get_user_by_session(sessions: dict, session_token: str) -> Optional[str]:
    session = sessions.get(session_token)
    if session and time.time() - session["created_at"] < 86400:
        return session["username"]
    return None


async def verify_session(sessions: dict, session_token: str = None) -> str:
    if not session_token:
        raise HTTPException(status_code=401, detail="Session token required")
    username = get_user_by_session(sessions, session_token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return username

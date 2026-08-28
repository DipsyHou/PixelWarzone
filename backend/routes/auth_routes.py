import time
import logging

from fastapi import APIRouter

from models import RegisterRequest, LoginRequest
from auth import hash_password, generate_token, get_user_by_session
from data_store import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["auth"])

DEFAULT_LOADOUT = {
    "weapon_slots": ["single", "shotgun", "crossbomb", "wall"],
    "perks": [],
}


@router.post("/register")
async def register(request: RegisterRequest):
    if request.username in store.users_db:
        return {"success": False, "error": "用户名已存在"}
    if len(request.username) > 16:
        return {"success": False, "error": "用户名过长"}

    store.users_db[request.username] = {
        "password_hash": hash_password(request.password),
        "email": request.email,
        "stats": {
            "games_played": 0, "wins": 0, "kills": 0,
            "deaths": 0, "total_damage": 0,
        },
        "loadout": dict(DEFAULT_LOADOUT),
        "created_at": time.time(),
    }

    session_token = generate_token()
    store.sessions[session_token] = {
        "username": request.username,
        "created_at": time.time(),
    }

    logger.info(f"User registered: {request.username}")
    store.save_all()
    return {
        "success": True,
        "session_token": session_token,
        "username": request.username,
        "stats": store.users_db[request.username]["stats"],
    }


@router.post("/login")
async def login(request: LoginRequest):
    user = store.users_db.get(request.username)
    if not user or user["password_hash"] != hash_password(request.password):
        return {"success": False, "error": "用户名或密码错误"}

    session_token = generate_token()
    store.sessions[session_token] = {
        "username": request.username,
        "created_at": time.time(),
    }

    logger.info(f"User logged in: {request.username}")
    store.save_all()
    return {
        "success": True,
        "session_token": session_token,
        "username": request.username,
        "stats": user["stats"],
        "loadout": user.get("loadout", DEFAULT_LOADOUT),
    }


@router.get("/user/{session_token}")
async def get_user_info(session_token: str):
    try:
        username = get_user_by_session(store.sessions, session_token)
        if not username:
            return {"success": False, "error": "Invalid or expired session"}
        user = store.users_db.get(username)
        if not user:
            return {"success": False, "error": "User not found"}
        return {
            "success": True,
            "username": username,
            "email": user["email"],
            "stats": user["stats"],
            "loadout": user.get("loadout", DEFAULT_LOADOUT),
            "current_room": store.user_rooms.get(username),
            "created_at": user.get("created_at", time.time()),
            "last_login": user.get("last_login", time.time()),
        }
    except Exception as e:
        logger.error(f"Get user info error: {e}")
        return {"success": False, "error": "Server error"}

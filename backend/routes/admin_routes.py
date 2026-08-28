import logging

from fastapi import APIRouter, HTTPException

from models import AdminRequest
from data_store import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_PASSWORD = "admin123"


@router.post("/clear-database")
async def clear_database(request: AdminRequest):
    if request.admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="管理员密码错误")

    stats_before = {
        "users": len(store.users_db),
        "sessions": len(store.sessions),
        "rooms": len(store.rooms),
        "user_rooms": len(store.user_rooms),
        "total_players": sum(len(r.players) for r in store.rooms.values()),
    }

    for room in store.rooms.values():
        for ws in list(room.connections.values()):
            try:
                await ws.close(code=4200, reason="Database clearing")
            except Exception:
                pass

    store.users_db.clear()
    store.sessions.clear()
    store.rooms.clear()
    store.user_rooms.clear()
    store.save_all()

    logger.info(f"Database cleared - Stats before: {stats_before}")
    return {"success": True, "message": "数据库已清空", "cleared": stats_before}


@router.post("/stats")
async def get_database_stats(request: AdminRequest):
    if request.admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="管理员密码错误")
    return {
        "success": True,
        "users_count": len(store.users_db),
        "active_sessions": len(store.sessions),
        "active_rooms": len(store.rooms),
        "users_in_rooms": len(store.user_rooms),
        "total_players_online": sum(len(r.players) for r in store.rooms.values()),
        "room_details": [
            {"id": r.room_id, "name": r.name, "players": len(r.players), "creator": r.creator}
            for r in store.rooms.values()
        ],
    }

import logging

from fastapi import APIRouter, Query

from models import CreateRoomRequest, JoinRoomRequest
from auth import generate_token, verify_session
from data_store import store
from room import Room

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["rooms"])


@router.post("/rooms/create")
async def create_room(
    request: CreateRoomRequest,
    session_token: str = Query(..., description="用户会话令牌"),
):
    username = await verify_session(store.sessions, session_token)
    if username in store.user_rooms:
        return {"success": False, "error": "你已经在一个房间中"}

    room_id = generate_token()[:8]
    room = Room(
        room_id=room_id,
        name=request.room_name,
        creator=username,
        max_players=request.max_players,
        password=request.password,
    )
    store.rooms[room_id] = room
    store.user_rooms[username] = room_id
    room.add_player(username, None)

    logger.info(f"Room created: {room_id} by {username}")
    store.save_all()
    return {
        "success": True,
        "room_id": room_id,
        "room": {
            "id": room_id,
            "name": room.name,
            "creator": room.creator,
            "player_count": len(room.players),
            "max_players": room.max_players,
            "has_password": bool(room.password),
        },
    }


@router.get("/rooms")
async def get_rooms():
    room_list = [
        {
            "id": r.room_id,
            "name": r.name,
            "creator": r.creator,
            "player_count": len(r.players),
            "max_players": r.max_players,
            "has_password": bool(r.password),
            "created_at": r.created_at,
        }
        for r in store.rooms.values()
    ]
    room_list.sort(key=lambda x: x["created_at"], reverse=True)
    return {"rooms": room_list}


@router.post("/rooms/{room_id}/join")
async def join_room(
    room_id: str,
    request: JoinRoomRequest,
    session_token: str = Query(..., description="用户会话令牌"),
):
    username = await verify_session(store.sessions, session_token)
    room = store.rooms.get(room_id)
    if not room:
        return {"success": False, "error": "房间不存在"}
    if len(room.players) >= room.max_players:
        return {"success": False, "error": "房间已满"}
    if room.password and room.password != request.password:
        return {"success": False, "error": "房间密码错误"}

    store.user_rooms[username] = room_id
    logger.info(f"User {username} joined room {room_id}")
    store.save_all()
    return {"success": True, "room_id": room_id, "username": username}


@router.post("/rooms/leave")
async def leave_room(
    session_token: str = Query(..., description="用户会话令牌"),
):
    username = await verify_session(store.sessions, session_token)
    room_id = store.user_rooms.get(username)
    if not room_id:
        return {"success": False, "error": "你不在任何房间中"}

    room = store.rooms.get(room_id)
    if room:
        room.remove_player(username)
        if not room.players:
            store.rooms.pop(room_id, None)
            logger.info(f"Room {room_id} deleted (empty)")

    store.user_rooms.pop(username, None)
    store.save_all()
    logger.info(f"User {username} left room {room_id}")
    return {"success": True}

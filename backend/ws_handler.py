"""
WebSocket endpoint: connection lifecycle, authentication, and message dispatch.
"""

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect, Query

from auth import get_user_by_session
from data_store import store
from message_handler import handle_message

logger = logging.getLogger(__name__)


async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    session_token: str = Query(...),
):
    try:
        username = get_user_by_session(store.sessions, session_token)
        if not username:
            await websocket.close(code=4001)
            return
        if store.user_rooms.get(username) != room_id:
            await websocket.close(code=4002)
            return
        room = store.rooms.get(room_id)
        if not room:
            await websocket.close(code=4003)
            return

        await websocket.accept()

        loadout = store.users_db.get(username, {}).get("loadout")
        if not room.add_player(username, websocket, loadout):
            await websocket.close(code=4004)
            return

        logger.info(f"Player {username} connected to room {room_id}")
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                except Exception:
                    continue
                handle_message(room, username, msg)
        except WebSocketDisconnect:
            pass
        finally:
            _on_disconnect(room, room_id, username)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    await websocket.close(code=4500)


def _on_disconnect(room, room_id: str, username: str):
    if username in room.players:
        pd = room.players[username]
        if username in store.users_db:
            stats = store.users_db[username]["stats"]
            stats["games_played"] += 1
            stats["kills"] += pd["kills"]
            stats["deaths"] += pd["deaths"]
            if len(room.players) <= 1 or pd["kills"] > 0:
                stats["wins"] += 1

    room.remove_player(username)
    logger.info(f"Player {username} disconnected from room {room_id}")

    if not room.players:
        store.rooms.pop(room_id, None)
        logger.info(f"Room {room_id} deleted (empty)")

    if store.user_rooms.get(username) == room_id:
        store.user_rooms.pop(username, None)
        
    store.save_all()

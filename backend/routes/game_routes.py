import time
import logging

from fastapi import APIRouter, Query

from models import UpdateLoadoutRequest
from auth import verify_session
from data_store import store
import server_config as cfg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["game"])

AVAILABLE_WEAPONS = [
    "single", "shotgun", "missile", "wall",
    "smoke", "turret", "iaido", "crossbomb",
]
AVAILABLE_PERKS = ["regen_boost", "regen_when_dead"]


@router.get("/game-config")
async def get_game_config():
    return {"success": True, "config": cfg.as_client_dict()}


@router.get("/loadout/meta")
async def get_loadout_meta():
    return {"success": True, "weapons": AVAILABLE_WEAPONS, "perks": AVAILABLE_PERKS}



@router.post("/loadout/update")
async def update_loadout(req: UpdateLoadoutRequest, session_token: str = Query(...)):
    username = await verify_session(store.sessions, session_token)
    if len(req.weapon_slots) != 4:
        return {"success": False, "error": "武器槽数量必须为4"}

    safe_weapons = [w for w in req.weapon_slots if w in AVAILABLE_WEAPONS][:4]
    while len(safe_weapons) < 4:
        safe_weapons.append("single")
    safe_perks = [p for p in req.perks if p in AVAILABLE_PERKS]

    store.users_db.setdefault(username, {}).setdefault("loadout", {})
    store.users_db[username]["loadout"] = {
        "weapon_slots": safe_weapons,
        "perks": safe_perks,
    }
    store.save_all()
    return {"success": True, "loadout": store.users_db[username]["loadout"]}


@router.get("/leaderboard")
async def get_leaderboard():
    board = []
    for uname, ud in store.users_db.items():
        s = ud["stats"]
        board.append({
            "username": uname,
            "kills": s["kills"],
            "deaths": s["deaths"],
            "wins": s["wins"],
            "games_played": s["games_played"],
            "kd_ratio": round(s["kills"] / max(s["deaths"], 1), 2),
            "win_rate": round(s["wins"] / max(s["games_played"], 1) * 100, 1),
        })
    board.sort(key=lambda x: x["kills"], reverse=True)
    return {"success": True, "leaderboard": board[:50]}


@router.get("/online-players")
async def get_online_players():
    now = time.time()
    online = []
    for _token, session in store.sessions.items():
        if now - session["created_at"] < 300:
            uname = session["username"]
            ud = store.users_db.get(uname, {})
            online.append({
                "username": uname,
                "in_game": uname in store.user_rooms,
                "stats": ud.get("stats", {
                    "games_played": 0, "wins": 0, "kills": 0,
                    "deaths": 0, "total_damage": 0,
                }),
            })
    return {"success": True, "online_players": online, "count": len(online)}

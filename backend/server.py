from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import asyncio
import random
import json
import time
import hashlib
import uuid
import math
from contextlib import asynccontextmanager
from typing import Optional, Dict, List
import logging
import os
import server_config as cfg
from utils import _dist_point_to_segment, circle_aabb_overlap, distance

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 生命周期管理：使用 lifespan 替代 on_event 以消除弃用警告
game_loop_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global game_loop_task
    logger.info("Starting game server...")
    game_loop_task = asyncio.create_task(game_loop())
    try:
        yield
    finally:
        logger.info("Saving all data before shutdown...")
        save_all_data()
        if game_loop_task and not game_loop_task.done():
            game_loop_task.cancel()
            try:
                await game_loop_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Battle Royale Game API", lifespan=lifespan)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务
# app.mount("/static", StaticFiles(directory="static"), name="static")


# 数据持久化
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录（backend 的上级）
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
USERS_FILE = os.path.join(DATA_DIR, "users_db.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
ROOMS_FILE = os.path.join(DATA_DIR, "rooms.json")
USER_ROOMS_FILE = os.path.join(DATA_DIR, "user_rooms.json")


def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


ensure_data_dir()
users_db: Dict = load_json(USERS_FILE)
sessions: Dict = load_json(SESSIONS_FILE)
user_rooms: Dict = load_json(USER_ROOMS_FILE)
rooms: Dict = {}

# 房间对象序列化/反序列化


class Room:
    def __init__(
            self,
            room_id: str,
            name: str,
            creator: str,
            max_players: int = 8,
            password: str = None):
        self.room_id = room_id
        self.name = name
        self.creator = creator
        self.max_players = max_players
        self.password = password
        self.players = {}  # {username: player_data}
        self.bullets = []
        self.connections = {}  # {username: websocket}
        self.game_running = False
        self.created_at = time.time()
        self.walls = []  # 墙体 {x, y, owner, blocks: [{x, y}]}
        self.graffiti = {}  # 涂鸦 {username: {x, y}}
        self.smokes = []  # 烟雾弹 [{x, y, radius, owner, created_at, duration}]
        self.turrets = []  # 炮台 [{x, y, hp, owner, created_at, last_fire}]
        self.cross_bombs = []  # 十字炸弹 [{x, y, owner, angle, planted_at, explode_at, state}]

    def add_player(self, username: str, websocket: WebSocket):
        if len(self.players) >= self.max_players:
            return False

        # 初始化玩家数据，增加武器槽与漏洞（被动）
        self.players[username] = {
            "x": random.randint(100, MAP_WIDTH - 100),
            "y": random.randint(100, MAP_HEIGHT - 100),
            "dx": 0,
            "dy": 0,
            "hp": cfg.PLAYER_MAX_HP,
            "last_hit": time.time(),
            "kills": 0,
            "deaths": 0,
            # weapon_slots: 四个槽位的武器类型字符串数组，例如 ["single","shotgun","missile","wall"]
            "weapon_slots": users_db.get(username, {}).get("loadout", {}).get("weapon_slots", ["single", "shotgun", "crossbomb", "wall"])[:4],
            # perks: 被动列表，例如 ["regen_boost","regen_when_dead"]
            "perks": users_db.get(username, {}).get("loadout", {}).get("perks", [])
        }
        self.connections[username] = websocket
        return True

    def remove_player(self, username: str):
        self.players.pop(username, None)
        self.connections.pop(username, None)
        if not self.players and self.game_running:
            self.game_running = False

    def get_state(self):
        state_players = {}
        for username, player in self.players.items():
            player_copy = player.copy()
            player_copy["status"] = "dead" if player_copy["hp"] <= 0 else "alive"
            player_copy["hp"] = max(0, int(player_copy.get("hp", 0)))
            state_players[username] = player_copy
        return {
            "players": state_players,
            "bullets": self.bullets,
            "walls": self.walls,
            "graffiti": self.graffiti,
            "smokes": self.smokes,
            "turrets": self.turrets,
            "cross_bombs": self.cross_bombs,
            "room_info": {
                "name": self.name,
                "player_count": len(self.players),
                "max_players": self.max_players
            }
        }

    def to_dict(self):
        return {
            "room_id": self.room_id,
            "name": self.name,
            "creator": self.creator,
            "max_players": self.max_players,
            "password": self.password,
            "players": self.players,
            "bullets": self.bullets,
            "game_running": self.game_running,
            "created_at": self.created_at
        }

    @staticmethod
    def from_dict(d):
        room = Room(
            room_id=d["room_id"],
            name=d["name"],
            creator=d["creator"],
            max_players=d.get("max_players", 8),
            password=d.get("password")
        )
        room.players = d.get("players", {})
        room.bullets = d.get("bullets", [])
        room.game_running = d.get("game_running", False)
        room.created_at = d.get("created_at", time.time())
        return room


# 加载房间数据
rooms_raw: Dict = load_json(ROOMS_FILE)
for room_id, room_data in rooms_raw.items():
    rooms[room_id] = Room.from_dict(room_data)


def save_all_data():
    save_json(USERS_FILE, users_db)
    save_json(SESSIONS_FILE, sessions)
    save_json(USER_ROOMS_FILE, user_rooms)
    rooms_dict = {room_id: room.to_dict() for room_id, room in rooms.items()}
    save_json(ROOMS_FILE, rooms_dict)


MAP_WIDTH = cfg.MAP_WIDTH
MAP_HEIGHT = cfg.MAP_HEIGHT


def point_in_cross_area(bomb, x, y):
    bx = bomb.get("x", 0.0)
    by = bomb.get("y", 0.0)
    dirx = bomb.get("dirx", 1.0)
    diry = bomb.get("diry", 0.0)
    norm = (dirx * dirx + diry * diry) ** 0.5 or 1.0
    ux = dirx / norm
    uy = diry / norm
    vx = x - bx
    vy = y - by
    proj = vx * ux + vy * uy
    perp = -vx * uy + vy * ux
    length = cfg.CROSS_BOMB_ARM_LENGTH
    half_width = cfg.CROSS_BOMB_ARM_HALF_WIDTH
    if abs(proj) <= length and abs(perp) <= half_width:
        return True
    if abs(perp) <= length and abs(proj) <= half_width:
        return True
    return False


def apply_cross_bomb_damage(room: "Room", bomb: dict, now_ts: float):
    owner = bomb.get("owner")
    damage = cfg.CROSS_BOMB_DAMAGE
    # 玩家伤害
    for uname, player in room.players.items():
        if player.get("hp", 0) <= 0:
            continue
        if owner and uname == owner:
            continue
        if point_in_cross_area(bomb, player.get("x", 0), player.get("y", 0)):
            player["hp"] = max(0, player.get("hp", 0) - damage)
            player["last_hit"] = now_ts
            if player["hp"] <= 0:
                player["hp"] = 0
                player["deaths"] = player.get("deaths", 0) + 1
                if owner and owner != uname and owner in room.players:
                    room.players[owner]["kills"] = room.players[owner].get("kills", 0) + 1
    # 炮台伤害
    for turret in room.turrets:
        if turret.get("hp", 0) <= 0:
            continue
        if point_in_cross_area(bomb, turret.get("x", 0), turret.get("y", 0)):
            turret["hp"] = max(0, turret.get("hp", 0) - damage)
    # 墙体破坏
    remove_map = []  # (wall_idx, block_idx)
    for w_idx, wall in enumerate(room.walls):
        for b_idx, block in enumerate(wall.get("blocks", [])):
            if point_in_cross_area(bomb, block.get("x", 0), block.get("y", 0)):
                remove_map.append((w_idx, b_idx))
    if remove_map:
        from collections import defaultdict
        grouped = defaultdict(list)
        for w_idx, b_idx in remove_map:
            grouped[w_idx].append(b_idx)
        for w_idx, b_idxs in grouped.items():
            if 0 <= w_idx < len(room.walls):
                wall = room.walls[w_idx]
                for b_idx in sorted(b_idxs, reverse=True):
                    if 0 <= b_idx < len(wall.get("blocks", [])):
                        wall["blocks"].pop(b_idx)
        room.walls = [w for w in room.walls if w.get("blocks")]

# 数据模型


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateRoomRequest(BaseModel):
    room_name: str
    max_players: int = 8
    password: Optional[str] = None


class JoinRoomRequest(BaseModel):
    room_id: Optional[str] = None
    password: Optional[str] = None


class AdminRequest(BaseModel):
    admin_password: str

class UpdateLoadoutRequest(BaseModel):
    weapon_slots: List[str]
    perks: List[str]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token() -> str:
    return str(uuid.uuid4())


# 可用武器与漏洞枚举（前端可拉取显示）
AVAILABLE_WEAPONS = [
    "single", "shotgun", "missile", "wall", "smoke", "turret", "iaido", "crossbomb"
]
AVAILABLE_PERKS = [
    # regen_boost: 增强回血效率；regen_when_dead: 死亡后仍可回血直到复活
    "regen_boost", "regen_when_dead"
]


@app.get("/api/loadout/meta")
async def get_loadout_meta():
    return {"success": True, "weapons": AVAILABLE_WEAPONS, "perks": AVAILABLE_PERKS}


@app.post("/api/loadout/update")
async def update_loadout(req: UpdateLoadoutRequest, session_token: str = Query(...)):
    username = await verify_session(session_token)
    if len(req.weapon_slots) != 4:
        return {"success": False, "error": "武器槽数量必须为4"}
    # 过滤非法项
    safe_weapons = [w for w in req.weapon_slots if w in AVAILABLE_WEAPONS][:4]
    while len(safe_weapons) < 4:
        safe_weapons.append("single")
    safe_perks = [p for p in req.perks if p in AVAILABLE_PERKS]
    users_db.setdefault(username, {}).setdefault("loadout", {})
    users_db[username]["loadout"] = {"weapon_slots": safe_weapons, "perks": safe_perks}
    save_all_data()
    return {"success": True, "loadout": users_db[username]["loadout"]}


def get_user_by_session(session_token: str) -> Optional[str]:
    session = sessions.get(session_token)
    if session and time.time() - session["created_at"] < 86400:
        return session["username"]
    return None


async def verify_session(session_token: str = None) -> str:
    if not session_token:
        raise HTTPException(status_code=401, detail="Session token required")
    username = get_user_by_session(session_token)
    if not username:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session")
    return username


@app.post("/api/register")
async def register(request: RegisterRequest):
    if request.username in users_db:
        return {"success": False, "error": "用户名已存在"}
    if len(request.username) > 16:
        return {"success": False, "error": "用户名过长"}
    users_db[request.username] = {
        "password_hash": hash_password(request.password),
        "email": request.email,
        "stats": {
            "games_played": 0,
            "wins": 0,
            "kills": 0,
            "deaths": 0,
            "total_damage": 0
        },
        "loadout": {
            "weapon_slots": ["single", "shotgun", "crossbomb", "wall"],
            "perks": []
        },
        "created_at": time.time()
    }
    session_token = generate_token()
    sessions[session_token] = {
        "username": request.username,
        "created_at": time.time()
    }
    logger.info(f"User registered: {request.username}")
    save_all_data()
    return {
        "success": True,
        "session_token": session_token,
        "username": request.username,
        "stats": users_db[request.username]["stats"]
    }


@app.post("/api/login")
async def login(request: LoginRequest):
    user = users_db.get(request.username)
    if not user or user["password_hash"] != hash_password(request.password):
        return {"success": False, "error": "用户名或密码错误"}
    session_token = generate_token()
    sessions[session_token] = {
        "username": request.username,
        "created_at": time.time()
    }
    logger.info(f"User logged in: {request.username}")
    save_all_data()
    return {
        "success": True,
        "session_token": session_token,
        "username": request.username,
        "stats": user["stats"],
        "loadout": user.get("loadout", {"weapon_slots": ["single", "shotgun", "missile", "wall"], "perks": []})
    }


@app.get("/api/user/{session_token}")
async def get_user_info_by_path(session_token: str):
    try:
        username = get_user_by_session(session_token)
        if not username:
            return {"success": False, "error": "Invalid or expired session"}
        user = users_db.get(username)
        if not user:
            return {"success": False, "error": "User not found"}
        return {
            "success": True,
            "username": username,
            "email": user["email"],
            "stats": user["stats"],
            "loadout": user.get("loadout", {"weapon_slots": ["single","shotgun","missile","wall"], "perks": []}),
            "current_room": user_rooms.get(username),
            "created_at": user.get("created_at", time.time()),
            "last_login": user.get("last_login", time.time())
        }
    except Exception as e:
        logger.error(f"Get user info error: {e}")
        return {"success": False, "error": "Server error"}


@app.post("/api/rooms/create")
async def create_room(request: CreateRoomRequest, session_token: str = Query(..., description="用户会话令牌")):
    username = await verify_session(session_token)
    if username in user_rooms:
        return {"success": False, "error": "你已经在一个房间中"}
    room_id = generate_token()[:8]
    room = Room(
        room_id=room_id,
        name=request.room_name,
        creator=username,
        max_players=request.max_players,
        password=request.password
    )
    rooms[room_id] = room
    user_rooms[username] = room_id
    room.add_player(username, None)
    logger.info(f"Room created: {room_id} by {username}")
    save_all_data()
    return {
        "success": True,
        "room_id": room_id,
        "room": {
            "id": room_id,
            "name": room.name,
            "creator": room.creator,
            "player_count": len(room.players),
            "max_players": room.max_players,
            "has_password": bool(room.password)
        }
    }


@app.get("/api/rooms")
async def get_rooms():
    room_list = []
    for room in rooms.values():
        room_list.append({
            "id": room.room_id,
            "name": room.name,
            "creator": room.creator,
            "player_count": len(room.players),
            "max_players": room.max_players,
            "has_password": bool(room.password),
            "created_at": room.created_at
        })
    room_list.sort(key=lambda x: x["created_at"], reverse=True)
    return {"rooms": room_list}


@app.post("/api/rooms/{room_id}/join")
async def join_room_by_path(room_id: str, request: JoinRoomRequest, session_token: str = Query(..., description="用户会话令牌")):
    username = await verify_session(session_token)
    room = rooms.get(room_id)
    if not room:
        return {"success": False, "error": "房间不存在"}
    if len(room.players) >= room.max_players:
        return {"success": False, "error": "房间已满"}
    if room.password and room.password != request.password:
        return {"success": False, "error": "房间密码错误"}
    user_rooms[username] = room_id
    logger.info(f"User {username} joined room {room_id}")
    save_all_data()
    return {
        "success": True,
        "room_id": room_id,
        "username": username
    }


@app.post("/api/rooms/leave")
async def leave_room(session_token: str = Query(..., description="用户会话令牌")):
    username = await verify_session(session_token)
    room_id = user_rooms.get(username)
    if not room_id:
        return {"success": False, "error": "你不在任何房间中"}
    room = rooms.get(room_id)
    if room:
        room.remove_player(username)
        if not room.players:
            rooms.pop(room_id, None)
            logger.info(f"Room {room_id} deleted (empty)")
    user_rooms.pop(username, None)
    save_all_data()
    logger.info(f"User {username} left room {room_id}")
    return {"success": True}


@app.get("/api/leaderboard")
async def get_leaderboard():
    leaderboard = []
    for username, user_data in users_db.items():
        stats = user_data["stats"]
        leaderboard.append({
            "username": username,
            "kills": stats["kills"],
            "deaths": stats["deaths"],
            "wins": stats["wins"],
            "games_played": stats["games_played"],
            "kd_ratio": round(stats["kills"] / max(stats["deaths"], 1), 2),
            "win_rate": round(stats["wins"] / max(stats["games_played"], 1) * 100, 1)
        })
    leaderboard.sort(key=lambda x: x["kills"], reverse=True)
    return {"success": True, "leaderboard": leaderboard[:50]}


@app.get("/api/online-players")
async def get_online_players():
    online_players = []
    current_time = time.time()
    for session_token, session in sessions.items():
        if current_time - session["created_at"] < 300:
            username = session["username"]
            user_data = users_db.get(username, {})
            online_players.append({
                "username": username,
                "in_game": username in user_rooms,
                "stats": user_data.get("stats", {
                    "games_played": 0,
                    "wins": 0,
                    "kills": 0,
                    "deaths": 0,
                    "total_damage": 0
                })
            })
    return {
        "success": True,
        "online_players": online_players,
        "count": len(online_players)}


@app.post("/api/admin/clear-database")
async def clear_database(request: AdminRequest):
    if request.admin_password != "admin123":
        raise HTTPException(status_code=403, detail="管理员密码错误")
    global users_db, sessions, rooms, user_rooms
    stats_before = {
        "users": len(users_db),
        "sessions": len(sessions),
        "rooms": len(rooms),
        "user_rooms": len(user_rooms),
        "total_players": sum(len(room.players) for room in rooms.values())
    }
    for room in rooms.values():
        for ws in list(room.connections.values()):
            try:
                await ws.close(code=4200, reason="Database clearing")
            except BaseException:
                pass
    users_db.clear()
    sessions.clear()
    rooms.clear()
    user_rooms.clear()
    save_all_data()
    logger.info(f"Database cleared - Stats before: {stats_before}")
    return {
        "success": True,
        "message": f"数据库已清空",
        "cleared": stats_before
    }


@app.post("/api/admin/stats")
async def get_database_stats(request: AdminRequest):
    if request.admin_password != "admin123":
        raise HTTPException(status_code=403, detail="管理员密码错误")
    return {"success": True,
            "users_count": len(users_db),
            "active_sessions": len(sessions),
            "active_rooms": len(rooms),
            "users_in_rooms": len(user_rooms),
            "total_players_online": sum(len(room.players) for room in rooms.values()),
            "room_details": [{"id": room.room_id,
                              "name": room.name,
                              "players": len(room.players),
                              "creator": room.creator} for room in rooms.values()]}


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, session_token: str = Query(...)):
    try:
        username = get_user_by_session(session_token)
        if not username:
            await websocket.close(code=4001)
            return
        if user_rooms.get(username) != room_id:
            await websocket.close(code=4002)
            return
        room = rooms.get(room_id)
        if not room:
            await websocket.close(code=4003)
            return
        await websocket.accept()
        if not room.add_player(username, websocket):
            await websocket.close(code=4004)
            return
        logger.info(f"Player {username} connected to room {room_id}")
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                except BaseException:
                    continue

                if msg.get("type") == "move":
                    dx, dy = msg.get("dx", 0), msg.get("dy", 0)
                    if username in room.players:
                        room.players[username]["target_dx"] = dx
                        room.players[username]["target_dy"] = dy

                elif msg.get("type") == "graffiti":
                    # 涂鸦：只保留该玩家最新涂鸦
                    if username in room.players:
                        x = int(msg.get("x", 0))
                        y = int(msg.get("y", 0))
                        room.graffiti[username] = {"x": x, "y": y}

                elif msg.get("type") == "smoke_grenade":
                    # 新增：烟雾弹
                    if username in room.players:
                        x = int(msg.get("x", 0))
                        y = int(msg.get("y", 0))
                        player = room.players[username]
                        radius = int(msg.get("radius", 120))
                        duration = float(msg.get("duration", 8))
                        room.smokes.append({
                            "x": x,
                            "y": y,
                            "radius": radius,
                            "owner": username,
                            "created_at": time.time(),
                            "duration": duration
                        })
                        player["last_hit"] = time.time()

                elif msg.get("type") == "build_wall":
                    if username in room.players:
                        x = int(msg.get("x", 0))
                        y = int(msg.get("y", 0))
                        player = room.players[username]
                        px, py = player["x"], player["y"]
                        dx = x - px
                        dy = y - py
                        angle = abs(math.atan2(dy, dx))
                        block_size = 32
                        wall_blocks = []

                        if angle < math.pi / 4 or angle > 3 * math.pi / 4:
                            # 竖墙
                            for i in range(-4, 4):
                                wall_blocks.append(
                                    {"x": x, "y": y + i * block_size})
                        else:
                            # 横墙
                            for i in range(-4, 4):
                                wall_blocks.append(
                                    {"x": x + i * block_size, "y": y})

                        room.walls.append({
                            "x": x, "y": y,
                            "owner": username,
                            "blocks": wall_blocks,
                            "created_at": time.time()
                        })
                        player["last_hit"] = time.time()

                elif msg.get("type") == "summon_turret":
                    if username in room.players:
                        x = int(msg.get("x", 0))
                        y = int(msg.get("y", 0))
                        room.turrets.append({
                            "x": x,
                            "y": y,
                            "hp": cfg.TURRET_INITIAL_HP,
                            "owner": username,
                            "created_at": time.time(),
                            "last_fire": 0.0
                        })
                        room.players[username]["last_hit"] = time.time()

                elif msg.get("type") == "place_cross_bomb":
                    if username in room.players:
                        player = room.players[username]
                        px, py = player["x"], player["y"]
                        tx = float(msg.get("x", px))
                        ty = float(msg.get("y", py))
                        dx = tx - px
                        dy = ty - py
                        dist = math.hypot(dx, dy)
                        if dist > 0:
                            max_dist = cfg.CROSS_BOMB_PLACE_DISTANCE
                            if max_dist > 0 and dist > max_dist:
                                ratio = max_dist / dist
                                tx = px + dx * ratio
                                ty = py + dy * ratio
                        else:
                            # 避免零向量导致角度异常，稍微偏移
                            dx, dy = 1.0, 0.0
                            tx = px + 1
                            ty = py
                        final_x = max(20, min(MAP_WIDTH - 20, tx))
                        final_y = max(20, min(MAP_HEIGHT - 20, ty))
                        angle = math.atan2(final_y - py, final_x - px)
                        dirx = math.cos(angle)
                        diry = math.sin(angle)
                        now_ts = time.time()
                        bomb = {
                            "id": str(uuid.uuid4())[:8],
                            "x": int(final_x),
                            "y": int(final_y),
                            "owner": username,
                            "angle": angle,
                            "dirx": dirx,
                            "diry": diry,
                            "planted_at": now_ts,
                            "explode_at": now_ts + cfg.CROSS_BOMB_FUSE_SEC,
                            "state": "armed"
                        }
                        # 限制同时存在的十字炸弹数量
                        active_bombs = [b for b in room.cross_bombs if b.get("owner") == username and b.get("state") != "detonating"]
                        if cfg.CROSS_BOMB_MAX_ACTIVE_PER_PLAYER > 0 and len(active_bombs) >= cfg.CROSS_BOMB_MAX_ACTIVE_PER_PLAYER:
                            oldest = min(active_bombs, key=lambda b: b.get("planted_at", 0))
                            try:
                                room.cross_bombs.remove(oldest)
                            except ValueError:
                                pass
                        room.cross_bombs.append(bomb)
                        player["last_hit"] = now_ts

                elif msg.get("type") == "iaido":
                    # 居合：向指定方向突进并对路径造成伤害
                    if username in room.players:
                        p = room.players[username]
                        now_ts = time.time()

                        dirx = float(msg.get("dirx", 0))
                        diry = float(msg.get("diry", 0))
                        dist = float(msg.get("distance", cfg.IAIDO_DISTANCE))
                        # 伤害服务端兜底与上限
                        try:
                            damage = int(msg.get("damage", cfg.IAIDO_DAMAGE))
                        except Exception:
                            damage = cfg.IAIDO_DAMAGE
                        damage = max(0, min(damage, cfg.IAIDO_DAMAGE))
                        # 方向归一化
                        norm = (dirx * dirx + diry * diry) ** 0.5 or 1.0
                        dirx /= norm
                        diry /= norm
                        sx, sy = p["x"], p["y"]
                        ex = sx + dirx * min(cfg.IAIDO_DISTANCE, max(0.0, dist))
                        ey = sy + diry * min(cfg.IAIDO_DISTANCE, max(0.0, dist))
                        # 限制在地图范围内
                        ex = max(20, min(MAP_WIDTH - 20, int(ex)))
                        ey = max(20, min(MAP_HEIGHT - 20, int(ey)))
                        # 居合穿墙：路径上的墙体方块将被破坏
                        tx, ty = ex, ey
                        # 记录需要移除的墙体方块
                        to_remove = []  # (wall_idx, block_idx)
                        thresh = (cfg.WALL_BLOCK_SIZE / 2.0) + cfg.IAIDO_WIDTH
                        for w_idx, wall in enumerate(room.walls):
                            for b_idx, block in enumerate(wall["blocks"]):
                                bx, by = block["x"], block["y"]
                                dseg = _dist_point_to_segment(bx, by, sx, sy, tx, ty)
                                if dseg <= thresh:
                                    to_remove.append((w_idx, b_idx))
                        if to_remove:
                            # 按墙分组并逆序删除
                            from collections import defaultdict
                            m = defaultdict(list)
                            for wi, bi in to_remove:
                                m[wi].append(bi)
                            for wi, bis in m.items():
                                wall = room.walls[wi]
                                for bi in sorted(bis, reverse=True):
                                    if 0 <= bi < len(wall["blocks"]):
                                        wall["blocks"].pop(bi)
                            # 移除空墙
                            room.walls = [w for w in room.walls if w["blocks"]]
                        # 设置服务端位移动画状态（按速度插值），位置由 game_loop 推进
                        dash_dist = math.hypot(tx - sx, ty - sy) or 1
                        dash_duration = dash_dist / max(1.0, cfg.IAIDO_SPEED)
                        p["iaido_dash"] = {
                            "sx": sx, "sy": sy,
                            "ex": tx, "ey": ty,
                            "start": now_ts,
                            "duration": dash_duration
                        }
                        p["last_iaido"] = now_ts
                        p["last_hit"] = now_ts
                        # 对路径上的敌人造成伤害（线段-圆距离）
                        for uname, other in room.players.items():
                            if uname == username:
                                continue
                            if other["hp"] <= 0:
                                continue
                            # 线段 sx,sy -> tx,ty 与 点 other 的最近距离
                            d = _dist_point_to_segment(other["x"], other["y"], sx, sy, tx, ty)
                            if d <= cfg.IAIDO_WIDTH:
                                other["hp"] -= damage
                                other["last_hit"] = now_ts
                                if other["hp"] <= 0:
                                    other["hp"] = 0
                                    p["kills"] += 1
                                    other["deaths"] += 1
                        # 对路径上的敌方炮台造成伤害
                        turret_indices_to_remove = set()
                        for i, t in enumerate(room.turrets):
                            if t.get("owner") == username:
                                continue
                            if t.get("hp", 0) <= 0:
                                continue
                            d = _dist_point_to_segment(t["x"], t["y"], sx, sy, tx, ty)
                            if d <= cfg.IAIDO_WIDTH:
                                t["hp"] = max(0, t.get("hp", 0) - damage)
                                if t["hp"] <= 0:
                                    turret_indices_to_remove.add(i)
                        if turret_indices_to_remove:
                            room.turrets = [t for j, t in enumerate(room.turrets) if j not in turret_indices_to_remove]

                elif msg.get("type") == "shoot":
                    if username in room.players:
                        player = room.players[username]
                        dx = msg.get("dx", player["dx"] or 10)
                        dy = msg.get("dy", player["dy"] or 0)
                        max_dist = msg.get("max_dist", 800)
                        damage = msg.get("damage", 300)
                        room.bullets.append({
                            "x": player["x"], "y": player["y"],
                            "dx": dx, "dy": dy,
                            "owner": username,
                            "hit_set": [],
                            "start_x": player["x"], "start_y": player["y"],
                            "max_dist": max_dist,
                            "damage": damage,
                            "created_at": time.time(),
                            "type": "normal"
                        })
                        player["last_hit"] = time.time()

                elif msg.get("type") == "shoot_missile":
                    if username in room.players:
                        player = room.players[username]
                        dx = msg.get("dx", 0)
                        dy = msg.get("dy", 0)
                        max_dist = msg.get("max_dist", 900)
                        damage = msg.get("damage", 600)
                        room.bullets.append({
                            "x": player["x"], "y": player["y"],
                            "dx": dx, "dy": dy,
                            "owner": username,
                            "hit_set": [],
                            "start_x": player["x"], "start_y": player["y"],
                            "max_dist": max_dist,
                            "damage": damage,
                            "created_at": time.time(),
                            "type": "missile",
                            "target": None,
                            "exploded": False
                        })
                        player["last_hit"] = time.time()

                elif msg.get("type") == "respawn":
                    if username in room.players and room.players[username]["hp"] <= 0:
                        room.players[username].update({
                            "x": random.randint(100, MAP_WIDTH - 100),
                            "y": random.randint(100, MAP_HEIGHT - 100),
                            "hp": cfg.PLAYER_MAX_HP,
                            "last_hit": time.time()
                        })

        except WebSocketDisconnect:
            pass
        finally:
            if username in room.players:
                player_data = room.players[username]
                if username in users_db:
                    user_stats = users_db[username]["stats"]
                    user_stats["games_played"] += 1
                    user_stats["kills"] += player_data["kills"]
                    user_stats["deaths"] += player_data["deaths"]
                    if len(room.players) <= 1 or player_data["kills"] > 0:
                        user_stats["wins"] += 1
            room.remove_player(username)
            logger.info(f"Player {username} disconnected from room {room_id}")
            if not room.players:
                rooms.pop(room_id, None)
                logger.info(f"Room {room_id} deleted (empty)")
            user_rooms.pop(username, None)
            save_all_data()
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    await websocket.close(code=4500)


async def game_loop():
    while True:
        try:
            now = time.time()
            for room in list(rooms.values()):
                if not room.players:
                    continue
                # 移除过期墙体
                now = time.time()
                room.walls = [
                    w for w in room.walls if now -
                    w.get(
                        "created_at",
                        now) < cfg.WALL_LIFETIME_SEC]

                # 更新并移除过期的烟雾弹
                updated_smokes = []
                for s in room.smokes:
                    elapsed = now - s.get("created_at", now)
                    if elapsed < s.get("duration", 8):
                        appear_duration = cfg.SMOKE_APPEAR_ANIM_SEC
                        progress = min(elapsed / appear_duration, 1.0)
                        max_radius = s.get("radius", cfg.SMOKE_DEFAULT_RADIUS)
                        s["current_radius"] = max_radius * progress
                        updated_smokes.append(s)
                room.smokes = updated_smokes

                # 十字炸弹：处理引爆与持续时间
                armed_bombs = []
                detonating_bombs = []
                trigger_queue = []
                for bomb in room.cross_bombs:
                    state = bomb.get("state", "armed")
                    if state == "armed":
                        if now >= bomb.get("explode_at", now):
                            trigger_queue.append(bomb)
                        else:
                            armed_bombs.append(bomb)
                    elif state == "detonating":
                        det_time = bomb.get("detonate_time", now)
                        if now - det_time <= cfg.CROSS_BOMB_EXPLOSION_DURATION:
                            detonating_bombs.append(bomb)
                processed_ids = set()
                while trigger_queue:
                    bomb = trigger_queue.pop(0)
                    bomb_id = bomb.get("id")
                    if bomb_id in processed_ids:
                        continue
                    processed_ids.add(bomb_id)
                    bomb["state"] = "detonating"
                    bomb["detonate_time"] = now
                    apply_cross_bomb_damage(room, bomb, now)
                    # 连锁引爆同一玩家的其他炸弹
                    owner = bomb.get("owner")
                    remaining = []
                    for other in armed_bombs:
                        if other.get("owner") == owner and point_in_cross_area(bomb, other.get("x", 0), other.get("y", 0)):
                            other["state"] = "detonating"
                            other["detonate_time"] = now
                            trigger_queue.append(other)
                        else:
                            remaining.append(other)
                    armed_bombs = remaining
                    detonating_bombs.append(bomb)
                room.cross_bombs = armed_bombs + detonating_bombs

                for player in room.players.values():
                    # 居合位移插值（优先于普通移动输入）
                    dash = player.get("iaido_dash")
                    if dash:
                        t = (now - dash.get("start", now)) / max(1e-6, dash.get("duration", 0.001))
                        if t >= 1:
                            player["x"] = dash.get("ex", player["x"]) 
                            player["y"] = dash.get("ey", player["y"]) 
                            player.pop("iaido_dash", None)
                        else:
                            player["x"] = dash["sx"] + (dash["ex"] - dash["sx"]) * t
                            player["y"] = dash["sy"] + (dash["ey"] - dash["sy"]) * t
                            # 本tick直接跳过普通输入移动与墙体阻挡评估
                            continue
                    inertia = 0.85  # 惯性阻尼系数，越接近1越滑
                    target_dx = player.get("target_dx", 0)
                    target_dy = player.get("target_dy", 0)
                    player["dx"] = player.get(
                        "dx", 0) * inertia + target_dx * (1 - inertia)
                    player["dy"] = player.get(
                        "dy", 0) * inertia + target_dy * (1 - inertia)
                    # 速度很小时直接归零，防止无限滑动
                    if abs(player["dx"]) < 0.1:
                        player["dx"] = 0
                    if abs(player["dy"]) < 0.1:
                        player["dy"] = 0
                    # 分别判断x和y方向移动，允许沿墙滑动
                    next_x = max(
                        20, min(
                            MAP_WIDTH - 20, player["x"] + player["dx"]))
                    next_y = max(
                        20, min(
                            MAP_HEIGHT - 20, player["y"] + player["dy"]))
                    # 判断x方向
                    blocked_x = False
                    for wall in room.walls:
                        for block in wall["blocks"]:
                            bx, by = block["x"], block["y"]
                            block_size = 32
                            # 玩家与墙体方块碰撞判定，半径约为 32
                            if circle_aabb_overlap(next_x, player["y"], 32, bx, by, block_size / 2):
                                blocked_x = True
                                break
                        if blocked_x:
                            break
                    # 判断y方向
                    blocked_y = False
                    for wall in room.walls:
                        for block in wall["blocks"]:
                            bx, by = block["x"], block["y"]
                            block_size = 32
                            if circle_aabb_overlap(player["x"], next_y, 32, bx, by, block_size / 2):
                                blocked_y = True
                                break
                        if blocked_y:
                            break
                    # 分别更新
                    if not blocked_x:
                        player["x"] = next_x
                    if not blocked_y:
                        player["y"] = next_y
                new_bullets = []
                bullets_to_remove = set()
                wall_blocks_to_remove = []  # (wall_idx, block_idx)
                for idx, bullet in enumerate(room.bullets):
                    # 新增：墙体与子弹碰撞检测
                    for w_idx, wall in enumerate(room.walls):
                        for b_idx, block in enumerate(wall["blocks"]):
                            bx, by = block["x"], block["y"]
                            if distance(bullet["x"], bullet["y"], bx, by) < 20:
                                wall_blocks_to_remove.append((w_idx, b_idx))
                                bullets_to_remove.add(idx)
                    # 导弹自动追踪（初始方向由玩家指定，飞行过程中逐步调整）
                    if bullet.get("type") == "missile" and not bullet.get(
                            "exploded", False):
                        # 只追踪固定范围内最近的敌人
                        min_dist = None
                        target_name = None
                        for uname, p in room.players.items():
                            if uname != bullet["owner"] and p["hp"] > 0:
                                d = distance(p["x"], p["y"], bullet["x"], bullet["y"])
                                if d <= cfg.MISSILE_TRACK_RANGE:
                                    if min_dist is None or d < min_dist:
                                        min_dist = d
                                        target_name = uname
                        bullet["target"] = target_name
                        # 追踪目标，微调方向（而不是瞬间锁定）
                        if target_name:
                            tx = room.players[target_name]["x"]
                            ty = room.players[target_name]["y"]
                            dx = tx - bullet["x"]
                            dy = ty - bullet["y"]
                            dist_to_target = math.hypot(dx, dy)
                            if dist_to_target > 0:
                                # 当前速度
                                speed = math.hypot(bullet["dx"], bullet["dy"]) or 12
                                # 当前方向归一化
                                cur_dir_x = bullet["dx"] / speed
                                cur_dir_y = bullet["dy"] / speed
                                # 目标方向归一化
                                tgt_dir_x = dx / dist_to_target
                                tgt_dir_y = dy / dist_to_target
                                # 线性插值微调方向（越大转向越快）
                                alpha = 0.04
                                new_dir_x = (
                                    1 - alpha) * cur_dir_x + alpha * tgt_dir_x
                                new_dir_y = (
                                    1 - alpha) * cur_dir_y + alpha * tgt_dir_y
                                norm = math.hypot(new_dir_x, new_dir_y) or 1
                                bullet["dx"] = new_dir_x / norm * speed
                                bullet["dy"] = new_dir_y / norm * speed

                    bullet["x"] += bullet["dx"]
                    bullet["y"] += bullet["dy"]
                    dist = distance(bullet["x"], bullet["y"], bullet["start_x"], bullet["start_y"])
                    if (
                        0 < bullet["x"] < MAP_WIDTH and 0 < bullet["y"] < MAP_HEIGHT and dist < bullet["max_dist"] and now -
                        bullet["created_at"] < cfg.BULLET_MAX_LIFETIME_SEC and not bullet.get(
                            "exploded",
                            False)):
                        new_bullets.append(bullet)
                room.bullets = new_bullets

                # 炮台逻辑
                updated_turrets = []
                for t in room.turrets:
                    # 炮台每秒掉血10点
                    last_decay = t.get("last_decay", t.get("created_at", now))
                    elapsed = max(0.0, now - last_decay)
                    if elapsed > 0:
                        t["hp"] = max(0, t.get("hp", 0) - cfg.TURRET_SELF_DECAY_PER_SEC * elapsed)
                        t["last_decay"] = now

                    if t.get("hp", 0) <= 0:
                        continue
                    tx, ty = t["x"], t["y"]
                    min_d = None
                    target_pos = None  # (px, py)
                    # 先考虑敌方玩家
                    for uname, p in room.players.items():
                        if uname == t.get("owner") or p["hp"] <= 0:
                            continue
                        d = ((p["x"] - tx) ** 2 + (p["y"] - ty) ** 2) ** 0.5
                        if d <= cfg.TURRET_RANGE and (min_d is None or d < min_d):
                            min_d = d
                            target_pos = (p["x"], p["y"])
                    # 再考虑敌方炮台
                    for other in room.turrets:
                        if other is t:
                            continue
                        if other.get("owner") == t.get("owner"):
                            continue
                        if other.get("hp", 0) <= 0:
                            continue
                        d = ((other["x"] - tx) ** 2 +
                             (other["y"] - ty) ** 2) ** 0.5
                        if d <= cfg.TURRET_RANGE and (min_d is None or d < min_d):
                            min_d = d
                            target_pos = (other["x"], other["y"])
                    # 冷却后发射
                    if target_pos and now - t.get("last_fire", 0) >= cfg.TURRET_CD:
                        px, py = target_pos
                        dx = px - tx
                        dy = py - ty
                        dist_to_target = (dx ** 2 + dy ** 2) ** 0.5 or 1
                        vx = dx / dist_to_target * cfg.TURRET_BULLET_SPEED
                        vy = dy / dist_to_target * cfg.TURRET_BULLET_SPEED
                        room.bullets.append({
                            "x": tx, "y": ty,
                            "dx": vx, "dy": vy,
                            "owner": t.get("owner"),
                            "hit_set": [],
                            "start_x": tx, "start_y": ty,
                            "max_dist": cfg.TURRET_MAX_DIST,
                            "damage": cfg.TURRET_BULLET_DAMAGE,
                            "created_at": time.time(),
                            "type": "turret"
                        })
                        t["last_fire"] = now
                    updated_turrets.append(t)
                room.turrets = updated_turrets

                # 子弹对玩家伤害判定
                dead_players = set()
                for username, player in room.players.items():
                    for idx, bullet in enumerate(room.bullets):
                        if player["hp"] <= 0 or username in dead_players:
                            continue
                        if (bullet["owner"] != username and
                                username not in bullet.get("hit_set", [])):
                            dist = distance(player["x"], player["y"], bullet["x"], bullet["y"]) 
                            hit_radius = cfg.MISSTLE_HIT_RADIUS if bullet.get(
                                "type") == "missile" else cfg.BULLET_HIT_RADIUS
                            if dist < hit_radius:
                                damage = bullet.get(
                                    "damage", cfg.BULLET_DEFAULT_DAMAGE)
                                player["hp"] -= damage
                                player["last_hit"] = now
                                bullet.setdefault(
                                    "hit_set", []).append(username)
                                if bullet["owner"] in users_db:
                                    users_db[bullet["owner"]
                                             ]["stats"]["total_damage"] += damage
                                # 仅首次降至<=0时累计死亡/击杀
                                if player["hp"] <= 0 and username not in dead_players:
                                    dead_players.add(username)
                                    player["deaths"] += 1
                                    if bullet["owner"] in room.players:
                                        room.players[bullet["owner"]
                                                     ]["kills"] += 1
                                bullets_to_remove.add(idx)

                # 子弹对炮台伤害判定
                turret_indices_to_remove = set()
                for t_idx, t in enumerate(room.turrets):
                    if t.get("hp", 0) <= 0:
                        turret_indices_to_remove.add(t_idx)
                        continue
                    tx, ty = t["x"], t["y"]
                    for idx, bullet in enumerate(room.bullets):
                        # 取消友伤
                        if bullet.get("owner") == t.get("owner"):
                            continue
                        dist = distance(tx, ty, bullet["x"], bullet["y"]) 
                        hit_radius = cfg.MISSTLE_HIT_RADIUS if bullet.get(
                            "type") == "missile" else cfg.BULLET_HIT_RADIUS
                        if dist < hit_radius:
                            t["hp"] = max(
                                0,
                                t.get(
                                    "hp",
                                    0) -
                                bullet.get(
                                    "damage",
                                    cfg.BULLET_DEFAULT_DAMAGE))
                            bullets_to_remove.add(idx)
                    if t.get("hp", 0) <= 0:
                        turret_indices_to_remove.add(t_idx)
                if turret_indices_to_remove:
                    room.turrets = [
                        t for i, t in enumerate(
                            room.turrets) if i not in turret_indices_to_remove]

                # 移除命中的子弹
                if bullets_to_remove:
                    room.bullets = [
                        b for i, b in enumerate(
                            room.bullets) if i not in bullets_to_remove]
                # 移除被击中的墙体方块
                if wall_blocks_to_remove:
                    # 按 wall_idx 分组
                    from collections import defaultdict
                    wall_remove_map = defaultdict(list)
                    for w_idx, b_idx in wall_blocks_to_remove:
                        wall_remove_map[w_idx].append(b_idx)
                    for w_idx, b_idxs in wall_remove_map.items():
                        wall = room.walls[w_idx]
                        # 按索引逆序删除，避免错位
                        for b_idx in sorted(b_idxs, reverse=True):
                            if 0 <= b_idx < len(wall["blocks"]):
                                wall["blocks"].pop(b_idx)
                    # 移除空墙体
                    room.walls = [w for w in room.walls if w["blocks"]]

                # 回血逻辑
                for player in room.players.values():
                    can_regen_when_dead = ("regen_when_dead" in player.get("perks", [])) and getattr(cfg, "ALLOW_REGEN_WHEN_DEAD", True)
                    can_regen = now - player["last_hit"] > cfg.REGEN_INTERVAL_SEC and player["hp"] < cfg.PLAYER_MAX_HP and (player["hp"] > 0 or can_regen_when_dead)
                    if can_regen:
                        amount = cfg.REGEN_AMOUNT_PER_TICK
                        if "regen_boost" in player.get("perks", []):
                            amount = amount * 10
                        player["hp"] += amount
                    if player["hp"] > cfg.PLAYER_MAX_HP:
                        player["hp"] = cfg.PLAYER_MAX_HP
                    if player["hp"] <= 0:
                        player["hp"] = 0

                # 给死亡玩家发送死亡消息
                for username in dead_players:
                    ws = room.connections.get(username)
                    if ws:
                        try:
                            await ws.send_text(json.dumps({"type": "death", "message": "你已死亡! 按R重生"}))
                        except BaseException:
                            pass
                if room.connections:
                    state = room.get_state()
                    message = json.dumps(state)
                    for ws in list(room.connections.values()):
                        try:
                            await ws.send_text(message)
                        except BaseException:
                            pass
            await asyncio.sleep(0.02)
        except Exception as e:
            logger.error(f"Game loop error: {e}")
            await asyncio.sleep(1)


# startup/shutdown 已通过 lifespan 处理


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "users_count": len(users_db),
        "active_sessions": len(sessions),
        "active_rooms": len(rooms),
        "total_players": sum(len(room.players) for room in rooms.values())
    }

# Mount static files (Frontend)
STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")

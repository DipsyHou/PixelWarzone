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
from typing import Optional, Dict, List
import logging
import os

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Battle Royale Game API")

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
DATA_DIR = "data"
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
    def __init__(self, room_id: str, name: str, creator: str, max_players: int = 8, password: str = None):
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
        self.walls = []  # 新增：墙体列表，每个墙体为 {x, y, owner, blocks: [{x, y}]}
        self.graffiti = {}  # 新增：涂鸦，{username: {x, y}}
        
    def add_player(self, username: str, websocket: WebSocket):
        if len(self.players) >= self.max_players:
            return False
            
        self.players[username] = {
            "x": random.randint(100, MAP_WIDTH-100),
            "y": random.randint(100, MAP_HEIGHT-100),
            "dx": 0,
            "dy": 0,
            "hp": 1000,
            "last_hit": time.time(),
            "kills": 0,
            "deaths": 0
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

MAP_WIDTH = 1920
MAP_HEIGHT = 1080

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

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token() -> str:
    return str(uuid.uuid4())

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
        raise HTTPException(status_code=401, detail="Invalid or expired session")
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
        "stats": user["stats"]
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
    return {"success": True, "online_players": online_players, "count": len(online_players)}

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
            except:
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
    return {
        "success": True,
        "users_count": len(users_db),
        "active_sessions": len(sessions),
        "active_rooms": len(rooms),
        "users_in_rooms": len(user_rooms),
        "total_players_online": sum(len(room.players) for room in rooms.values()),
        "room_details": [
            {
                "id": room.room_id,
                "name": room.name,
                "players": len(room.players),
                "creator": room.creator
            } for room in rooms.values()
        ]
    }

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
                except:
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

                        if angle < math.pi/4 or angle > 3 * math.pi/4:
                            # 竖墙
                            for i in range(-4, 4):
                                wall_blocks.append({"x": x, "y": y + i * block_size})
                        else:
                            # 横墙
                            for i in range(-4, 4):
                                wall_blocks.append({"x": x + i * block_size, "y": y})

                        room.walls.append({
                            "x": x, "y": y,
                            "owner": username,
                            "blocks": wall_blocks,
                            "created_at": time.time()
                        })


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
                            "x": random.randint(100, MAP_WIDTH-100),
                            "y": random.randint(100, MAP_HEIGHT-100),
                            "hp": 1000,
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
                # 移除过期墙体（存活10秒）
                now = time.time()
                room.walls = [w for w in room.walls if now - w.get("created_at", now) < 20]
                for player in room.players.values():
                    inertia = 0.85  # 惯性阻尼系数，越接近1越滑
                    target_dx = player.get("target_dx", 0)
                    target_dy = player.get("target_dy", 0)
                    player["dx"] = player.get("dx", 0) * inertia + target_dx * (1 - inertia)
                    player["dy"] = player.get("dy", 0) * inertia + target_dy * (1 - inertia)
                    # 速度很小时直接归零，防止无限滑动
                    if abs(player["dx"]) < 0.1:
                        player["dx"] = 0
                    if abs(player["dy"]) < 0.1:
                        player["dy"] = 0
                    # 分别判断x和y方向移动，允许沿墙滑动
                    next_x = max(20, min(MAP_WIDTH-20, player["x"] + player["dx"]))
                    next_y = max(20, min(MAP_HEIGHT-20, player["y"] + player["dy"]))
                    # 判断x方向
                    blocked_x = False
                    for wall in room.walls:
                        for block in wall["blocks"]:
                            bx, by = block["x"], block["y"]
                            block_size = 32
                            # 玩家与墙体方块碰撞判定，半径约为 32
                            closest_x = max(bx - block_size/2, min(next_x, bx + block_size/2))
                            closest_y = max(by - block_size/2, min(player["y"], by + block_size/2))
                            dist = ((next_x - closest_x) ** 2 + (player["y"] - closest_y) ** 2) ** 0.5
                            if dist < 32:
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
                            closest_x = max(bx - block_size/2, min(player["x"], bx + block_size/2))
                            closest_y = max(by - block_size/2, min(next_y, by + block_size/2))
                            dist = ((player["x"] - closest_x) ** 2 + (next_y - closest_y) ** 2) ** 0.5
                            if dist < 32:
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
                            dist = ((bullet["x"] - bx) ** 2 + (bullet["y"] - by) ** 2) ** 0.5
                            if dist < 20:
                                wall_blocks_to_remove.append((w_idx, b_idx))
                                bullets_to_remove.add(idx)
                    # 导弹自动追踪（初始方向由玩家指定，飞行过程中逐步调整）
                    if bullet.get("type") == "missile" and not bullet.get("exploded", False):
                        # 只追踪200像素范围内最近的敌人
                        min_dist = None
                        target_name = None
                        for uname, p in room.players.items():
                            if uname != bullet["owner"] and p["hp"] > 0:
                                d = ((p["x"] - bullet["x"]) ** 2 + (p["y"] - bullet["y"]) ** 2) ** 0.5
                                if d <= 500:
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
                            dist_to_target = (dx ** 2 + dy ** 2) ** 0.5
                            if dist_to_target > 0:
                                # 当前速度
                                speed = (bullet["dx"] ** 2 + bullet["dy"] ** 2) ** 0.5 or 12
                                # 当前方向归一化
                                cur_dir_x = bullet["dx"] / speed
                                cur_dir_y = bullet["dy"] / speed
                                # 目标方向归一化
                                tgt_dir_x = dx / dist_to_target
                                tgt_dir_y = dy / dist_to_target
                                # 线性插值微调方向（越大转向越快）
                                alpha = 0.04
                                new_dir_x = (1 - alpha) * cur_dir_x + alpha * tgt_dir_x
                                new_dir_y = (1 - alpha) * cur_dir_y + alpha * tgt_dir_y
                                norm = (new_dir_x ** 2 + new_dir_y ** 2) ** 0.5 or 1
                                bullet["dx"] = new_dir_x / norm * speed
                                bullet["dy"] = new_dir_y / norm * speed

                    bullet["x"] += bullet["dx"]
                    bullet["y"] += bullet["dy"]
                    dist = ((bullet["x"] - bullet["start_x"]) ** 2 + (bullet["y"] - bullet["start_y"]) ** 2) ** 0.5
                    if (0 < bullet["x"] < MAP_WIDTH and 
                        0 < bullet["y"] < MAP_HEIGHT and 
                        dist < bullet["max_dist"] and
                        now - bullet["created_at"] < 10 and not bullet.get("exploded", False)):
                        new_bullets.append(bullet)
                room.bullets = new_bullets
                dead_players = set()
                for username, player in room.players.items():
                    for idx, bullet in enumerate(room.bullets):
                        if bullet.get("type") == "missile" and not bullet.get("exploded", False):
                            # 导弹命中判定，爆炸范围 60
                            dist = ((player["x"] - bullet["x"]) ** 2 + (player["y"] - bullet["y"]) ** 2) ** 0.5
                            if bullet["owner"] != username and player["hp"] > 0 and dist < 60:
                                    # 只对第一个命中的敌人造成伤害
                                    damage = bullet.get("damage", 600)
                                    player["hp"] -= damage
                                    player["last_hit"] = now
                                    if bullet["owner"] in users_db:
                                        users_db[bullet["owner"]]["stats"]["total_damage"] += damage
                                    if player["hp"] <= 0:
                                        dead_players.add(username)
                                        player["deaths"] += 1
                                        if bullet["owner"] in room.players:
                                            room.players[bullet["owner"]]["kills"] += 1
                                        if bullet["owner"] in users_db:
                                            users_db[bullet["owner"]]["stats"]["kills"] += 1
                                    bullet["exploded"] = True
                                    bullets_to_remove.add(idx)
                        elif bullet.get("type") != "missile":
                            if (bullet["owner"] != username and 
                                username not in bullet.get("hit_set", [])):
                                dist = ((player["x"] - bullet["x"]) ** 2 + (player["y"] - bullet["y"]) ** 2) ** 0.5
                                if dist < 30:
                                    damage = bullet.get("damage", 300)
                                    player["hp"] -= damage
                                    player["last_hit"] = now
                                    bullet.setdefault("hit_set", []).append(username)
                                    if bullet["owner"] in users_db:
                                        users_db[bullet["owner"]]["stats"]["total_damage"] += damage
                                    if player["hp"] <= 0:
                                        dead_players.add(username)
                                        player["deaths"] += 1
                                        if bullet["owner"] in room.players:
                                            room.players[bullet["owner"]]["kills"] += 1
                                        if bullet["owner"] in users_db:
                                            users_db[bullet["owner"]]["stats"]["kills"] += 1
                                    bullets_to_remove.add(idx)
                # 移除命中的子弹
                if bullets_to_remove:
                    room.bullets = [b for i, b in enumerate(room.bullets) if i not in bullets_to_remove]
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
                for player in room.players.values():
                    if now - player["last_hit"] > 5 and player["hp"] < 1000:
                        player["hp"] += 10
                        if player["hp"] > 1000:
                            player["hp"] = 1000
                for username in dead_players:
                    ws = room.connections.get(username)
                    if ws:
                        try:
                            await ws.send_text(json.dumps({"type": "death", "message": "你已死亡！按R重生"}))
                        except:
                            pass
                if room.connections:
                    state = room.get_state()
                    message = json.dumps(state)
                    for ws in list(room.connections.values()):
                        try:
                            await ws.send_text(message)
                        except:
                            pass
            await asyncio.sleep(0.02)
        except Exception as e:
            logger.error(f"Game loop error: {e}")
            await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting game server...")
    asyncio.create_task(game_loop())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Saving all data before shutdown...")
    save_all_data()

@app.get("/")
async def root():
    return {"message": "Battle Royale Game Server", "status": "running"}

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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
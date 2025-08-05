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
from typing import Optional, Dict, List
import logging

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
    room_id: Optional[str] = None  # 对于路径参数版本，这个字段可选
    password: Optional[str] = None

class AdminRequest(BaseModel):
    admin_password: str

# 全局数据存储
users_db: Dict = {}  # {username: {password_hash, email, stats, created_at}}
sessions: Dict = {}  # {session_token: {username, created_at}}
rooms: Dict = {}  # {room_id: Room}
user_rooms: Dict = {}  # {username: room_id}

MAP_WIDTH = 1920
MAP_HEIGHT = 1080

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
        
        # 如果房间空了，标记为待删除
        if not self.players and self.game_running:
            self.game_running = False
            
    def get_state(self):
        # 增加 status 字段
        state_players = {}
        for username, player in self.players.items():
            player_copy = player.copy()
            player_copy["status"] = "dead" if player_copy["hp"] <= 0 else "alive"
            # 保证 hp 字段始终存在
            player_copy["hp"] = max(0, int(player_copy.get("hp", 0)))
            state_players[username] = player_copy
        return {
            "players": state_players,
            "bullets": self.bullets,
            "room_info": {
                "name": self.name,
                "player_count": len(self.players),
                "max_players": self.max_players
            }
        }

# 辅助函数
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token() -> str:
    return str(uuid.uuid4())

def get_user_by_session(session_token: str) -> Optional[str]:
    session = sessions.get(session_token)
    if session and time.time() - session["created_at"] < 86400:  # 24小时过期
        return session["username"]
    return None

async def verify_session(session_token: str = None) -> str:
    if not session_token:
        raise HTTPException(status_code=401, detail="Session token required")
    username = get_user_by_session(session_token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return username

# 认证API
@app.post("/api/register")
async def register(request: RegisterRequest):
    if request.username in users_db:
        return {"success": False, "error": "用户名已存在"}
    
    if len(request.username) > 16:
        return {"success": False, "error": "用户名过长"}
    
    # 创建用户
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
    
    # 创建会话
    session_token = generate_token()
    sessions[session_token] = {
        "username": request.username,
        "created_at": time.time()
    }
    
    logger.info(f"User registered: {request.username}")
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
    
    # 创建会话
    session_token = generate_token()
    sessions[session_token] = {
        "username": request.username,
        "created_at": time.time()
    }
    
    logger.info(f"User logged in: {request.username}")
    return {
        "success": True,
        "session_token": session_token,
        "username": request.username,
        "stats": user["stats"]
    }

@app.get("/api/user/{session_token}")
async def get_user_info_by_path(session_token: str):
    """通过路径参数获取用户信息 - 兼容前端调用"""
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

# 创建房间
@app.post("/api/rooms/create")
async def create_room(request: CreateRoomRequest, session_token: str = Query(..., description="用户会话令牌")):
    username = await verify_session(session_token)
    
    # 检查用户是否已在房间中
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

    # 自动把玩家加入房间（但不传websocket，先用None占位）
    room.add_player(username, None)

    logger.info(f"Room created: {room_id} by {username}")
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
    
    # 按创建时间排序
    room_list.sort(key=lambda x: x["created_at"], reverse=True)
    # 返回rooms数组
    return {"rooms": room_list}  

@app.post("/api/rooms/{room_id}/join")
async def join_room_by_path(room_id: str, request: JoinRoomRequest, session_token: str = Query(..., description="用户会话令牌")):
    """通过路径参数加入房间 - 匹配前端调用方式"""
    username = await verify_session(session_token)
    
    # 检查用户是否已在房间中
    # if username in user_rooms:
    #     return {"success": False, "error": "你已经在一个房间中"}
    
    room = rooms.get(room_id)
    if not room:
        return {"success": False, "error": "房间不存在"}
    
    if len(room.players) >= room.max_players:
        return {"success": False, "error": "房间已满"}
    
    if room.password and room.password != request.password:
        return {"success": False, "error": "房间密码错误"}
    
    user_rooms[username] = room_id
    
    logger.info(f"User {username} joined room {room_id}")
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
        
        # 如果房间空了，删除房间
        if not room.players:
            rooms.pop(room_id, None)
            logger.info(f"Room {room_id} deleted (empty)")
    
    user_rooms.pop(username, None)
    logger.info(f"User {username} left room {room_id}")
    return {"success": True}

@app.get("/api/leaderboard")
async def get_leaderboard():
    """获取排行榜"""
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
    
    # 按击杀数排序
    leaderboard.sort(key=lambda x: x["kills"], reverse=True)
    return {"success": True, "leaderboard": leaderboard[:50]}  # 前50名

@app.get("/api/online-players")
async def get_online_players():
    """获取在线玩家"""
    online_players = []
    current_time = time.time()
    
    for session_token, session in sessions.items():
        if current_time - session["created_at"] < 300:  # 5分钟内活跃
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

# 管理员API
@app.post("/api/admin/clear-database")
async def clear_database(request: AdminRequest):
    if request.admin_password != "admin123":  # 设置你的管理员密码
        raise HTTPException(status_code=403, detail="管理员密码错误")
    
    global users_db, sessions, rooms, user_rooms
    
    # 记录清空前的统计
    stats_before = {
        "users": len(users_db),
        "sessions": len(sessions),
        "rooms": len(rooms),
        "user_rooms": len(user_rooms),
        "total_players": sum(len(room.players) for room in rooms.values())
    }
    
    # 关闭所有WebSocket连接
    for room in rooms.values():
        for ws in list(room.connections.values()):
            try:
                await ws.close(code=4200, reason="Database clearing")
            except:
                pass
    
    # 清空所有数据
    users_db.clear()
    sessions.clear()
    rooms.clear()
    user_rooms.clear()
    
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

# WebSocket游戏逻辑
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, session_token: str = Query(...)):
    try:
        username = get_user_by_session(session_token)
        if not username:
            await websocket.close(code=4001, reason="Invalid session")
            return

        # 检查用户是否在该房间
        if user_rooms.get(username) != room_id:
            await websocket.close(code=4002, reason="Not in this room")
            return

        room = rooms.get(room_id)
        if not room:
            await websocket.close(code=4003, reason="Room not found")
            return

        await websocket.accept()

        # 添加玩家到房间
        if not room.add_player(username, websocket):
            await websocket.close(code=4004, reason="Room is full")
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
                        room.players[username]["dx"] = dx
                        room.players[username]["dy"] = dy

                elif msg.get("type") == "shoot":
                    if username in room.players:
                        player = room.players[username]
                        dx = msg.get("dx", player["dx"] or 10)
                        dy = msg.get("dy", player["dy"] or 0)
                        max_dist = msg.get("max_dist", 800)

                        room.bullets.append({
                            "x": player["x"], "y": player["y"],
                            "dx": dx, "dy": dy,
                            "owner": username,
                            "hit_set": [],
                            "start_x": player["x"], "start_y": player["y"],
                            "max_dist": max_dist,
                            "created_at": time.time()
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
            # 清理连接
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

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=4500, reason="Server error")

# 游戏主循环
async def game_loop():
    while True:
        try:
            now = time.time()
            
            for room in list(rooms.values()):
                if not room.players:
                    continue
                    
                # 移动玩家
                for player in room.players.values():
                    player["x"] = max(20, min(MAP_WIDTH-20, player["x"] + player["dx"]))
                    player["y"] = max(20, min(MAP_HEIGHT-20, player["y"] + player["dy"]))
                
                # 移动子弹
                new_bullets = []
                for bullet in room.bullets:
                    bullet["x"] += bullet["dx"]
                    bullet["y"] += bullet["dy"]
                    
                    # 检查子弹边界和距离
                    dist = ((bullet["x"] - bullet["start_x"]) ** 2 + (bullet["y"] - bullet["start_y"]) ** 2) ** 0.5
                    if (0 < bullet["x"] < MAP_WIDTH and 
                        0 < bullet["y"] < MAP_HEIGHT and 
                        dist < bullet["max_dist"] and
                        now - bullet["created_at"] < 10):  # 10秒后自动清除
                        new_bullets.append(bullet)
                
                room.bullets = new_bullets
                
                # 碰撞检测
                dead_players = set()
                for username, player in room.players.items():
                    for bullet in room.bullets:
                        if (bullet["owner"] != username and 
                            username not in bullet.get("hit_set", [])):
                            
                            dist = ((player["x"] - bullet["x"]) ** 2 + (player["y"] - bullet["y"]) ** 2) ** 0.5
                            if dist < 30:
                                player["hp"] -= 300
                                player["last_hit"] = now
                                bullet.setdefault("hit_set", []).append(username)
                                
                                # 更新伤害统计
                                if bullet["owner"] in users_db:
                                    users_db[bullet["owner"]]["stats"]["total_damage"] += 300
                                
                                if player["hp"] <= 0:
                                    dead_players.add(username)
                                    player["deaths"] += 1
                                    
                                    # 更新击杀统计
                                    if bullet["owner"] in room.players:
                                        room.players[bullet["owner"]]["kills"] += 1
                                    if bullet["owner"] in users_db:
                                        users_db[bullet["owner"]]["stats"]["kills"] += 1
                
                # 回血逻辑
                for player in room.players.values():
                    if now - player["last_hit"] > 5 and player["hp"] < 1000:
                        player["hp"] += 10  # 每帧回10血
                        if player["hp"] > 1000:
                            player["hp"] = 1000
                
                # 处理死亡玩家 - 不立即踢出，而是通知死亡
                for username in dead_players:
                    ws = room.connections.get(username)
                    if ws:
                        try:
                            await ws.send_text(json.dumps({"type": "death", "message": "你已死亡！按R重生"}))
                        except:
                            pass
                
                # 广播游戏状态
                if room.connections:
                    state = room.get_state()
                    message = json.dumps(state)
                    
                    for ws in list(room.connections.values()):
                        try:
                            await ws.send_text(message)
                        except:
                            pass
            
            await asyncio.sleep(0.02)  # 50 FPS
            
        except Exception as e:
            logger.error(f"Game loop error: {e}")
            await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting game server...")
    asyncio.create_task(game_loop())

@app.get("/")
async def root():
    return {"message": "Battle Royale Game Server", "status": "running"}

# 健康检查端点
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
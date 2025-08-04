from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
import random
import json
import time

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

players = {}  # {username: {"x":..., "y":..., "dx":..., "dy":..., "hp":..., "last_hit":...}}
bullets = []  # [{"x":..., "y":..., "dx":..., "dy":..., "owner":..., "hit_set": [...], "start_x":..., "start_y":..., "max_dist":...}]
connections = {}

MAP_WIDTH = 1920
MAP_HEIGHT = 1080

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()
    # 初始化玩家
    players[username] = {
        "x": random.randint(100, MAP_WIDTH-100),
        "y": random.randint(100, MAP_HEIGHT-100),
        "dx": 0,
        "dy": 0,
        "hp": 1000,
        "last_hit": time.time()
    }
    connections[username] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            msg = {}
            try:
                msg = eval(data)
            except:
                continue
            if msg.get("type") == "move":
                dx, dy = msg.get("dx", 0), msg.get("dy", 0)
                players[username]["dx"] = dx
                players[username]["dy"] = dy
            elif msg.get("type") == "shoot":
                px = players[username]["x"]
                py = players[username]["y"]
                dx = msg.get("dx", players[username]["dx"] or 10)
                dy = msg.get("dy", players[username]["dy"] or 0)
                max_dist = msg.get("max_dist", 800)
                bullets.append({
                    "x": px, "y": py,
                    "dx": dx, "dy": dy,
                    "owner": username,
                    "hit_set": [],
                    "start_x": px, "start_y": py,
                    "max_dist": max_dist
                })
                players[username]["last_hit"] = time.time()  # 发射子弹也刷新last_hit
    except WebSocketDisconnect:
        del players[username]
        del connections[username]

async def game_loop():
    while True:
        now = time.time()
        # 移动玩家
        for p in players.values():
            p["x"] = max(20, min(MAP_WIDTH-20, p["x"] + p["dx"]))
            p["y"] = max(20, min(MAP_HEIGHT-20, p["y"] + p["dy"]))
        # 移动子弹
        new_bullets = []
        for b in bullets:
            b["x"] += b["dx"]
            b["y"] += b["dy"]
            dist = ((b["x"] - b["start_x"]) ** 2 + (b["y"] - b["start_y"]) ** 2) ** 0.5
            if 0 < b["x"] < MAP_WIDTH and 0 < b["y"] < MAP_HEIGHT and dist < b["max_dist"]:
                new_bullets.append(b)
        bullets[:] = new_bullets

        # 碰撞检测：穿透+每颗子弹只伤害一次
        dead_players = set()
        for username, player in players.items():
            for b in bullets:
                if b["owner"] != username and username not in b.get("hit_set", []):
                    dist = ((player["x"] - b["x"]) ** 2 + (player["y"] - b["y"]) ** 2) ** 0.5
                    if dist < 30:
                        player["hp"] -= 300
                        player["last_hit"] = now
                        b.setdefault("hit_set", []).append(username)
                        if player["hp"] <= 0:
                            dead_players.add(username)

        # 回血逻辑（攻击后或发射后5秒内不能回血）
        for player in players.values():
            if now - player["last_hit"] > 5 and player["hp"] < 1000:
                player["hp"] += 1  # 每帧回10，约每秒回250
                if player["hp"] > 1000:
                    player["hp"] = 1000

        # 移除死亡玩家和连接
        for username in dead_players:
            players.pop(username, None)
            ws = connections.pop(username, None)
            if ws:
                try:
                    await ws.close()
                except:
                    pass

        # 广播状态
        state = {
            "players": players,
            "bullets": bullets
        }
        for ws in list(connections.values()):
            try:
                await ws.send_text(json.dumps(state))
            except:
                pass
        await asyncio.sleep(0.02)  # 50帧

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(game_loop())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
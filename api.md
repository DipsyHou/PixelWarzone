# PixelWarzone 后端 API 文档

## 用户相关

### 注册
**POST** `/api/register`

请求体：
```json
{
    "username": "string",
    "password": "string",
    "email": "string"
}
```
返回：
```json
{
    "success": true,
    "session_token": "string",
    "username": "string",
    "stats": { ... }
}
```

---

### 登录
**POST** `/api/login`

请求体：
```json
{
    "username": "string",
    "password": "string"
}
```
返回：
```json
{
    "success": true,
    "session_token": "string",
    "username": "string",
    "stats": { ... }
}
```

---

### 获取用户信息
**GET** `/api/user/{session_token}`

返回：
```json
{
    "success": true,
    "username": "string",
    "email": "string",
    "stats": { ... },
    "current_room": "string",
    "created_at": 1234567890,
    "last_login": 1234567890
}
```

---

## 房间相关

### 创建房间（自动加入）
**POST** `/api/rooms/create?session_token=xxx`

请求体：
```json
{
    "room_name": "string",
    "max_players": 8,
    "password": "string" // 可选
}
```
返回：
```json
{
    "success": true,
    "room_id": "string",
    "room": {
        "id": "string",
        "name": "string",
        "creator": "string",
        "player_count": 1,
        "max_players": 8,
        "has_password": true/false
    }
}
```

---

### 获取房间列表
**GET** `/api/rooms`

返回：
```json
{
    "rooms": [
        {
            "id": "string",
            "name": "string",
            "creator": "string",
            "player_count": 1,
            "max_players": 8,
            "has_password": true/false,
            "created_at": 1234567890
        }
    ]
}
```

---

### 加入房间
**POST** `/api/rooms/{room_id}/join?session_token=xxx`

请求体：
```json
{
    "password": "string" // 可选
}
```
返回：
```json
{
    "success": true,
    "room_id": "string",
    "username": "string"
}
```

---

### 离开房间
**POST** `/api/rooms/leave?session_token=xxx`

返回：
```json
{
    "success": true
}
```

---

## 游戏相关

### WebSocket 游戏连接
地址：`ws://<host>/ws/{room_id}?session_token=xxx`

说明：连接后即可实时收发游戏数据。

---

## 其它

### 获取排行榜
**GET** `/api/leaderboard`

返回：
```json
{
    "success": true,
    "leaderboard": [
        {
            "username": "string",
            "kills": 0,
            "deaths": 0,
            "wins": 0,
            "games_played": 0,
            "kd_ratio": 0.0,
            "win_rate": 0.0
        }
    ]
}
```

---

### 获取在线玩家
**GET** `/api/online-players`

返回：
```json
{
    "success": true,
    "online_players": [
        {
            "username": "string",
            "in_game": true/false,
            "stats": { ... }
        }
    ],
    "count": 1
}
```

---

### 健康检查
**GET** `/health`

返回：
```json
{
    "status": "healthy",
    "timestamp": 1234567890,
    "users_count": 1,
    "active_sessions": 1,
    "active_rooms": 1,
    "total_players": 1
}
```

---

## 管理员相关

### 清空数据库
**POST** `/api/admin/clear-database`

请求体：
```json
{
    "admin_password": "string"
}
```
返回：
```json
{
    "success": true,
    "message": "数据库已清空",
    "cleared": { ... }
}
```

---

### 获取数据库统计
**POST** `/api/admin/stats`

请求体：
```json
{
    "admin_password": "string"
}
```
返回：
```json
{
    "success": true,
    "users_count": 1,
    "active_sessions": 1,
    "active_rooms": 1,
    "users_in_rooms": 1,
    "total_players_online": 1,
    "room_details": [ ... ]
}
```
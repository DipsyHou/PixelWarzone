class WebSocketManager {
    constructor(auth, gameRenderer) {
        this.auth = auth;
        this.gameRenderer = gameRenderer;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
    }

    connect(roomId) {
        if (this.ws) {
            this.ws.close();
        }

        this.ws = new WebSocket(`ws://${CONFIG.BACKEND_URL}/ws/${roomId}?session_token=${this.auth.sessionToken}`);
        
        this.ws.onopen = () => {
            console.log(`WebSocket连接成功，房间：${roomId}`);
            this.reconnectAttempts = 0;
        };
        
        this.ws.onmessage = (event) => {
            const state = JSON.parse(event.data);
            this.gameRenderer.updateState(state);
        };
        
        this.ws.onerror = (e) => {
            console.error("WebSocket连接错误", e);
        };
        
        this.ws.onclose = (e) => {
            this.handleClose(e, roomId);
        };
    }

    handleClose(event, roomId) {
        if (event.code === 4001) {
            alert("登录已过期，请重新登录");
            this.auth.logout();
            window.ui.showLoginForm();
        } else if (event.code === 4004) {
            alert("房间不存在");
            window.ui.showRoomList();
        } else if (this.reconnectAttempts < this.maxReconnectAttempts) {
            console.log(`连接断开，${this.reconnectDelay/1000}秒后尝试重连...`);
            setTimeout(() => {
                this.reconnectAttempts++;
                this.connect(roomId);
            }, this.reconnectDelay);
        } else {
            alert("连接断开，无法重连，请刷新页面");
        }
    }

    sendMessage(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
            return true;
        }
        return false;
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.reconnectAttempts = 0;
    }

    move(dx, dy) {
        this.sendMessage({ type: "move", dx, dy });
    }

    shoot(dx, dy, maxDist = CONFIG.MAX_BULLET_DIST) {
        return this.sendMessage({ type: "shoot", dx, dy, max_dist: maxDist });
    }

    respawn() {
        this.sendMessage({ type: "respawn" });
    }
}

window.WebSocketManager = WebSocketManager;
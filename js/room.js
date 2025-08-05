class RoomManager {
    constructor(auth) {
        this.auth = auth;
        this.currentRoom = null;
        this.refreshInterval = null;
    }

    async getRooms() {
        try {
            const response = await fetch(`http://${CONFIG.BACKEND_URL}/api/rooms`);
            const data = await response.json();
            return data.rooms || [];
        } catch (error) {
            console.error('获取房间列表失败:', error);
            return [];
        }
    }

    async createRoom(roomName, maxPlayers = 8, password = '') {
        try {
            const response = await fetch(`http://${CONFIG.BACKEND_URL}/api/rooms/create?session_token=${this.auth.sessionToken}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    room_name: roomName,
                    max_players: maxPlayers,
                    password: password
                })
            });
            
            const data = await response.json();
            return data;
        } catch (error) {
            return { success: false, error: '网络错误：' + error.message };
        }
    }

    async joinRoom(roomId, password = '') {
        try {
            const response = await fetch(`http://${CONFIG.BACKEND_URL}/api/rooms/${roomId}/join?session_token=${this.auth.sessionToken}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });
            
            const data = await response.json();
            if (data.success) {
                this.currentRoom = roomId;
            }
            return data;
        } catch (error) {
            return { success: false, error: '网络错误：' + error.message };
        }
    }

    leaveRoom() {
        this.currentRoom = null;
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    startRoomListRefresh(callback, interval = 3000) {
        this.refreshInterval = setInterval(async () => {
            const rooms = await this.getRooms();
            callback(rooms);
        }, interval);
    }
}

window.RoomManager = RoomManager;
class UI {
    constructor(auth, roomManager) {
        this.auth = auth;
        this.roomManager = roomManager;
        this.templateCache = {};
    }

    async loadTemplate(path) {
        if (this.templateCache[path]) {
            return this.templateCache[path];
        }
        const response = await fetch(path);
        if (!response.ok) {
            throw new Error(`Failed to load template: ${path}`);
        }
        const text = await response.text();
        this.templateCache[path] = text;
        return text;
    }

    async showLoginForm() {
        const template = await this.loadTemplate('/res/ui/login.html');
        document.body.innerHTML = template;
    }

    showRegisterForm() {
        document.getElementById('loginForm').style.display = 'none';
        document.getElementById('registerForm').style.display = 'block';
    }

    async handleLogin() {
        const username = document.getElementById('loginUsername').value.trim();
        const password = document.getElementById('loginPassword').value;

        if (!username || !password) {
            alert('请填写用户名和密码');
            return;
        }

        const result = await this.auth.login(username, password);
        if (result.success) {
            this.showRoomList();
        } else {
            alert(result.error);
        }
    }

    async handleRegister() {
        const username = document.getElementById('regUsername').value.trim();
        const email = document.getElementById('regEmail').value.trim();
        const password = document.getElementById('regPassword').value;

        if (!username || !email || !password) {
            alert('请填写所有字段');
            return;
        }

        const result = await this.auth.register(username, password, email);
        if (result.success) {
            this.showRoomList();
        } else {
            alert(result.error);
        }
    }

    async showRoomList() {
        let template = await this.loadTemplate('/res/ui/room_list.html');
        
        // Simple template replacement
        template = template.replace('${this.auth.currentUser.username}', this.auth.currentUser.username);
        template = template.replace('${this.auth.currentUser.stats?.games_played || 0}', this.auth.currentUser.stats?.games_played || 0);
        template = template.replace('${this.auth.currentUser.stats?.wins || 0}', this.auth.currentUser.stats?.wins || 0);
        template = template.replace('${this.auth.currentUser.stats?.kills || 0}', this.auth.currentUser.stats?.kills || 0);
        template = template.replace('${this.auth.currentUser.stats?.deaths || 0}', this.auth.currentUser.stats?.deaths || 0);
        const kd = this.auth.currentUser.stats?.deaths > 0 ? (this.auth.currentUser.stats.kills / this.auth.currentUser.stats.deaths).toFixed(2) : (this.auth.currentUser.stats?.kills || 0);
        template = template.replace('${this.auth.currentUser.stats?.deaths > 0 ? (this.auth.currentUser.stats.kills / this.auth.currentUser.stats.deaths).toFixed(2) : (this.auth.currentUser.stats?.kills || 0)}', kd);

        document.body.innerHTML = template;

        await this.loadRoomList();
        this.roomManager.startRoomListRefresh((rooms) => this.updateRoomList(rooms));
    }

    async loadRoomList() {
        const rooms = await this.roomManager.getRooms();
        this.updateRoomList(rooms);
    }

    updateRoomList(rooms) {
        const roomListDiv = document.getElementById('roomList');
        if (!roomListDiv) return;

        if (rooms.length === 0) {
            roomListDiv.innerHTML = '<div style="text-align: center; color: #666;">暂无房间</div>';
        } else {
            roomListDiv.innerHTML = rooms.map(room => `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px; margin: 10px 0; background: #444; border-radius: 8px;">
                    <div>
                        <h3 style="margin: 0; color: #ff4444;">${room.name}</h3>
                        <p style="margin: 5px 0; color: #ccc;">玩家: ${room.players}/${room.max_players} | 状态: ${room.status === 'waiting' ? '等待中' : room.status === 'playing' ? '游戏中' : '已结束'}</p>
                        ${room.has_password ? '<span style="color: #ffaa00;">🔒 需要密码</span>' : ''}
                    </div>
                    <button onclick="window.ui.joinRoom('${room.id}', ${room.has_password})" 
                            style="padding: 8px 15px; background: #44ff44; color: white; border: none; border-radius: 5px; cursor: pointer;"
                            ${room.players >= room.max_players ? 'disabled' : ''}>
                        ${room.players >= room.max_players ? '房间已满' : '加入'}
                    </button>
                </div>
            `).join('');
        }
    }

    async joinRoom(roomId, hasPassword) {
        let password = '';
        if (hasPassword) {
            password = prompt('请输入房间密码:');
            if (password === null) return;
        }

        const result = await this.roomManager.joinRoom(roomId, password);
        if (result.success) {
            this.showGameCanvas();
            window.wsManager.connect(roomId);
        } else {
            alert(result.error);
        }
    }

    async showGameCanvas() {
        const template = await this.loadTemplate('/res/ui/game.html');
        document.body.innerHTML = template;

        const canvas = document.getElementById("gameCanvas");
        window.game.init(canvas, window.wsManager);
    }

    updateRoomInfo(roomInfo) {
        const roomNameSpan = document.getElementById('roomName');
        const playerCountSpan = document.getElementById('playerCount');
        if (roomNameSpan) roomNameSpan.textContent = roomInfo.name;
        if (playerCountSpan) playerCountSpan.textContent = `${roomInfo.players_count}/${roomInfo.max_players}`;
    }

    leaveRoom() {
        window.wsManager.disconnect();
        this.roomManager.leaveRoom();
        this.showRoomList();
    }

    logout() {
        this.auth.logout();
        this.showLoginForm();
    }

    async showCreateRoomForm() {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
            background: rgba(0,0,0,0.7); display: flex; justify-content: center; 
            align-items: center; z-index: 1000;
        `;

        modal.innerHTML = await this.loadTemplate('/res/ui/create_room.html');

        document.body.appendChild(modal);
        modal.onclick = (e) => {
            if (e.target === modal) this.closeModal();
        };

        this.currentModal = modal;
    }

    async createRoom() {
        const roomName = document.getElementById('roomName').value.trim();
        const maxPlayers = parseInt(document.getElementById('maxPlayers').value);
        const password = document.getElementById('roomPassword').value;

        if (!roomName) {
            alert('请输入房间名称');
            return;
        }

        const result = await this.roomManager.createRoom(roomName, maxPlayers, password);
        if (result.success) {
            this.closeModal();
            this.joinRoom(result.room_id, !!password);
        } else {
            alert(result.error);
        }
    }

    closeModal() {
        if (this.currentModal) {
            this.currentModal.remove();
            this.currentModal = null;
        }
    }
}

window.UI = UI;
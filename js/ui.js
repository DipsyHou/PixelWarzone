class UI {
    constructor(auth, roomManager) {
        this.auth = auth;
        this.roomManager = roomManager;
    }

    showLoginForm() {
        document.body.innerHTML = `
            <div style="display: flex; justify-content: center; align-items: center; min-height: 100vh; background: linear-gradient(120deg, #222244 60%, #444466 100%); font-family: Arial, sans-serif;">
                <div style="background: #333; padding: 40px; border-radius: 15px; box-shadow: 0 0 50px rgba(0,0,0,0.5); color: white; width: 400px;">
                    <h1 style="text-align: center; margin-bottom: 30px; color: #ff4444;">PixelWarzone</h1>
                    
                    <div id="loginForm">
                        <h2>登录</h2>
                        <input type="text" id="loginUsername" placeholder="用户名" style="width: 100%; padding: 15px; margin: 10px 0; border: none; border-radius: 5px; background: #555; color: white;">
                        <input type="password" id="loginPassword" placeholder="密码" style="width: 100%; padding: 15px; margin: 10px 0; border: none; border-radius: 5px; background: #555; color: white;">
                        <button onclick="window.ui.handleLogin()" style="width: 100%; padding: 15px; margin: 15px 0; background: #ff4444; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px;">登录</button>
                        <p style="text-align: center; margin: 20px 0;">没有账号？<a href="#" onclick="window.ui.showRegisterForm()" style="color: #ff4444;">注册</a></p>
                    </div>
                    
                    <div id="registerForm" style="display: none;">
                        <h2>注册</h2>
                        <input type="text" id="regUsername" placeholder="用户名" style="width: 100%; padding: 15px; margin: 10px 0; border: none; border-radius: 5px; background: #555; color: white;">
                        <input type="email" id="regEmail" placeholder="邮箱" style="width: 100%; padding: 15px; margin: 10px 0; border: none; border-radius: 5px; background: #555; color: white;">
                        <input type="password" id="regPassword" placeholder="密码" style="width: 100%; padding: 15px; margin: 10px 0; border: none; border-radius: 5px; background: #555; color: white;">
                        <button onclick="window.ui.handleRegister()" style="width: 100%; padding: 15px; margin: 15px 0; background: #44ff44; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px;">注册</button>
                        <p style="text-align: center; margin: 20px 0;">已有账号？<a href="#" onclick="window.ui.showLoginForm()" style="color: #ff4444;">登录</a></p>
                    </div>
                </div>
            </div>
        `;
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
        document.body.innerHTML = `
            <div style="background: linear-gradient(120deg, #222244 60%, #444466 100%); min-height: 100vh; color: white; font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 1200px; margin: 0 auto;">
                    <header style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; background: #333; padding: 20px; border-radius: 10px;">
                        <h1 style="color: #ff4444; margin: 0;">PixelWarzone</h1>
                        <div>
                            <span>欢迎, ${this.auth.currentUser.username}!</span>
                            <button onclick="window.ui.logout()" style="margin-left: 15px; padding: 8px 15px; background: #666; color: white; border: none; border-radius: 5px; cursor: pointer;">登出</button>
                        </div>
                    </header>
                    
                    <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 20px;">
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                                <h2>房间列表</h2>
                                <button onclick="window.ui.showCreateRoomForm()" style="padding: 10px 20px; background: #ff4444; color: white; border: none; border-radius: 5px; cursor: pointer;">创建房间</button>
                            </div>
                            <div id="roomList" style="background: #333; border-radius: 10px; padding: 20px;">
                                <div style="text-align: center; color: #666;">加载中...</div>
                            </div>
                        </div>
                        
                        <div>
                            <h2>个人统计</h2>
                            <div style="background: #333; border-radius: 10px; padding: 20px;">
                                <p>游戏场数: ${this.auth.currentUser.stats?.games_played || 0}</p>
                                <p>胜利次数: ${this.auth.currentUser.stats?.wins || 0}</p>
                                <p>击杀数: ${this.auth.currentUser.stats?.kills || 0}</p>
                                <p>死亡数: ${this.auth.currentUser.stats?.deaths || 0}</p>
                                <p>K/D比: ${this.auth.currentUser.stats?.deaths > 0 ? (this.auth.currentUser.stats.kills / this.auth.currentUser.stats.deaths).toFixed(2) : (this.auth.currentUser.stats?.kills || 0)}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
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

    showGameCanvas() {
        document.body.innerHTML = `
            <div style="margin: 0; background: linear-gradient(120deg, #222244 60%, #444466 100%); font-family: Arial, sans-serif;">
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh;">
                    <div style="display: flex; justify-content: space-between; width: 960px; margin-bottom: 10px; color: white;">
                        <div>房间: <span id="roomName">加载中...</span></div>
                        <div>玩家: <span id="playerCount">-/-</span></div>
                        <button onclick="window.ui.leaveRoom()" style="padding: 5px 10px; background: #ff4444; color: white; border: none; border-radius: 3px; cursor: pointer;">离开房间</button>
                    </div>
                    <canvas id="gameCanvas" width="1920" height="1080" style="background: #000; border: 4px solid #ff4444; border-radius: 12px; box-shadow: 0 0 32px #222;"></canvas>
                    <div style="color: #eee; margin-top: 10px; text-align: center;">
                        <p>WASD移动，鼠标拖动瞄准并发射子弹</p>
                        <p>死亡后按R键复活</p>
                    </div>
                </div>
            </div>
        `;
        
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

    showCreateRoomForm() {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
            background: rgba(0,0,0,0.7); display: flex; justify-content: center; 
            align-items: center; z-index: 1000;
        `;
        
        modal.innerHTML = `
            <div style="background: #333; padding: 30px; border-radius: 10px; color: white; width: 400px;">
                <h2>创建房间</h2>
                <input type="text" id="roomName" placeholder="房间名称" style="width: 100%; padding: 10px; margin: 10px 0; border: none; border-radius: 5px; background: #555; color: white;">
                <input type="number" id="maxPlayers" placeholder="最大玩家数" min="2" max="16" value="8" style="width: 100%; padding: 10px; margin: 10px 0; border: none; border-radius: 5px; background: #555; color: white;">
                <input type="password" id="roomPassword" placeholder="房间密码(可选)" style="width: 100%; padding: 10px; margin: 10px 0; border: none; border-radius: 5px; background: #555; color: white;">
                <div style="margin-top: 20px;">
                    <button onclick="window.ui.createRoom()" style="padding: 10px 20px; margin-right: 10px; background: #ff4444; color: white; border: none; border-radius: 5px; cursor: pointer;">创建</button>
                    <button onclick="window.ui.closeModal()" style="padding: 10px 20px; background: #666; color: white; border: none; border-radius: 5px; cursor: pointer;">取消</button>
                </div>
            </div>
        `;
        
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
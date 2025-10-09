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
        await this.appendFooter();
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
        // 渲染武器槽/漏洞面板
        this.renderLoadoutPanel();
        await this.appendFooter();
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
                        <p style="margin: 5px 0; color: #ccc;">玩家: ${room.player_count || room.players}/${room.max_players}</p>
                        ${room.has_password ? '<span style="color: #ffaa00;">🔒 需要密码</span>' : ''}
                    </div>
                    <button onclick="window.ui.joinRoom('${room.id}', ${room.has_password})" 
                            style="padding: 8px 15px; background: #44ff44; color: white; border: none; border-radius: 5px; cursor: pointer;"
                            ${(room.player_count || room.players) >= room.max_players ? 'disabled' : ''}>
                        ${(room.player_count || room.players) >= room.max_players ? '房间已满' : '加入'}
                    </button>
                </div>
            `).join('');
        }
    }

    async renderLoadoutPanel() {
        const panel = document.getElementById('loadoutPanel');
        if (!panel) return;
        try {
            // 拉取可用项
            const metaRes = await fetch(`http://${CONFIG.BACKEND_URL}/api/loadout/meta`);
            const meta = await metaRes.json();
            const weapons = meta.weapons || ["single","shotgun","missile","wall"];
            const perks = meta.perks || ["regen_boost","regen_when_dead"];
            // 当前用户配置
            let loadout = (this.auth.currentUser && this.auth.currentUser.loadout) || { weapon_slots: ["single","shotgun","missile","wall"], perks: [] };
            if (!loadout || !Array.isArray(loadout.weapon_slots)) {
                const me = await this.auth.getUserInfo();
                loadout = (me && me.loadout) || { weapon_slots: ["single","shotgun","missile","wall"], perks: [] };
            }

            const slotSelect = (idx) => `
                <label style="display:block; margin:6px 0; color:#ddd;">
                    Slot ${idx+1} (key ${idx+1}):
                    <select id="slot_${idx}" style="width:100%; padding:6px; margin-top:4px; background:#444; color:#fff; border:1px solid #555; border-radius:4px;">
                        ${weapons.map(w => `<option value="${w}" ${loadout.weapon_slots[idx]===w?'selected':''}>${w}</option>`).join('')}
                    </select>
                </label>`;

            const perkCheck = (p, label) => `
                <label style="display:flex; align-items:center; gap:8px; margin:6px 0;">
                    <input type="checkbox" id="perk_${p}" ${loadout.perks.includes(p)?'checked':''}>
                    <span>${label}</span>
                </label>`;

            panel.innerHTML = `
                <div>
                    <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; align-items:start;">
                        ${[0,1,2,3].map(i=>`<div style=\"min-width:0;\">${slotSelect(i)}</div>`).join('')}
                    </div>
                    <div style="margin-top:12px; border-top:1px solid #444; padding-top:10px;">
                        <div style="color:#ddd; margin-bottom:6px;">Hacking skills</div>
                        ${perkCheck('regen_boost','Regenerating not easily disrupted but slower')}
                        ${perkCheck('regen_when_dead','Regenerating when dead')}
                    </div>
                    <div style="margin-top:12px; display:flex; gap:10px;">
                        <button id="saveLoadoutBtn" style="padding:8px 12px; background:#ff4444; color:#fff; border:none; border-radius:6px; cursor:pointer;">Save</button>
                    </div>
                    <div id="loadoutHint" style="margin-top:8px; color:#aaa; font-size:12px;"></div>
                </div>
            `;

            document.getElementById('saveLoadoutBtn').onclick = async () => {
                const selected = [0,1,2,3].map(i=>document.getElementById(`slot_${i}`).value);
                const chosenPerks = [];
                if (document.getElementById('perk_regen_boost').checked) chosenPerks.push('regen_boost');
                if (document.getElementById('perk_regen_when_dead').checked) chosenPerks.push('regen_when_dead');
                const resp = await fetch(`http://${CONFIG.BACKEND_URL}/api/loadout/update?session_token=${this.auth.sessionToken}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ weapon_slots: selected, perks: chosenPerks })
                });
                const data = await resp.json();
                if (data.success) {
                    // 写回内存用户对象
                    this.auth.currentUser.loadout = data.loadout;
                    document.getElementById('loadoutHint').textContent = 'Saved';
                } else {
                    document.getElementById('loadoutHint').textContent = 'Failed:' + (data.error || 'unknown error');
                }
            };
        } catch (e) {
            panel.innerHTML = '<span style="color:#f66">载入失败</span>';
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
        await this.appendFooter();
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

    async appendFooter() {
        try {
            const footerTpl = await this.loadTemplate('/res/ui/footer.html');
            if (!document.querySelector('footer')) {
                document.body.insertAdjacentHTML('beforeend', footerTpl);
            }
            const year = (new Date()).getFullYear();
            const name = (window.CONFIG && window.CONFIG.COPYRIGHT_NAME) || 'DipsyHou';
            const line = document.getElementById('copyrightLine');
            if (line) {
                line.textContent = `© ${year} ${name}. All rights reserved.`;
            }
        } catch (e) {
            console.warn('Footer load failed', e);
        }
    }
}

window.UI = UI;
// js/main.js
class App {
    constructor() {
        this.auth = new Auth();
        this.roomManager = new RoomManager(this.auth);
        this.ui = new UI(this.auth, this.roomManager);
        this.game = new Game();
        this.wsManager = new WebSocketManager(this.auth, this.game);
        
        // 将实例挂载到全局
        window.auth = this.auth;
        window.roomManager = this.roomManager;
        window.ui = this.ui;
        window.game = this.game;
        window.wsManager = this.wsManager;
    }

    async init() {
        // 检查是否已登录
        if (this.auth.isLoggedIn()) {
            const userData = await this.auth.getUserInfo();
            if (userData) {
                this.ui.showRoomList();
            } else {
                this.ui.showLoginForm();
            }
        } else {
            this.ui.showLoginForm();
        }
    }
}

// 应用启动
window.onload = async function() {
    const app = new App();
    await app.init();
};
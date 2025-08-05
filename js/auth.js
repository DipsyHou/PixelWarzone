class Auth {
    constructor() {
        this.sessionToken = localStorage.getItem('session_token');
        this.currentUser = null;
    }

    async register(username, password, email) {
        try {
            const response = await fetch(`http://${CONFIG.BACKEND_URL}/api/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password, email })
            });
            
            const data = await response.json();
            if (data.success) {
                this.sessionToken = data.session_token;
                localStorage.setItem('session_token', this.sessionToken);
                this.currentUser = { username: data.username };
                return { success: true, user: this.currentUser };
            } else {
                return { success: false, error: data.detail || '注册失败' };
            }
        } catch (error) {
            return { success: false, error: '网络错误：' + error.message };
        }
    }

    async login(username, password) {
        try {
            const response = await fetch(`http://${CONFIG.BACKEND_URL}/api/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            
            const data = await response.json();
            if (data.success) {
                this.sessionToken = data.session_token;
                localStorage.setItem('session_token', this.sessionToken);
                this.currentUser = { username: data.username, stats: data.stats };
                return { success: true, user: this.currentUser };
            } else {
                return { success: false, error: data.detail || '登录失败' };
            }
        } catch (error) {
            return { success: false, error: '网络错误：' + error.message };
        }
    }

    async getUserInfo() {
        if (!this.sessionToken) return null;
        
        try {
            const response = await fetch(`http://${CONFIG.BACKEND_URL}/api/user/${this.sessionToken}`);
            if (response.ok) {
                const userData = await response.json();
                this.currentUser = userData;
                return userData;
            } else {
                this.logout();
                return null;
            }
        } catch {
            this.logout();
            return null;
        }
    }

    logout() {
        this.sessionToken = null;
        this.currentUser = null;
        localStorage.removeItem('session_token');
    }

    isLoggedIn() {
        return !!this.sessionToken;
    }
}

window.Auth = Auth;
/**
 * Common Authentication Logic
 */
const Auth = {
    async login(email, password) {
        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            if (response.ok) {
                const data = await response.json();
                localStorage.setItem('user', JSON.stringify(data.user));
                return true;
            }
            return false;
        } catch (error) {
            console.error('Login error:', error);
            return false;
        }
    },

    async register(data) {
        try {
            const response = await fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            const result = await response.json();
            if (response.ok) {
                return { success: true };
            }
            return { success: false, error: result.error };
        } catch (error) {
            console.error('Register error:', error);
            return { success: false, error: 'Lỗi kết nối máy chủ' };
        }
    },

    async logout() {
        try {
            await fetch('/api/logout');
            localStorage.removeItem('user');
            window.location.href = '/login.html';
        } catch (error) {
            console.error('Logout error:', error);
        }
    },

    getUser() {
        const user = localStorage.getItem('user');
        return user ? JSON.parse(user) : null;
    },

    async checkAuth() {
        try {
            const response = await fetch('/api/profile');
            if (response.ok) {
                const user = await response.json();
                localStorage.setItem('user', JSON.stringify(user));
                return user;
            } else {
                localStorage.removeItem('user');
                return null;
            }
        } catch (error) {
            return null;
        }
    }
};

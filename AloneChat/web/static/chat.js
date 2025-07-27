class AloneChat {
    constructor(config = {}) {
        // WebSocket 配置
        this.wsConfig = {
            protocol: config.wsProtocol || 'ws',
            host: config.wsHost || 'localhost',
            port: config.wsPort || 8765,
            path: config.wsPath || ''
        };

        // 登录相关元素
        this.loginContainer = document.getElementById('loginContainer');
        this.chatContainer = document.getElementById('chatContainer');
        this.usernameInput = document.getElementById('usernameInput');
        this.loginButton = document.getElementById('loginButton');
        this.currentUser = document.getElementById('currentUser');

        // 聊天相关元素
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.messageArea = document.getElementById('messageArea');
        this.connectionStatus = document.querySelector('.connection-status');

        this.ws = null;
        this.username = null;

        this.setupEventListeners();
    }

    setupEventListeners() {
        // 登录事件监听
        this.loginButton.addEventListener('click', () => this.handleLogin());
        this.usernameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.handleLogin();
            }
        });

        // 聊天事件监听
        this.sendButton.addEventListener('click', () => this.handleSendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.handleSendMessage();
            }
        });
    }

    handleLogin() {
        const username = this.usernameInput.value.trim();
        if (this.validateUsername(username)) {
            this.username = username;
            this.currentUser.textContent = username;
            this.connect();
            this.showChat();
        }
    }

    validateUsername(username) {
        if (!username) {
            this.showError('用户名不能为空');
            return false;
        }
        if (username.length < 2 || username.length > 20) {
            this.showError('用户名长度必须在2-20个字符之间');
            return false;
        }
        if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(username)) {
            this.showError('用户名只能包含字母、数字、下划线和中文');
            return false;
        }
        return true;
    }

    showError(message) {
        // 移除旧的错误信息
        const oldError = this.loginContainer.querySelector('.error-message');
        if (oldError) {
            oldError.remove();
        }

        // 显示新的错误信息
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        this.loginButton.insertAdjacentElement('afterend', errorDiv);
    }

    showChat() {
        this.loginContainer.style.display = 'none';
        this.chatContainer.style.display = 'flex';
        this.messageInput.focus();
    }

    connect() {
        // 关闭现有连接
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        const wsUrl = `${this.wsConfig.protocol}://${this.wsConfig.host}:${this.wsConfig.port}${this.wsConfig.path}`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.connectionStatus.textContent = '已连接';
            this.connectionStatus.classList.add('connected');
            // 发送加入消息
            this.sendMessage('', 'JOIN');
        };

        this.ws.onclose = () => {
            this.connectionStatus.textContent = '未连接';
            this.connectionStatus.classList.remove('connected');
            // 3秒后尝试重新连接
            setTimeout(() => this.connect(), 3000);
        };

        this.ws.onerror = (error) => {
            this.showError('连接失败，请检查服务器是否正常运行');
            console.error('WebSocket error:', error);
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.displayMessage(message);
        };
    }

    handleSendMessage() {
        const content = this.messageInput.value.trim();
        if (content) {
            this.sendMessage(content, 'TEXT');
            this.messageInput.value = '';
        }
    }

    sendMessage(content, type) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            const message = {
                type: type === 'TEXT' ? 1 : type === 'JOIN' ? 2 : 3,
                sender: this.username,
                content: content, 
                target: null
            };
            this.ws.send(JSON.stringify(message));
        }
    }

    displayMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message');

        if (message.type === 1) { // TEXT
            messageDiv.classList.add(message.sender === this.username ? 'sent' : 'received');
            messageDiv.innerHTML = `
                <div class="sender">${this.escapeHtml(message.sender)}</div>
                <div class="content">${this.escapeHtml(message.content)}</div>
            `;
        } else if (message.type === 2 || message.type === 3) { // JOIN or LEAVE
            messageDiv.classList.add('system');
            messageDiv.textContent = `${this.escapeHtml(message.sender)} ${message.type === 2 ? '加入了聊天' : '离开了聊天'}`;
        }

        this.messageArea.appendChild(messageDiv);
        this.messageArea.scrollTop = this.messageArea.scrollHeight;
    }

    escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
}

// 从 URL 参数中获取配置
function getConfigFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return {
        wsProtocol: params.get('wsProtocol'),
        wsHost: params.get('wsHost'),
        wsPort: params.get('wsPort'),
        wsPath: params.get('wsPath')
    };
}

// 初始化聊天应用
document.addEventListener('DOMContentLoaded', () => {
    const config = getConfigFromUrl();
    new AloneChat(config);
});
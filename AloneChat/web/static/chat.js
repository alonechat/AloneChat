class AloneChat {
    constructor(config = {}) {
        // WebSocket config
        this.wsConfig = {
            protocol: config.wsProtocol || 'ws',
            host: config.wsHost || 'localhost',
            port: config.wsPort || 8765,
            path: config.wsPath || ''
        };

        // Login-related elements
        this.loginContainer = document.getElementById('loginContainer');
        this.chatContainer = document.getElementById('chatContainer');
        this.usernameInput = document.getElementById('usernameInput');
        this.loginButton = document.getElementById('loginButton');
        this.currentUser = document.getElementById('currentUser');

        // Chat-related elements
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.messageArea = document.getElementById('messageArea');
        this.connectionStatus = document.querySelector('.connection-status');

        this.ws = null;
        this.username = null;

        this.setupEventListeners();
    }

    setupEventListeners() {
        // Listener for login button and username input
        this.loginButton.addEventListener('click', () => this.handleLogin());
        this.usernameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.handleLogin();
            }
        });

        // Listener for chat events
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
            this.showError('Username cannot be empty');
            return false;
        }
        if (username.length < 2 || username.length > 20) {
            this.showError('Username must between 2 and 20 characters');
            return false;
        }
        if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(username)) {
            this.showError('Username can only contain letters, numbers, underscores, and Chinese characters');
            return false;
        }
        return true;
    }

    showError(message) {
        // Remove any existing error messages
        const oldError = this.loginContainer.querySelector('.error-message');
        if (oldError) {
            oldError.remove();
        }

        // Display the new error message
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
        // Remove any existing WebSocket connection
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        const wsUrl = `${this.wsConfig.protocol}://${this.wsConfig.host}:${this.wsConfig.port}${this.wsConfig.path}`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.connectionStatus.textContent = 'Connected';
            this.connectionStatus.classList.add('connected');
            // Send a JOIN message to the server
            this.sendMessage('', 'JOIN');
        };

        this.ws.onclose = () => {
            this.connectionStatus.textContent = 'Disconnected';
            this.connectionStatus.classList.remove('connected');
            // Retry connection after 3 seconds
            setTimeout(() => this.connect(), 3000);
        };

        this.ws.onerror = (error) => {
            this.showError('Connect failed, please check your WebSocket server at port 8765.');
            console.error('WebSocket error:', error);
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            console.log('Called, Received message:', message);
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
            messageDiv.textContent = `${this.escapeHtml(message.sender)} ${message.type === 2 ? 'joined' : 'leaved'}`;
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

// Get config from URL parameters
function getConfigFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return {
        wsProtocol: params.get('wsProtocol'),
        wsHost: params.get('wsHost'),
        wsPort: params.get('wsPort'),
        wsPath: params.get('wsPath')
    };
}

// Initialize the chat application when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
    const config = getConfigFromUrl();
    new AloneChat(config);
});
let ws = null;

// 从cookie获取认证令牌
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

// 清除cookie
function clearCookie(name) {
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; SameSite=Lax`;
}

// 验证JWT令牌是否过期
function isTokenExpired(token) {
    try {
        const tokenParts = token.split('.');
        if (tokenParts.length < 3) {
            return true;
        }
        const payload = JSON.parse(atob(tokenParts[1]));
        if (!payload.exp) {
            return false;
        }
        return payload.exp * 1000 < Date.now();
    } catch (e) {
        console.error('验证令牌过期失败:', e);
        return true;
    }
}

// 从localStorage获取登录信息
let username = localStorage.getItem('username') || '';
let authToken = getCookie('authToken') || localStorage.getItem('authToken') || null;

// 验证令牌是否过期
if (authToken && isTokenExpired(authToken)) {
    console.log('令牌已过期，清除登录信息');
    clearCookie('authToken');
    localStorage.removeItem('authToken');
    localStorage.removeItem('username');
    authToken = null;
    username = '';
}

// 登录功能
function login() {
    const loginUsername = document.getElementById('loginUsername').value.trim();
    const loginPassword = document.getElementById('loginPassword').value.trim();
    let isValid = true;

    // 清除之前的错误消息
    document.getElementById('loginUsernameError').textContent = '';
    document.getElementById('loginPasswordError').textContent = '';
    document.getElementById('loginStatus').textContent = '';

    // 验证表单
    if (!loginUsername) {
        document.getElementById('loginUsernameError').textContent = '用户名不能为空';
        isValid = false;
    }

    if (!loginPassword) {
        document.getElementById('loginPasswordError').textContent = '密码不能为空';
        isValid = false;
    }

    if (!isValid) {
        return;
    }

    // 发送登录请求到后端API
    fetch('/api/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            username: loginUsername,
            password: loginPassword
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 存储登录信息到localStorage
                localStorage.setItem('authToken', data.token);
                localStorage.setItem('username', loginUsername);
                authToken = data.token;

                // 同时存储认证令牌到cookie，有效期1小时
                const expiration = new Date();
                expiration.setTime(expiration.getTime() + (60 * 60 * 1000));
                document.cookie = `authToken=${data.token}; expires=${expiration.toUTCString()}; path=/; SameSite=Lax`;
                console.log('Cookie已设置:', document.cookie);

                // 解码JWT令牌以获取角色信息
                try {
                    const tokenParts = data.token.split('.');
                    console.log('JWT令牌部分:', tokenParts);

                    // 确保令牌有足够的部分
                    if (tokenParts.length < 3) {
                        throw new Error('JWT令牌格式不正确');
                    }

                    // 解码payload部分
                    const payload = JSON.parse(atob(tokenParts[1]));
                    console.log('JWT payload:', payload);

                    // 获取角色信息
                    const role = payload.role || 'user';
                    console.log('用户角色:', role);

                    // 根据角色重定向到相应页面
                    if (role.toLowerCase() === 'admin') {
                        console.log('重定向到管理员页面');
                        // 添加短暂延迟以便查看日志
                        setTimeout(() => {
                            console.log('即将重定向到/admin.html，当前cookie:', document.cookie);
                            window.location.href = '/admin.html';
                        }, 1000);
                    } else {
                        console.log('重定向到用户页面');
                        window.location.href = '/index.html';
                    }
                } catch (e) {
                    console.error('解析JWT令牌失败:', e);
                    // 显示错误信息给用户
                    document.getElementById('loginStatus').textContent = '登录成功，但无法确定用户角色: ' + e.message;
                    document.getElementById('loginStatus').style.color = 'orange';
                    // 不立即重定向，让用户看到错误信息
                    setTimeout(() => {
                        window.location.href = '/index.html';
                    }, 3000);
                }
            } else {
                document.getElementById('loginStatus').textContent = data.message || '登录失败';
                document.getElementById('loginStatus').style.color = 'red';
            }
        })
        .catch(error => {
            console.error('登录请求失败:', error);
            document.getElementById('loginStatus').textContent = '登录请求失败，请检查网络连接';
            document.getElementById('loginStatus').style.color = 'red';
        });
}

// 连接到服务器
function connect() {
    // 检查是否在管理员页面
    const isAdminPage = window.location.pathname.includes('admin.html');

    // 管理员页面也需要连接WebSocket以获取在线用户状态
    if (isAdminPage) {
        console.log('管理员页面连接WebSocket');
    }

    // 从localStorage获取服务器地址
    // 优先从defaultServer读取（管理员页面设置的值）
    let serverAddress = localStorage.getItem('defaultServer');
    if (!serverAddress) {
        // 其次尝试从serverAddress读取
        serverAddress = localStorage.getItem('serverAddress');
    }
    // 如果都没有设置，使用默认值
    if (!serverAddress) {
        // 检测当前页面协议，自动匹配ws或wss
        const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        // 使用当前域名和端口
        serverAddress = `${protocol}${window.location.hostname}:8765`;
        console.log('使用自动检测的服务器地址:', serverAddress);
    }
    // 确保添加认证令牌
    if (authToken) {
        const separator = serverAddress.includes('?') ? '&' : '?';
        serverAddress += `${separator}token=${encodeURIComponent(authToken)}`;
        console.log('添加认证令牌后的服务器地址:', serverAddress);
    } else {
        console.warn('没有找到认证令牌，连接可能会失败');
        // 所有页面没有令牌都重定向到登录页面
        console.log('没有令牌，重定向到登录页面');
        window.location.href = '/login.html';
        return;
    }
    // 处理不同协议前缀，确保使用ws://
    if (serverAddress.startsWith('http://')) {
        serverAddress = 'ws://' + serverAddress.substring(7);
    } else if (serverAddress.startsWith('https://')) {
        serverAddress = 'wss://' + serverAddress.substring(8);
    } else if (!serverAddress.startsWith('ws://') && !serverAddress.startsWith('wss://')) {
        serverAddress = 'ws://' + serverAddress;
    }
    // 处理URL，对于标准端口（80/443）不添加默认端口
    try {
        const url = new URL(serverAddress);
        // 如果是ws://或wss://协议且没有指定端口，则不添加默认端口
        // 这样当使用内网穿透地址时，会使用默认的80或443端口
    } catch (e) {
        addSystemMessage(`无效的服务器地址: ${e}`);
        return;
    }
    const statusElement = document.getElementById('status');
    const messagesElement = document.getElementById('messages');

    // 关闭现有连接
    if (ws) {
        ws.close();
    }

    try {
        ws = new WebSocket(serverAddress);

        // 连接成功
        ws.onopen = () => {
            statusElement.textContent = '已连接';
            statusElement.style.color = 'green';
            addSystemMessage('成功连接到服务器');

            // 提示输入用户名
            try {
                username = document.getElementById('username').value.trim() || '匿名用户';
            } catch (e) { // Catch for error: Cannot read properties of null (reading 'value')
                ws.close();
                return;
            }
            if (username) {
                // 已通过令牌验证，无需发送JOIN消息
            } else {
                // 登录失败，不应继续连接流程
                ws.close();

            }
        };

        // 接收消息
        ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                displayMessage(message);
            } catch (e) {
                addSystemMessage(`解析消息错误: ${e}`);
            }
        };

        // 连接关闭
        ws.onclose = () => {
            statusElement.textContent = '已断开连接';
            statusElement.style.color = 'red';
            addSystemMessage('与服务器的连接已断开');
            ws = null;
        };

        // 连接错误
        ws.onerror = (error) => {
            // 增强错误信息显示
            let errorMessage = '未知错误';
            if (error && error.message) {
                errorMessage = error.message;
            } else if (error && typeof error === 'object') {
                // 尝试获取更多错误详情
                const errorDetails = [];
                for (const key in error) {
                    if (error.hasOwnProperty(key)) {
                        errorDetails.push(`${key}: ${error[key]}`);
                    }
                }
                errorMessage = errorDetails.length > 0 ? errorDetails.join(', ') : JSON.stringify(error);
            }
            statusElement.textContent = `连接错误: ${errorMessage}`;
            statusElement.style.color = 'red';
            addSystemMessage(`连接错误: ${errorMessage}`);
            console.error('WebSocket错误:', error);
        };

        // 定期检查连接状态，防止连接断开
        function checkConnectionStatus() {
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                console.log('连接已断开，尝试重新连接');
                connect();
            }
        }

// 每30秒检查一次连接状态
        setInterval(checkConnectionStatus, 30000);

// 添加心跳机制，定期发送ping消息保持连接
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                try {
                    // 使用type=7作为心跳消息，避免与服务器端的HELP类型冲突
                    ws.send(JSON.stringify({type: 7, sender: username, content: 'ping'}));
                } catch (e) {
                    console.error('发送心跳失败:', e);
                }
            }
        }, 30000); // 每30秒发送一次心跳
    } catch (e) {
        statusElement.textContent = `连接失败: ${e}`;
        statusElement.style.color = 'red';
    }
}

// 打开反馈表单
function openFeedbackForm() {
    document.getElementById('feedbackForm').style.display = 'block';
    document.getElementById('feedbackContent').focus();
}

// 关闭反馈表单
function closeFeedbackForm() {
    document.getElementById('feedbackForm').style.display = 'none';
}

// 显示反馈通知
function showFeedbackNotification(message = '反馈已提交，感谢您的意见！') {
    const notification = document.getElementById('feedbackNotification');
    notification.textContent = message;
    notification.style.opacity = '1';
    notification.style.display = 'block';

    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            notification.style.display = 'none';
        }, 300);
    }, 3000);
}

// 提交反馈到服务器
function submitFeedbackToServer(feedback) {
    return fetch('/api/feedback/submit', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${window.authToken}`
        },
        body: JSON.stringify({content: feedback.content})
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('提交反馈失败');
            }
            return response.json();
        });
}


// 提交反馈
function submitFeedback() {
    const content = document.getElementById('feedbackContent').value.trim();
    if (!content) {
        alert('请输入反馈内容');
        return;
    }

    const feedback = {
        content: content
    };

    // 提交反馈到服务器
    submitFeedbackToServer(feedback)
        .then(data => {
            if (data.success) {
                // 清空输入框
                document.getElementById('feedbackContent').value = '';
                // 关闭表单
                closeFeedbackForm();
                // 显示通知
                showFeedbackNotification('反馈已提交，感谢您的意见！');
            } else {
                showFeedbackNotification('保存反馈失败: ' + (data.message || '未知错误'));
            }
        })
        .catch(error => {
            console.error('提交反馈失败:', error);
            showFeedbackNotification('提交反馈失败，请稍后重试');
        });
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function () {
    // 如果存在反馈按钮，则添加点击事件
    const feedbackButton = document.getElementById('feedbackButton');
    if (feedbackButton) {
        feedbackButton.addEventListener('click', openFeedbackForm);
    }
});

// 发送消息
function sendMessage() {
    const inputElement = document.getElementById('messageInput');
    const message = inputElement.value.trim();

    if (!message) return;

    // 处理/help命令
    if (message === '/help') {
        showHelp();
        inputElement.value = '';
        // 重置textarea高度为一行
        inputElement.style.height = 'auto';
        inputElement.rows = 1;
        return;
    }

    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const messageObject = {
        type: 1,
        sender: username,
        content: message
    };

    ws.send(JSON.stringify(messageObject));
    inputElement.value = '';
    // 重置textarea高度为一行
    inputElement.style.height = 'auto';
    inputElement.rows = 1;
}

// 显示帮助文档
function showHelp() {
    // 检查是否已存在帮助弹窗
    let helpModal = document.getElementById('helpModal');
    if (helpModal) {
        helpModal.style.display = 'flex';
        return;
    }

    // 创建帮助弹窗
    helpModal = document.createElement('div');
    helpModal.id = 'helpModal';
    helpModal.className = 'help-modal';

    // 帮助内容容器
    const helpContent = document.createElement('div');
    helpContent.className = 'help-content';

    // 标题栏
    const header = document.createElement('div');
    header.className = 'help-header';

    const title = document.createElement('h2');
    title.textContent = '帮助文档 / Help Documentation';

    const closeBtn = document.createElement('span');
    closeBtn.className = 'close-btn';
    closeBtn.textContent = '×';
    closeBtn.onclick = () => {
        helpModal.style.display = 'none';
    };

    header.appendChild(title);
    header.appendChild(closeBtn);

    // 语言切换按钮
    const langContainer = document.createElement('div');
    langContainer.className = 'lang-container';

    const zhBtn = document.createElement('button');
    zhBtn.id = 'zhBtn';
    zhBtn.className = 'lang-btn active';
    zhBtn.textContent = '中文';
    zhBtn.onclick = () => {
        document.getElementById('zhContent').style.display = 'block';
        document.getElementById('enContent').style.display = 'none';
        zhBtn.classList.add('active');
        enBtn.classList.remove('active');
    };

    const enBtn = document.createElement('button');
    enBtn.id = 'enBtn';
    enBtn.className = 'lang-btn';
    enBtn.textContent = 'English';
    enBtn.onclick = () => {
        document.getElementById('zhContent').style.display = 'none';
        document.getElementById('enContent').style.display = 'block';
        enBtn.classList.add('active');
        zhBtn.classList.remove('active');
    };

    langContainer.appendChild(zhBtn);
    langContainer.appendChild(enBtn);

    // 中文内容
    const zhContent = document.createElement('div');
    zhContent.id = 'zhContent';
    zhContent.className = 'help-text';
    zhContent.innerHTML = `
        <h3>项目开发流程</h3>
        <p>我们将会以Python作为开发语言，在一阶段的开发及测试完成之后我们会通过工具把程序封装成可执行文件(.exe)。</p>

        <h3>开发周期</h3>
        <p>我们希望可以在6个月以内成功上传最基础的第一版。（纯命令行）</p>
        <p>后续版本我们会尽量一迭代一版。</p>

        <h3>开发结果</h3>
        <p>我们的第一版会沿用Web-socket协议进行多设备之间的沟通，后续不出意外也还是用Web-socket。</p>
        <p>我们的第一版希望可以通过命令进入提前设置好的共同聊天室，并可以直接在里面发消息。</p>
        <p>我们还会做一个服务器端可执行文件，只有当服务器端在一台和公网可访问的服务器上，或是内网运行，聊天室才会开启。</p>
        <p>同时服务器端可以起到管理员的身份，可以强制下线别的用户，同时所有的聊天记录也会存储在服务器端所在的电脑上。</p>

        <h3>远期开发</h3>
        <p>后面我们会把命令行界面升级成图形化界面，并提供更多元化的聊天信息形式的支持。</p>
        <p>甚至我们有可能做成网页，让所有人都可以随时随地进入公共聊天室。</p>
        <p>我们还会设置联系人单聊、发起群聊、视频通话等功能丰富用户体验。</p>

        <h3>开发者及其负责项目</h3>
        <p>hi-zcy：项目大部分代码和项目构思。</p>
        <p>tony231218：项目代码框架即代码修改、调试。（开发者负责项目可能随时变动）</p>
    `;

    // 英文内容
    const enContent = document.createElement('div');
    enContent.id = 'enContent';
    enContent.className = 'help-text';
    enContent.style.display = 'none';
    enContent.innerHTML = `
        <h3>Project Development Process</h3>
        <p>We will use Python as the primary development language. After completing the initial development and testing phase, we'll package the program into an executable (.exe) file using specialized tools.</p>

        <h3>Development Timeline</h3>
        <p>Our goal is to release the most basic first version (pure command-line interface) within 6 months.</p>
        <p>Subsequent versions will follow an iterative release approach (one iteration per version).</p>

        <h3>Deliverables (First Version)</h3>
        <p>The initial release will utilize the WebSocket protocol for multi-device communication, and we plan to maintain this protocol in future versions unless circumstances change.</p>
        <p>Users will be able to join pre-configured shared chat rooms via commands and send messages directly within them.</p>
        <p>We'll develop a server-side executable that must run on a public-facing server to activate the chat room functionality.</p>
        <p>The server will act as an administrator, with capabilities to forcibly disconnect users.</p>

        <h3>Long-term Development Roadmap</h3>
        <p>Upgrade the command-line interface to a graphical user interface (GUI)</p>
        <p>Support more diverse chat message formats</p>
        <p>Potential web-based implementation allowing universal access to public chat rooms</p>
        <p>Additional features including:</p>
        <ul>
            <li>Private messaging between contacts</li>
            <li>Group chat creation</li>
            <li>Video calling functionality to enhance user experience</li>
        </ul>

        <h3>Development Team & Responsibilities</h3>
        <p>hi-zcy: Primary code development and project conceptualization</p>
        <p>tony231218: Code framework establishment, modifications, and debugging</p>
        <p>(Note: Developer responsibilities may change as needed)</p>
    `;

    // 页脚
    const footer = document.createElement('div');
    footer.className = 'help-footer';
    footer.textContent = '© 2025 AloneChat 开发团队';

    // 组装帮助内容
    helpContent.appendChild(header);
    helpContent.appendChild(langContainer);
    helpContent.appendChild(zhContent);
    helpContent.appendChild(enContent);
    helpContent.appendChild(footer);

    // 添加样式
    const style = document.createElement('style');
    style.textContent = `
        .help-modal {
            display: flex;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            align-items: center;
            justify-content: center;
        }

        .help-content {
            background-color: #fff;
            margin: auto;
            padding: 20px;
            border: 1px solid #888;
            width: 80%;
            max-width: 800px;
            max-height: 80vh;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
            display: flex;
            flex-direction: column;
        }

        .help-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
            margin-bottom: 15px;
        }

        .help-header h2 {
            margin: 0;
            color: #333;
        }

        .close-btn {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }

        .close-btn:hover {
            color: #333;
        }

        .lang-container {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }

        .lang-btn {
            padding: 8px 16px;
            background-color: #f1f1f1;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            transition: background-color 0.3s;
        }

        .lang-btn.active {
            background-color: #4CAF50;
            color: white;
        }

        .help-text {
            overflow-y: auto;
            flex-grow: 1;
            padding: 10px 0;
        }

        .help-text h3 {
            color: #4CAF50;
            margin-top: 15px;
            margin-bottom: 10px;
        }

        .help-text p {
            margin: 8px 0;
            line-height: 1.6;
        }

        .help-text ul {
            margin: 8px 0 8px 20px;
        }

        .help-footer {
            text-align: center;
            padding-top: 15px;
            border-top: 1px solid #eee;
            margin-top: 15px;
            color: #777;
            font-size: 0.9em;
        }
    `;

    helpContent.appendChild(style);
    helpModal.appendChild(helpContent);
    document.body.appendChild(helpModal);
}

// 显示接收到的消息
function displayMessage(message) {
    const messagesElement = document.getElementById('messages');
    const messageElement = document.createElement('div');

    switch (message.type) {
        case 2:
            messageElement.className = 'message message-system';
            messageElement.textContent = `${message.sender} 加入了聊天`;
            break;
        case 1:
            if (message.sender === username) {
                messageElement.className = 'message outgoing';
                // 使用innerHTML并将换行符转换为<br>标签
                messageElement.innerHTML = message.content.replace(/\n/g, '<br>');
            } else {
                messageElement.className = 'message incoming';
                // 使用innerHTML并将换行符转换为<br>标签
                messageElement.innerHTML = `[${message.sender}] ${message.content.replace(/\n/g, '<br>')}`;
            }
            break;
        case 3:
            messageElement.className = 'message message-system';
            messageElement.textContent = `${message.sender} 离开了聊天`;
            break;
        case 7:
            // 忽略心跳消息
            return;
        default:
            messageElement.className = 'message message-system';
            messageElement.textContent = `[系统] ${message.content || JSON.stringify(message)}`;
    }

    messagesElement.appendChild(messageElement);
    messagesElement.scrollTop = messagesElement.scrollHeight;
}

// 添加系统消息
function addSystemMessage(text) {
    const messagesElement = document.getElementById('messages');
    const messageElement = document.createElement('div');
    messageElement.className = 'message message-system';
    messageElement.textContent = text;
    messagesElement.appendChild(messageElement);
    messagesElement.scrollTop = messagesElement.scrollHeight;
}

// 登出功能
function logout() {
    console.log('用户登出');
    // 清除WebSocket连接
    if (ws) {
        ws.close();
        ws = null;
    }
    // 清除登录信息
    clearCookie('authToken');
    localStorage.removeItem('authToken');
    localStorage.removeItem('username');
    authToken = null;
    username = '';
    // 重定向到登录页面
    window.location.href = '/login.html';
}

// 踢出用户
function kickUser(username) {
    if (confirm(`确定要踢出用户 ${username} 吗？`)) {
        fetch('/api/admin/kick-user', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({username})
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('踢出用户失败');
                }
                return response.json();
            })
            .then(data => {
                alert(data.message || '踢出用户成功');
                // 刷新用户列表
                viewOnlineUsers();
            })
            .catch(error => {
                console.error('踢出用户失败:', error);
                alert(`踢出用户失败: ${error.message}`);
            });
    }
}

// 查看聊天历史
function viewChatHistory() {
    console.log('查看聊天历史');
    const chatHistoryElement = document.getElementById('chatHistory');
    chatHistoryElement.innerHTML = '<p>加载中...</p>';

    // 发送请求到后端API
    fetch('/api/admin/chat-history', {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${authToken}`
        }
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('获取聊天历史失败');
            }
            return response.json();
        })
        .then(data => {
            if (data.messages && data.messages.length > 0) {
                let html = '<table><tr><th>时间</th><th>发送者</th><th>内容</th></tr>';
                data.messages.forEach(message => {
                    const time = new Date(message.timestamp).toLocaleString();
                    html += `<tr><td>${time}</td><td>${message.sender}</td><td>${message.content}</td></tr>`;
                });
                html += '</table>';
                chatHistoryElement.innerHTML = html;
            } else {
                chatHistoryElement.innerHTML = '<p>暂无聊天记录</p>';
            }
        })
        .catch(error => {
            console.error('获取聊天历史失败:', error);
            chatHistoryElement.innerHTML = `<p>获取失败: ${error.message}</p>`;
        });
}

// 查看系统状态
function viewSystemStatus() {
    console.log('查看系统状态');
    const systemStatusElement = document.getElementById('systemStatus');
    systemStatusElement.innerHTML = '<p>加载中...</p>';

    // 发送请求到后端API
    fetch('/api/admin/system-status', {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${authToken}`
        }
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('获取系统状态失败');
            }
            return response.json();
        })
        .then(data => {
            let html = '';
            html += `<div class="system-info-item"><span class="system-info-label">服务器版本:</span> ${data.version || '未知'}</div>`;
            html += `<div class="system-info-item"><span class="system-info-label">运行时间:</span> ${data.uptime || '未知'}</div>`;
            html += `<div class="system-info-item"><span class="system-info-label">在线用户数:</span> ${data.online_users || 0}</div>`;
            html += `<div class="system-info-item"><span class="system-info-label">总用户数:</span> ${data.total_users || 0}</div>`;
            html += `<div class="system-info-item"><span class="system-info-label">CPU使用率:</span> ${data.cpu_usage || '未知'}</div>`;
            html += `<div class="system-info-item"><span class="system-info-label">内存使用:</span> ${data.memory_usage || '未知'}</div>`;
            systemStatusElement.innerHTML = html;
        })
        .catch(error => {
            console.error('获取系统状态失败:', error);
            systemStatusElement.innerHTML = `<p>获取失败: ${error.message}</p>`;
        });
}

// 确保DOM加载完成后再添加事件监听器
document.addEventListener('DOMContentLoaded', function () {
    // 添加登出按钮事件监听
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }

    // 检查是否在管理员页面
    const isAdminPage = window.location.pathname.includes('admin.html');
    if (isAdminPage) {
        // 管理员页面专属功能
        // 查看聊天历史按钮事件
        const viewChatHistoryBtn = document.getElementById('viewChatHistoryBtn');
        if (viewChatHistoryBtn) {
            viewChatHistoryBtn.addEventListener('click', viewChatHistory);
        }

        // 查看系统状态按钮事件
        const viewSystemStatusBtn = document.getElementById('viewSystemStatusBtn');
        if (viewSystemStatusBtn) {
            viewSystemStatusBtn.addEventListener('click', viewSystemStatus);
        }
    }
    // 监听回车键发送消息，支持Shift+Enter换行
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                if (e.shiftKey) {
                    // 按住Shift+Enter，添加换行
                    // 对于textarea，默认就支持换行，不需要额外处理
                } else {
                    // 单独按Enter，发送消息
                    e.preventDefault(); // 阻止默认行为
                    sendMessage();
                }
            }
        });

        // 添加textarea自动调整高度功能
        messageInput.addEventListener('input', function () {
            // 重置高度
            this.style.height = 'auto';
            // 设置新高度，基于内容.scrollHeight
            // 限制最大高度为120px
            const newHeight = Math.min(this.scrollHeight, 120);
            this.style.height = newHeight + 'px';
        });
    }

    // 服务器地址输入框事件监听
    const serverAddress = document.getElementById('serverAddress');
    if (serverAddress) {
        serverAddress.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                connect();
            }
        });
    }

    // 自动连接（如果已有令牌）
    if (authToken && !window.location.pathname.includes('login.html')) {
        setTimeout(() => {
            connect();
        }, 1000);
    } else if (authToken && window.location.pathname.includes('login.html')) {
        // 如果已有令牌但在登录页面，重定向到首页或管理员页面
        try {
            const tokenParts = authToken.split('.');
            if (tokenParts.length >= 3) {
                const payload = JSON.parse(atob(tokenParts[1]));
                const role = payload.role || 'user';
                if (role.toLowerCase() === 'admin') {
                    window.location.href = '/admin.html';
                } else {
                    window.location.href = '/index.html';
                }
            }
        } catch (e) {
            console.error('解析令牌失败:', e);
            window.location.href = '/index.html';
        }
    }
});
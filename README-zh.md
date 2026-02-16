# AloneChat（中文说明）

一个可扩展的聊天应用：HTTP API + 实时消息（SSE/WebSocket），统一日志体系，并使用 ClickHouse 作为持久化存储。

## 功能亮点

- 实时消息：SSE / WebSocket
- JWT 登录鉴权
- 统一日志与环境配置
- **好友机制（私聊前置条件）**：支持好友申请、接受/拒绝；只有互为好友才能私聊（为后续朋友圈/群聊打基础）
- ClickHouse 持久化（用户、私聊历史等）

## 快速开始

### 1）安装依赖

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 2）启动服务端

```bash
python -m AloneChat server

# ClickHouse 默认地址（本地开发）
# HTTP:   127.0.0.1:8123
# Native: 127.0.0.1:9000
```

### 3）启动客户端（GUI）

```bash
python -m AloneChat client
```

## 配置（ClickHouse）

ClickHouse 一般有两个端口：

- **Native（驱动连接）**：通常是 `9000`（clickhouse-driver 用这个）
- **HTTP（浏览器/HTTP接口）**：通常是 `8123`（你提到的 `127.0.0.1:8123` 属于这个）

可用环境变量：

- `CLICKHOUSE_HOST` / `CLICKHOUSE_PORT`：Native 连接（默认 `127.0.0.1:9000`）
- `CLICKHOUSE_HTTP_HOST` / `CLICKHOUSE_HTTP_PORT`：HTTP 地址（默认 `127.0.0.1:8123`）

> 提示：如果你使用 clickhouse-driver（Native 协议）就连 `127.0.0.1:9000`；如果你用 HTTP 客户端/浏览器访问就用 `127.0.0.1:8123`。

## 好友 & 私聊接口

- 发起好友申请：`POST /api/friends/request`（body: `{ "to_user": "xxx" }`）
- 接受好友申请：`POST /api/friends/accept`（body: `{ "from_user": "xxx" }`）
- 拒绝好友申请：`POST /api/friends/reject`（body: `{ "from_user": "xxx" }`）
- 获取好友列表：`GET /api/friends/list`
- 获取申请列表：`GET /api/friends/requests?direction=incoming|outgoing`

**重要：** 私聊是“好友门槛”的——若双方不是好友，私聊会返回 `403 NOT_FRIENDS`。

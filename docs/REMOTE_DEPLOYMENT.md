# 远程服务器部署指南

本文档介绍如何将 JobHistory MCP Server 部署到远程服务器，并从本地客户端连接使用。

## 部署架构

```
┌─────────────────┐         HTTP          ┌─────────────────┐         HTTP          ┌─────────────────┐
│   本地客户端     │ ◄──────────────────► │   MCP Server    │ ◄──────────────────► │  JobHistory     │
│  (Cursor等)     │      (网络)           │   (远程服务器)   │      (内网)           │   Server        │
└─────────────────┘                       └─────────────────┘                       └─────────────────┘
```

**优势**：
- MCP Server 部署在靠近 Hadoop 集群的服务器，网络延迟低
- 本地客户端无需直接访问 Hadoop 集群
- 支持多个客户端同时连接

---

## 方式一：使用 HTTP 传输（推荐）

### 1. 修改代码支持 HTTP 传输

编辑 `jobhistory_mcp.py`，修改主入口：

```python
# 在文件末尾修改
if __name__ == "__main__":
    import sys
    
    # 检查是否使用 HTTP 模式
    if "--http" in sys.argv or os.getenv("MCP_TRANSPORT") == "http":
        port = int(os.getenv("MCP_PORT", "8080"))
        host = os.getenv("MCP_HOST", "0.0.0.0")
        logger.info(f"启动 HTTP 模式: {host}:{port}")
        mcp.run(transport="streamable_http", host=host, port=port)
    else:
        # 默认 stdio 模式
        mcp.run()
```

### 2. 服务器端部署

#### 使用 Docker 部署（推荐）

**创建 `Dockerfile.http`**：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY jobhistory_mcp.py .

RUN useradd --create-home mcpuser && \
    mkdir -p /app/logs && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

ENV JOBHISTORY_URL="http://localhost:19888/ws/v1/history" \
    MCP_TRANSPORT="http" \
    MCP_HOST="0.0.0.0" \
    MCP_PORT="8080" \
    LOG_LEVEL="INFO" \
    LOG_FILE="/app/logs/jobhistory_mcp.log"

EXPOSE 8080

VOLUME ["/app/logs"]

CMD ["python", "jobhistory_mcp.py", "--http"]
```

**构建并运行**：

```bash
# 构建镜像
docker build -f Dockerfile.http -t jobhistory-mcp-server:http .

# 运行容器
docker run -d \
  --name jobhistory-mcp-http \
  -p 8080:8080 \
  -e JOBHISTORY_URL="http://your-hadoop-cluster:19888/ws/v1/history" \
  -v /var/log/mcp:/app/logs \
  --restart unless-stopped \
  jobhistory-mcp-server:http
```

#### 直接部署（不使用 Docker）

```bash
# 1. 在服务器上克隆或上传项目
scp -r JobHistoryMcpServer user@server:/opt/

# 2. SSH 登录服务器
ssh user@server

# 3. 安装依赖
cd /opt/JobHistoryMcpServer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. 配置环境变量
export JOBHISTORY_URL="http://hadoop-cluster:19888/ws/v1/history"
export MCP_TRANSPORT="http"
export MCP_HOST="0.0.0.0"
export MCP_PORT="8080"

# 5. 启动服务
python jobhistory_mcp.py --http
```

#### 使用 systemd 管理服务

创建 `/etc/systemd/system/jobhistory-mcp.service`：

```ini
[Unit]
Description=JobHistory MCP Server
After=network.target

[Service]
Type=simple
User=mcpuser
WorkingDirectory=/opt/JobHistoryMcpServer
Environment="JOBHISTORY_URL=http://hadoop-cluster:19888/ws/v1/history"
Environment="MCP_TRANSPORT=http"
Environment="MCP_HOST=0.0.0.0"
Environment="MCP_PORT=8080"
Environment="LOG_LEVEL=INFO"
Environment="LOG_FILE=/var/log/mcp/jobhistory_mcp.log"
ExecStart=/opt/JobHistoryMcpServer/venv/bin/python jobhistory_mcp.py --http
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable jobhistory-mcp
sudo systemctl start jobhistory-mcp
sudo systemctl status jobhistory-mcp
```

### 3. 本地客户端配置

#### Cursor 配置

在 `~/.cursor/mcp.json` 中配置远程服务器：

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "url": "http://your-server-ip:8080/mcp"
    }
  }
}
```

#### Claude Desktop 配置

在配置文件中添加：

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "url": "http://your-server-ip:8080/mcp"
    }
  }
}
```

---

## 方式二：使用 SSH 隧道

如果不想修改代码，可以通过 SSH 隧道连接。

### 1. 服务器端准备

在服务器上正常部署（stdio 模式）：

```bash
# 安装依赖
cd /opt/JobHistoryMcpServer
pip install -r requirements.txt
```

### 2. 本地配置 SSH 隧道 + 远程执行

在 `~/.cursor/mcp.json` 中配置：

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "ssh",
      "args": [
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "user@your-server-ip",
        "cd /opt/JobHistoryMcpServer && JOBHISTORY_URL=http://hadoop-cluster:19888/ws/v1/history ./venv/bin/python jobhistory_mcp.py"
      ]
    }
  }
}
```

**优点**：
- 无需修改代码
- 使用 SSH 加密通信
- 复用现有 SSH 认证

**缺点**：
- 每次连接都会启动新进程
- 需要配置 SSH 免密登录

### 3. 配置 SSH 免密登录

```bash
# 生成 SSH 密钥（如果没有）
ssh-keygen -t ed25519

# 复制公钥到服务器
ssh-copy-id user@your-server-ip

# 测试连接
ssh user@your-server-ip "echo OK"
```

---

## 方式三：使用反向代理（Nginx）

适合需要 HTTPS、负载均衡等场景。

### 1. 部署 MCP Server（HTTP 模式）

按方式一部署，监听 `127.0.0.1:8080`。

### 2. 配置 Nginx

```nginx
server {
    listen 443 ssl;
    server_name mcp.example.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location /mcp {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
```

### 3. 本地客户端配置

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "url": "https://mcp.example.com/mcp"
    }
  }
}
```

---

## 安全建议

### 1. 网络隔离

```
                    ┌─────────────┐
                    │   防火墙     │
    ┌───────────────┴─────────────┴───────────────┐
    │                                              │
    │  ┌──────────┐    内网    ┌──────────────┐   │
    │  │ MCP      │◄─────────►│ Hadoop       │   │
    │  │ Server   │            │ Cluster      │   │
    │  └────┬─────┘            └──────────────┘   │
    │       │                                      │
    └───────┼──────────────────────────────────────┘
            │ 8080 (仅允许特定 IP)
            ▼
    ┌───────────────┐
    │ 本地客户端     │
    └───────────────┘
```

### 2. 防火墙规则

```bash
# 只允许特定 IP 访问 MCP Server
sudo ufw allow from YOUR_LOCAL_IP to any port 8080

# 或使用 iptables
sudo iptables -A INPUT -p tcp --dport 8080 -s YOUR_LOCAL_IP -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8080 -j DROP
```

### 3. 使用 HTTPS

强烈建议在生产环境使用 HTTPS：
- 使用 Let's Encrypt 免费证书
- 或通过 Nginx 反向代理添加 SSL

### 4. 认证（可选）

如果需要认证，可以在 Nginx 层添加 Basic Auth：

```nginx
location /mcp {
    auth_basic "MCP Server";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://127.0.0.1:8080;
}
```

---

## 常见问题

### Q1: 连接超时

**可能原因**：
1. 防火墙阻止连接
2. 服务未启动
3. 端口不正确

**排查步骤**：
```bash
# 检查服务是否运行
curl http://server-ip:8080/mcp

# 检查端口是否监听
ss -tlnp | grep 8080

# 检查防火墙
sudo iptables -L -n | grep 8080
```

### Q2: SSH 方式连接失败

**可能原因**：
1. SSH 密钥未配置
2. 服务器上 Python 环境问题

**排查步骤**：
```bash
# 测试 SSH 连接
ssh user@server "python3 --version"

# 测试 MCP Server
ssh user@server "cd /opt/JobHistoryMcpServer && ./venv/bin/python -c 'import mcp; print(\"OK\")'"
```

### Q3: HTTP 模式性能问题

**建议**：
- 增加连接超时时间
- 考虑使用 HTTP/2
- 部署在靠近 Hadoop 集群的网络

---

## 部署方式对比

| 方式 | 复杂度 | 性能 | 安全性 | 适用场景 |
|------|--------|------|--------|----------|
| HTTP 传输 | 中 | 高 | 中 | 多客户端、长期运行 |
| SSH 隧道 | 低 | 中 | 高 | 单用户、临时使用 |
| Nginx 反向代理 | 高 | 高 | 高 | 生产环境、需要 HTTPS |

**推荐**：
- 开发测试：SSH 隧道
- 生产环境：HTTP 传输 + Nginx + HTTPS

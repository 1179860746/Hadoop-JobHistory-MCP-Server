# Docker 部署指南

本文档介绍如何使用 Docker 构建和运行 JobHistory MCP Server。

## 快速开始

### 1. 构建镜像

```bash
cd JobHistoryMcpServer

# 构建 Docker 镜像
docker build -t jobhistory-mcp-server:latest .

# 或使用 docker-compose
docker-compose build
```

### 2. 运行容器

```bash
# 基本运行
docker run -e JOBHISTORY_URL="http://your-hadoop-cluster:19888/ws/v1/history" \
  jobhistory-mcp-server:latest

# 交互模式运行（用于调试）
docker run -it \
  -e JOBHISTORY_URL="http://your-hadoop-cluster:19888/ws/v1/history" \
  jobhistory-mcp-server:latest

# 使用 docker-compose
JOBHISTORY_URL="http://your-hadoop-cluster:19888/ws/v1/history" docker-compose up
```

---

## 详细配置

### 环境变量

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `JOBHISTORY_URL` | JobHistory Server REST API 地址 | `http://localhost:19888/ws/v1/history` |

### 网络配置

#### 访问宿主机上的 Hadoop 集群

**macOS / Windows (Docker Desktop)**:
```bash
docker run -e JOBHISTORY_URL="http://host.docker.internal:19888/ws/v1/history" \
  jobhistory-mcp-server:latest
```

**Linux**:
```bash
# 方式 1: 使用 host 网络模式
docker run --network host \
  -e JOBHISTORY_URL="http://localhost:19888/ws/v1/history" \
  jobhistory-mcp-server:latest

# 方式 2: 添加宿主机映射
docker run --add-host=host.docker.internal:host-gateway \
  -e JOBHISTORY_URL="http://host.docker.internal:19888/ws/v1/history" \
  jobhistory-mcp-server:latest
```

#### 访问远程 Hadoop 集群

```bash
docker run -e JOBHISTORY_URL="http://hadoop-cluster.example.com:19888/ws/v1/history" \
  jobhistory-mcp-server:latest
```

---

## MCP 客户端配置

### Cursor 配置（使用 Docker）

在 `~/.cursor/mcp.json` 中配置：

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "JOBHISTORY_URL=http://your-hadoop-cluster:19888/ws/v1/history",
        "jobhistory-mcp-server:latest"
      ]
    }
  }
}
```

**参数说明**:
- `-i`: 保持 stdin 打开（MCP stdio 传输需要）
- `--rm`: 容器退出后自动删除
- `-e`: 设置环境变量

### Claude Desktop 配置（使用 Docker）

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "JOBHISTORY_URL=http://your-hadoop-cluster:19888/ws/v1/history",
        "jobhistory-mcp-server:latest"
      ]
    }
  }
}
```

### 访问宿主机服务的配置

如果 Hadoop 运行在宿主机上：

**macOS / Windows**:
```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "JOBHISTORY_URL=http://host.docker.internal:19888/ws/v1/history",
        "jobhistory-mcp-server:latest"
      ]
    }
  }
}
```

**Linux**:
```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--network", "host",
        "-e", "JOBHISTORY_URL=http://localhost:19888/ws/v1/history",
        "jobhistory-mcp-server:latest"
      ]
    }
  }
}
```

---

## 构建优化

### 多阶段构建（可选）

如果需要更小的镜像，可以使用多阶段构建：

```dockerfile
# 构建阶段
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# 运行阶段
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY jobhistory_mcp.py .
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "jobhistory_mcp.py"]
```

### 查看镜像大小

```bash
docker images jobhistory-mcp-server
```

预期大小：约 150-200MB（基于 python:3.11-slim）

---

## 常用命令

### 构建

```bash
# 构建镜像
docker build -t jobhistory-mcp-server:latest .

# 构建并指定版本标签
docker build -t jobhistory-mcp-server:1.0.0 .

# 不使用缓存构建
docker build --no-cache -t jobhistory-mcp-server:latest .
```

### 运行

```bash
# 前台运行
docker run -e JOBHISTORY_URL="http://..." jobhistory-mcp-server:latest

# 后台运行
docker run -d --name jobhistory-mcp \
  -e JOBHISTORY_URL="http://..." \
  jobhistory-mcp-server:latest

# 查看日志
docker logs -f jobhistory-mcp

# 进入容器调试
docker exec -it jobhistory-mcp /bin/bash
```

### 管理

```bash
# 查看运行中的容器
docker ps | grep jobhistory

# 停止容器
docker stop jobhistory-mcp

# 删除容器
docker rm jobhistory-mcp

# 删除镜像
docker rmi jobhistory-mcp-server:latest
```

### Docker Compose

```bash
# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down

# 重新构建并启动
docker-compose up -d --build
```

---

## 发布镜像

### 推送到 Docker Hub

```bash
# 登录
docker login

# 标记镜像
docker tag jobhistory-mcp-server:latest yourusername/jobhistory-mcp-server:latest
docker tag jobhistory-mcp-server:latest yourusername/jobhistory-mcp-server:1.0.0

# 推送
docker push yourusername/jobhistory-mcp-server:latest
docker push yourusername/jobhistory-mcp-server:1.0.0
```

### 推送到私有仓库

```bash
# 标记镜像
docker tag jobhistory-mcp-server:latest registry.example.com/jobhistory-mcp-server:latest

# 推送
docker push registry.example.com/jobhistory-mcp-server:latest
```

---

## 故障排查

### 问题 1: 无法连接到 Hadoop 集群

**症状**: "无法连接到 JobHistory Server"

**排查步骤**:
```bash
# 1. 进入容器测试网络
docker run -it --rm jobhistory-mcp-server:latest /bin/bash
curl http://your-hadoop-cluster:19888/ws/v1/history/info

# 2. 检查 DNS 解析
docker run -it --rm jobhistory-mcp-server:latest nslookup your-hadoop-cluster
```

**解决方案**:
- 确认 JOBHISTORY_URL 正确
- 检查网络配置（host.docker.internal 或 --network host）
- 确认防火墙设置

### 问题 2: MCP 客户端无法启动 Docker 容器

**症状**: MCP 工具不可用

**排查步骤**:
```bash
# 手动测试 Docker 命令
docker run -i --rm -e JOBHISTORY_URL="http://..." jobhistory-mcp-server:latest
```

**解决方案**:
- 确认 Docker 已安装并运行
- 确认当前用户有 Docker 权限
- 检查 MCP 配置文件语法

### 问题 3: 容器启动后立即退出

**排查步骤**:
```bash
# 查看容器日志
docker logs <container_id>

# 交互模式运行调试
docker run -it --rm jobhistory-mcp-server:latest /bin/bash
python jobhistory_mcp.py
```

---

## 安全建议

1. **使用非 root 用户**: Dockerfile 已配置 `mcpuser` 用户
2. **最小化镜像**: 使用 slim 基础镜像
3. **限制资源**: 使用 `--memory` 和 `--cpus` 限制
4. **网络隔离**: 仅开放必要的网络访问
5. **定期更新**: 定期重建镜像以获取安全补丁

```bash
# 安全运行示例
docker run -it --rm \
  --read-only \
  --memory=256m \
  --cpus=0.5 \
  -e JOBHISTORY_URL="http://..." \
  jobhistory-mcp-server:latest
```

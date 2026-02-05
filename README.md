# JobHistory MCP Server

基于 Hadoop JobHistory Server REST API 的 MCP (Model Context Protocol) 服务器实现。

该服务允许 AI 助手（如 Claude、Cursor）通过 MCP 协议查询 Hadoop MapReduce 作业的历史信息。

## 功能特性

- 🔍 **作业查询**: 列出和搜索 MapReduce 作业，支持多种过滤条件
- 📊 **详细信息**: 获取作业、任务、尝试的完整详情
- 📈 **计数器查询**: 查看作业和任务的执行统计数据
- ⚙️ **配置查询**: 获取作业运行时的配置参数
- 🔄 **灵活输出**: 支持 Markdown（人类可读）和 JSON（程序处理）两种格式

## 部署方式

### 方式一：本地部署（stdio 模式）

适合 MCP Server 和客户端在同一台机器上运行。

#### 1. 安装依赖

```bash
cd JobHistoryMcpServer
pip install -r requirements.txt
```

#### 2. 配置环境变量

```bash
export JOBHISTORY_URL="http://your-history-server:19888/ws/v1/history"
```

#### 3. 配置 MCP 客户端

**Cursor** (`~/.cursor/mcp.json`)：

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "python",
      "args": ["/path/to/JobHistoryMcpServer/jobhistory_mcp.py"],
      "env": {
        "JOBHISTORY_URL": "http://your-history-server:19888/ws/v1/history"
      }
    }
  }
}
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`)：

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "python",
      "args": ["/path/to/JobHistoryMcpServer/jobhistory_mcp.py"],
      "env": {
        "JOBHISTORY_URL": "http://your-history-server:19888/ws/v1/history"
      }
    }
  }
}
```

---

### 方式二：远程服务器部署（HTTP 模式）

适合将 MCP Server 部署在靠近 Hadoop 集群的服务器，本地客户端通过 HTTP 远程连接。

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

#### 服务器端部署（使用 Conda）

##### 1. 上传项目到服务器

```bash
scp -r JobHistoryMcpServer user@server:/app/
```

##### 2. 创建 Conda 环境并安装依赖

```bash
# SSH 登录服务器
ssh user@server

# 创建并激活 conda 环境
conda create -n py310 python=3.10 -y
conda activate py310

# 安装依赖
cd /app/JobHistoryMcpServer
pip install -r requirements.txt
```

##### 3. 配置环境变量文件

创建 `/app/JobHistoryMcpServer/.env`：

```bash
JOBHISTORY_URL=http://your-hadoop-cluster:19888/ws/v1/history
MCP_TRANSPORT=http
MCP_HOST=0.0.0.0
MCP_PORT=8080
LOG_LEVEL=INFO
LOG_FILE=/app/JobHistoryMcpServer/logs/jobhistory_mcp.log
```

##### 4. 创建启动脚本

创建 `/app/JobHistoryMcpServer/start.sh`：

```bash
#!/bin/bash
# 激活 conda 环境
source /app/miniconda3/etc/profile.d/conda.sh
conda activate py310

# 验证 Python 版本
echo "Python version:"
python --version

# 启动服务
exec python /app/JobHistoryMcpServer/jobhistory_mcp.py --http
```

添加执行权限：

```bash
chmod +x /app/JobHistoryMcpServer/start.sh
```

##### 5. 配置 systemd 服务

创建 `/etc/systemd/system/jobhistory-mcp.service`：

```ini
[Unit]
Description=JobHistory MCP Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/app/JobHistoryMcpServer
EnvironmentFile=/app/JobHistoryMcpServer/.env
ExecStart=/app/JobHistoryMcpServer/start.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用并启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable jobhistory-mcp
sudo systemctl start jobhistory-mcp
sudo systemctl status jobhistory-mcp
```

##### 6. 验证服务运行

```bash
# 检查服务状态
systemctl status jobhistory-mcp

# 检查端口监听
ss -tlnp | grep 8080

# 测试 MCP 端点
curl http://localhost:8080/mcp
```

#### 本地客户端配置

**Cursor** (`~/.cursor/mcp.json`)：

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "url": "http://your-server-ip:8080/mcp"
    }
  }
}
```

**Claude Desktop**：

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "url": "http://your-server-ip:8080/mcp"
    }
  }
}
```

#### 安全建议

1. **防火墙规则**：只允许特定 IP 访问 MCP Server 端口
   ```bash
   sudo ufw allow from YOUR_LOCAL_IP to any port 8080
   ```

2. **使用 HTTPS**：生产环境建议通过 Nginx 反向代理添加 SSL

3. **网络隔离**：将 MCP Server 部署在可访问 Hadoop 集群的内网中

## 可用工具列表

| 工具名 | 功能描述 |
|--------|----------|
| `jobhistory_get_info` | 获取 JobHistory Server 基本信息 |
| `jobhistory_list_jobs` | 列出作业（支持过滤和分页） |
| `jobhistory_get_job` | 获取作业详情 |
| `jobhistory_get_job_counters` | 获取作业计数器 |
| `jobhistory_get_job_conf` | 获取作业配置 |
| `jobhistory_get_job_attempts` | 获取作业 AM 尝试列表 |
| `jobhistory_list_tasks` | 列出作业的任务 |
| `jobhistory_get_task` | 获取任务详情 |
| `jobhistory_get_task_counters` | 获取任务计数器 |
| `jobhistory_list_task_attempts` | 列出任务尝试 |
| `jobhistory_get_task_attempt` | 获取任务尝试详情 |
| `jobhistory_get_task_attempt_counters` | 获取任务尝试计数器 |

## 使用示例

### 示例 1: 查询最近的作业

```
请列出最近 10 个 MapReduce 作业
```

AI 助手会调用 `jobhistory_list_jobs` 工具，参数 `limit=10`。

### 示例 2: 查询失败的作业

```
查找所有失败的 MapReduce 作业
```

AI 助手会调用 `jobhistory_list_jobs` 工具，参数 `state="FAILED"`。

### 示例 3: 获取作业详情

```
获取作业 job_1326381300833_2_2 的详细信息
```

AI 助手会调用 `jobhistory_get_job` 工具。

### 示例 4: 分析作业性能

```
分析作业 job_xxx 的性能，包括任务执行时间和计数器
```

AI 助手会依次调用多个工具获取全面信息。

## 项目结构

```
JobHistoryMcpServer/
├── README.md                    # 项目说明文档
├── requirements.txt             # Python 依赖
├── jobhistory_mcp.py           # MCP Server 主代码
├── start.sh                     # 启动脚本
├── .env                         # 环境变量配置
└── docs/
    ├── REST_API.md             # JobHistory REST API 文档
    ├── CODE_EXPLANATION.md     # 代码详解
    └── LOGGING.md              # 日志配置指南
```

## 日志配置

日志系统记录工具调用和 REST 请求，支持滚动日志。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |
| `LOG_FILE` | `./logs/jobhistory_mcp.log` | 日志文件路径 |
| `LOG_MAX_SIZE` | `268435456` (256MB) | 单文件最大大小 |
| `LOG_BACKUP_COUNT` | `5` | 保留文件数量 |
| `LOG_TO_STDERR` | `true` | 是否输出到 stderr |

### 日志示例

```
2024-01-15 10:30:45 | INFO  | a1b2c3d4 | [TOOL_CALL] jobhistory_list_jobs, params: {"limit": 10}
2024-01-15 10:30:45 | INFO  | a1b2c3d4 | [REST_REQ] GET http://hadoop:19888/ws/v1/history/mapreduce/jobs?limit=10
2024-01-15 10:30:46 | INFO  | a1b2c3d4 | [REST_RSP] 200 OK, size: 1523 bytes, duration: 856.23ms
2024-01-15 10:30:46 | INFO  | a1b2c3d4 | [TOOL_RSP] success, size: 1856 bytes, duration: 892.45ms
```

详细说明请参考 [日志配置指南](docs/LOGGING.md)

## 文档

- [REST API 文档](docs/REST_API.md) - JobHistory Server REST API 完整说明
- [代码详解](docs/CODE_EXPLANATION.md) - 代码结构和实现说明
- [日志配置指南](docs/LOGGING.md) - 日志功能和配置说明

## 依赖

- Python 3.10+
- fastmcp >= 2.0.0
- pydantic >= 2.0.0
- httpx >= 0.25.0

## 许可证

MIT License

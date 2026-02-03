# JobHistory MCP Server

基于 Hadoop JobHistory Server REST API 的 MCP (Model Context Protocol) 服务器实现。

该服务允许 AI 助手（如 Claude、Cursor）通过 MCP 协议查询 Hadoop MapReduce 作业的历史信息。

## 功能特性

- 🔍 **作业查询**: 列出和搜索 MapReduce 作业，支持多种过滤条件
- 📊 **详细信息**: 获取作业、任务、尝试的完整详情
- 📈 **计数器查询**: 查看作业和任务的执行统计数据
- ⚙️ **配置查询**: 获取作业运行时的配置参数
- 🔄 **灵活输出**: 支持 Markdown（人类可读）和 JSON（程序处理）两种格式

## 快速开始

### 1. 安装依赖

```bash
cd JobHistoryMcpServer
pip install -r requirements.txt
```

### 2. 配置 JobHistory Server 地址

通过环境变量配置 JobHistory Server 的地址：

```bash
export JOBHISTORY_URL="http://your-history-server:19888/ws/v1/history"
```

默认地址为 `http://localhost:19888/ws/v1/history`

### 3. 运行服务

```bash
python jobhistory_mcp.py
```

## MCP 客户端配置

### Cursor 配置

在 `~/.cursor/mcp.json` 中添加：

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

### Claude Desktop 配置

在 `~/Library/Application Support/Claude/claude_desktop_config.json` 中添加：

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
├── Dockerfile                   # Docker 镜像构建文件
├── docker-compose.yml          # Docker Compose 配置
├── .dockerignore               # Docker 忽略文件
└── docs/
    ├── REST_API.md             # JobHistory REST API 文档
    ├── MCP_USAGE.md            # MCP 使用说明
    ├── CODE_EXPLANATION.md     # 代码详解
    └── DOCKER.md               # Docker 部署指南
```

## Docker 部署

### 构建镜像

```bash
cd JobHistoryMcpServer
docker build -t jobhistory-mcp-server:latest .
```

### 运行容器

```bash
docker run -i --rm \
  -e JOBHISTORY_URL="http://your-hadoop-cluster:19888/ws/v1/history" \
  jobhistory-mcp-server:latest
```

### Cursor MCP 配置（Docker 方式）

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "JOBHISTORY_URL=http://your-hadoop-cluster:19888/ws/v1/history",
        "jobhistory-mcp-server:latest"
      ]
    }
  }
}
```

详细说明请参考 [Docker 部署指南](docs/DOCKER.md)

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
- [MCP 使用说明](docs/MCP_USAGE.md) - MCP Server 配置和使用指南
- [代码详解](docs/CODE_EXPLANATION.md) - 代码结构和实现说明
- [Docker 部署指南](docs/DOCKER.md) - Docker 构建和部署说明
- [日志配置指南](docs/LOGGING.md) - 日志功能和配置说明

## 依赖

- Python 3.9+
- mcp >= 1.0.0 (FastMCP)
- pydantic >= 2.0.0
- httpx >= 0.25.0

## 许可证

MIT License

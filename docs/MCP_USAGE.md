# MCP Server 使用说明

本文档介绍如何配置和使用 JobHistory MCP Server。

## 什么是 MCP

MCP (Model Context Protocol) 是一种开放协议，允许 AI 助手与外部工具和数据源进行交互。通过 MCP，AI 可以：

- 调用外部工具执行操作
- 访问外部数据源获取信息
- 与外部服务进行交互

JobHistory MCP Server 将 Hadoop JobHistory Server 的 REST API 封装为 MCP 工具，使 AI 助手能够查询 MapReduce 作业历史。

---

## 安装配置

### 前置要求

1. **Python 环境**: Python 3.9 或更高版本
2. **Hadoop 集群**: 运行中的 JobHistory Server
3. **MCP 客户端**: Cursor、Claude Desktop 或其他支持 MCP 的客户端

### 安装步骤

```bash
# 1. 克隆或下载项目
cd /path/to/JobHistoryMcpServer

# 2. 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # macOS/Linux
# 或 Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 验证安装
python jobhistory_mcp.py --help
```

### 配置 JobHistory Server 地址

通过环境变量 `JOBHISTORY_URL` 配置 JobHistory Server 地址：

```bash
# 方式 1: 导出环境变量
export JOBHISTORY_URL="http://your-hadoop-cluster:19888/ws/v1/history"

# 方式 2: 在命令行指定
JOBHISTORY_URL="http://localhost:19888/ws/v1/history" python jobhistory_mcp.py
```

默认地址为 `http://localhost:19888/ws/v1/history`

---

## 客户端配置

### Cursor 配置

1. 打开 Cursor 设置
2. 找到 MCP 配置文件位置: `~/.cursor/mcp.json`
3. 添加以下配置:

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "python",
      "args": [
        "/Users/winston/Library/Mobile Documents/com~apple~CloudDocs/work/code/PycharmProjects/JobHistoryMcpServer/jobhistory_mcp.py"
      ],
      "env": {
        "JOBHISTORY_URL": "http://your-hadoop-cluster:19888/ws/v1/history"
      }
    }
  }
}
```

4. 重启 Cursor

### Claude Desktop 配置

1. 找到配置文件:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. 添加以下配置:

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "python",
      "args": [
        "/path/to/JobHistoryMcpServer/jobhistory_mcp.py"
      ],
      "env": {
        "JOBHISTORY_URL": "http://your-hadoop-cluster:19888/ws/v1/history"
      }
    }
  }
}
```

3. 重启 Claude Desktop

### 使用虚拟环境

如果使用虚拟环境，需要指定虚拟环境中的 Python 路径:

```json
{
  "mcpServers": {
    "jobhistory_mcp": {
      "command": "/path/to/JobHistoryMcpServer/venv/bin/python",
      "args": [
        "/path/to/JobHistoryMcpServer/jobhistory_mcp.py"
      ],
      "env": {
        "JOBHISTORY_URL": "http://your-hadoop-cluster:19888/ws/v1/history"
      }
    }
  }
}
```

---

## 可用工具

### 服务器信息

#### jobhistory_get_info

获取 JobHistory Server 的基本信息，包括版本和启动时间。

**参数**: 无

**使用场景**: 检查服务是否可用

**示例对话**:
```
用户: 检查 JobHistory Server 状态
AI: [调用 jobhistory_get_info]
返回服务器版本、启动时间等信息
```

---

### 作业查询

#### jobhistory_list_jobs

列出 MapReduce 作业，支持多种过滤条件。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| user | string | 否 | 按用户过滤 |
| state | enum | 否 | 按状态过滤 (SUCCEEDED/FAILED/KILLED) |
| queue | string | 否 | 按队列过滤 |
| limit | int | 否 | 返回数量限制 (默认 20) |
| started_time_begin | int | 否 | 开始时间范围起点 |
| started_time_end | int | 否 | 开始时间范围终点 |
| finished_time_begin | int | 否 | 结束时间范围起点 |
| finished_time_end | int | 否 | 结束时间范围终点 |
| response_format | enum | 否 | 输出格式 (markdown/json) |

**使用场景**:
- 查看最近的作业
- 查找失败的作业
- 查找特定用户的作业

**示例对话**:
```
用户: 列出最近 5 个 MapReduce 作业
AI: [调用 jobhistory_list_jobs, limit=5]

用户: 查找用户 hadoop 的失败作业
AI: [调用 jobhistory_list_jobs, user="hadoop", state="FAILED"]

用户: 查看 default 队列的作业
AI: [调用 jobhistory_list_jobs, queue="default"]
```

---

#### jobhistory_get_job

获取指定作业的详细信息。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| response_format | enum | 否 | 输出格式 |

**使用场景**:
- 查看作业执行详情
- 分析作业性能
- 查看作业失败原因

**示例对话**:
```
用户: 获取作业 job_1326381300833_2_2 的详细信息
AI: [调用 jobhistory_get_job, job_id="job_1326381300833_2_2"]
```

---

#### jobhistory_get_job_counters

获取作业的计数器信息。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| response_format | enum | 否 | 输出格式 |

**使用场景**:
- 分析作业 I/O 性能
- 查看任务执行统计
- 排查数据倾斜问题

---

#### jobhistory_get_job_conf

获取作业的配置信息。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| filter_key | string | 否 | 配置键名过滤 |
| response_format | enum | 否 | 输出格式 |

**使用场景**:
- 查看作业运行配置
- 排查配置问题
- 审计作业参数

**示例对话**:
```
用户: 查看作业的内存配置
AI: [调用 jobhistory_get_job_conf, job_id="...", filter_key="memory"]

用户: 查看 MapReduce 相关配置
AI: [调用 jobhistory_get_job_conf, job_id="...", filter_key="mapreduce"]
```

---

#### jobhistory_get_job_attempts

获取作业的 AM 尝试列表。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| response_format | enum | 否 | 输出格式 |

---

### 任务查询

#### jobhistory_list_tasks

列出作业的任务。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| task_type | enum | 否 | 任务类型 (m/r) |
| response_format | enum | 否 | 输出格式 |

**示例对话**:
```
用户: 列出作业的所有 Map 任务
AI: [调用 jobhistory_list_tasks, job_id="...", task_type="m"]
```

---

#### jobhistory_get_task

获取任务详情。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| task_id | string | 是 | 任务 ID |
| response_format | enum | 否 | 输出格式 |

---

#### jobhistory_get_task_counters

获取任务计数器。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| task_id | string | 是 | 任务 ID |
| response_format | enum | 否 | 输出格式 |

---

### 任务尝试查询

#### jobhistory_list_task_attempts

列出任务的尝试。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| task_id | string | 是 | 任务 ID |
| response_format | enum | 否 | 输出格式 |

---

#### jobhistory_get_task_attempt

获取任务尝试详情。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| task_id | string | 是 | 任务 ID |
| attempt_id | string | 是 | 尝试 ID |
| response_format | enum | 否 | 输出格式 |

---

#### jobhistory_get_task_attempt_counters

获取任务尝试计数器。

**参数**:

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| job_id | string | 是 | 作业 ID |
| task_id | string | 是 | 任务 ID |
| attempt_id | string | 是 | 尝试 ID |
| response_format | enum | 否 | 输出格式 |

---

## 使用示例

### 示例 1: 日常监控

```
用户: 查看最近运行的 MapReduce 作业情况

AI 会执行:
1. 调用 jobhistory_list_jobs 获取最近的作业列表
2. 返回包含作业名称、状态、用户、执行时间等信息的表格
```

### 示例 2: 故障排查

```
用户: 帮我分析为什么 job_xxx 失败了

AI 会执行:
1. 调用 jobhistory_get_job 获取作业详情和诊断信息
2. 调用 jobhistory_list_tasks 查看哪些任务失败
3. 调用 jobhistory_list_task_attempts 查看失败任务的尝试
4. 综合分析并给出失败原因和建议
```

### 示例 3: 性能分析

```
用户: 分析 job_xxx 的性能瓶颈

AI 会执行:
1. 调用 jobhistory_get_job 查看平均任务执行时间
2. 调用 jobhistory_get_job_counters 查看 I/O 计数器
3. 调用 jobhistory_list_tasks 找出执行时间最长的任务
4. 分析数据并给出优化建议
```

### 示例 4: 配置审计

```
用户: 检查 job_xxx 的内存配置是否合理

AI 会执行:
1. 调用 jobhistory_get_job_conf 并过滤内存相关配置
2. 调用 jobhistory_get_job_counters 查看实际内存使用
3. 对比配置和实际使用，给出优化建议
```

---

## 常见问题

### Q1: 无法连接到 JobHistory Server

**错误信息**: "无法连接到 JobHistory Server"

**解决方法**:
1. 检查 JobHistory Server 是否启动: `jps | grep JobHistoryServer`
2. 检查环境变量 `JOBHISTORY_URL` 是否正确
3. 检查网络连接: `curl http://your-server:19888/ws/v1/history/info`

### Q2: 找不到作业

**错误信息**: "资源未找到"

**可能原因**:
1. 作业 ID 不正确
2. 作业历史已被清理（超过保留期限）
3. 作业尚未完成（仍在运行中，需要使用 YARN API）

### Q3: MCP 工具未加载

**检查步骤**:
1. 确认配置文件路径正确
2. 确认 Python 路径正确
3. 重启 MCP 客户端
4. 查看客户端日志

### Q4: 权限问题

**错误信息**: "权限不足"

**解决方法**:
1. 检查 Hadoop 集群的安全配置
2. 如果启用了 Kerberos，需要额外配置认证

---

## 进阶配置

### 超时设置

在代码中修改 `REQUEST_TIMEOUT` 常量:

```python
REQUEST_TIMEOUT = 60.0  # 增加到 60 秒
```

### 日志调试

启用详细日志:

```bash
PYTHONPATH=. python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from jobhistory_mcp import mcp
mcp.run()
"
```

### 自定义输出格式

所有工具支持 `response_format` 参数:
- `markdown`: 人类可读格式（默认）
- `json`: 机器可读格式，便于进一步处理

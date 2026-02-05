# 日志配置指南

本文档介绍 JobHistory MCP Server 的日志功能和配置方法。

## 概述

日志系统记录以下信息：
1. **工具调用日志**: 来自 LLM 的 MCP 工具调用请求
2. **REST 请求日志**: 向 JobHistory Server 发出的 HTTP 请求
3. **容器日志请求**: 获取任务容器日志的 HTTP 请求
4. **错误日志**: 执行过程中的异常和错误

## 日志格式

```
时间戳 | 日志级别 | 请求ID | 消息内容
```

**示例**:
```
2024-01-15 10:30:45 | INFO  | a1b2c3d4 | [TOOL_CALL] jobhistory_list_jobs, params: {"limit": 10, "state": "FAILED"}
2024-01-15 10:30:45 | INFO  | a1b2c3d4 | [REST_REQ] GET http://hadoop:19888/ws/v1/history/mapreduce/jobs?limit=10&state=FAILED
2024-01-15 10:30:46 | INFO  | a1b2c3d4 | [REST_RSP] 200 OK, size: 1523 bytes, duration: 856.23ms
2024-01-15 10:30:46 | INFO  | a1b2c3d4 | [TOOL_RSP] success, size: 1856 bytes, duration: 892.45ms
```

## 日志标签说明

| 标签 | 说明 |
|------|------|
| `[TOOL_CALL]` | MCP 工具调用开始 |
| `[TOOL_RSP]` | MCP 工具调用成功响应 |
| `[TOOL_ERR]` | MCP 工具调用错误 |
| `[REST_REQ]` | 发送 REST API 请求 |
| `[REST_RSP]` | 收到 REST API 响应 |
| `[REST_ERR]` | REST API 请求错误 |

## 请求 ID

每个工具调用会生成一个 8 位的唯一请求 ID（如 `a1b2c3d4`），用于关联同一请求的所有日志，便于问题追踪。

---

## 配置方式

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 日志级别：DEBUG, INFO, WARNING, ERROR |
| `LOG_FILE` | `./logs/jobhistory_mcp.log` | 日志文件路径 |
| `LOG_MAX_SIZE` | `268435456` (256MB) | 单个日志文件最大大小（字节） |
| `LOG_BACKUP_COUNT` | `5` | 保留的历史日志文件数量 |
| `LOG_TO_STDERR` | `true` | 是否同时输出到 stderr |

### 日志级别说明

| 级别 | 说明 |
|------|------|
| `DEBUG` | 详细调试信息，包括完整的请求/响应内容 |
| `INFO` | 常规操作信息（推荐生产环境使用） |
| `WARNING` | 警告信息，如请求重试、超时等 |
| `ERROR` | 错误信息，请求失败、异常等 |

---

## 滚动日志

日志系统使用 `RotatingFileHandler` 实现滚动：

- **按大小滚动**: 单个文件达到 `LOG_MAX_SIZE`（默认 256MB）后创建新文件
- **文件保留**: 最多保留 `LOG_BACKUP_COUNT`（默认 5）个历史文件

**日志文件命名**:
```
jobhistory_mcp.log          # 当前日志
jobhistory_mcp.log.1        # 上一个滚动文件
jobhistory_mcp.log.2        # 更早的滚动文件
jobhistory_mcp.log.3
jobhistory_mcp.log.4
jobhistory_mcp.log.5        # 最老的文件（之后会被删除）
```

**磁盘空间计算**:
```
最大磁盘占用 = LOG_MAX_SIZE × (LOG_BACKUP_COUNT + 1)
默认配置 = 256MB × 6 = 1.5GB
```

---

## 日志分析

### 查看最近的错误

```bash
# 查看最近的错误日志
grep "ERROR\|ERR\]" logs/jobhistory_mcp.log | tail -20

# 查看特定请求 ID 的所有日志
grep "a1b2c3d4" logs/jobhistory_mcp.log
```

### 统计工具调用

```bash
# 统计各工具的调用次数
grep "\[TOOL_CALL\]" logs/jobhistory_mcp.log | awk '{print $6}' | sort | uniq -c | sort -rn

# 查看平均响应时间
grep "\[TOOL_RSP\]" logs/jobhistory_mcp.log | grep -oP 'duration: \K[0-9.]+' | awk '{sum+=$1; count++} END {print "平均响应时间:", sum/count, "ms"}'
```

### 监控日志

```bash
# 实时监控日志
tail -f logs/jobhistory_mcp.log

# 实时监控错误
tail -f logs/jobhistory_mcp.log | grep --line-buffered "ERROR\|ERR\]"
```

---

## 常见问题

### Q1: 日志文件未创建

**可能原因**:
1. 目录不存在或无写入权限
2. Docker 卷挂载问题

**解决方法**:
```bash
# 创建日志目录
mkdir -p logs
chmod 755 logs

# Docker 中检查挂载
docker exec -it <container> ls -la /app/logs
```

### Q2: 日志输出到 stdout 导致 MCP 通信失败

**原因**: MCP stdio 模式使用 stdout 进行协议通信，日志不能输出到 stdout。

**解决方法**: 日志系统已设计为只输出到 stderr 和文件，不会影响 MCP 通信。

### Q3: 日志文件过大

**解决方法**:
```bash
# 减小单文件大小
export LOG_MAX_SIZE=134217728  # 128MB

# 减少保留数量
export LOG_BACKUP_COUNT=3
```

### Q4: 日志中没有请求 ID

**可能原因**: 日志在请求上下文之外记录。

**说明**: 服务启动时的日志（如初始化信息）不在请求上下文中，显示为 `-`。

---

## 日志示例

### 正常请求

```
2024-01-15 10:30:45 | INFO  | -        | JobHistory MCP Server 初始化
2024-01-15 10:30:45 | INFO  | -        | JobHistory URL: http://hadoop:19888/ws/v1/history
2024-01-15 10:30:45 | INFO  | -        | Logs Base URL: http://hadoop:19888/jobhistory/logs
2024-01-15 10:30:45 | INFO  | -        | NodeManager Port: 8052
2024-01-15 10:30:45 | INFO  | -        | 请求超时: 30.0s
2024-01-15 10:31:00 | INFO  | a1b2c3d4 | [TOOL_CALL] jobhistory_list_jobs, params: {"limit": 10}
2024-01-15 10:31:00 | INFO  | a1b2c3d4 | [REST_REQ] GET http://hadoop:19888/ws/v1/history/mapreduce/jobs?limit=10
2024-01-15 10:31:01 | INFO  | a1b2c3d4 | [REST_RSP] 200 OK, size: 4523 bytes, duration: 856.23ms
2024-01-15 10:31:01 | INFO  | a1b2c3d4 | [TOOL_RSP] success, size: 5234 bytes, duration: 892.45ms
```

### 请求失败

```
2024-01-15 10:32:00 | INFO  | b2c3d4e5 | [TOOL_CALL] jobhistory_get_job, params: {"job_id": "job_invalid"}
2024-01-15 10:32:00 | INFO  | b2c3d4e5 | [REST_REQ] GET http://hadoop:19888/ws/v1/history/mapreduce/jobs/job_invalid
2024-01-15 10:32:00 | WARN  | b2c3d4e5 | [REST_ERR] HTTP 404, duration: 123.45ms
2024-01-15 10:32:00 | INFO  | b2c3d4e5 | [TOOL_RSP] success, size: 89 bytes, duration: 145.67ms
```

### 连接超时

```
2024-01-15 10:33:00 | INFO  | c3d4e5f6 | [TOOL_CALL] jobhistory_get_info, params: {}
2024-01-15 10:33:00 | INFO  | c3d4e5f6 | [REST_REQ] GET http://hadoop:19888/ws/v1/history/info
2024-01-15 10:33:30 | WARN  | c3d4e5f6 | [REST_ERR] Timeout after 30000.12ms
2024-01-15 10:33:30 | INFO  | c3d4e5f6 | [TOOL_RSP] success, size: 156 bytes, duration: 30023.45ms
```

### 获取容器日志（部分读取）

```
2024-01-15 10:35:00 | INFO  | d4e5f6g7 | [TOOL_CALL] jobhistory_get_task_attempt_logs_partial, params: {"job_id": "job_xxx", "task_id": "task_xxx", "attempt_id": "attempt_xxx", "log_type": "syslog", "start": -4096}
2024-01-15 10:35:00 | INFO  | d4e5f6g7 | [REST_REQ] GET http://hadoop:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks/task_xxx/attempts/attempt_xxx
2024-01-15 10:35:00 | INFO  | d4e5f6g7 | [REST_RSP] 200 OK, size: 523 bytes, duration: 45.23ms
2024-01-15 10:35:00 | INFO  | d4e5f6g7 | [REST_REQ] GET http://hadoop:19888/ws/v1/history/mapreduce/jobs/job_xxx
2024-01-15 10:35:00 | INFO  | d4e5f6g7 | [REST_RSP] 200 OK, size: 1234 bytes, duration: 32.15ms
2024-01-15 10:35:00 | INFO  | d4e5f6g7 | 获取部分日志 URL: http://hadoop:19888/jobhistory/logs/node01:8052/container_xxx/attempt_xxx/user/syslog/?start=-4096
2024-01-15 10:35:01 | INFO  | d4e5f6g7 | [REST_REQ] GET http://hadoop:19888/jobhistory/logs/node01:8052/container_xxx/attempt_xxx/user/syslog/?start=-4096
2024-01-15 10:35:01 | INFO  | d4e5f6g7 | [REST_RSP] 200 OK, size: 8234 bytes, duration: 256.78ms
2024-01-15 10:35:01 | INFO  | d4e5f6g7 | [TOOL_RSP] success, size: 4523 bytes, duration: 356.45ms
```

### 获取容器日志（完整读取）

```
2024-01-15 10:36:00 | INFO  | e5f6g7h8 | [TOOL_CALL] jobhistory_get_task_attempt_logs, params: {"job_id": "job_xxx", "task_id": "task_xxx", "attempt_id": "attempt_xxx", "log_type": "stdout"}
2024-01-15 10:36:00 | INFO  | e5f6g7h8 | [REST_REQ] GET http://hadoop:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks/task_xxx/attempts/attempt_xxx
2024-01-15 10:36:00 | INFO  | e5f6g7h8 | [REST_RSP] 200 OK, size: 523 bytes, duration: 45.23ms
2024-01-15 10:36:00 | INFO  | e5f6g7h8 | [REST_REQ] GET http://hadoop:19888/ws/v1/history/mapreduce/jobs/job_xxx
2024-01-15 10:36:00 | INFO  | e5f6g7h8 | [REST_RSP] 200 OK, size: 1234 bytes, duration: 32.15ms
2024-01-15 10:36:00 | INFO  | e5f6g7h8 | 获取日志 URL: http://hadoop:19888/jobhistory/logs/node01:8052/container_xxx/attempt_xxx/user/stdout/?start=0&start.time=0&end.time=9223372036854775807
2024-01-15 10:36:01 | INFO  | e5f6g7h8 | [REST_REQ] GET http://hadoop:19888/jobhistory/logs/node01:8052/container_xxx/attempt_xxx/user/stdout/?start=0&start.time=0&end.time=9223372036854775807
2024-01-15 10:36:03 | INFO  | e5f6g7h8 | [REST_RSP] 200 OK, size: 1523456 bytes, duration: 2156.78ms
2024-01-15 10:36:03 | INFO  | e5f6g7h8 | [TOOL_RSP] success, size: 1234567 bytes, duration: 2356.45ms
```

> **注意**: 完整日志可能非常大，建议优先使用部分读取工具 `jobhistory_get_task_attempt_logs_partial` 来避免消耗过多 Token。

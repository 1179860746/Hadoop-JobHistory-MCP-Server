# Hadoop JobHistory Server REST API 文档

本文档详细描述了 Hadoop JobHistory Server 提供的 REST API 接口，这些接口被 MCP Server 封装使用。

## 概述

JobHistory Server 是 Hadoop MapReduce 框架的一个组件，用于存储和查询已完成作业的历史信息。它提供 REST API 供外部程序查询作业状态、任务信息、计数器等数据。

### 基础信息

- **默认端口**: 19888
- **基础路径**: `/ws/v1/history`
- **完整 URL**: `http://<history-server>:19888/ws/v1/history`
- **支持格式**: JSON 和 XML（通过 Accept 请求头指定）

---

## API 端点列表

### 1. History Server 信息 API

#### 获取服务器信息

获取 JobHistory Server 的基本信息。

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history` 或 `/ws/v1/history/info` |
| **HTTP 方法** | GET |
| **查询参数** | 无 |

**响应字段 (historyInfo 对象)**:

| 字段 | 类型 | 描述 |
|------|------|------|
| startedOn | long | 服务启动时间（毫秒时间戳） |
| hadoopVersion | string | Hadoop 版本号 |
| hadoopBuildVersion | string | Hadoop 构建版本信息 |
| hadoopVersionBuiltOn | string | Hadoop 构建时间 |

**示例请求**:

```bash
curl -H "Accept: application/json" \
  http://localhost:19888/ws/v1/history/info
```

**示例响应**:

```json
{
  "historyInfo": {
    "startedOn": 1353512830963,
    "hadoopVersion": "3.2.2",
    "hadoopBuildVersion": "3.2.2 from xxx",
    "hadoopVersionBuiltOn": "2021-01-01T00:00:00Z"
  }
}
```

---

### 2. Jobs API（作业相关）

#### 2.1 列出作业

获取已完成的 MapReduce 作业列表。

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs` |
| **HTTP 方法** | GET |

**查询参数**:

| 参数 | 类型 | 描述 |
|------|------|------|
| user | string | 按用户名过滤 |
| state | string | 按状态过滤（NEW, INITED, RUNNING, SUCCEEDED, FAILED, KILLED） |
| queue | string | 按队列名过滤 |
| limit | int | 返回的最大作业数 |
| startedTimeBegin | long | 开始时间范围起点（毫秒时间戳） |
| startedTimeEnd | long | 开始时间范围终点（毫秒时间戳） |
| finishedTimeBegin | long | 结束时间范围起点（毫秒时间戳） |
| finishedTimeEnd | long | 结束时间范围终点（毫秒时间戳） |

**示例请求**:

```bash
# 获取最近 10 个作业
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs?limit=10"

# 获取用户 hadoop 的失败作业
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs?user=hadoop&state=FAILED"

# 获取指定时间范围内的作业
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs?startedTimeBegin=1609459200000&startedTimeEnd=1609545600000"
```

**响应字段（作业列表简要信息）**:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | string | 作业 ID |
| name | string | 作业名称 |
| user | string | 提交用户 |
| queue | string | 队列名称 |
| state | string | 作业状态 |
| startTime | long | 开始时间 |
| finishTime | long | 结束时间 |
| mapsTotal | int | Map 任务总数 |
| mapsCompleted | int | 已完成 Map 任务数 |
| reducesTotal | int | Reduce 任务总数 |
| reducesCompleted | int | 已完成 Reduce 任务数 |

---

#### 2.2 获取作业详情

获取指定作业的详细信息。

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}` |
| **HTTP 方法** | GET |
| **路径参数** | jobid - 作业 ID |

**响应字段（完整作业信息）**:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | string | 作业 ID |
| name | string | 作业名称 |
| user | string | 提交用户 |
| queue | string | 队列名称 |
| state | string | 作业状态 |
| diagnostics | string | 诊断信息 |
| submitTime | long | 提交时间 |
| startTime | long | 开始时间 |
| finishTime | long | 结束时间 |
| mapsTotal | int | Map 任务总数 |
| mapsCompleted | int | 已完成 Map 数 |
| reducesTotal | int | Reduce 任务总数 |
| reducesCompleted | int | 已完成 Reduce 数 |
| uberized | boolean | 是否使用 Uber 模式 |
| avgMapTime | long | 平均 Map 时间（毫秒） |
| avgReduceTime | long | 平均 Reduce 时间（毫秒） |
| avgShuffleTime | long | 平均 Shuffle 时间（毫秒） |
| avgMergeTime | long | 平均 Merge 时间（毫秒） |
| failedMapAttempts | int | 失败的 Map 尝试数 |
| killedMapAttempts | int | 被终止的 Map 尝试数 |
| successfulMapAttempts | int | 成功的 Map 尝试数 |
| failedReduceAttempts | int | 失败的 Reduce 尝试数 |
| killedReduceAttempts | int | 被终止的 Reduce 尝试数 |
| successfulReduceAttempts | int | 成功的 Reduce 尝试数 |
| acls | array | 访问控制列表 |

**示例请求**:

```bash
curl http://localhost:19888/ws/v1/history/mapreduce/jobs/job_1326381300833_2_2
```

---

#### 2.3 获取作业尝试列表

获取作业的 ApplicationMaster 尝试列表。

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}/jobattempts` |
| **HTTP 方法** | GET |

**响应字段（jobAttempt 对象）**:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | int | 尝试 ID |
| nodeId | string | 节点 ID |
| nodeHttpAddress | string | 节点 HTTP 地址 |
| logsLink | string | 日志链接 |
| containerId | string | 容器 ID |
| startTime | long | 开始时间 |

---

#### 2.4 获取作业计数器

获取作业的所有计数器信息。

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}/counters` |
| **HTTP 方法** | GET |

**响应字段**:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | string | 作业 ID |
| counterGroup | array | 计数器组列表 |

**counterGroup 对象**:

| 字段 | 类型 | 描述 |
|------|------|------|
| counterGroupName | string | 计数器组名称 |
| counter | array | 计数器列表 |

**counter 对象**:

| 字段 | 类型 | 描述 |
|------|------|------|
| name | string | 计数器名称 |
| mapCounterValue | long | Map 阶段值 |
| reduceCounterValue | long | Reduce 阶段值 |
| totalCounterValue | long | 总值 |

**常见计数器组**:

- `org.apache.hadoop.mapreduce.FileSystemCounter` - 文件系统计数器
- `org.apache.hadoop.mapreduce.TaskCounter` - 任务计数器
- `Shuffle Errors` - Shuffle 错误计数器
- `org.apache.hadoop.mapreduce.lib.input.FileInputFormatCounter` - 输入格式计数器
- `org.apache.hadoop.mapreduce.lib.output.FileOutputFormatCounter` - 输出格式计数器

---

#### 2.5 获取作业配置

获取作业的配置信息。

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}/conf` |
| **HTTP 方法** | GET |

**响应字段**:

| 字段 | 类型 | 描述 |
|------|------|------|
| path | string | 配置文件路径 |
| property | array | 配置属性列表 |

**property 对象**:

| 字段 | 类型 | 描述 |
|------|------|------|
| name | string | 配置名称 |
| value | string | 配置值 |
| source | array | 配置来源 |

---

### 3. Tasks API（任务相关）

#### 3.1 列出任务

获取作业的任务列表。

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}/tasks` |
| **HTTP 方法** | GET |

**查询参数**:

| 参数 | 类型 | 描述 |
|------|------|------|
| type | string | 任务类型过滤：m（Map）或 r（Reduce） |

**响应字段（task 对象）**:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | string | 任务 ID |
| type | string | 任务类型（MAP 或 REDUCE） |
| state | string | 任务状态 |
| successfulAttempt | string | 成功的尝试 ID |
| progress | float | 进度百分比 |
| startTime | long | 开始时间 |
| finishTime | long | 结束时间 |
| elapsedTime | long | 耗时（毫秒） |

**示例请求**:

```bash
# 获取所有任务
curl http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks

# 只获取 Map 任务
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks?type=m"

# 只获取 Reduce 任务
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks?type=r"
```

---

#### 3.2 获取任务详情

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}/tasks/{taskid}` |
| **HTTP 方法** | GET |

---

#### 3.3 获取任务计数器

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}/tasks/{taskid}/counters` |
| **HTTP 方法** | GET |

---

### 4. Task Attempts API（任务尝试相关）

#### 4.1 列出任务尝试

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}/tasks/{taskid}/attempts` |
| **HTTP 方法** | GET |

**响应字段（taskAttempt 对象）**:

| 字段 | 类型 | 描述 |
|------|------|------|
| id | string | 尝试 ID |
| rack | string | 机架位置 |
| state | string | 尝试状态 |
| type | string | 任务类型 |
| assignedContainerId | string | 分配的容器 ID |
| nodeHttpAddress | string | 节点 HTTP 地址 |
| diagnostics | string | 诊断信息 |
| progress | float | 进度 |
| startTime | long | 开始时间 |
| finishTime | long | 结束时间 |
| elapsedTime | long | 耗时 |

**Reduce 任务尝试额外字段**:

| 字段 | 类型 | 描述 |
|------|------|------|
| shuffleFinishTime | long | Shuffle 完成时间 |
| mergeFinishTime | long | Merge 完成时间 |
| elapsedShuffleTime | long | Shuffle 耗时 |
| elapsedMergeTime | long | Merge 耗时 |
| elapsedReduceTime | long | Reduce 耗时 |

---

#### 4.2 获取任务尝试详情

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}/tasks/{taskid}/attempts/{attemptid}` |
| **HTTP 方法** | GET |

---

#### 4.3 获取任务尝试计数器

| 属性 | 值 |
|------|-----|
| **URI** | `/ws/v1/history/mapreduce/jobs/{jobid}/tasks/{taskid}/attempts/{attemptid}/counters` |
| **HTTP 方法** | GET |

---

## 状态码说明

| 状态码 | 描述 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 未认证（安全模式下） |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

---

## ID 格式说明

### 作业 ID (Job ID)

格式: `job_{clusterTimestamp}_{jobId}_{attemptId}`

示例: `job_1326381300833_2_2`

- `1326381300833`: 集群时间戳
- `2`: 作业序号
- `2`: 尝试序号

### 任务 ID (Task ID)

格式: `task_{clusterTimestamp}_{jobId}_{attemptId}_{taskType}_{taskId}`

示例: `task_1326381300833_2_2_m_0`

- `m`: Map 任务
- `r`: Reduce 任务
- `0`: 任务序号

### 尝试 ID (Attempt ID)

格式: `attempt_{clusterTimestamp}_{jobId}_{attemptId}_{taskType}_{taskId}_{attemptNum}`

示例: `attempt_1326381300833_2_2_m_0_0`

- 最后的 `0`: 尝试序号

---

## 常见使用场景

### 场景 1: 监控作业执行情况

```bash
# 1. 获取正在运行的作业
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs?state=RUNNING"

# 2. 获取作业详情
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx"

# 3. 查看任务进度
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks"
```

### 场景 2: 分析失败作业

```bash
# 1. 查找失败作业
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs?state=FAILED"

# 2. 获取失败作业的详细信息（包含诊断信息）
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx"

# 3. 查看失败的任务
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks"

# 4. 获取失败任务的尝试信息
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks/task_xxx/attempts"
```

### 场景 3: 性能分析

```bash
# 1. 获取作业计数器
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx/counters"

# 2. 获取任务执行时间
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks"

# 3. 分析 Reduce 任务的 Shuffle/Merge/Reduce 阶段时间
curl "http://localhost:19888/ws/v1/history/mapreduce/jobs/job_xxx/tasks/task_xxx_r_0/attempts"
```

---

## 参考资源

- [Apache Hadoop 官方文档](https://hadoop.apache.org/docs/current/hadoop-mapreduce-client/hadoop-mapreduce-client-hs/HistoryServerRest.html)
- [YARN REST API](https://hadoop.apache.org/docs/current/hadoop-yarn/hadoop-yarn-site/ResourceManagerRest.html)

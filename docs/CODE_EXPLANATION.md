# 代码详解

本文档详细解释 JobHistory MCP Server 的代码结构和实现原理。

## 项目概述

JobHistory MCP Server 是一个基于 Python FastMCP 框架实现的 MCP 服务器，它将 Hadoop JobHistory Server 的 REST API 封装为 MCP 工具，使 AI 助手能够查询 MapReduce 作业历史。

### 技术栈

- **FastMCP**: MCP Python SDK 提供的高级框架
- **Pydantic v2**: 用于输入参数验证
- **httpx**: 异步 HTTP 客户端
- **Python 3.9+**: 运行环境

---

## 代码结构

```
jobhistory_mcp.py
├── 日志配置（setup_logging, RequestIdFilter）
├── 配置常量（JOBHISTORY_BASE_URL, NODEMANAGER_PORT, LOGS_BASE_URL 等）
├── 日志装饰器（log_tool_call）
├── MCP Server 初始化
├── 枚举类型定义（ResponseFormat, JobState, TaskType, TaskState, LogType）
├── Pydantic 输入模型（ListJobsInput, GetJobInput, GetTaskAttemptLogsInput 等）
├── 工具函数（_make_request, _handle_error, _format_*, _extract_*, _fetch_logs_html）
└── MCP 工具定义（14 个工具）
```

---

## 详细代码解析

### 1. 配置常量

```python
# JobHistory Server 地址，可通过环境变量配置
JOBHISTORY_BASE_URL = os.getenv(
    "JOBHISTORY_URL",
    "http://localhost:19888/ws/v1/history"
)

# NodeManager 端口，用于获取容器日志
NODEMANAGER_PORT = os.getenv("NODEMANAGER_PORT", "8052")

# HTTP 请求超时时间（秒）
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "30.0"))


def _get_logs_base_url() -> str:
    """从 JOBHISTORY_BASE_URL 构造日志服务的基础 URL"""
    parsed = urlparse(JOBHISTORY_BASE_URL)
    return f"{parsed.scheme}://{parsed.netloc}/jobhistory/logs"

# 日志服务基础 URL
LOGS_BASE_URL = _get_logs_base_url()
```

**设计说明**:
- 使用环境变量配置服务地址，便于在不同环境中部署
- 提供合理的默认值，开箱即用
- `NODEMANAGER_PORT` 用于构造容器日志的 URL
- `LOGS_BASE_URL` 从 `JOBHISTORY_BASE_URL` 自动派生，减少配置项
- 超时时间可根据网络情况调整

---

### 2. FastMCP 初始化

```python
mcp = FastMCP("jobhistory_mcp")
```

**说明**:
- `FastMCP` 是 MCP Python SDK 提供的高级封装
- 参数 `"jobhistory_mcp"` 是服务器名称，遵循 `{service}_mcp` 命名规范
- 初始化后可通过 `@mcp.tool` 装饰器注册工具

---

### 3. 枚举类型定义

#### ResponseFormat 枚举

```python
class ResponseFormat(str, Enum):
    """响应格式枚举"""
    MARKDOWN = "markdown"
    JSON = "json"
```

**设计说明**:
- 继承 `str` 和 `Enum`，使枚举值可以直接作为字符串使用
- MARKDOWN 格式适合人类阅读，包含格式化的表格和列表
- JSON 格式适合程序处理，便于进一步分析

#### JobState 枚举

```python
class JobState(str, Enum):
    """作业状态枚举"""
    NEW = "NEW"
    INITED = "INITED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    KILL_WAIT = "KILL_WAIT"
    KILLED = "KILLED"
    ERROR = "ERROR"
```

**说明**:
- 枚举所有可能的作业状态
- 用于类型安全的状态过滤
- 值与 Hadoop REST API 返回的状态一致

#### TaskType 枚举

```python
class TaskType(str, Enum):
    """任务类型枚举"""
    MAP = "m"
    REDUCE = "r"
```

**说明**:
- 对应 REST API 的 `type` 查询参数
- `m` 表示 Map 任务，`r` 表示 Reduce 任务

#### LogType 枚举

```python
class LogType(str, Enum):
    """容器日志类型枚举"""
    STDOUT = "stdout"
    STDERR = "stderr"
    SYSLOG = "syslog"
    SYSLOG_SHUFFLE = "syslog.shuffle"
    PRELAUNCH_OUT = "prelaunch.out"
    PRELAUNCH_ERR = "prelaunch.err"
    CONTAINER_LOCALIZER_SYSLOG = "container-localizer-syslog"
```

**说明**:
- 定义容器支持的日志文件类型
- `syslog` 是最常用的日志类型，包含任务执行的详细信息
- `stdout/stderr` 是任务的标准输出和错误输出
- `prelaunch.*` 是容器启动前的日志

---

### 4. Pydantic 输入模型

#### 基本结构

```python
class ListJobsInput(BaseModel):
    """列出作业的输入参数模型"""
    model_config = ConfigDict(
        str_strip_whitespace=True,    # 自动去除字符串首尾空白
        validate_assignment=True       # 赋值时也进行验证
    )

    user: Optional[str] = Field(
        default=None,
        description="按用户名过滤作业，例如 'hadoop'"
    )
    # ... 其他字段
```

**Pydantic v2 特性说明**:

1. **model_config**: 替代了 v1 的嵌套 `Config` 类
2. **Field()**: 定义字段约束和描述
3. **Optional[T]**: 表示可选字段，默认为 None

#### 字段验证器

```python
@field_validator('job_id')
@classmethod
def validate_job_id(cls, v: str) -> str:
    """验证作业 ID 格式"""
    if not v.strip():
        raise ValueError("作业 ID 不能为空")
    return v.strip()
```

**说明**:
- `@field_validator`: Pydantic v2 的字段验证装饰器
- `@classmethod`: v2 要求验证器为类方法
- 返回处理后的值（这里去除了首尾空白）

#### 字段约束示例

```python
limit: Optional[int] = Field(
    default=20,      # 默认值
    ge=1,           # 最小值（greater than or equal）
    le=100,         # 最大值（less than or equal）
    description="返回的最大作业数量，范围 1-100，默认 20"
)
```

**常用约束**:
- `ge/le/gt/lt`: 数值范围
- `min_length/max_length`: 字符串长度
- `pattern`: 正则表达式匹配

---

### 5. 工具函数

#### HTTP 请求函数

```python
async def _make_request(endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """发送 HTTP GET 请求到 JobHistory Server"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{JOBHISTORY_BASE_URL}/{endpoint}",
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        return response.json()
```

**设计说明**:
- 使用 `async/await` 进行异步请求，不阻塞事件循环
- 使用 `async with` 确保 HTTP 客户端正确关闭
- `raise_for_status()` 在 HTTP 错误时抛出异常
- 返回解析后的 JSON 数据

#### 错误处理函数

```python
def _handle_error(e: Exception) -> str:
    """统一错误处理函数"""
    if isinstance(e, httpx.HTTPStatusError):
        status_code = e.response.status_code
        if status_code == 404:
            return "错误：资源未找到。请检查 ID 是否正确..."
        elif status_code == 403:
            return "错误：权限不足..."
        # ... 其他状态码处理
    elif isinstance(e, httpx.TimeoutException):
        return f"错误：请求超时..."
    elif isinstance(e, httpx.ConnectError):
        return f"错误：无法连接到 JobHistory Server..."
    return f"错误：{type(e).__name__} - {str(e)}"
```

**设计说明**:
- 针对不同类型的异常提供具体的错误信息
- 错误消息包含解决建议，便于用户排查问题
- 返回字符串而非抛出异常，使工具调用始终返回结果

#### 格式化函数

```python
def _format_timestamp(ms: int) -> str:
    """将毫秒时间戳转换为人类可读格式"""
    if not ms or ms <= 0:
        return "N/A"
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return "N/A"

def _format_duration(ms: int) -> str:
    """将毫秒时长转换为人类可读格式"""
    if not ms or ms <= 0:
        return "N/A"
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        return f"{seconds // 60}分{seconds % 60}秒"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}时{minutes}分"
```

**说明**:
- 将 API 返回的毫秒时间戳转换为可读格式
- 处理无效值（0 或负数）返回 "N/A"
- 智能选择时间单位（秒/分/时）

#### 容器日志函数

```python
def _extract_hostname(node_http_address: str) -> str:
    """从 nodeHttpAddress 提取主机名"""
    if ':' in node_http_address:
        return node_http_address.rsplit(':', 1)[0]
    return node_http_address

async def _fetch_logs_html(url: str) -> str:
    """获取日志 HTML 内容"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"Accept": "text/html"},
            follow_redirects=True
        )
        response.raise_for_status()
        return response.text

def _extract_pre_content(html: str) -> str:
    """从 HTML 中提取 <pre> 标签的内容"""
    match = re.search(r'<pre[^>]*>(.*?)</pre>', html, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1)
        # 处理 HTML 实体
        content = content.replace('&lt;', '<')
        content = content.replace('&gt;', '>')
        content = content.replace('&amp;', '&')
        return content.strip()
    return ""
```

**设计说明**:
- `_extract_hostname`: 从 `nodeHttpAddress`（如 `host:8042`）提取主机名，与 `NODEMANAGER_PORT` 组合构造日志 URL
- `_fetch_logs_html`: 获取日志页面的 HTML 内容，使用 `follow_redirects=True` 处理重定向
- `_extract_pre_content`: 使用正则表达式从 HTML 中提取 `<pre>` 标签的内容，并处理 HTML 实体转义

---

### 6. MCP 工具定义

#### 工具装饰器

```python
@mcp.tool(
    name="jobhistory_list_jobs",
    annotations={
        "title": "列出 MapReduce 作业",
        "readOnlyHint": True,      # 只读操作
        "destructiveHint": False,   # 非破坏性
        "idempotentHint": True,    # 幂等（重复调用结果相同）
        "openWorldHint": True       # 与外部服务交互
    }
)
async def jobhistory_list_jobs(params: ListJobsInput) -> str:
```

**装饰器参数说明**:

| 参数 | 说明 |
|------|------|
| name | 工具名称，遵循 `{service}_{action}` 命名规范 |
| annotations.title | 人类可读的工具标题 |
| annotations.readOnlyHint | 是否为只读操作 |
| annotations.destructiveHint | 是否可能造成破坏 |
| annotations.idempotentHint | 是否幂等 |
| annotations.openWorldHint | 是否与外部服务交互 |

#### 工具函数签名

```python
async def jobhistory_list_jobs(params: ListJobsInput) -> str:
```

**说明**:
- 必须是 `async` 函数（FastMCP 要求）
- 参数类型为 Pydantic 模型，自动验证输入
- 返回类型为 `str`，用于向用户展示结果

#### 工具文档字符串

```python
async def jobhistory_list_jobs(params: ListJobsInput) -> str:
    """
    列出已完成的 MapReduce 作业。
    
    支持多种过滤条件：
    - 按用户名过滤
    - 按作业状态过滤
    - 按队列名过滤
    - 按时间范围过滤
    
    Args:
        params (ListJobsInput): 查询参数，包括：
            - user: 用户名过滤
            - state: 状态过滤
            ...
    
    Returns:
        str: 作业列表，Markdown 或 JSON 格式
        
    Examples:
        - 查询所有作业: 使用默认参数
        - 查询失败的作业: state="FAILED"
    """
```

**说明**:
- 文档字符串自动成为工具的 `description` 字段
- 详细描述功能、参数和返回值
- 包含使用示例，帮助 AI 正确调用

#### 工具实现模式

```python
async def jobhistory_list_jobs(params: ListJobsInput) -> str:
    try:
        # 1. 构建查询参数
        query_params = {}
        if params.user:
            query_params["user"] = params.user
        # ... 其他参数

        # 2. 调用 REST API
        data = await _make_request("mapreduce/jobs", query_params)
        
        # 3. 提取数据
        jobs = data.get("jobs", {}).get("job", [])

        # 4. 处理空结果
        if not jobs:
            return "没有找到符合条件的作业。"

        # 5. 根据格式返回结果
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"total": len(jobs), "jobs": jobs}, indent=2)

        # 6. 构建 Markdown 输出
        lines = ["# MapReduce 作业列表", ...]
        return "\n".join(lines)
        
    except Exception as e:
        return _handle_error(e)
```

**实现模式说明**:
1. **参数处理**: 将 Pydantic 模型转换为 API 查询参数
2. **API 调用**: 使用共享的 `_make_request` 函数
3. **数据提取**: 安全地从嵌套 JSON 中提取数据
4. **空结果处理**: 返回友好的提示信息
5. **格式选择**: 根据用户选择返回不同格式
6. **错误处理**: 捕获所有异常并返回友好消息

---

### 7. 主入口

```python
if __name__ == "__main__":
    mcp.run()
```

**说明**:
- `mcp.run()` 启动 MCP 服务器
- 默认使用 stdio 传输（适合本地集成）
- 可以通过参数切换到 HTTP 传输

---

### 8. 容器日志工具

#### 完整日志获取

```python
@mcp.tool(name="jobhistory_get_task_attempt_logs", ...)
async def jobhistory_get_task_attempt_logs(params: GetTaskAttemptLogsInput) -> str:
    """获取指定任务尝试的容器日志内容（完整）"""
    try:
        # 1. 获取任务尝试信息（获取 containerId 和 nodeHttpAddress）
        attempt_data = await _make_request(f"mapreduce/jobs/{params.job_id}/tasks/{params.task_id}/attempts/{params.attempt_id}")
        attempt = attempt_data.get("taskAttempt", {})
        container_id = attempt.get("assignedContainerId")
        node_http_address = attempt.get("nodeHttpAddress")
        
        # 2. 获取作业信息（获取 user）
        job_data = await _make_request(f"mapreduce/jobs/{params.job_id}")
        user = job_data.get("job", {}).get("user")
        
        # 3. 构造日志 URL
        hostname = _extract_hostname(node_http_address)
        log_url = f"{LOGS_BASE_URL}/{hostname}:{NODEMANAGER_PORT}/{container_id}/{params.attempt_id}/{user}/{params.log_type.value}/?start=0&start.time=0&end.time=9223372036854775807"
        
        # 4. 获取并解析日志
        html_content = await _fetch_logs_html(log_url)
        log_content = _extract_pre_content(html_content)
        
        return formatted_result
    except Exception as e:
        return _handle_error(e)
```

**日志 URL 格式**:
```
{LOGS_BASE_URL}/{nodeManager}:{port}/{containerId}/{attemptId}/{user}/{logType}/?start=0&start.time=0&end.time=9223372036854775807
```

**设计说明**:
- 通过多个 API 调用收集构造 URL 所需的信息
- `start.time=0&end.time=9223372036854775807` 表示获取完整时间范围的日志
- 日志内容在 HTML 页面的 `<pre>` 标签中

#### 部分日志读取

```python
@mcp.tool(name="jobhistory_get_task_attempt_logs_partial", ...)
async def jobhistory_get_task_attempt_logs_partial(params: GetTaskAttemptLogsPartialInput) -> str:
    """部分读取指定任务尝试的容器日志内容"""
    # ... 前置步骤相同 ...
    
    # 关键区别：使用 start 和 end 参数控制读取范围
    if params.start < 0:
        # 负数表示从末尾倒数，不需要 end 参数
        log_url = f"{base_url}?start={params.start}"
    else:
        log_url = f"{base_url}?start={params.start}&end={params.end}"
```

**字节范围参数**:
| 参数 | 说明 | 示例 |
|------|------|------|
| `start=-4096, end=0` | 读取末尾 4KB | 任务失败分析 |
| `start=0, end=2048` | 读取开头 2KB | 查看启动日志 |
| `start=-8192` | 读取末尾 8KB | 更多上下文 |

**设计说明**:
- 部分读取可以大幅减少数据传输量，节省 Token
- 负数 `start` 表示从文件末尾倒数，适合快速查看错误信息
- 默认读取 `syslog` 末尾 4KB，通常包含关键错误信息

---

## 设计原则

### 1. 工具命名规范

```
{service}_{action}_{resource}
```

示例:
- `jobhistory_get_info` - 获取服务信息
- `jobhistory_list_jobs` - 列出作业
- `jobhistory_get_job_counters` - 获取作业计数器

### 2. 输入验证

- 所有输入通过 Pydantic 模型验证
- 使用 Field() 定义约束和描述
- 验证失败时自动返回清晰的错误信息

### 3. 输出格式

- 支持 Markdown 和 JSON 两种格式
- Markdown 格式包含表格、列表、图标，便于阅读
- JSON 格式保留完整数据，便于程序处理

### 4. 错误处理

- 所有工具都有 try-except 包装
- 错误消息包含原因和解决建议
- 不抛出异常，始终返回字符串结果

### 5. 代码复用

- 共享的 HTTP 请求函数
- 共享的错误处理函数
- 共享的格式化函数

---

## 扩展指南

### 添加新工具

1. 定义输入模型:

```python
class NewToolInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    param1: str = Field(..., description="参数描述")
```

2. 实现工具函数:

```python
@mcp.tool(
    name="jobhistory_new_tool",
    annotations={"readOnlyHint": True, ...}
)
async def jobhistory_new_tool(params: NewToolInput) -> str:
    """工具描述"""
    try:
        data = await _make_request("endpoint")
        # 处理数据...
        return result
    except Exception as e:
        return _handle_error(e)
```

### 添加新的输出格式

1. 扩展 ResponseFormat 枚举:

```python
class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"
    CSV = "csv"  # 新增
```

2. 在工具中处理新格式:

```python
if params.response_format == ResponseFormat.CSV:
    # 生成 CSV 格式输出
    ...
```

### 添加认证支持

修改 `_make_request` 函数:

```python
async def _make_request(endpoint: str, params: dict = None) -> dict:
    headers = {"Accept": "application/json"}
    
    # 添加认证
    auth_token = os.getenv("HADOOP_AUTH_TOKEN")
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{JOBHISTORY_BASE_URL}/{endpoint}",
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
```

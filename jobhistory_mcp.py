#!/usr/bin/env python3
"""
JobHistory MCP Server - Hadoop MapReduce 作业历史查询服务

该 MCP Server 封装了 Hadoop JobHistory Server 的 REST API，
提供工具来查询 MapReduce 作业历史信息，包括：
- 作业列表查询（支持过滤和分页）
- 作业详情查询
- 作业计数器查询
- 作业配置查询
- 任务列表和详情查询
- 任务尝试信息查询

使用 FastMCP 框架构建，支持 Pydantic v2 输入验证。

环境变量:
    JOBHISTORY_URL: JobHistory Server 地址，默认 http://localhost:19888/ws/v1/history
    NODEMANAGER_PORT: NodeManager 端口，用于获取容器日志，默认 8052
    LOG_LEVEL: 日志级别，默认 INFO
    LOG_FILE: 日志文件路径，默认 ./logs/jobhistory_mcp.log
    LOG_MAX_SIZE: 单个日志文件最大大小（字节），默认 268435456 (256MB)
    LOG_BACKUP_COUNT: 保留的日志文件数量，默认 5
    LOG_TO_STDERR: 是否输出到 stderr，默认 true

作者: Winston
版本: 1.3.0
"""

import json
import os
import re
import sys
import time
import uuid
import logging
import functools
from logging.handlers import RotatingFileHandler
from typing import Optional, List, Dict, Any, Callable
from enum import Enum
from datetime import datetime
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from fastmcp import FastMCP

# ==============================================================================
# 日志配置
# ==============================================================================

# 请求 ID 上下文变量，用于关联同一请求的所有日志
request_id_var: ContextVar[str] = ContextVar('request_id', default='-')


class RequestIdFilter(logging.Filter):
    """日志过滤器，为每条日志添加请求 ID"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging() -> logging.Logger:
    """
    配置日志系统
    
    支持滚动日志，同时输出到文件和 stderr。
    注意：MCP stdio 模式使用 stdout 进行协议通信，
    因此日志只能输出到 stderr 或文件。
    
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    # 从环境变量读取配置
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = os.getenv("LOG_FILE", "./logs/jobhistory_mcp.log")
    log_max_size = int(os.getenv("LOG_MAX_SIZE", 268435456))  # 256MB
    log_backup_count = int(os.getenv("LOG_BACKUP_COUNT", 5))
    log_to_stderr = os.getenv("LOG_TO_STDERR", "true").lower() == "true"
    
    # 创建日志记录器
    logger = logging.getLogger("jobhistory_mcp")
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # 清除已有的处理器（避免重复添加）
    logger.handlers.clear()
    
    # 日志格式
    log_format = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-5s | %(request_id)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 添加请求 ID 过滤器
    request_id_filter = RequestIdFilter()
    
    # 文件处理器（滚动日志）
    try:
        log_dir = Path(log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=log_max_size,
            backupCount=log_backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(log_format)
        file_handler.addFilter(request_id_filter)
        logger.addHandler(file_handler)
    except Exception as e:
        # 如果无法创建日志文件，输出警告到 stderr
        print(f"警告：无法创建日志文件 {log_file}: {e}", file=sys.stderr)
    
    # stderr 处理器
    if log_to_stderr:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(log_format)
        stderr_handler.addFilter(request_id_filter)
        logger.addHandler(stderr_handler)
    
    return logger


# 初始化日志
logger = setup_logging()

# ==============================================================================
# 配置常量
# ==============================================================================

# JobHistory Server 地址，可通过环境变量配置
JOBHISTORY_BASE_URL = os.getenv(
    "JOBHISTORY_URL",
    "https://jobhistory.hellobike.cn/ws/v1/history"
)

# NodeManager 端口，用于获取容器日志
NODEMANAGER_PORT = os.getenv("NODEMANAGER_PORT", "8052")

# HTTP 请求超时时间（秒）
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "30.0"))


def _get_logs_base_url() -> str:
    """
    从 JOBHISTORY_BASE_URL 构造日志服务的基础 URL
    
    例如:
        输入: http://jobhistory.example.com:19888/ws/v1/history
        输出: http://jobhistory.example.com:19888/jobhistory/logs
    
    Returns:
        日志服务基础 URL
    """
    parsed = urlparse(JOBHISTORY_BASE_URL)
    return f"{parsed.scheme}://{parsed.netloc}/jobhistory/logs"


# 日志服务基础 URL
LOGS_BASE_URL = _get_logs_base_url()

# 启动日志
logger.info(f"JobHistory MCP Server 初始化")
logger.info(f"JobHistory URL: {JOBHISTORY_BASE_URL}")
logger.info(f"Logs Base URL: {LOGS_BASE_URL}")
logger.info(f"NodeManager Port: {NODEMANAGER_PORT}")
logger.info(f"请求超时: {REQUEST_TIMEOUT}s")

# ==============================================================================
# 日志装饰器
# ==============================================================================


def log_tool_call(func: Callable) -> Callable:
    """
    工具调用日志装饰器
    
    记录 MCP 工具的调用信息，包括：
    - 工具名称和参数
    - 执行时间
    - 成功或失败状态
    
    Args:
        func: 被装饰的工具函数
        
    Returns:
        装饰后的函数
    """
    @functools.wraps(func)
    async def wrapper(params=None):
        # 生成请求 ID
        req_id = str(uuid.uuid4())[:8]
        request_id_var.set(req_id)
        
        # 记录请求
        tool_name = func.__name__
        params_str = _safe_serialize_params(params)
        logger.info(f"[TOOL_CALL] {tool_name}, params: {params_str}")
        
        start_time = time.time()
        try:
            # 执行工具函数
            result = await func(params) if params is not None else await func()
            
            # 记录成功响应
            duration_ms = (time.time() - start_time) * 1000
            result_size = len(result) if isinstance(result, str) else 0
            logger.info(f"[TOOL_RSP] success, size: {result_size} bytes, duration: {duration_ms:.2f}ms")
            
            return result
            
        except Exception as e:
            # 记录错误
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[TOOL_ERR] {type(e).__name__}: {str(e)}, duration: {duration_ms:.2f}ms")
            raise
    
    return wrapper


def _safe_serialize_params(params) -> str:
    """
    安全地序列化参数用于日志记录
    
    对敏感信息进行脱敏处理，限制长度避免日志过大。
    
    Args:
        params: Pydantic 模型或其他参数对象
        
    Returns:
        JSON 格式的参数字符串
    """
    if params is None:
        return "{}"
    
    try:
        if hasattr(params, 'model_dump'):
            # Pydantic v2 模型
            data = params.model_dump()
        elif hasattr(params, 'dict'):
            # Pydantic v1 模型
            data = params.dict()
        else:
            data = str(params)
            
        # 转换为 JSON 字符串
        result = json.dumps(data, ensure_ascii=False, default=str)
        
        # 限制长度
        if len(result) > 500:
            result = result[:500] + "..."
            
        return result
    except Exception:
        return "<序列化失败>"


# ==============================================================================
# 初始化 MCP Server
# ==============================================================================

mcp = FastMCP("jobhistory_mcp")

# ==============================================================================
# 枚举类型定义
# ==============================================================================


class ResponseFormat(str, Enum):
    """
    响应格式枚举
    
    - MARKDOWN: 人类可读的 Markdown 格式，适合直接展示
    - JSON: 机器可读的 JSON 格式，适合程序处理
    """
    MARKDOWN = "markdown"
    JSON = "json"


class JobState(str, Enum):
    """
    作业状态枚举
    
    MapReduce 作业的生命周期状态：
    - NEW: 新建
    - INITED: 已初始化
    - RUNNING: 运行中
    - SUCCEEDED: 成功完成
    - FAILED: 失败
    - KILL_WAIT: 等待终止
    - KILLED: 已终止
    - ERROR: 错误
    """
    NEW = "NEW"
    INITED = "INITED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    KILL_WAIT = "KILL_WAIT"
    KILLED = "KILLED"
    ERROR = "ERROR"


class TaskType(str, Enum):
    """
    任务类型枚举
    
    MapReduce 任务类型：
    - MAP: Map 任务（m）
    - REDUCE: Reduce 任务（r）
    """
    MAP = "m"
    REDUCE = "r"


class TaskState(str, Enum):
    """
    任务状态枚举
    
    任务的生命周期状态：
    - NEW: 新建
    - SCHEDULED: 已调度
    - RUNNING: 运行中
    - SUCCEEDED: 成功
    - FAILED: 失败
    - KILL_WAIT: 等待终止
    - KILLED: 已终止
    """
    NEW = "NEW"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    KILL_WAIT = "KILL_WAIT"
    KILLED = "KILLED"


class LogType(str, Enum):
    """
    容器日志类型枚举
    
    支持的日志文件类型：
    - STDOUT: 标准输出
    - STDERR: 标准错误
    - SYSLOG: 系统日志
    - SYSLOG_SHUFFLE: Shuffle 系统日志
    - PRELAUNCH_OUT: 预启动输出
    - PRELAUNCH_ERR: 预启动错误
    - CONTAINER_LOCALIZER_SYSLOG: 容器本地化系统日志
    """
    STDOUT = "stdout"
    STDERR = "stderr"
    SYSLOG = "syslog"
    SYSLOG_SHUFFLE = "syslog.shuffle"
    PRELAUNCH_OUT = "prelaunch.out"
    PRELAUNCH_ERR = "prelaunch.err"
    CONTAINER_LOCALIZER_SYSLOG = "container-localizer-syslog"


# ==============================================================================
# Pydantic 输入模型定义
# ==============================================================================


class BaseInput(BaseModel):
    """
    支持 JSON 字符串输入的基础输入模型
    
    用于兼容某些 MCP 客户端（如 Cherry Studio）的参数序列化 bug，
    这些客户端会将参数对象序列化为 JSON 字符串而不是直接传递对象。
    """
    
    @model_validator(mode='before')
    @classmethod
    def parse_json_string(cls, data):
        """
        在验证之前预处理输入数据
        
        如果输入是 JSON 字符串，先解析为字典。
        这解决了某些 MCP 客户端将参数双重序列化的问题。
        
        Args:
            data: 原始输入数据
            
        Returns:
            处理后的数据（字典或原始数据）
        """
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                logger.debug(f"参数从 JSON 字符串解析: {data[:100]}...")
                return parsed
            except json.JSONDecodeError:
                # 如果不是有效的 JSON，保持原样让后续验证处理
                pass
        return data


class ListJobsInput(BaseInput):
    """
    列出作业的输入参数模型
    
    用于 jobhistory_list_jobs 工具，支持多种过滤条件和分页。
    
    Attributes:
        user: 按用户名过滤
        state: 按作业状态过滤
        queue: 按队列名过滤
        limit: 返回结果数量限制（1-100）
        started_time_begin: 开始时间范围的起点（毫秒时间戳）
        started_time_end: 开始时间范围的终点（毫秒时间戳）
        finished_time_begin: 结束时间范围的起点（毫秒时间戳）
        finished_time_end: 结束时间范围的终点（毫秒时间戳）
        response_format: 响应格式（markdown 或 json）
    """
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )

    user: Optional[str] = Field(
        default=None,
        description="按用户名过滤作业，例如 'hadoop'"
    )
    state: Optional[JobState] = Field(
        default=None,
        description="按作业状态过滤，可选值: NEW, INITED, RUNNING, SUCCEEDED, FAILED, KILLED"
    )
    queue: Optional[str] = Field(
        default=None,
        description="按队列名过滤，例如 'default'"
    )
    limit: Optional[int] = Field(
        default=20,
        ge=1,
        le=100,
        description="返回的最大作业数量，范围 1-100，默认 20"
    )
    started_time_begin: Optional[int] = Field(
        default=None,
        ge=0,
        description="作业开始时间的起点（毫秒时间戳），用于时间范围查询"
    )
    started_time_end: Optional[int] = Field(
        default=None,
        ge=0,
        description="作业开始时间的终点（毫秒时间戳），用于时间范围查询"
    )
    finished_time_begin: Optional[int] = Field(
        default=None,
        ge=0,
        description="作业结束时间的起点（毫秒时间戳），用于时间范围查询"
    )
    finished_time_end: Optional[int] = Field(
        default=None,
        ge=0,
        description="作业结束时间的终点（毫秒时间戳），用于时间范围查询"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式: 'markdown' 人类可读格式，'json' 机器可读格式"
    )


class GetJobInput(BaseInput):
    """
    获取作业详情的输入参数模型
    
    用于 jobhistory_get_job 工具。
    
    Attributes:
        job_id: MapReduce 作业 ID
        response_format: 响应格式
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(
        ...,
        description="作业ID，格式如 'job_1326381300833_2_2'",
        min_length=1,
        max_length=100
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )

    @field_validator('job_id')
    @classmethod
    def validate_job_id(cls, v: str) -> str:
        """验证作业 ID 格式"""
        if not v.strip():
            raise ValueError("作业 ID 不能为空")
        return v.strip()


class GetJobCountersInput(BaseInput):
    """
    获取作业计数器的输入参数模型
    
    用于 jobhistory_get_job_counters 工具。
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(
        ...,
        description="作业ID",
        min_length=1
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class GetJobConfInput(BaseInput):
    """
    获取作业配置的输入参数模型
    
    用于 jobhistory_get_job_conf 工具。
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(
        ...,
        description="作业ID",
        min_length=1
    )
    filter_key: Optional[str] = Field(
        default=None,
        description="按配置键名过滤，支持部分匹配，例如 'mapreduce'"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class GetJobAttemptsInput(BaseInput):
    """
    获取作业尝试列表的输入参数模型
    
    用于 jobhistory_get_job_attempts 工具。
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(
        ...,
        description="作业ID",
        min_length=1
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class ListTasksInput(BaseInput):
    """
    列出任务的输入参数模型
    
    用于 jobhistory_list_tasks 工具。
    
    Attributes:
        job_id: 所属作业 ID
        task_type: 任务类型过滤（Map 或 Reduce）
        response_format: 响应格式
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(
        ...,
        description="作业ID",
        min_length=1
    )
    task_type: Optional[TaskType] = Field(
        default=None,
        description="任务类型: 'm' 表示 Map 任务，'r' 表示 Reduce 任务"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class GetTaskInput(BaseInput):
    """
    获取任务详情的输入参数模型
    
    用于 jobhistory_get_task 工具。
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(
        ...,
        description="作业ID",
        min_length=1
    )
    task_id: str = Field(
        ...,
        description="任务ID，格式如 'task_1326381300833_2_2_m_0'",
        min_length=1
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class GetTaskCountersInput(BaseInput):
    """
    获取任务计数器的输入参数模型
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(..., description="作业ID", min_length=1)
    task_id: str = Field(..., description="任务ID", min_length=1)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class ListTaskAttemptsInput(BaseInput):
    """
    列出任务尝试的输入参数模型
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(..., description="作业ID", min_length=1)
    task_id: str = Field(..., description="任务ID", min_length=1)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class GetTaskAttemptInput(BaseInput):
    """
    获取任务尝试详情的输入参数模型
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(..., description="作业ID", min_length=1)
    task_id: str = Field(..., description="任务ID", min_length=1)
    attempt_id: str = Field(
        ...,
        description="尝试ID，格式如 'attempt_1326381300833_2_2_m_0_0'",
        min_length=1
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class GetTaskAttemptCountersInput(BaseInput):
    """
    获取任务尝试计数器的输入参数模型
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(..., description="作业ID", min_length=1)
    task_id: str = Field(..., description="任务ID", min_length=1)
    attempt_id: str = Field(..., description="尝试ID", min_length=1)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class GetTaskAttemptLogsInput(BaseInput):
    """
    获取任务尝试日志的输入参数模型（完整获取）
    
    用于 jobhistory_get_task_attempt_logs 工具，获取完整的日志内容。
    注意：大任务可能产生大量日志，建议先使用 partial 工具读取末尾内容。
    
    Attributes:
        job_id: 作业 ID
        task_id: 任务 ID
        attempt_id: 尝试 ID
        log_type: 日志类型
        response_format: 响应格式
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(
        ...,
        description="作业ID",
        min_length=1
    )
    task_id: str = Field(
        ...,
        description="任务ID",
        min_length=1
    )
    attempt_id: str = Field(
        ...,
        description="尝试ID，格式如 'attempt_1326381300833_2_2_m_0_0'",
        min_length=1
    )
    log_type: LogType = Field(
        default=LogType.STDOUT,
        description="日志类型: stdout, stderr, syslog, syslog.shuffle, prelaunch.out, prelaunch.err, container-localizer-syslog"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


class GetTaskAttemptLogsPartialInput(BaseInput):
    """
    部分读取任务尝试日志的输入参数模型
    
    用于 jobhistory_get_task_attempt_logs_partial 工具，按字节范围读取日志。
    适用于大任务或长期运行任务的日志分析，避免一次性读取全部内容。
    
    Attributes:
        job_id: 作业 ID
        task_id: 任务 ID
        attempt_id: 尝试 ID
        log_type: 日志类型
        start: 起始字节位置，负数表示从末尾倒数
        end: 结束字节位置，0 表示文件末尾
        response_format: 响应格式
        
    Examples:
        - 读取末尾 4KB: start=-4096, end=0
        - 读取开头 2KB: start=0, end=2048
        - 读取中间部分: start=1024, end=5120
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: str = Field(
        ...,
        description="作业ID",
        min_length=1
    )
    task_id: str = Field(
        ...,
        description="任务ID",
        min_length=1
    )
    attempt_id: str = Field(
        ...,
        description="尝试ID，格式如 'attempt_1326381300833_2_2_m_0_0'",
        min_length=1
    )
    log_type: LogType = Field(
        default=LogType.SYSLOG,
        description="日志类型: stdout, stderr, syslog, syslog.shuffle, prelaunch.out, prelaunch.err, container-localizer-syslog"
    )
    start: int = Field(
        default=-4096,
        description="起始字节位置。正数从文件开头计算，负数从文件末尾倒数。默认 -4096 表示从末尾倒数 4KB 开始"
    )
    end: int = Field(
        default=0,
        description="结束字节位置。0 表示文件末尾，正数表示具体位置。默认 0 表示读到文件末尾"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="输出格式"
    )


# ==============================================================================
# 工具函数（内部使用）
# ==============================================================================


async def _make_request(endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    发送 HTTP GET 请求到 JobHistory Server
    
    这是所有 API 调用的基础函数，封装了：
    - HTTP 客户端创建和管理
    - 请求超时处理
    - JSON 响应解析
    - 请求和响应日志记录
    
    Args:
        endpoint: API 端点路径（相对于 JOBHISTORY_BASE_URL）
        params: 查询参数字典
        
    Returns:
        解析后的 JSON 响应数据
        
    Raises:
        httpx.HTTPStatusError: HTTP 错误状态码
        httpx.TimeoutException: 请求超时
        httpx.ConnectError: 连接失败
    """
    url = f"{JOBHISTORY_BASE_URL}/{endpoint}"
    params_str = "&".join(f"{k}={v}" for k, v in (params or {}).items())
    full_url = f"{url}?{params_str}" if params_str else url
    
    # 记录请求
    logger.info(f"[REST_REQ] GET {full_url}")
    
    start_time = time.time()
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "application/json"}
            )
            
            # 计算响应时间
            duration_ms = (time.time() - start_time) * 1000
            response_size = len(response.content)
            
            # 记录响应
            logger.info(
                f"[REST_RSP] {response.status_code} {response.reason_phrase}, "
                f"size: {response_size} bytes, duration: {duration_ms:.2f}ms"
            )
            
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.warning(
            f"[REST_ERR] HTTP {e.response.status_code}, "
            f"duration: {duration_ms:.2f}ms"
        )
        raise
    except httpx.TimeoutException as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.warning(f"[REST_ERR] Timeout after {duration_ms:.2f}ms")
        raise
    except httpx.ConnectError as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.warning(f"[REST_ERR] Connection failed: {e}, duration: {duration_ms:.2f}ms")
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"[REST_ERR] {type(e).__name__}: {e}, duration: {duration_ms:.2f}ms")
        raise


def _handle_error(e: Exception) -> str:
    """
    统一错误处理函数
    
    将各种异常转换为用户友好的错误消息，
    提供明确的错误原因和解决建议。
    
    Args:
        e: 捕获的异常
        
    Returns:
        格式化的错误消息字符串
    """
    if isinstance(e, httpx.HTTPStatusError):
        status_code = e.response.status_code
        if status_code == 404:
            return "错误：资源未找到。请检查 ID 是否正确，或者该作业/任务可能已被清理。"
        elif status_code == 403:
            return "错误：权限不足，无法访问该资源。请检查访问权限配置。"
        elif status_code == 401:
            return "错误：认证失败。如果启用了安全模式，请检查认证配置。"
        elif status_code == 500:
            return "错误：服务器内部错误。请检查 JobHistory Server 日志。"
        elif status_code == 503:
            return "错误：服务暂时不可用。JobHistory Server 可能正在启动或过载。"
        return f"错误：API 请求失败，HTTP 状态码 {status_code}。"
    elif isinstance(e, httpx.TimeoutException):
        return f"错误：请求超时（{REQUEST_TIMEOUT}秒）。请检查网络连接或增加超时时间。"
    elif isinstance(e, httpx.ConnectError):
        return f"错误：无法连接到 JobHistory Server ({JOBHISTORY_BASE_URL})。\n请检查：\n1. 服务是否已启动\n2. 地址和端口是否正确\n3. 网络是否可达"
    return f"错误：{type(e).__name__} - {str(e)}"


def _format_timestamp(ms: int) -> str:
    """
    将毫秒时间戳转换为人类可读格式
    
    Args:
        ms: 毫秒时间戳（自 1970-01-01 00:00:00 UTC）
        
    Returns:
        格式化的时间字符串，如 "2024-01-15 10:30:45"
        如果时间戳无效，返回 "N/A"
    """
    if not ms or ms <= 0:
        return "N/A"
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return "N/A"


def _format_duration(ms: int) -> str:
    """
    将毫秒时长转换为人类可读格式
    
    Args:
        ms: 毫秒数
        
    Returns:
        格式化的时长字符串，如 "2时30分15秒"
    """
    if not ms or ms <= 0:
        return "N/A"
    
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}分{secs}秒"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours}时{minutes}分{secs}秒"


def _format_bytes(bytes_value: int) -> str:
    """
    将字节数转换为人类可读格式
    
    Args:
        bytes_value: 字节数
        
    Returns:
        格式化的大小字符串，如 "1.5 GB"
    """
    if not bytes_value or bytes_value < 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    unit_index = 0
    value = float(bytes_value)
    
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.2f} {units[unit_index]}"


def _format_counters_markdown(counters_data: Dict[str, Any], title: str = "计数器") -> str:
    """
    将计数器数据格式化为 Markdown
    
    Args:
        counters_data: 计数器数据字典
        title: 标题
        
    Returns:
        Markdown 格式的计数器信息
    """
    lines = [f"# {title}", ""]
    
    counter_groups = counters_data.get("counterGroup", [])
    if not counter_groups:
        counter_groups = counters_data.get("taskCounterGroup", [])
    if not counter_groups:
        counter_groups = counters_data.get("taskAttemptCounterGroup", [])
    
    for group in counter_groups:
        group_name = group.get("counterGroupName", "Unknown Group")
        # 简化组名显示
        short_name = group_name.split(".")[-1] if "." in group_name else group_name
        lines.append(f"## {short_name}")
        lines.append("")
        
        counters = group.get("counter", [])
        for counter in counters:
            name = counter.get("name", "Unknown")
            # 尝试获取不同类型的值
            total_value = counter.get("totalCounterValue", counter.get("value", 0))
            map_value = counter.get("mapCounterValue")
            reduce_value = counter.get("reduceCounterValue")
            
            if map_value is not None and reduce_value is not None:
                lines.append(f"- **{name}**: {total_value:,} (Map: {map_value:,}, Reduce: {reduce_value:,})")
            else:
                lines.append(f"- **{name}**: {total_value:,}")
        lines.append("")
    
    return "\n".join(lines)


def _extract_hostname(node_http_address: str) -> str:
    """
    从 nodeHttpAddress 提取主机名
    
    Args:
        node_http_address: 节点 HTTP 地址，格式如 "hostname:port"
        
    Returns:
        主机名部分
        
    Example:
        输入: pro-hadooptemporary-dc01-085025.vm.dc01.hellocloud.tech:8042
        输出: pro-hadooptemporary-dc01-085025.vm.dc01.hellocloud.tech
    """
    if ':' in node_http_address:
        return node_http_address.rsplit(':', 1)[0]
    return node_http_address


async def _fetch_logs_html(url: str) -> str:
    """
    获取日志 HTML 内容
    
    发送 HTTP GET 请求获取日志页面的 HTML 内容。
    
    Args:
        url: 日志 URL
        
    Returns:
        HTML 内容字符串
        
    Raises:
        httpx.HTTPStatusError: HTTP 错误状态码
        httpx.TimeoutException: 请求超时
        httpx.ConnectError: 连接失败
    """
    logger.info(f"[REST_REQ] GET {url}")
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "text/html"},
                follow_redirects=True
            )
            
            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                f"[REST_RSP] {response.status_code} {response.reason_phrase}, "
                f"size: {len(response.content)} bytes, duration: {duration_ms:.2f}ms"
            )
            
            response.raise_for_status()
            return response.text
            
    except httpx.HTTPStatusError as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.warning(
            f"[REST_ERR] HTTP {e.response.status_code}, "
            f"duration: {duration_ms:.2f}ms"
        )
        raise
    except httpx.TimeoutException:
        duration_ms = (time.time() - start_time) * 1000
        logger.warning(f"[REST_ERR] Timeout after {duration_ms:.2f}ms")
        raise
    except httpx.ConnectError as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.warning(f"[REST_ERR] Connection failed: {e}, duration: {duration_ms:.2f}ms")
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"[REST_ERR] {type(e).__name__}: {e}, duration: {duration_ms:.2f}ms")
        raise


def _extract_pre_content(html: str) -> str:
    """
    从 HTML 中提取 <pre> 标签的内容
    
    Args:
        html: HTML 内容字符串
        
    Returns:
        <pre> 标签中的文本内容，如果未找到则返回空字符串
    """
    # 使用正则匹配 <pre>...</pre> 内容
    match = re.search(r'<pre[^>]*>(.*?)</pre>', html, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1)
        # 处理 HTML 实体
        content = content.replace('&lt;', '<')
        content = content.replace('&gt;', '>')
        content = content.replace('&amp;', '&')
        content = content.replace('&quot;', '"')
        content = content.replace('&#39;', "'")
        content = content.replace('&nbsp;', ' ')
        return content.strip()
    return ""


# ==============================================================================
# MCP 工具定义
# ==============================================================================


@mcp.tool(
    name="jobhistory_get_info",
    annotations={
        "title": "获取 History Server 信息",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_info() -> str:
    """
    获取 Hadoop JobHistory Server 的基本信息。
    
    返回服务器启动时间、Hadoop 版本、构建信息等。
    这是一个简单的健康检查工具，可以验证服务是否可用。
    
    Returns:
        str: Markdown 格式的服务器信息
        
    Example:
        使用此工具检查 JobHistory Server 是否正常运行。
    """
    try:
        data = await _make_request("info")
        info = data.get("historyInfo", {})
        
        result = f"""# JobHistory Server 信息

## 服务状态
- **启动时间**: {_format_timestamp(info.get('startedOn', 0))}
- **运行状态**: 正常

## Hadoop 版本信息
- **版本**: {info.get('hadoopVersion', 'N/A')}
- **构建版本**: {info.get('hadoopBuildVersion', 'N/A')}
- **构建时间**: {info.get('hadoopVersionBuiltOn', 'N/A')}

## 连接信息
- **服务地址**: {JOBHISTORY_BASE_URL}
"""
        return result
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_list_jobs",
    annotations={
        "title": "列出 MapReduce 作业",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_list_jobs(params: ListJobsInput) -> str:
    """
    列出已完成的 MapReduce 作业。
    
    支持多种过滤条件：
    - 按用户名过滤
    - 按作业状态过滤
    - 按队列名过滤
    - 按时间范围过滤
    
    支持分页，默认返回 20 条记录。
    
    Args:
        params (ListJobsInput): 查询参数，包括：
            - user: 用户名过滤
            - state: 状态过滤（SUCCEEDED, FAILED, KILLED 等）
            - queue: 队列名过滤
            - limit: 返回数量限制
            - started_time_begin/end: 开始时间范围
            - finished_time_begin/end: 结束时间范围
            - response_format: 输出格式
    
    Returns:
        str: 作业列表，Markdown 或 JSON 格式
        
    Examples:
        - 查询所有作业: 使用默认参数
        - 查询失败的作业: state="FAILED"
        - 查询特定用户的作业: user="hadoop"
    """
    try:
        # 构建查询参数
        query_params = {}
        if params.user:
            query_params["user"] = params.user
        if params.state:
            query_params["state"] = params.state.value
        if params.queue:
            query_params["queue"] = params.queue
        if params.limit:
            query_params["limit"] = params.limit
        if params.started_time_begin:
            query_params["startedTimeBegin"] = params.started_time_begin
        if params.started_time_end:
            query_params["startedTimeEnd"] = params.started_time_end
        if params.finished_time_begin:
            query_params["finishedTimeBegin"] = params.finished_time_begin
        if params.finished_time_end:
            query_params["finishedTimeEnd"] = params.finished_time_end

        data = await _make_request("mapreduce/jobs", query_params)
        jobs = data.get("jobs", {}).get("job", [])

        if not jobs:
            return "没有找到符合条件的作业。"

        # JSON 格式输出
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": len(jobs),
                "jobs": jobs
            }, indent=2, ensure_ascii=False)

        # Markdown 格式输出
        lines = [
            "# MapReduce 作业列表",
            f"共找到 **{len(jobs)}** 个作业",
            ""
        ]

        for job in jobs:
            job_id = job.get('id', 'N/A')
            job_name = job.get('name', 'N/A')
            state = job.get('state', 'N/A')
            user = job.get('user', 'N/A')
            queue = job.get('queue', 'N/A')
            
            # 状态图标
            state_icon = {
                'SUCCEEDED': '✅',
                'FAILED': '❌',
                'KILLED': '⚠️',
                'RUNNING': '🔄'
            }.get(state, '❓')
            
            lines.append(f"## {state_icon} {job_name}")
            lines.append(f"**ID**: `{job_id}`")
            lines.append("")
            lines.append(f"| 属性 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 用户 | {user} |")
            lines.append(f"| 队列 | {queue} |")
            lines.append(f"| 状态 | {state} |")
            lines.append(f"| 开始时间 | {_format_timestamp(job.get('startTime', 0))} |")
            lines.append(f"| 结束时间 | {_format_timestamp(job.get('finishTime', 0))} |")
            lines.append(f"| Map 进度 | {job.get('mapsCompleted', 0)}/{job.get('mapsTotal', 0)} |")
            lines.append(f"| Reduce 进度 | {job.get('reducesCompleted', 0)}/{job.get('reducesTotal', 0)} |")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_job",
    annotations={
        "title": "获取作业详情",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_job(params: GetJobInput) -> str:
    """
    获取指定 MapReduce 作业的详细信息。
    
    包括作业的完整元数据：
    - 基本信息（ID、名称、用户、队列、状态）
    - 时间信息（提交、开始、结束时间）
    - 任务统计（Map/Reduce 数量、成功/失败数）
    - 性能统计（平均执行时间）
    - 访问控制列表（ACL）
    
    Args:
        params (GetJobInput): 包含 job_id 的输入参数
    
    Returns:
        str: 作业详情，Markdown 或 JSON 格式
        
    Examples:
        - 获取作业详情: job_id="job_1326381300833_2_2"
    """
    try:
        data = await _make_request(f"mapreduce/jobs/{params.job_id}")
        job = data.get("job", {})

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(job, indent=2, ensure_ascii=False)

        state = job.get('state', 'N/A')
        state_icon = {
            'SUCCEEDED': '✅',
            'FAILED': '❌',
            'KILLED': '⚠️',
            'RUNNING': '🔄'
        }.get(state, '❓')

        lines = [
            f"# {state_icon} 作业详情: {job.get('name', 'N/A')}",
            "",
            "## 基本信息",
            f"| 属性 | 值 |",
            f"|------|-----|",
            f"| 作业 ID | `{job.get('id', 'N/A')}` |",
            f"| 作业名称 | {job.get('name', 'N/A')} |",
            f"| 用户 | {job.get('user', 'N/A')} |",
            f"| 队列 | {job.get('queue', 'N/A')} |",
            f"| 状态 | {state} |",
            f"| Uber 模式 | {'是' if job.get('uberized') else '否'} |",
            "",
            "## 时间信息",
            f"| 阶段 | 时间 |",
            f"|------|-----|",
            f"| 提交时间 | {_format_timestamp(job.get('submitTime', 0))} |",
            f"| 开始时间 | {_format_timestamp(job.get('startTime', 0))} |",
            f"| 结束时间 | {_format_timestamp(job.get('finishTime', 0))} |",
            "",
            "## 任务统计",
            f"| 类型 | 完成/总数 | 成功 | 失败 | 终止 |",
            f"|------|----------|------|------|------|",
            f"| Map | {job.get('mapsCompleted', 0)}/{job.get('mapsTotal', 0)} | {job.get('successfulMapAttempts', 0)} | {job.get('failedMapAttempts', 0)} | {job.get('killedMapAttempts', 0)} |",
            f"| Reduce | {job.get('reducesCompleted', 0)}/{job.get('reducesTotal', 0)} | {job.get('successfulReduceAttempts', 0)} | {job.get('failedReduceAttempts', 0)} | {job.get('killedReduceAttempts', 0)} |",
            "",
            "## 性能统计",
            f"| 指标 | 耗时 |",
            f"|------|------|",
            f"| 平均 Map 时间 | {_format_duration(job.get('avgMapTime', 0))} |",
            f"| 平均 Reduce 时间 | {_format_duration(job.get('avgReduceTime', 0))} |",
            f"| 平均 Shuffle 时间 | {_format_duration(job.get('avgShuffleTime', 0))} |",
            f"| 平均 Merge 时间 | {_format_duration(job.get('avgMergeTime', 0))} |",
        ]

        # 诊断信息
        diagnostics = job.get('diagnostics')
        if diagnostics:
            lines.extend([
                "",
                "## 诊断信息",
                f"```",
                diagnostics,
                f"```"
            ])

        # ACL 信息
        acls = job.get('acls', [])
        if acls:
            lines.extend([
                "",
                "## 访问控制",
                f"| ACL 名称 | 值 |",
                f"|----------|-----|"
            ])
            for acl in acls:
                lines.append(f"| {acl.get('name', 'N/A')} | {acl.get('value', 'N/A')} |")

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_job_counters",
    annotations={
        "title": "获取作业计数器",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_job_counters(params: GetJobCountersInput) -> str:
    """
    获取指定作业的所有计数器信息。
    
    计数器包含作业执行的详细统计数据：
    - 文件系统计数器（读写字节数、操作数）
    - 任务计数器（输入输出记录数、溢出记录数）
    - Shuffle 错误计数器
    - 自定义计数器
    
    Args:
        params (GetJobCountersInput): 包含 job_id 的输入参数
    
    Returns:
        str: 计数器信息，按组分类展示
    """
    try:
        data = await _make_request(f"mapreduce/jobs/{params.job_id}/counters")
        counters = data.get("jobCounters", {})

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(counters, indent=2, ensure_ascii=False)

        job_id = counters.get('id', params.job_id)
        return _format_counters_markdown(
            counters,
            f"作业计数器: {job_id}"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_job_conf",
    annotations={
        "title": "获取作业配置",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_job_conf(params: GetJobConfInput) -> str:
    """
    获取指定作业的配置信息。
    
    返回作业运行时使用的所有配置参数，
    包括 Hadoop 默认配置、站点配置和作业特定配置。
    
    可以通过 filter_key 参数过滤配置项。
    
    Args:
        params (GetJobConfInput): 包含 job_id 和可选的 filter_key
    
    Returns:
        str: 配置信息列表
        
    Examples:
        - 获取所有配置: job_id="job_xxx"
        - 过滤 MapReduce 配置: job_id="job_xxx", filter_key="mapreduce"
    """
    try:
        data = await _make_request(f"mapreduce/jobs/{params.job_id}/conf")
        conf = data.get("conf", {})

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(conf, indent=2, ensure_ascii=False)

        path = conf.get('path', 'N/A')
        properties = conf.get('property', [])

        # 应用过滤
        if params.filter_key:
            filter_lower = params.filter_key.lower()
            properties = [
                p for p in properties
                if filter_lower in p.get('name', '').lower()
            ]

        lines = [
            f"# 作业配置: {params.job_id}",
            f"**配置文件路径**: `{path}`",
            "",
            f"共 **{len(properties)}** 个配置项" + (f"（过滤: '{params.filter_key}'）" if params.filter_key else ""),
            ""
        ]

        # 按配置名称前缀分组
        groups: Dict[str, List[Dict]] = {}
        for prop in properties:
            name = prop.get('name', '')
            prefix = name.split('.')[0] if '.' in name else 'other'
            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(prop)

        for prefix in sorted(groups.keys()):
            props = groups[prefix]
            lines.append(f"## {prefix} ({len(props)} 项)")
            lines.append("")
            for prop in props:
                name = prop.get('name', 'N/A')
                value = prop.get('value', 'N/A')
                # 截断过长的值
                if len(value) > 100:
                    value = value[:100] + "..."
                lines.append(f"- `{name}` = `{value}`")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_job_attempts",
    annotations={
        "title": "获取作业尝试列表",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_job_attempts(params: GetJobAttemptsInput) -> str:
    """
    获取指定作业的 ApplicationMaster 尝试列表。
    
    当作业的 AM 失败时，YARN 会重新启动 AM，
    每次启动都是一个新的尝试。此工具返回所有尝试的信息。
    
    Args:
        params (GetJobAttemptsInput): 包含 job_id
    
    Returns:
        str: AM 尝试列表
    """
    try:
        data = await _make_request(f"mapreduce/jobs/{params.job_id}/jobattempts")
        attempts = data.get("jobAttempts", {}).get("jobAttempt", [])

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": len(attempts),
                "attempts": attempts
            }, indent=2, ensure_ascii=False)

        if not attempts:
            return "没有找到作业尝试记录。"

        lines = [
            f"# 作业尝试列表: {params.job_id}",
            f"共 **{len(attempts)}** 次尝试",
            ""
        ]

        for attempt in attempts:
            attempt_id = attempt.get('id', 'N/A')
            lines.append(f"## 尝试 #{attempt_id}")
            lines.append("")
            lines.append(f"| 属性 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 容器 ID | `{attempt.get('containerId', 'N/A')}` |")
            lines.append(f"| 节点 ID | {attempt.get('nodeId', 'N/A')} |")
            lines.append(f"| 节点 HTTP 地址 | {attempt.get('nodeHttpAddress', 'N/A')} |")
            lines.append(f"| 开始时间 | {_format_timestamp(attempt.get('startTime', 0))} |")
            
            logs_link = attempt.get('logsLink', '')
            if logs_link:
                lines.append(f"| 日志链接 | [查看日志]({logs_link}) |")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_list_tasks",
    annotations={
        "title": "列出作业任务",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_list_tasks(params: ListTasksInput) -> str:
    """
    列出指定作业的所有任务。
    
    可以按任务类型（Map 或 Reduce）过滤。
    
    Args:
        params (ListTasksInput): 包含 job_id 和可选的 task_type
    
    Returns:
        str: 任务列表
        
    Examples:
        - 列出所有任务: job_id="job_xxx"
        - 只列出 Map 任务: job_id="job_xxx", task_type="m"
        - 只列出 Reduce 任务: job_id="job_xxx", task_type="r"
    """
    try:
        query_params = {}
        if params.task_type:
            query_params["type"] = params.task_type.value

        data = await _make_request(
            f"mapreduce/jobs/{params.job_id}/tasks",
            query_params
        )
        tasks = data.get("tasks", {}).get("task", [])

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": len(tasks),
                "tasks": tasks
            }, indent=2, ensure_ascii=False)

        if not tasks:
            return "没有找到任务。"

        lines = [
            f"# 任务列表: {params.job_id}",
            f"共 **{len(tasks)}** 个任务",
            ""
        ]

        # 按类型分组
        map_tasks = [t for t in tasks if t.get('type') == 'MAP']
        reduce_tasks = [t for t in tasks if t.get('type') == 'REDUCE']

        if map_tasks:
            lines.append(f"## Map 任务 ({len(map_tasks)} 个)")
            lines.append("")
            lines.append("| 任务 ID | 状态 | 进度 | 耗时 |")
            lines.append("|---------|------|------|------|")
            for task in map_tasks:
                task_id = task.get('id', 'N/A')
                state = task.get('state', 'N/A')
                progress = task.get('progress', 0)
                elapsed = _format_duration(task.get('elapsedTime', 0))
                lines.append(f"| `{task_id}` | {state} | {progress:.1f}% | {elapsed} |")
            lines.append("")

        if reduce_tasks:
            lines.append(f"## Reduce 任务 ({len(reduce_tasks)} 个)")
            lines.append("")
            lines.append("| 任务 ID | 状态 | 进度 | 耗时 |")
            lines.append("|---------|------|------|------|")
            for task in reduce_tasks:
                task_id = task.get('id', 'N/A')
                state = task.get('state', 'N/A')
                progress = task.get('progress', 0)
                elapsed = _format_duration(task.get('elapsedTime', 0))
                lines.append(f"| `{task_id}` | {state} | {progress:.1f}% | {elapsed} |")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_task",
    annotations={
        "title": "获取任务详情",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_task(params: GetTaskInput) -> str:
    """
    获取指定任务的详细信息。
    
    Args:
        params (GetTaskInput): 包含 job_id 和 task_id
    
    Returns:
        str: 任务详情
    """
    try:
        data = await _make_request(
            f"mapreduce/jobs/{params.job_id}/tasks/{params.task_id}"
        )
        task = data.get("task", {})

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(task, indent=2, ensure_ascii=False)

        task_type = task.get('type', 'UNKNOWN')
        state = task.get('state', 'N/A')
        state_icon = {
            'SUCCEEDED': '✅',
            'FAILED': '❌',
            'KILLED': '⚠️',
            'RUNNING': '🔄'
        }.get(state, '❓')

        lines = [
            f"# {state_icon} 任务详情: {task.get('id', 'N/A')}",
            "",
            f"| 属性 | 值 |",
            f"|------|-----|",
            f"| 任务 ID | `{task.get('id', 'N/A')}` |",
            f"| 类型 | {task_type} |",
            f"| 状态 | {state} |",
            f"| 进度 | {task.get('progress', 0):.1f}% |",
            f"| 开始时间 | {_format_timestamp(task.get('startTime', 0))} |",
            f"| 结束时间 | {_format_timestamp(task.get('finishTime', 0))} |",
            f"| 耗时 | {_format_duration(task.get('elapsedTime', 0))} |",
            f"| 成功尝试 | `{task.get('successfulAttempt', 'N/A')}` |",
        ]

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_task_counters",
    annotations={
        "title": "获取任务计数器",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_task_counters(params: GetTaskCountersInput) -> str:
    """
    获取指定任务的计数器信息。
    
    Args:
        params (GetTaskCountersInput): 包含 job_id 和 task_id
    
    Returns:
        str: 任务计数器信息
    """
    try:
        data = await _make_request(
            f"mapreduce/jobs/{params.job_id}/tasks/{params.task_id}/counters"
        )
        counters = data.get("jobTaskCounters", {})

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(counters, indent=2, ensure_ascii=False)

        task_id = counters.get('id', params.task_id)
        return _format_counters_markdown(
            counters,
            f"任务计数器: {task_id}"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_list_task_attempts",
    annotations={
        "title": "列出任务尝试",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_list_task_attempts(params: ListTaskAttemptsInput) -> str:
    """
    列出指定任务的所有尝试。
    
    当任务失败时会进行重试，每次重试都是一个新的尝试。
    
    Args:
        params (ListTaskAttemptsInput): 包含 job_id 和 task_id
    
    Returns:
        str: 任务尝试列表
    """
    try:
        data = await _make_request(
            f"mapreduce/jobs/{params.job_id}/tasks/{params.task_id}/attempts"
        )
        attempts = data.get("taskAttempts", {}).get("taskAttempt", [])

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": len(attempts),
                "attempts": attempts
            }, indent=2, ensure_ascii=False)

        if not attempts:
            return "没有找到任务尝试记录。"

        lines = [
            f"# 任务尝试列表",
            f"**任务 ID**: `{params.task_id}`",
            f"共 **{len(attempts)}** 次尝试",
            ""
        ]

        for attempt in attempts:
            attempt_id = attempt.get('id', 'N/A')
            state = attempt.get('state', 'N/A')
            state_icon = {
                'SUCCEEDED': '✅',
                'FAILED': '❌',
                'KILLED': '⚠️'
            }.get(state, '❓')

            lines.append(f"## {state_icon} {attempt_id}")
            lines.append("")
            lines.append(f"| 属性 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 状态 | {state} |")
            lines.append(f"| 类型 | {attempt.get('type', 'N/A')} |")
            lines.append(f"| 进度 | {attempt.get('progress', 0):.1f}% |")
            lines.append(f"| 容器 ID | `{attempt.get('assignedContainerId', 'N/A')}` |")
            lines.append(f"| 节点 | {attempt.get('nodeHttpAddress', 'N/A')} |")
            lines.append(f"| 机架 | {attempt.get('rack', 'N/A')} |")
            lines.append(f"| 开始时间 | {_format_timestamp(attempt.get('startTime', 0))} |")
            lines.append(f"| 结束时间 | {_format_timestamp(attempt.get('finishTime', 0))} |")
            lines.append(f"| 耗时 | {_format_duration(attempt.get('elapsedTime', 0))} |")
            
            diagnostics = attempt.get('diagnostics')
            if diagnostics:
                lines.append(f"| 诊断信息 | {diagnostics} |")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_task_attempt",
    annotations={
        "title": "获取任务尝试详情",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_task_attempt(params: GetTaskAttemptInput) -> str:
    """
    获取指定任务尝试的详细信息。
    
    对于 Reduce 任务尝试，还包含 Shuffle 和 Merge 阶段的时间信息。
    
    Args:
        params (GetTaskAttemptInput): 包含 job_id, task_id 和 attempt_id
    
    Returns:
        str: 任务尝试详情
    """
    try:
        data = await _make_request(
            f"mapreduce/jobs/{params.job_id}/tasks/{params.task_id}/attempts/{params.attempt_id}"
        )
        attempt = data.get("taskAttempt", {})

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(attempt, indent=2, ensure_ascii=False)

        state = attempt.get('state', 'N/A')
        state_icon = {
            'SUCCEEDED': '✅',
            'FAILED': '❌',
            'KILLED': '⚠️'
        }.get(state, '❓')

        lines = [
            f"# {state_icon} 任务尝试详情",
            f"**尝试 ID**: `{attempt.get('id', 'N/A')}`",
            "",
            "## 基本信息",
            f"| 属性 | 值 |",
            f"|------|-----|",
            f"| 状态 | {state} |",
            f"| 类型 | {attempt.get('type', 'N/A')} |",
            f"| 进度 | {attempt.get('progress', 0):.1f}% |",
            "",
            "## 执行环境",
            f"| 属性 | 值 |",
            f"|------|-----|",
            f"| 容器 ID | `{attempt.get('assignedContainerId', 'N/A')}` |",
            f"| 节点地址 | {attempt.get('nodeHttpAddress', 'N/A')} |",
            f"| 机架 | {attempt.get('rack', 'N/A')} |",
            "",
            "## 时间信息",
            f"| 阶段 | 时间/耗时 |",
            f"|------|----------|",
            f"| 开始时间 | {_format_timestamp(attempt.get('startTime', 0))} |",
            f"| 结束时间 | {_format_timestamp(attempt.get('finishTime', 0))} |",
            f"| 总耗时 | {_format_duration(attempt.get('elapsedTime', 0))} |",
        ]

        # Reduce 任务特有的阶段时间
        if attempt.get('type') == 'REDUCE':
            lines.append(f"| Shuffle 完成时间 | {_format_timestamp(attempt.get('shuffleFinishTime', 0))} |")
            lines.append(f"| Merge 完成时间 | {_format_timestamp(attempt.get('mergeFinishTime', 0))} |")
            lines.append(f"| Shuffle 耗时 | {_format_duration(attempt.get('elapsedShuffleTime', 0))} |")
            lines.append(f"| Merge 耗时 | {_format_duration(attempt.get('elapsedMergeTime', 0))} |")
            lines.append(f"| Reduce 耗时 | {_format_duration(attempt.get('elapsedReduceTime', 0))} |")

        diagnostics = attempt.get('diagnostics')
        if diagnostics:
            lines.extend([
                "",
                "## 诊断信息",
                "```",
                diagnostics,
                "```"
            ])

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_task_attempt_counters",
    annotations={
        "title": "获取任务尝试计数器",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_task_attempt_counters(params: GetTaskAttemptCountersInput) -> str:
    """
    获取指定任务尝试的计数器信息。
    
    Args:
        params (GetTaskAttemptCountersInput): 包含 job_id, task_id 和 attempt_id
    
    Returns:
        str: 任务尝试计数器信息
    """
    try:
        data = await _make_request(
            f"mapreduce/jobs/{params.job_id}/tasks/{params.task_id}/attempts/{params.attempt_id}/counters"
        )
        counters = data.get("jobTaskAttemptCounters", {})

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(counters, indent=2, ensure_ascii=False)

        attempt_id = counters.get('id', params.attempt_id)
        return _format_counters_markdown(
            counters,
            f"任务尝试计数器: {attempt_id}"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_task_attempt_logs",
    annotations={
        "title": "获取任务尝试日志",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_task_attempt_logs(params: GetTaskAttemptLogsInput) -> str:
    """
    获取指定任务尝试的容器日志内容。
    
    该工具通过以下步骤获取日志：
    1. 查询任务尝试信息获取容器 ID 和节点地址
    2. 查询作业信息获取用户名
    3. 构造日志 URL 并获取日志内容
    
    支持的日志类型包括：
    - stdout: 标准输出（默认）
    - stderr: 标准错误
    - syslog: 系统日志
    - syslog.shuffle: Shuffle 系统日志
    - prelaunch.out: 预启动输出
    - prelaunch.err: 预启动错误
    - container-localizer-syslog: 容器本地化系统日志
    
    Args:
        params (GetTaskAttemptLogsInput): 包含 job_id, task_id, attempt_id 和 log_type
    
    Returns:
        str: 日志内容，Markdown 或 JSON 格式
        
    Examples:
        - 获取 stdout 日志: job_id="job_xxx", task_id="task_xxx", attempt_id="attempt_xxx"
        - 获取 stderr 日志: job_id="job_xxx", task_id="task_xxx", attempt_id="attempt_xxx", log_type="stderr"
    """
    try:
        # 1. 获取任务尝试信息
        attempt_data = await _make_request(
            f"mapreduce/jobs/{params.job_id}/tasks/{params.task_id}/attempts/{params.attempt_id}"
        )
        attempt = attempt_data.get("taskAttempt", {})
        
        container_id = attempt.get("assignedContainerId")
        node_http_address = attempt.get("nodeHttpAddress")
        
        if not container_id:
            return "错误：无法获取容器 ID 信息。请检查 attempt_id 是否正确。"
        if not node_http_address:
            return "错误：无法获取节点地址信息。请检查 attempt_id 是否正确。"
        
        # 2. 获取作业信息以获取用户名
        job_data = await _make_request(f"mapreduce/jobs/{params.job_id}")
        job = job_data.get("job", {})
        user = job.get("user")
        
        if not user:
            return "错误：无法获取作业用户信息。请检查 job_id 是否正确。"
        
        # 3. 构造 NodeManager 地址
        hostname = _extract_hostname(node_http_address)
        node_manager = f"{hostname}:{NODEMANAGER_PORT}"
        
        # 4. 构造日志 URL
        log_url = (
            f"{LOGS_BASE_URL}/{node_manager}/{container_id}/"
            f"{params.attempt_id}/{user}/{params.log_type.value}/"
            f"?start=0&start.time=0&end.time=9223372036854775807"
        )
        
        logger.info(f"获取日志 URL: {log_url}")
        
        # 5. 获取日志 HTML
        html_content = await _fetch_logs_html(log_url)
        
        # 6. 提取 <pre> 标签中的日志内容
        log_content = _extract_pre_content(html_content)
        
        if not log_content:
            return f"日志为空或无法解析日志内容。\n\n**日志 URL**: {log_url}"
        
        # 7. 格式化输出
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "job_id": params.job_id,
                "task_id": params.task_id,
                "attempt_id": params.attempt_id,
                "container_id": container_id,
                "node_manager": node_manager,
                "user": user,
                "log_type": params.log_type.value,
                "log_url": log_url,
                "content": log_content
            }, indent=2, ensure_ascii=False)
        
        # Markdown 格式输出
        lines = [
            f"# 任务尝试日志: {params.log_type.value}",
            "",
            "## 日志信息",
            f"| 属性 | 值 |",
            f"|------|-----|",
            f"| 作业 ID | `{params.job_id}` |",
            f"| 任务 ID | `{params.task_id}` |",
            f"| 尝试 ID | `{params.attempt_id}` |",
            f"| 容器 ID | `{container_id}` |",
            f"| 节点 | {node_manager} |",
            f"| 用户 | {user} |",
            f"| 日志类型 | {params.log_type.value} |",
            "",
            "## 日志内容",
            "```",
            log_content,
            "```"
        ]
        
        return "\n".join(lines)
        
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="jobhistory_get_task_attempt_logs_partial",
    annotations={
        "title": "部分读取任务尝试日志",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
@log_tool_call
async def jobhistory_get_task_attempt_logs_partial(params: GetTaskAttemptLogsPartialInput) -> str:
    """
    部分读取指定任务尝试的容器日志内容。
    
    该工具按字节范围读取日志，适用于：
    - 大任务或长期运行任务产生的大量日志
    - 快速查看日志末尾的错误信息（任务失败分析）
    - 节省 Token 消耗，避免一次性读取全部内容
    
    字节范围参数说明：
    - start: 起始字节位置
      - 正数: 从文件开头计算（0 表示第一个字节）
      - 负数: 从文件末尾倒数（-4096 表示倒数 4096 字节）
    - end: 结束字节位置
      - 正数: 具体字节位置
      - 0: 表示文件末尾
    
    常用场景：
    - 任务失败分析: start=-4096, end=0 (读取末尾 4KB，通常包含错误信息)
    - 查看启动日志: start=0, end=2048 (读取开头 2KB)
    - 读取中间部分: start=10240, end=20480 (读取 10KB-20KB 范围)
    
    如果部分日志无法完成分析，请使用 jobhistory_get_task_attempt_logs 获取完整日志。
    
    Args:
        params (GetTaskAttemptLogsPartialInput): 包含 job_id, task_id, attempt_id, log_type, start, end
    
    Returns:
        str: 部分日志内容，Markdown 或 JSON 格式
        
    Examples:
        - 读取 syslog 末尾 4KB: job_id="job_xxx", task_id="task_xxx", attempt_id="attempt_xxx", log_type="syslog"
        - 读取 stderr 末尾 8KB: job_id="job_xxx", ..., log_type="stderr", start=-8192, end=0
        - 读取 stdout 开头 2KB: job_id="job_xxx", ..., log_type="stdout", start=0, end=2048
    """
    try:
        # 1. 获取任务尝试信息
        attempt_data = await _make_request(
            f"mapreduce/jobs/{params.job_id}/tasks/{params.task_id}/attempts/{params.attempt_id}"
        )
        attempt = attempt_data.get("taskAttempt", {})
        
        container_id = attempt.get("assignedContainerId")
        node_http_address = attempt.get("nodeHttpAddress")
        
        if not container_id:
            return "错误：无法获取容器 ID 信息。请检查 attempt_id 是否正确。"
        if not node_http_address:
            return "错误：无法获取节点地址信息。请检查 attempt_id 是否正确。"
        
        # 2. 获取作业信息以获取用户名
        job_data = await _make_request(f"mapreduce/jobs/{params.job_id}")
        job = job_data.get("job", {})
        user = job.get("user")
        
        if not user:
            return "错误：无法获取作业用户信息。请检查 job_id 是否正确。"
        
        # 3. 构造 NodeManager 地址
        hostname = _extract_hostname(node_http_address)
        node_manager = f"{hostname}:{NODEMANAGER_PORT}"
        
        # 4. 构造日志 URL（使用 start 和 end 参数）
        log_url = (
            f"{LOGS_BASE_URL}/{node_manager}/{container_id}/"
            f"{params.attempt_id}/{user}/{params.log_type.value}/"
            f"?start={params.start}&end={params.end}"
        )
        
        logger.info(f"获取部分日志 URL: {log_url}")
        
        # 5. 获取日志 HTML
        html_content = await _fetch_logs_html(log_url)
        
        # 6. 提取 <pre> 标签中的日志内容
        log_content = _extract_pre_content(html_content)
        
        if not log_content:
            return f"日志为空或无法解析日志内容。\n\n**日志 URL**: {log_url}"
        
        # 计算读取范围描述
        if params.start < 0:
            range_desc = f"末尾 {abs(params.start)} 字节"
        elif params.end == 0:
            range_desc = f"从 {params.start} 字节到末尾"
        else:
            range_desc = f"{params.start} - {params.end} 字节"
        
        # 7. 格式化输出
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "job_id": params.job_id,
                "task_id": params.task_id,
                "attempt_id": params.attempt_id,
                "container_id": container_id,
                "node_manager": node_manager,
                "user": user,
                "log_type": params.log_type.value,
                "byte_range": {
                    "start": params.start,
                    "end": params.end,
                    "description": range_desc
                },
                "log_url": log_url,
                "content_length": len(log_content),
                "content": log_content
            }, indent=2, ensure_ascii=False)
        
        # Markdown 格式输出
        lines = [
            f"# 任务尝试日志（部分）: {params.log_type.value}",
            "",
            "## 日志信息",
            f"| 属性 | 值 |",
            f"|------|-----|",
            f"| 作业 ID | `{params.job_id}` |",
            f"| 任务 ID | `{params.task_id}` |",
            f"| 尝试 ID | `{params.attempt_id}` |",
            f"| 容器 ID | `{container_id}` |",
            f"| 节点 | {node_manager} |",
            f"| 用户 | {user} |",
            f"| 日志类型 | {params.log_type.value} |",
            f"| 读取范围 | {range_desc} |",
            f"| 内容长度 | {len(log_content)} 字节 |",
            "",
            "## 日志内容",
            "```",
            log_content,
            "```",
            "",
            f"*提示：如需完整日志，请使用 `jobhistory_get_task_attempt_logs` 工具*"
        ]
        
        return "\n".join(lines)
        
    except Exception as e:
        return _handle_error(e)


# ==============================================================================
# 主入口
# ==============================================================================

if __name__ == "__main__":
    import sys
    
    # 检查是否使用 HTTP 传输模式
    use_http = "--http" in sys.argv or os.getenv("MCP_TRANSPORT", "").lower() == "http"
    
    if use_http:
        # HTTP 模式 - 用于远程服务器部署
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8080"))
        logger.info(f"启动 HTTP 传输模式: http://{host}:{port}")
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        # stdio 模式 - 默认，用于本地部署
        logger.info("启动 stdio 传输模式")
        mcp.run()

# JobHistory MCP Server Docker Image
# 基于 Python 3.11 slim 镜像，体积小且安全

FROM python:3.11-slim

# 设置元数据
LABEL maintainer="Winston"
LABEL description="MCP Server for Hadoop JobHistory REST API"
LABEL version="1.0.0"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY jobhistory_mcp.py .

# 创建非 root 用户运行应用（安全最佳实践）
RUN useradd --create-home --shell /bin/bash mcpuser && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

# 默认环境变量（可在运行时覆盖）
ENV JOBHISTORY_URL="http://localhost:19888/ws/v1/history"

# 健康检查（可选，验证 Python 环境）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import mcp; import httpx; import pydantic; print('OK')" || exit 1

# 默认命令：运行 MCP Server
CMD ["python", "jobhistory_mcp.py"]

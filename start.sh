#!/bin/bash
# 激活 conda 环境
source /app/miniconda3/etc/profile.d/conda.sh
conda activate py310
# 验证 Python 版本
echo "Python version:"
python --version
# 启动服务
exec python /app/JobHistoryMcpServer/jobhistory_mcp.py --http
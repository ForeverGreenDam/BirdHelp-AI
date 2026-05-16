# ============================================================
# BirdHelp AI 模块 — Docker 镜像
# ============================================================
FROM python:3.12-slim

LABEL app="BirdHelp-AI"
LABEL description="大学生文档助手 AI 能力层"

# 安装系统依赖:
#   libxml2          — python-pptx 解析依赖
#   libreoffice-writer — PDF 生成: .docx → .pdf 无头转换
# 使用国内清华源加速
RUN sed -i "s@deb.debian.org@mirrors.tuna.tsinghua.edu.cn@g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        curl \
        libxml2 \
        libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 运行用户
RUN useradd -r -s /bin/false birdhelp

# 工作目录
WORKDIR /app

# 先复制依赖文件单独构建层（利用 Docker 缓存）
COPY requirements.txt .

# 安装依赖（强制使用国内清华源，超时必好）
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    --default-timeout=100

# 复制项目代码
COPY --chown=birdhelp:birdhelp . .

# 临时文件目录
RUN mkdir -p /tmp/birdhelp && chown birdhelp:birdhelp /tmp/birdhelp

# 切换到非 root 用户
USER birdhelp

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8686/ || exit 1

EXPOSE 8686
ENV PYTHONUNBUFFERED=1


CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8686", "--workers", "1" , "--log-level", "debug"]

# y2b Dockerfile for ARM64 (Orange Pi Zero 3)
# 增量升级方式：基于已有镜像添加新依赖
# 适用于网络受限环境

FROM flask-y2b:latest

WORKDIR /app

USER root

# 清理旧代码
RUN rm -rf /app/src /app/cli

# 复制新代码
COPY src ./src
COPY cli ./cli
COPY db ./db
COPY forms ./forms
COPY static ./static
COPY upgrade_yt_dlp.py ./
COPY upgrade_bilibili_api.py ./

# 安装新依赖（使用已配置的阿里云镜像源）
RUN python -m pip install --no-cache-dir \
    'openai>=1.0.0' \
    'httpx==0.28.1' \
    'srt==3.5.3'

# 配置端口
ARG PORT=5000
ENV PORT=${PORT}
EXPOSE ${PORT}

# 启动命令
ENTRYPOINT ["sh", "-c", "python src/index.py --port $PORT"]

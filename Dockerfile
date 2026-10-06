# y2b Dockerfile for ARM64 (Orange Pi Zero 3)
# 增量升级方式：基于已有镜像添加新依赖
# 适用于网络受限环境

FROM flask-y2b:upgraded

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

# 安装 nodejs（yt-dlp 需要 JS runtime 解决 YouTube 验证挑战）
RUN apk add --no-cache nodejs npm

# 配置 yt-dlp 使用 node 作为 JS runtime
RUN mkdir -p /root/.config/yt-dlp && \
    echo "--js-runtimes node" > /root/.config/yt-dlp/config

# 清除所有代理环境变量并安装新依赖
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY && \
    rm -rf /root/.pip /root/.config/pip /opt/venv/pip.conf && \
    python -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    python -m pip config set install.trusted-host mirrors.aliyun.com && \
    python -m pip install --no-cache-dir \
        'openai>=1.0.0' \
        'httpx==0.28.1' \
        'srt==3.5.3' \
        'PySocks>=1.7.0'

# 清除环境变量（让应用自行决定是否使用代理）
ENV http_proxy="" \
    https_proxy="" \
    HTTP_PROXY="" \
    HTTPS_PROXY="" \
    no_proxy="" \
    NO_PROXY=""

# 配置端口
ARG PORT=5000
ENV PORT=${PORT}
EXPOSE ${PORT}

# 启动命令
ENTRYPOINT ["sh", "-c", "python src/index.py --port $PORT"]

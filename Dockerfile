FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-alpine-linuxarm64

WORKDIR /app

USER root

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories
RUN apk add --no-cache --update-cache ffmpeg
RUN apk add --no-cache --update-cache git
RUN apk add --no-cache --update-cache vim
RUN mkdir -p /usr/share/fonts/ukai
# https://github.com/SilentByte/fonts-arphic-ukai/raw/master/fonts-arphic-ukai/ukai.ttc
ADD ./static/ukai.ttc /usr/share/fonts/ukai/

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip config set global.index-url http://mirrors.aliyun.com/pypi/simple/
RUN pip config set install.trusted-host mirrors.aliyun.com
RUN pip install flask[async]

COPY requirements.txt .
RUN pip install -r requirements.txt
# RUN pip install git+https://github.com/Nemo2011/bilibili-api.git#main
RUN pip install git+https://gitee.com/nemo2011/bilibili-api.git#main

COPY . /app
RUN python db/init_db.py

ARG PORT=5000
ENV PORT=${PORT}
EXPOSE ${PORT}
ENTRYPOINT ["sh", "-c", "python src/index.py --port $PORT"]

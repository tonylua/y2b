FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.9-slim

WORKDIR /app
COPY . /app

RUN echo "deb https://mirrors.huaweicloud.com/debian bullseye main contrib" >/etc/apt/sources.list
RUN echo "deb https://mirrors.huaweicloud.com/debian-security bullseye-security main contrib" >>/etc/apt/sources.list
RUN echo "deb https://mirrors.huaweicloud.com/debian bullseye-updates main contrib" >>/etc/apt/sources.list
RUN pip config set global.index-url http://mirrors.aliyun.com/pypi/simple/
RUN pip config set install.trusted-host mirrors.aliyun.com

USER root
RUN apt -y update
USER root
RUN apt install -y --fix-missing ffmpeg
RUN apt-get update
RUN apt-get install -y ffmpeg
RUN apt-get install fonts-arphic-ukai fonts-arphic-uming
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir flask[async]

# TODO 改bili库

# 执行数据库初始化脚本
RUN python db/init_db.py

# 暴露端口
EXPOSE 5000

# 运行 Flask 应用
CMD ["python", "src/index.py"]

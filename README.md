``` 
# ~/.docker/config.json
"proxies":
{
   "default":
   {
     "httpProxy": "http://127.0.0.1:7890",
     "httpsProxy": "http://127.0.0.1:7890",
     "noProxy": "localhost"
   }
}
}
```

```
docker build -t flask-y2b .
docker run --rm --net host --restart always -p 5000:5000 -d flask-y2b
docker stats <containerId> # 查看运行状态
docker logs -f <containerId> # 查看实时运行输出
```

---

<del>
## 初始化
sudo apt install ffmpeg
sudo apt-get install fonts-arphic-ukai fonts-arphic-uming
pip install -r requirements.txt
vim /usr/local/lib/python3.11/dist-packages/bilibili_api/video_uploader.py
# 或 vim app-venv/lib/python3.10/site-packages/bilibili_api/video_uploader.py
# 修改这行
"porder": self.porder.__dict__() if self.porder else None,
# 56x行meta中增加：
"source": self.source,
pip uninstall flask
pip install flask[async]
## DB
sudo apt-get install sqlite3
python db/init_db.py
sqlite3 db/database.db
SELECT * FROM videos;
.schema videos
## 转换参数
python cli_to_api.py --extractor-arg "youtube:player_client=ios"
</del>
pip3 install bilibili-api-python

sudo apt-get install fonts-arphic-ukai fonts-arphic-uming

vim /usr/local/lib/python3.11/dist-packages/bilibili_api/video_uploader.py
# 修改这行
"porder": self.porder.__dict__() if self.porder else None,
# 56x行meta中增加：
"source": self.source,

sudo apt-get install sqlite3
sqlite3 db/database.db
SELECT * FROM videos;
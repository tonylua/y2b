pip3 install bilibili-api-python

vim /usr/local/lib/python3.11/dist-packages/bilibili_api/video_uploader.py
# 修改这行
"porder": self.porder.__dict__() if self.porder else None,
# 56x行meta中增加：
"source": self.source,
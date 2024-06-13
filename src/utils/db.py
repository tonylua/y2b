import sqlite3
from contextlib import contextmanager
from .sys import join_root_path

db_dir = join_root_path('db')

class BaseORM:
    def __init__(self, db_name):
        db_path = f"{db_dir}/{db_name}"
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # 设置row_factory，以便查询时使用字典结果
        print('db path', db_path)
        self.cursor = self.conn.cursor()

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    @contextmanager
    def transaction(self):
        try:
            yield
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise e

class VideoDB(BaseORM):
    def __init__(self, db_name = 'database.db'):
        super().__init__(db_name)
        self.table_name = 'videos'

    def create_video(self, user, origin_id, title, save_path, origin_url):
        """插入一条新的视频记录"""
        with self.transaction():
            query = f"""
            INSERT INTO {self.table_name} (user, origin_id, title, save_path, origin_url)
            VALUES (?, ?, ?, ?, ?);
            """
            self.cursor.execute(query, (user, origin_id, title, save_path, origin_url))
            return self.cursor.lastrowid

    def read_video(self, id):
        """根据ID读取视频记录"""
        with self.transaction():
            query = f"SELECT * FROM {self.table_name} WHERE id = ? ;"
            self.cursor.execute(query, (id,))
            row = self.cursor.fetchone()
            return dict(row)
    
    def list_videos(self, user):
        """列出所有视频记录"""
        with self.transaction():
            query = f"SELECT * FROM {self.table_name} WHERE user = {user};"
            self.cursor.execute(query)
            # return self.cursor.fetchall()
            return [dict(row) for row in self.cursor.fetchall()]  # 转换为字典列表

    def update_video(self, id, **kwargs):
        """根据ID更新视频记录"""
        set_clause = ', '.join([f"{key} = ?" for key in kwargs])
        with self.transaction():
            query = f"""
            UPDATE {self.table_name}
            SET {set_clause}
            WHERE id = ?;
            """
            values = list(kwargs.values()) + [id]
            self.cursor.execute(query, values)

    def delete_video(self, id):
        """根据ID删除视频记录"""
        with self.transaction():
            query = f"DELETE FROM {self.table_name} WHERE id = ?;"
            self.cursor.execute(query, (id,))

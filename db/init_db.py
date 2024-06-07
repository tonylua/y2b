import sqlite3
import os

current_file_path = os.path.abspath(__file__)
current_dir_path = os.path.dirname(current_file_path)

# 产生 .db
connection = sqlite3.connect(f'{current_dir_path}/database.db')
with open(f'{current_dir_path}/schema.sql') as f:
    connection.executescript(f.read())

# cur = connection.cursor()

connection.commit()
connection.close()
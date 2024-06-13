import os
import json

def ensure_file_exists(filepath, content):
    """确保文件存在，如果不存在则创建并写入默认内容"""
    if not os.path.exists(filepath):
        with open(filepath, 'w', encoding='utf-8') as file:
            json.dump(content, file, ensure_ascii=False, indent=4)

def main():
    # 定义配置文件路径和初始内容
    app_accounts_path = 'config/app_accounts.json'
    bili_cookie_path = 'config/bili_cookie.json'
    
    # 初始化app_accounts.json的内容
    app_accounts_content = {
        "users": [
            {
                "username": "",
                "password": ""
            }
        ]
    }

    # 初始化bili_cookie.json的内容
    bili_cookie_content = {
        "uid": "43244387",
        "SESSDATA": "",
        "bili_jct": "",
        "buvid3": ""
    }
    
    # 确保两个配置文件存在
    ensure_file_exists(app_accounts_path, app_accounts_content)
    ensure_file_exists(bili_cookie_path, bili_cookie_content)
    
    print("配置文件初始化完成。")

if __name__ == "__main__":
    main()

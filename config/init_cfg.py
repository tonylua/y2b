import os
import json

def ensure_file_exists(filepath, content):
    """确保文件存在，如果不存在则创建并写入默认内容"""
    if not os.path.exists(filepath):
        with open(filepath, 'w', encoding='utf-8') as file:
            json.dump(content, file, ensure_ascii=False, indent=4)
        print(f"Created {filepath}")
    else:
        print(f"Already exists: {filepath}")

def main():
    # 定义配置文件路径和初始内容（敏感配置用 _ 前缀避免误提交）
    app_accounts_path = 'config/_app_accounts.json'
    bili_cookie_path = 'config/_bili_cookie.json'
    llm_config_path = 'config/_llm.json'
    upload_config_path = 'config/_upload.json'

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

    # 初始化 llm.json 的内容
    llm_config_content = {
        "_comment": "LLM 翻译配置（必需）。填写 api_key 后即可使用",
        "enabled": True,

        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-flash",
        "api_key": "",

        "features": {
            "term_extraction": True,
            "context_translation": True,
            "proofread": False
        },

        "translation": {
            "mode": "sentence",
            "max_line_chars": 40,
            "temperature": 0.3,
            "max_tokens": 2048
        },

        "_usage_note": "填写 api_key 后即可使用。DeepSeek 约 ¥0.02/视频"
    }

    # 初始化 upload.json 的内容
    upload_config_content = {
        "_comment": "上传配置（本机生效，不入库）。上传成功后自动把视频加入指定合集（新版合集/SEASON）。season_id 优先，按 id 找不到时再用 season_title 兜底；两者都留空则不启用。合集列表可用 python cli/seasons.py 查看。",
        "season_id": 0,
        "season_title": ""
    }

    # 确保所有配置文件存在
    ensure_file_exists(app_accounts_path, app_accounts_content)
    ensure_file_exists(bili_cookie_path, bili_cookie_content)
    ensure_file_exists(llm_config_path, llm_config_content)
    ensure_file_exists(upload_config_path, upload_config_content)

    print("\n配置文件初始化完成。")
    print("提示：")
    print("  - 编辑 config/_app_accounts.json 填写 B站账号密码")
    print("  - 编辑 config/_bili_cookie.json 填写 cookie（可选，用于上传）")
    print("  - 编辑 config/_llm.json 填写 API key 启用 LLM 增强（可选）")
    print("  - 编辑 config/_upload.json 设置上传后自动加入的合集（可选）")
    print("  - config/glossary.json 可根据视频内容添加专业术语")

if __name__ == "__main__":
    main()

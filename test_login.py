from utils.account import AccountUtil

def main():
    try:
        bili = AccountUtil(config_path="/root/move_video/bili_cookie.json")
        bili.verify_cookie()
    except Exception as e:
        raise(e)

main()

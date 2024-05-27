from utils import AccountUtil

def main():
    try:
        bili = AccountUtil(config_path="./bili_cookie.json")
        bili.verify_cookie()
    except Exception as e:
        raise(e)

main()

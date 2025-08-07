import os
from src.utils.subtitle import download_subtitles

def main():
    save_srt = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"123.srt") 
    download_subtitles("AAkrmfkC1L4", save_srt, "cn")

if __name__ == "__main__":
    main()

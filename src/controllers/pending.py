import yt_dlp
 
url = 'https://www.youtube.com/playlist?list=PLVqKV0TGDQZdJCPzLHfUNObyeHVeSGddU'
 
# Set up yt-dlp options to only get video titles
ydl_opts = {
    'skip_download': True,
    'writesubtitles': False,
    'writeinfojson': False,
    'writeannotations': False,
    'write_all_thumbnails': False,
    'ignoreerrors': True,
    'format': 'best',
    'simulate': True,
    'dump_single_json': True,
    'extract_flat': True,
    'youtube_include_dash_manifest': False,
}
 
# Create yt-dlp object and download video info
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    video_info = ydl.extract_info(url, download=False)
 
# Extract video titles from info
video_titles = [video['title'] for video in video_info['entries']]
 
print(video_titles)
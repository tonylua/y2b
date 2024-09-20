from flask import Flask, jsonify
import yt_dlp

def fetch_pending_list(): 
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
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        video_info = ydl.extract_info(url, download=False)
    
    entries = video_info.get('entries', [])
    video_data = [{
        'title': entry.get('title'),
        'url': entry.get('webpage_url'),
        'id': entry.get('id'),
        'duration': entry.get('duration'),
        'upload_date': entry.get('upload_date'),
        'thumbnail': entry.get('thumbnail'),
    } for entry in entries]
    
    return jsonify(video_data)
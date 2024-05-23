from flask import Flask, render_template_string

app = Flask(__name__)

@app.route('/')
def video_player():
    # 这里直接嵌入HTML字符串作为页面内容，实际项目中你可能希望将HTML放在单独的文件中
    html_content = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Video Player</title>
    </head>
    <body>
        <video width="640" height="480" controls>
            <source src="{{ url_for('static', filename='video.mp4') }}" type="video/mp4">
            <track kind="subtitles" label="English" srclang="en" src="static/video.en.srt" default>
            Your browser does not support the video tag.
        </video>
    </body>
    </html>
    '''
    return render_template_string(html_content)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

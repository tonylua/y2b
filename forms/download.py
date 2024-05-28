from flask import Flask
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import DataRequired, URL

class YouTubeDownloadForm(FlaskForm):
    sessdata = StringField('Sessdata')
    bili_jct = StringField('Bili_Jct')
    buvid3 = StringField('Buvid3')
    video_url = StringField('Video URL', validators=[DataRequired(), URL()])
    resolution = SelectField('Resolution', choices=[
        ('1080', '1080p'), 
        ('720', '720p'), 
        ('480', '480p'),
        ('360', '360p'),
    ], default='720')
    submit = SubmitField('下载')

from flask import Flask
from flask_wtf import FlaskForm
from wtforms import RadioField, StringField, IntegerField, SelectField, TextAreaField, SubmitField
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
    need_subtitle = RadioField(
        '添加字幕',
        choices=[('en', '英文'), ('cn', '中文'), ('', '不添加')],
        default='en'
    )
    auto_upload = RadioField(
        '自动上传',
        choices=[('1', '是'), ('', '否')],
        default='1'
    )
    tid = IntegerField('Tid', default=231, validators=[DataRequired()])
    tags = StringField('Tags', default='Youtube')
    desc = TextAreaField('Description')
    submit = SubmitField('下一步')

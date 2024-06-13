from flask import Flask
from flask_wtf import FlaskForm
from wtforms import HiddenField, StringField, IntegerField, TextAreaField, FileField, SelectMultipleField
from wtforms.validators import DataRequired

class BilibiliUploadForm(FlaskForm):
    sessdata = HiddenField('Sessdata', validators=[DataRequired()])
    bili_jct = HiddenField('Bili_Jct', validators=[DataRequired()])
    buvid3 = HiddenField('Buvid3', validators=[DataRequired()])
    tid = IntegerField('Tid', default=231, validators=[DataRequired()])
    title = StringField('Title', validators=[DataRequired()])
    tags = StringField('Tags')
    desc = TextAreaField('Description')
    cover = FileField('Custom Cover')

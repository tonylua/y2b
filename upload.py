from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, TextAreaField, FileField, SelectMultipleField
from wtforms.validators import DataRequired

class BilibiliUploadForm(FlaskForm):
    sessdata = StringField('Sessdata', validators=[DataRequired()])
    bili_jct = StringField('Bili_Jct', validators=[DataRequired()])
    buvid3 = StringField('Buvid3', validators=[DataRequired()])
    tid = IntegerField('Tid', default=231, validators=[DataRequired()])
    title = StringField('Title', validators=[DataRequired()])
    tags = StringField('Tags')
    desc = TextAreaField('Description')
    cover = FileField('Custom Cover')

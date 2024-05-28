import secrets
import os
from flask import Flask, session
from controllers.index_route import index_controller
from controllers.preview_route import preview_controller
from controllers.upload_route import upload_controller

app = Flask(__name__, template_folder='/root/move_video/templates')
app.config['SECRET_KEY'] = secrets.token_urlsafe(32) 
app.config['SESSION_TYPE'] = 'filesystem'

@app.before_request
def setup_session():
    session.permanent = True 

@app.route('/', methods=['GET', 'POST'])
def index():
    return index_controller(session)

@app.route('/preview', methods=['GET', 'POST'])
def preview():
    return preview_controller(session)

@app.route('/upload', methods=['GET', 'POST'])  
async def upload():
    return await upload_controller(session)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

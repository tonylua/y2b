from flask import Flask, request, redirect, url_for, render_template
from utils.account import load_app_accounts
from utils.sys import clear_video_directory

def login_controller(session):
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        accounts = load_app_accounts()
        for account in accounts:
            if account['username'] == username and account['password'] == password:
                print(f"Login successful! {username}", 'success')
                session["login_name"] = username
                return redirect(url_for('download')) 
        
        flash('Invalid username or password.', 'error')

    return render_template('login.html')
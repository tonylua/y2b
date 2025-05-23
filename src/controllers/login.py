from flask import Flask, request, redirect, url_for, render_template, flash
from utils.account import load_app_accounts
from utils.sys import clear_video_directory, join_root_path

def login_controller(session):
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        accounts = load_app_accounts()
        for account in accounts:
            if account['username'] == username and account['password'] == password:
                print(f"Login successful! {username}", 'success')
                session["login_name"] = username
                session['save_dir_rel'] = f"video/{username}"
                session['save_dir'] = join_root_path('static', session['save_dir_rel']) 
                return redirect(url_for('list_page')) 

        flash('Invalid username or password.', 'error')

    return render_template('login.html')

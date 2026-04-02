from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import json
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'ataa_secret_key_2024'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file_field):
    file = request.files.get(file_field)
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{int(time.time())}{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    return None

# الصفحة الرئيسية
@app.route('/')
def index():
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT *, (SELECT COUNT(*) FROM campaigns WHERE charity_id=charities.id) AS camp_count FROM charities")
    charities = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM charities")
    total_charities = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM campaigns")
    total_campaigns = cur.fetchone()[0]

    db.close()

    return render_template('index.html', charities=charities,
                           total_charities=total_charities,
                           total_campaigns=total_campaigns)

# تسجيل دخول الأدمن
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'admin' in session:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM admins WHERE username=? AND password=?", (username, password))
        admin = cur.fetchone()
        db.close()

        if admin:
            session['admin'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            flash('بيانات غلط', 'danger')

    return render_template('admin/login.html')

# داشبورد
@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) FROM charities")
    total_charities = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM campaigns")
    total_campaigns = cur.fetchone()[0]

    db.close()

    return render_template('admin/dashboard.html',
                           total_charities=total_charities,
                           total_campaigns=total_campaigns)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=81)
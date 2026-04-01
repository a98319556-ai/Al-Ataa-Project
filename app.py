from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
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


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file_field):
    """حفظ الصورة المرفوعة وإرجاع اسم الملف"""
    file = request.files.get(file_field)
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{int(time.time())}{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    return None


def get_db():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='ataa_partners',
        charset='utf8mb4'
    )


# ============================================================
# الصفحة الرئيسية
# ============================================================
@app.route('/')
def index():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT *, (SELECT COUNT(*) FROM campaigns WHERE charity_id=charities.id) AS camp_count FROM charities ORDER BY id ASC")
    charities = cur.fetchall()
    cur.execute("SELECT COUNT(*) AS total FROM charities")
    total_charities = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) AS total FROM campaigns")
    total_campaigns = cur.fetchone()['total']
    cur.close(); db.close()
    return render_template('index.html', charities=charities,
                           total_charities=total_charities,
                           total_campaigns=total_campaigns)


# ============================================================
# صفحة الجمعية
# ============================================================
@app.route('/charity/<int:charity_id>')
def charity_detail(charity_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM charities WHERE id = %s", (charity_id,))
    charity = cur.fetchone()
    if not charity:
        cur.close(); db.close()
        return render_template('404.html'), 404
    cur.execute("SELECT * FROM campaigns WHERE charity_id = %s ORDER BY created_at DESC", (charity_id,))
    campaigns = cur.fetchall()
    categories = list({c['category'] for c in campaigns})
    cur.close(); db.close()
    fields = [f.strip() for f in charity['fields'].split(',') if f.strip()] if charity['fields'] else []
    return render_template('charity_detail.html', charity=charity,
                           campaigns=campaigns, categories=categories, fields=fields)


# ============================================================
# صفحة الدفع
# ============================================================
@app.route('/pay/<int:campaign_id>')
def payment(campaign_id):
    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT * FROM campaigns WHERE id = %s", (campaign_id,))
    campaign = cur.fetchone()
    if not campaign:
        cur.close(); db.close()
        return render_template('404.html'), 404

    cur.execute("SELECT * FROM charities WHERE id = %s", (campaign['charity_id'],))
    charity = cur.fetchone()

    cur.execute("SELECT id, name FROM charities ORDER BY id ASC")
    all_charities = cur.fetchall()

    cur.execute("SELECT id, charity_id, title, goal_amount FROM campaigns ORDER BY charity_id, id ASC")
    all_campaigns = cur.fetchall()
    for c in all_campaigns:
        c['goal_amount'] = float(c['goal_amount'])

    cur.close(); db.close()

    back_url = url_for('charity_detail', charity_id=charity['id'])
    campaigns_json = json.dumps(
        [{'id': c['id'], 'charity_id': c['charity_id'], 'title': c['title']} for c in all_campaigns],
        ensure_ascii=False
    )

    return render_template('payment.html',
                           campaign=campaign,
                           charity=charity,
                           all_charities=all_charities,
                           all_campaigns=all_campaigns,
                           campaigns_json=campaigns_json,
                           back_url=back_url)


# Ajax: حملات جمعية معينة
@app.route('/api/campaigns/<int:charity_id>')
def api_campaigns(charity_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id, title FROM campaigns WHERE charity_id = %s ORDER BY id ASC", (charity_id,))
    campaigns = cur.fetchall()
    cur.close(); db.close()
    return jsonify(campaigns)


# ============================================================
# لوحة الأدمن
# ============================================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'admin' in session:
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM admins WHERE username=%s AND password=%s", (username, password))
        admin = cur.fetchone()
        cur.close(); db.close()
        if admin:
            session['admin'] = admin['username']
            return redirect(url_for('admin_dashboard'))
        flash('اسم المستخدم أو كلمة المرور غلط!', 'danger')
    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS t FROM charities")
    total_charities = cur.fetchone()['t']
    cur.execute("SELECT COUNT(*) AS t FROM campaigns")
    total_campaigns = cur.fetchone()['t']
    cur.execute("""SELECT c.*, COUNT(camp.id) AS campaign_count
                   FROM charities c LEFT JOIN campaigns camp ON c.id = camp.charity_id
                   GROUP BY c.id ORDER BY c.id ASC""")
    charities = cur.fetchall()
    cur.close(); db.close()
    return render_template('admin/dashboard.html', total_charities=total_charities,
                           total_campaigns=total_campaigns, charities=charities)


# ============================================================
# جمعيات
# ============================================================
@app.route('/admin/charity/add', methods=['GET', 'POST'])
def admin_add_charity():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        name        = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        fields      = request.form.get('fields', '').strip()
        stat1_num   = request.form.get('stat1_num', '').strip()
        stat1_label = request.form.get('stat1_label', '').strip()
        stat2_num   = request.form.get('stat2_num', '').strip()
        stat2_label = request.form.get('stat2_label', '').strip()
        stat3_num   = request.form.get('stat3_num', '').strip()
        stat3_label = request.form.get('stat3_label', '').strip()
        img = save_image('image')
        image_name = img if img else 'default.jpg'
        if not name or not description:
            flash('من فضلك املأ الاسم والوصف', 'danger')
        else:
            db = get_db(); cur = db.cursor()
            cur.execute("""INSERT INTO charities
                (name,description,image,fields,stat1_num,stat1_label,stat2_num,stat2_label,stat3_num,stat3_label)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (name, description, image_name, fields,
                 stat1_num, stat1_label, stat2_num, stat2_label, stat3_num, stat3_label))
            db.commit(); cur.close(); db.close()
            flash('تم إضافة الجمعية بنجاح!', 'success')
            return redirect(url_for('admin_dashboard'))
    return render_template('admin/add_charity.html')


@app.route('/admin/charity/edit/<int:cid>', methods=['GET', 'POST'])
def admin_edit_charity(cid):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM charities WHERE id=%s", (cid,))
    charity = cur.fetchone()
    if not charity:
        cur.close(); db.close()
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        name        = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        fields      = request.form.get('fields', '').strip()
        stat1_num   = request.form.get('stat1_num', '').strip()
        stat1_label = request.form.get('stat1_label', '').strip()
        stat2_num   = request.form.get('stat2_num', '').strip()
        stat2_label = request.form.get('stat2_label', '').strip()
        stat3_num   = request.form.get('stat3_num', '').strip()
        stat3_label = request.form.get('stat3_label', '').strip()
        img = save_image('image')
        image_name = img if img else charity['image']
        cur2 = db.cursor()
        cur2.execute("""UPDATE charities SET
            name=%s,description=%s,image=%s,fields=%s,
            stat1_num=%s,stat1_label=%s,stat2_num=%s,stat2_label=%s,stat3_num=%s,stat3_label=%s
            WHERE id=%s""",
            (name, description, image_name, fields,
             stat1_num, stat1_label, stat2_num, stat2_label, stat3_num, stat3_label, cid))
        db.commit(); cur2.close(); cur.close(); db.close()
        flash('تم التعديل بنجاح!', 'success')
        return redirect(url_for('admin_dashboard'))
    cur.close(); db.close()
    return render_template('admin/edit_charity.html', charity=charity)


@app.route('/admin/charity/delete/<int:cid>', methods=['POST'])
def admin_delete_charity(cid):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    db = get_db(); cur = db.cursor()
    cur.execute("DELETE FROM charities WHERE id=%s", (cid,))
    db.commit(); cur.close(); db.close()
    flash('تم حذف الجمعية وحملاتها', 'success')
    return redirect(url_for('admin_dashboard'))


# ============================================================
# حملات
# ============================================================
@app.route('/admin/campaigns/<int:cid>')
def admin_campaigns(cid):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM charities WHERE id=%s", (cid,))
    charity = cur.fetchone()
    cur.execute("SELECT * FROM campaigns WHERE charity_id=%s ORDER BY created_at DESC", (cid,))
    campaigns = cur.fetchall()
    cur.close(); db.close()
    return render_template('admin/campaigns.html', charity=charity, campaigns=campaigns)


@app.route('/admin/campaign/add/<int:cid>', methods=['GET', 'POST'])
def admin_add_campaign(cid):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM charities WHERE id=%s", (cid,))
    charity = cur.fetchone()
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        goal_amount = request.form.get('goal_amount', '0').strip()
        category    = request.form.get('category', 'عام').strip()
        img = save_image('image')
        image_name = img if img else 'default.jpg'
        if not title or not description:
            flash('من فضلك املأ الحقول المطلوبة', 'danger')
        else:
            cur2 = db.cursor()
            cur2.execute("""INSERT INTO campaigns (charity_id,title,description,goal_amount,image,category)
                            VALUES (%s,%s,%s,%s,%s,%s)""",
                         (cid, title, description, float(goal_amount or 0), image_name, category))
            db.commit(); cur2.close()
            flash('تم إضافة الحملة!', 'success')
            cur.close(); db.close()
            return redirect(url_for('admin_campaigns', cid=cid))
    cur.close(); db.close()
    return render_template('admin/add_campaign.html', charity=charity)


@app.route('/admin/campaign/edit/<int:camp_id>', methods=['GET', 'POST'])
def admin_edit_campaign(camp_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM campaigns WHERE id=%s", (camp_id,))
    campaign = cur.fetchone()
    if not campaign:
        return redirect(url_for('admin_dashboard'))
    cur.execute("SELECT * FROM charities WHERE id=%s", (campaign['charity_id'],))
    charity = cur.fetchone()
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        goal_amount = request.form.get('goal_amount', '0').strip()
        category    = request.form.get('category', 'عام').strip()
        img = save_image('image')
        image_name = img if img else campaign['image']
        cur2 = db.cursor()
        cur2.execute("""UPDATE campaigns SET title=%s,description=%s,goal_amount=%s,image=%s,category=%s
                        WHERE id=%s""",
                     (title, description, float(goal_amount or 0), image_name, category, camp_id))
        db.commit(); cur2.close(); cur.close(); db.close()
        flash('تم تعديل الحملة!', 'success')
        return redirect(url_for('admin_campaigns', cid=campaign['charity_id']))
    cur.close(); db.close()
    return render_template('admin/edit_campaign.html', campaign=campaign, charity=charity)


@app.route('/admin/campaign/delete/<int:camp_id>', methods=['POST'])
def admin_delete_campaign(camp_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT charity_id FROM campaigns WHERE id=%s", (camp_id,))
    row = cur.fetchone()
    cid = row['charity_id'] if row else 1
    cur2 = db.cursor()
    cur2.execute("DELETE FROM campaigns WHERE id=%s", (camp_id,))
    db.commit(); cur2.close(); cur.close(); db.close()
    flash('تم حذف الحملة', 'success')
    return redirect(url_for('admin_campaigns', cid=cid))


if __name__ == '__main__':
    app.run(debug=True)

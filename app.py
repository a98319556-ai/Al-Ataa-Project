import os
import uuid
import logging
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from mysql.connector import pooling, Error as MySQLError
from flask_sqlalchemy import SQLAlchemy

# ==========================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ataa_platform_super_secret_2024')
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ==========================================
# قاعدة البيانات - Pool
# ==========================================
try:
    db_pool = pooling.MySQLConnectionPool(
        pool_name="ataa_pool", pool_size=10,
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "ataa_platform"),
        charset="utf8mb4"
    )
    logger.info("✅ تم الاتصال بقاعدة البيانات")
except Exception as e:
    logger.critical(f"❌ فشل الاتصال: {e}")
    db_pool = None

def get_db():
    if db_pool is None:
        raise RuntimeError("قاعدة البيانات غير متاحة")
    return db_pool.get_connection()

# ==========================================
# Flask-Login + SQLAlchemy
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{os.environ.get('DB_USER','root')}:"
    f"{os.environ.get('DB_PASSWORD','')}@"
    f"{os.environ.get('DB_HOST','localhost')}/"
    f"{os.environ.get('DB_NAME','ataa_platform')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db_orm = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'unified_login'
login_manager.login_message = "يرجى تسجيل الدخول."
login_manager.login_message_category = "warning"

class User(UserMixin, db_orm.Model):
    __tablename__ = 'users'
    id = db_orm.Column(db_orm.Integer, primary_key=True)
    username = db_orm.Column(db_orm.String(50), unique=True, nullable=False)
    password_hash = db_orm.Column(db_orm.String(255), nullable=False)
    email = db_orm.Column(db_orm.String(100))
    full_name = db_orm.Column(db_orm.String(100))
    role = db_orm.Column(db_orm.String(10), default='donor')

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except:
        return None

# ==========================================
# فلاتر ومساعدات
# ==========================================
@app.template_filter('fmt_date')
def fmt_date(value):
    if not value: return '—'
    if isinstance(value, datetime):
        return value.strftime('%Y/%m/%d — %H:%M')
    try:
        return datetime.strptime(str(value)[:19], '%Y-%m-%d %H:%M:%S').strftime('%Y/%m/%d — %H:%M')
    except:
        return str(value)[:16]

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file_field):
    file = request.files.get(file_field)
    if file and file.filename and allowed_file(file.filename):
        safe = secure_filename(file.filename)
        base, ext = os.path.splitext(safe)
        filename = f"{base}_{int(time.time())}{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    return None

def admin_required_session(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin' not in session:
            flash("يجب تسجيل الدخول كمشرف", "warning")
            return redirect(url_for('unified_login'))
        return f(*args, **kwargs)
    return decorated

# ==========================================
# صفحة حملات المنصة العامة
# ==========================================
@app.route('/campaigns')
def platform_campaigns_public():
    status_filter = request.args.get('status', '').strip()
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        sql = "SELECT * FROM platform_campaigns"
        params = []
        if status_filter:
            sql += " WHERE status=%s"
            params.append(status_filter)
        else:
            sql += " WHERE status != 'paused'"
        sql += " ORDER BY created_at DESC"
        cur.execute(sql, tuple(params)); campaigns = cur.fetchall()

        cur.execute("SELECT COUNT(*) AS t FROM platform_campaigns"); total = cur.fetchone()['t']
        cur.execute("SELECT COUNT(*) AS t FROM platform_campaigns WHERE status='active'"); active = cur.fetchone()['t']
        cur.execute("SELECT COUNT(*) AS t FROM platform_campaigns WHERE status='completed'"); completed = cur.fetchone()['t']
        counts = {'total': total, 'active': active, 'completed': completed}
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e); campaigns, counts = [], {'total':0,'active':0,'completed':0}
    return render_template('platform_campaigns_public.html',
                           campaigns=campaigns, counts=counts, status_filter=status_filter)

# ==========================================
# الصفحة الرئيسية - تعرض الجمعيات والحملات
# ==========================================
@app.route('/')
def landing():
    charities, campaigns, stats = [], [], {'total_charities': 0, 'total_campaigns': 0, 'total_donors': 0}
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT c.*, COUNT(camp.id) AS camp_count
            FROM charities c LEFT JOIN campaigns camp ON c.id = camp.charity_id
            GROUP BY c.id ORDER BY c.id ASC LIMIT 9
        """)
        charities = cur.fetchall()
        cur.execute("""
            SELECT camp.*, ch.name AS charity_name, ch.image AS charity_image
            FROM campaigns camp JOIN charities ch ON camp.charity_id = ch.id
            ORDER BY camp.created_at DESC LIMIT 6
        """)
        campaigns = cur.fetchall()
        cur.execute("SELECT COUNT(*) AS t FROM charities"); stats['total_charities'] = cur.fetchone()['t']
        cur.execute("SELECT COUNT(*) AS t FROM campaigns"); stats['total_campaigns'] = cur.fetchone()['t']
        cur.execute("SELECT COUNT(*) AS t FROM users"); stats['total_donors'] = cur.fetchone()['t']
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ في الرئيسية: {e}")
    return render_template('landing.html', charities=charities, campaigns=campaigns, stats=stats)

# ==========================================
# لوجين موحد - يحدد تلقائياً أدمن أو متبرع
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def unified_login():
    if current_user.is_authenticated:
        return redirect(url_for('donor_home'))
    if 'admin' in session:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        remember = bool(request.form.get('remember'))

        if not username or not password:
            flash('يرجى إدخال اسم المستخدم وكلمة المرور', 'danger')
            return render_template('login.html')

        # تحقق من جدول الأدمن أولاً
        try:
            conn = get_db(); cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM admins WHERE username=%s", (username,))
            admin = cur.fetchone()
            cur.close(); conn.close()
            if admin and admin['password'] == password:
                session['admin'] = admin['username']
                session['admin_role'] = admin.get('role', 'admin')
                flash(f'مرحباً {admin["username"]}! 🛡️', 'success')
                if admin.get('role') == 'manager':
                    return redirect(url_for('manager_dashboard'))
                return redirect(url_for('admin_dashboard'))
        except Exception as e:
            logger.error(f"خطأ تحقق أدمن: {e}")

        # تحقق من جدول المتبرعين
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            flash(f'مرحباً {user.username}! أهلاً بك في منصة العطاء. 🤝', 'success')
            return redirect(request.args.get('next') or url_for('donor_home'))

        flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'danger')

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('donor_home'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm  = request.form.get('confirm_password', '').strip()
        if not username or not password:
            flash('يرجى تعبئة جميع الحقول.', 'danger')
        elif len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل.', 'danger')
        elif password != confirm:
            flash('كلمات المرور غير متطابقة.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('اسم المستخدم مستخدم بالفعل.', 'warning')
        else:
            db_orm.session.add(User(username=username, password_hash=generate_password_hash(password), role='donor'))
            db_orm.session.commit()
            flash('✅ تم إنشاء حسابك بنجاح! سجّل الدخول الآن.', 'success')
            return redirect(url_for('unified_login'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    if current_user.is_authenticated:
        logout_user()
    session.pop('admin', None)
    session.pop('admin_role', None)
    flash('تم تسجيل الخروج.', 'info')
    return redirect(url_for('landing'))

# ==========================================
# صفحات المتبرعين
# ==========================================
@app.route('/donor/home')
@login_required
def donor_home():
    donations = [
        {"id": "01", "campaign": "تجهيز وحدة غسيل كلوي (قصر العيني)", "amount": "5,000 ج.م", "status": "مكتمل", "status_class": "success"},
        {"id": "02", "campaign": "سداد ديون غارمات (بني سويف)", "amount": "3,500 ج.م", "status": "مكتمل", "status_class": "success"},
        {"id": "03", "campaign": "وصلات مياه للقرى (الفيوم)", "amount": "10,000 ج.م", "status": "قيد التنفيذ", "status_class": "warning"},
    ]
    return render_template('donor/home.html', username=current_user.username, donations=donations)

@app.route('/donor/donate', methods=['GET', 'POST'])
@login_required
def donor_donate():
    campaigns_db = []
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT camp.id, camp.title, camp.goal_amount, ch.name AS charity_name
            FROM campaigns camp JOIN charities ch ON camp.charity_id = ch.id
            ORDER BY ch.name, camp.title
        """)
        campaigns_db = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ جلب حملات: {e}")

    if request.method == 'POST':
        campaign = request.form.get('campaign', '')
        amount = request.form.get('amount', '')
        custom_amount = request.form.get('custom_amount', '').strip()
        final_amount = custom_amount if custom_amount else amount
        flash(f'شكراً! تم تسجيل مساهمتك بمبلغ {final_amount} ج.م لصالح "{campaign}". 🙏', 'success')
        return redirect(url_for('donor_home'))
    return render_template('donor/donate.html', username=current_user.username, campaigns_db=campaigns_db)

@app.route('/donor/my-donations')
@login_required
def donor_my_donations():
    user_donations = [
        {"date": "10 مايو 2024", "campaign": "تجهيز وحدة غسيل كلوي", "amount": "1,000 ج.م", "payment_method": "بطاقة بنكية", "status": "تم التوصيل", "status_color": "success", "receipt_id": "TRX-98765"},
        {"date": "25 أبريل 2024", "campaign": "سداد ديون غارمات", "amount": "500 ج.م", "payment_method": "فوري", "status": "تم التوصيل", "status_color": "success", "receipt_id": "TRX-43210"},
        {"date": "اليوم", "campaign": "وصلات مياه للقرى (الفيوم)", "amount": "2,500 ج.م", "payment_method": "إنستا باي", "status": "جاري التوجيه", "status_color": "warning", "receipt_id": "TRX-11223"},
    ]
    return render_template('donor/my_donations.html', username=current_user.username,
                           donations=user_donations, total_donated="4,000", total_campaigns=len(user_donations))

@app.route('/donor/reports')
@login_required
def donor_reports():
    today = datetime.now()
    reports = [
        {"date": today.strftime("%d-%m-%Y"), "title": "دراسة جدوى: وصلات مياه قرية كفر داود",
         "investigator": "المهندس طارق سعيد", "details": "تم معاينة القرية وتبين الحاجة لحفر بئر وتركيب مواسير.",
         "feasibility": {"materials": "85,000", "labor": "25,000", "shipping": "5,000", "admin": "0", "total": "115,000"},
         "status": "مقبولة وجاهزة للتنفيذ", "status_color": "success", "icon": "fa-file-invoice-dollar"},
        {"date": (today - timedelta(days=7)).strftime("%d-%m-%Y"), "title": "دراسة حالة: وحدة الغسيل الكلوي",
         "investigator": "لجنة التقييم الطبي", "details": "تم تقييم وشراء جهازين للغسيل الكلوي.",
         "feasibility": {"materials": "450,000", "labor": "15,000", "shipping": "8,000", "admin": "0", "total": "473,000"},
         "status": "تم الشراء والتوريد", "status_color": "success", "icon": "fa-truck-medical"},
    ]
    return render_template('donor/reports.html', username=current_user.username, reports=reports)

@app.route('/donor/donors')
@login_required
def donor_donors():
    donors_data = [
        {"name": "فاعل خير", "type": "تبرع فردي", "impact": "تكفل بسداد ديون 3 غارمات.", "badge": "متبرع ذهبي", "icon": "fa-user-shield", "color": "#f39c12"},
        {"name": "شركة التوحيد للتجارة", "type": "مسؤولية مجتمعية", "impact": "المساهمة في تجهيز وحدة الغسيل الكلوي.", "badge": "شريك استراتيجي", "icon": "fa-building", "color": "#2e8b81"},
        {"name": "مجموعة شباب الخير", "type": "مبادرة شبابية", "impact": "جمع تبرعات لتوصيل مياه لـ 15 منزل.", "badge": "مبادرة مجتمعية", "icon": "fa-users", "color": "#3498db"},
    ]
    return render_template('donor/donors.html', username=current_user.username, donors=donors_data)

@app.route('/donor/beneficiaries')
@login_required
def donor_beneficiaries():
    beneficiaries_data = [
        {"name": "تجهيز وحدة غسيل كلوي", "location": "مستشفى قصر العيني", "category": "رعاية طبية", "story": "توفير 3 أجهزة غسيل كلوي حديثة.", "icon": "fa-bed-pulse", "color": "#2e8b81"},
        {"name": "سداد ديون 5 غارمات", "location": "محافظة بني سويف", "category": "فك كرب", "story": "تم سداد الديون بالكامل.", "icon": "fa-scale-balanced", "color": "#f39c12"},
    ]
    return render_template('donor/beneficiaries.html', username=current_user.username, beneficiaries=beneficiaries_data)

@app.route('/donor/settings', methods=['GET', 'POST'])
@login_required
def donor_settings():
    if request.method == 'POST':
        new_pw = request.form.get('new_password', '').strip()
        confirm_pw = request.form.get('confirm_password', '').strip()
        if new_pw:
            if new_pw != confirm_pw:
                flash('كلمات المرور غير متطابقة.', 'danger')
            elif len(new_pw) < 6:
                flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل.', 'danger')
            else:
                current_user.password_hash = generate_password_hash(new_pw)
                db_orm.session.commit()
                flash('✅ تم تحديث كلمة المرور بنجاح!', 'success')
        else:
            flash('تم حفظ الإعدادات.', 'success')
        return redirect(url_for('donor_settings'))
    return render_template('donor/settings.html', username=current_user.username)

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_msg = request.json.get('message', '').lower()
    responses = {
        "مرحبا": f"أهلاً بك يا {current_user.username}! 🤝",
        "سلام": "وعليكم السلام! أنا هنا لمساعدتك.",
        "تبرع": "اضغط على 'تبرع جديد' في القائمة لاختيار الحملة وطريقة الدفع.",
        "طرق الدفع": "متاح: الفيزا، إنستاباي، فوري، ومحافظ إلكترونية.",
        "فلوسي": "فلوسك بتروح 100% للحالة اللي تختارها. مفيش مصاريف إدارية.",
        "جمعيات": "شريكين مع جمعيات موثقة مثل رسالة، مصر الخير، بنك الطعام وغيرها.",
        "شكرا": "العفو! ربنا يتقبل منك. 🙏",
    }
    bot_reply = "عفواً، هل تسأل عن التبرع أو طرق الدفع أو الجمعيات؟"
    for key, reply in responses.items():
        if key in user_msg:
            bot_reply = reply
            break
    return jsonify({"response": bot_reply})

# ==========================================
# لوحة الأدمن
# ==========================================
@app.route('/admin/login')
def admin_login():
    return redirect(url_for('unified_login'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None); session.pop('admin_role', None)
    flash('تم تسجيل الخروج', 'info')
    return redirect(url_for('landing'))

@app.route('/admin')
@admin_required_session
def admin_dashboard():
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS t FROM inventory WHERE status='available'"); total_inventory = cur.fetchone()['t']
        cur.execute("SELECT COUNT(*) AS t FROM users"); total_donors = cur.fetchone()['t']
        cur.execute("SELECT COUNT(*) AS t FROM donation_requests WHERE status='pending'"); pending_requests = cur.fetchone()['t']
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ dashboard: {e}")
        total_inventory = total_donors = pending_requests = 0
    return render_template('admin/dashboard.html',
                           total_inventory=total_inventory,
                           total_donors=total_donors,
                           pending_requests=pending_requests,
                           admin_name=session.get('admin', 'المشرف'))

# ==========================================
# المخازن
# ==========================================
@app.route('/admin/inventory')
@admin_required_session
def admin_inventory():
    category_filter = request.args.get("category", "").strip()
    search_query = request.args.get("q", "").strip()
    history_query = request.args.get("hq", "").strip()
    history_action_filter = request.args.get("ha", "").strip()
    try:
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        base = """SELECT i.id,i.item_name,i.description,i.quantity,i.status,i.image,i.unique_code,
                         c.name AS category, s.name AS subcategory
                  FROM inventory i
                  JOIN categories c ON i.category_id=c.id
                  LEFT JOIN subcategories s ON i.subcategory_id=s.id
                  WHERE i.status IN ('available','returned')"""
        conds, params = [], []
        if category_filter: conds.append("c.name=%s"); params.append(category_filter)
        if search_query:
            conds.append("(i.item_name LIKE %s OR i.description LIKE %s OR c.name LIKE %s OR i.unique_code LIKE %s)")
            q = f"%{search_query}%"; params.extend([q,q,q,q])
        if conds: base += " AND " + " AND ".join(conds)
        cursor.execute(base, tuple(params)); items = cursor.fetchall()

        cursor.execute("""SELECT c.name, COUNT(i.id) AS count FROM categories c
                          LEFT JOIN inventory i ON i.category_id=c.id AND i.status='available'
                          GROUP BY c.name""")
        counts = {r["name"]: r["count"] for r in cursor.fetchall()}

        hbase = """SELECT h.id,h.item_id,h.action,h.timestamp,i.item_name,i.unique_code,c.name AS category
                   FROM history h JOIN inventory i ON h.item_id=i.id
                   JOIN categories c ON i.category_id=c.id WHERE 1=1"""
        hp = []
        if history_query:
            hbase += " AND (i.item_name LIKE %s OR i.unique_code LIKE %s)"
            hp.extend([f"%{history_query}%", f"%{history_query}%"])
        if history_action_filter: hbase += " AND h.action=%s"; hp.append(history_action_filter)
        hbase += " ORDER BY h.timestamp DESC LIMIT 100"
        cursor.execute(hbase, tuple(hp)); history = cursor.fetchall()
        cursor.close(); conn.close()
        return render_template('admin/inventory.html', items=items, counts=counts, history=history,
                               history_query=history_query, history_action_filter=history_action_filter)
    except Exception as e:
        logger.error(f"خطأ inventory: {e}"); flash("خطأ في تحميل المخزون", "danger")
        return render_template('admin/inventory.html', items=[], counts={}, history=[], history_query="", history_action_filter="")

@app.route('/admin/add_item', methods=['GET', 'POST'])
@admin_required_session
def admin_add_item():
    try:
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        if request.method == 'POST':
            item_name = request.form.get('item_name','').strip()
            description = request.form.get('description','').strip()
            category_id = request.form.get('category_id')
            subcategory_id = request.form.get('subcategory_id') or None
            try: quantity = int(request.form.get('quantity','1') or 1)
            except: quantity = 1
            if not item_name or not category_id:
                flash('اسم الصنف والفئة مطلوبان', 'danger')
            else:
                img_file = request.files.get('image')
                img_name = None
                if img_file and img_file.filename and allowed_file(img_file.filename):
                    safe = secure_filename(img_file.filename)
                    b, e = os.path.splitext(safe)
                    img_name = f"{b}_{uuid.uuid4().hex[:8]}{e}"
                    img_file.save(os.path.join(app.config['UPLOAD_FOLDER'], img_name))
                uc = str(uuid.uuid4())
                cursor.execute("INSERT INTO inventory (item_name,description,category_id,subcategory_id,quantity,image,unique_code) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                               (item_name,description,category_id,subcategory_id,quantity,img_name,uc))
                nid = cursor.lastrowid
                cursor.execute("INSERT INTO history (item_id,unique_code,action) VALUES (%s,%s,'add')", (nid,uc))
                conn.commit(); cursor.close(); conn.close()
                flash(f"✅ تم إضافة '{item_name}' للمخزن", 'success')
                return redirect(url_for('admin_inventory'))
        cursor.execute("SELECT * FROM categories ORDER BY name"); cats = cursor.fetchall()
        cursor.execute("SELECT * FROM subcategories ORDER BY category_id,name"); subs = cursor.fetchall()
        cursor.close(); conn.close()
        return render_template('admin/add_item.html', categories=cats, subcategories=subs)
    except Exception as e:
        logger.error(f"خطأ add_item: {e}"); flash(f"خطأ: {e}", 'danger')
        return redirect(url_for('admin_inventory'))

@app.route('/admin/deliver/<int:item_id>', methods=['POST'])
@admin_required_session
def admin_deliver(item_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT unique_code,status,item_name FROM inventory WHERE id=%s", (item_id,))
        item = cur.fetchone()
        if item and item['status'] in ('available','returned'):
            cur.execute("UPDATE inventory SET status='delivered' WHERE id=%s", (item_id,))
            cur.execute("INSERT INTO history (item_id,unique_code,action) VALUES (%s,%s,'deliver')", (item_id,item['unique_code']))
            conn.commit(); flash(f"✅ تم تسليم '{item['item_name']}'", 'success')
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e); flash("خطأ", 'danger')
    return redirect(url_for('admin_inventory') + '#history')

@app.route('/admin/delete_item/<int:item_id>', methods=['POST'])
@admin_required_session
def admin_delete_item(item_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT unique_code,item_name FROM inventory WHERE id=%s", (item_id,))
        item = cur.fetchone()
        if item:
            cur.execute("UPDATE inventory SET status='deleted' WHERE id=%s", (item_id,))
            cur.execute("INSERT INTO history (item_id,unique_code,action) VALUES (%s,%s,'delete')", (item_id,item['unique_code']))
            conn.commit(); flash(f"🗑️ تم حذف '{item['item_name']}'", 'success')
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e); flash("خطأ", 'danger')
    return redirect(url_for('admin_inventory') + '#history')

@app.route('/admin/undo/<int:history_id>', methods=['POST'])
@admin_required_session
def admin_undo(history_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM history WHERE id=%s", (history_id,))
        rec = cur.fetchone()
        if rec:
            cur.execute("UPDATE inventory SET status='returned' WHERE unique_code=%s", (rec['unique_code'],))
            cur.execute("DELETE FROM history WHERE id=%s", (history_id,))
            cur.execute("INSERT INTO history (item_id,unique_code,action) VALUES (%s,%s,'returned')", (rec['item_id'],rec['unique_code']))
            conn.commit(); flash("✅ تم استرجاع المنتج", 'success')
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e); flash("خطأ", 'danger')
    return redirect(url_for('admin_inventory'))

# ==========================================
# الجمعيات والحملات
# ==========================================
@app.route('/admin/charities')
@admin_required_session
def admin_charities():
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT c.*, COUNT(camp.id) AS campaign_count
                       FROM charities c LEFT JOIN campaigns camp ON c.id=camp.charity_id
                       GROUP BY c.id ORDER BY c.id ASC""")
        charities = cur.fetchall(); cur.close(); conn.close()
    except Exception as e:
        logger.error(e); charities = []
    return render_template('admin/charities.html', charities=charities)

@app.route('/admin/charity/add', methods=['GET', 'POST'])
@admin_required_session
def admin_add_charity():
    if request.method == 'POST':
        name        = request.form.get('name','').strip()
        description = request.form.get('description','').strip()
        fields      = request.form.get('fields','').strip()
        stat1_num   = request.form.get('stat1_num','').strip()
        stat1_label = request.form.get('stat1_label','').strip()
        stat2_num   = request.form.get('stat2_num','').strip()
        stat2_label = request.form.get('stat2_label','').strip()
        stat3_num   = request.form.get('stat3_num','').strip()
        stat3_label = request.form.get('stat3_label','').strip()
        if not name or not description:
            flash('اسم الجمعية والوصف مطلوبان.', 'danger')
            return render_template('admin/add_charity.html')
        img = save_image('image'); image_name = img or 'default.jpg'
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("""INSERT INTO charities (name,description,image,fields,stat1_num,stat1_label,stat2_num,stat2_label,stat3_num,stat3_label)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (name,description,image_name,fields,stat1_num,stat1_label,stat2_num,stat2_label,stat3_num,stat3_label))
            conn.commit(); cur.close(); conn.close()
            flash(f'✅ تم إضافة جمعية "{name}" بنجاح!', 'success')
            return redirect(url_for('admin_charities'))
        except Exception as e:
            logger.error(e); flash(f'خطأ: {e}', 'danger')
    return render_template('admin/add_charity.html')

@app.route('/admin/charity/edit/<int:cid>', methods=['GET', 'POST'])
@admin_required_session
def admin_edit_charity(cid):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM charities WHERE id=%s", (cid,))
        charity = cur.fetchone()
        if not charity:
            cur.close(); conn.close()
            flash('الجمعية غير موجودة', 'danger')
            return redirect(url_for('admin_charities'))
        if request.method == 'POST':
            name        = request.form.get('name','').strip()
            description = request.form.get('description','').strip()
            fields      = request.form.get('fields','').strip()
            stat1_num   = request.form.get('stat1_num','').strip()
            stat1_label = request.form.get('stat1_label','').strip()
            stat2_num   = request.form.get('stat2_num','').strip()
            stat2_label = request.form.get('stat2_label','').strip()
            stat3_num   = request.form.get('stat3_num','').strip()
            stat3_label = request.form.get('stat3_label','').strip()
            img = save_image('image'); image_name = img or charity['image']
            cur2 = conn.cursor()
            cur2.execute("""UPDATE charities SET name=%s,description=%s,image=%s,fields=%s,
                stat1_num=%s,stat1_label=%s,stat2_num=%s,stat2_label=%s,stat3_num=%s,stat3_label=%s WHERE id=%s""",
                (name,description,image_name,fields,stat1_num,stat1_label,stat2_num,stat2_label,stat3_num,stat3_label,cid))
            conn.commit(); cur2.close(); cur.close(); conn.close()
            flash('✅ تم تعديل الجمعية بنجاح!', 'success')
            return redirect(url_for('admin_charities'))
        cur.close(); conn.close()
        return render_template('admin/edit_charity.html', charity=charity)
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('admin_charities'))

@app.route('/admin/charity/delete/<int:cid>', methods=['POST'])
@admin_required_session
def admin_delete_charity(cid):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT name FROM charities WHERE id=%s", (cid,))
        row = cur.fetchone()
        cur2 = conn.cursor()
        cur2.execute("DELETE FROM charities WHERE id=%s", (cid,))
        conn.commit(); cur2.close(); cur.close(); conn.close()
        flash(f'✅ تم حذف جمعية "{row["name"] if row else cid}"', 'success')
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
    return redirect(url_for('admin_charities'))

@app.route('/admin/campaigns/<int:cid>')
@admin_required_session
def admin_campaigns(cid):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM charities WHERE id=%s", (cid,)); charity = cur.fetchone()
        cur.execute("SELECT * FROM campaigns WHERE charity_id=%s ORDER BY created_at DESC", (cid,)); campaigns = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e); charity, campaigns = None, []
    return render_template('admin/campaigns.html', charity=charity, campaigns=campaigns)

@app.route('/admin/campaign/add/<int:cid>', methods=['GET', 'POST'])
@admin_required_session
def admin_add_campaign(cid):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM charities WHERE id=%s", (cid,)); charity = cur.fetchone()
        if not charity:
            cur.close(); conn.close()
            flash('الجمعية غير موجودة', 'danger')
            return redirect(url_for('admin_charities'))
        if request.method == 'POST':
            title       = request.form.get('title','').strip()
            description = request.form.get('description','').strip()
            goal_amount = request.form.get('goal_amount','0').strip() or '0'
            category    = request.form.get('category','عام').strip()
            if not title or not description:
                flash('عنوان الحملة والوصف مطلوبان.', 'danger')
            else:
                img = save_image('image'); image_name = img or 'default.jpg'
                try: goal = float(goal_amount)
                except: goal = 0.0
                cur2 = conn.cursor()
                cur2.execute("INSERT INTO campaigns (charity_id,title,description,goal_amount,image,category) VALUES (%s,%s,%s,%s,%s,%s)",
                             (cid,title,description,goal,image_name,category))
                conn.commit(); cur2.close(); cur.close(); conn.close()
                flash(f'✅ تم إضافة حملة "{title}" بنجاح!', 'success')
                return redirect(url_for('admin_campaigns', cid=cid))
        cur.close(); conn.close()
        return render_template('admin/add_campaign.html', charity=charity)
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('admin_charities'))

@app.route('/admin/campaign/edit/<int:camp_id>', methods=['GET', 'POST'])
@admin_required_session
def admin_edit_campaign(camp_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM campaigns WHERE id=%s", (camp_id,)); campaign = cur.fetchone()
        if not campaign:
            cur.close(); conn.close()
            return redirect(url_for('admin_charities'))
        cur.execute("SELECT * FROM charities WHERE id=%s", (campaign['charity_id'],)); charity = cur.fetchone()
        if request.method == 'POST':
            title       = request.form.get('title','').strip()
            description = request.form.get('description','').strip()
            goal_amount = request.form.get('goal_amount','0').strip() or '0'
            category    = request.form.get('category','عام').strip()
            img = save_image('image'); image_name = img or campaign['image']
            try: goal = float(goal_amount)
            except: goal = 0.0
            cur2 = conn.cursor()
            cur2.execute("UPDATE campaigns SET title=%s,description=%s,goal_amount=%s,image=%s,category=%s WHERE id=%s",
                         (title,description,goal,image_name,category,camp_id))
            conn.commit(); cur2.close(); cur.close(); conn.close()
            flash('✅ تم تعديل الحملة بنجاح!', 'success')
            return redirect(url_for('admin_campaigns', cid=campaign['charity_id']))
        cur.close(); conn.close()
        return render_template('admin/edit_campaign.html', campaign=campaign, charity=charity)
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('admin_charities'))

@app.route('/admin/campaign/delete/<int:camp_id>', methods=['POST'])
@admin_required_session
def admin_delete_campaign(camp_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT charity_id,title FROM campaigns WHERE id=%s", (camp_id,)); row = cur.fetchone()
        cid = row['charity_id'] if row else 1
        cur2 = conn.cursor()
        cur2.execute("DELETE FROM campaigns WHERE id=%s", (camp_id,))
        conn.commit(); cur2.close(); cur.close(); conn.close()
        flash(f'✅ تم حذف الحملة "{row["title"] if row else ""}"', 'success')
        return redirect(url_for('admin_campaigns', cid=cid))
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('admin_charities'))

def manager_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin' not in session:
            flash("يجب تسجيل الدخول", "warning")
            return redirect(url_for('unified_login'))
        if session.get('admin_role') != 'manager':
            flash("هذه الصفحة خاصة بالمدير فقط", "danger")
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated

@app.route('/manager')
@manager_required
def manager_dashboard():
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS t FROM charities"); total_charities = cur.fetchone()['t']
        cur.execute("SELECT COUNT(*) AS t FROM platform_campaigns"); total_platform_campaigns = cur.fetchone()['t']
        cur.execute("SELECT COUNT(*) AS t FROM platform_campaigns WHERE status='active'"); active_campaigns = cur.fetchone()['t']
        cur.close(); conn.close()
    except:
        total_charities = total_platform_campaigns = active_campaigns = 0
    return render_template('admin/manager_dashboard.html',
                           total_charities=total_charities,
                           total_platform_campaigns=total_platform_campaigns,
                           active_campaigns=active_campaigns)

@app.route('/manager/inventory')
@manager_required
def manager_inventory():
    category_filter = request.args.get("category", "").strip()
    search_query = request.args.get("q", "").strip()
    try:
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        base = """SELECT i.id,i.item_name,i.description,i.quantity,i.status,i.image,i.unique_code,
                         c.name AS category, s.name AS subcategory
                  FROM inventory i
                  JOIN categories c ON i.category_id=c.id
                  LEFT JOIN subcategories s ON i.subcategory_id=s.id
                  WHERE i.status IN ('available','returned')"""
        conds, params = [], []
        if category_filter: conds.append("c.name=%s"); params.append(category_filter)
        if search_query:
            conds.append("(i.item_name LIKE %s OR i.description LIKE %s OR c.name LIKE %s OR i.unique_code LIKE %s)")
            q = f"%{search_query}%"; params.extend([q,q,q,q])
        if conds: base += " AND " + " AND ".join(conds)
        cursor.execute(base, tuple(params)); items = cursor.fetchall()
        cursor.execute("""SELECT c.name, COUNT(i.id) AS count FROM categories c
                          LEFT JOIN inventory i ON i.category_id=c.id AND i.status='available'
                          GROUP BY c.name""")
        counts = {r["name"]: r["count"] for r in cursor.fetchall()}
        cursor.execute("""SELECT h.id,h.item_id,h.action,h.timestamp,i.item_name,i.unique_code,c.name AS category
                          FROM history h JOIN inventory i ON h.item_id=i.id
                          JOIN categories c ON i.category_id=c.id
                          ORDER BY h.timestamp DESC LIMIT 100""")
        history = cursor.fetchall()
        cursor.close(); conn.close()
        return render_template('admin/manager_inventory.html', items=items, counts=counts, history=history)
    except Exception as e:
        logger.error(f"خطأ manager_inventory: {e}")
        return render_template('admin/manager_inventory.html', items=[], counts={}, history=[])

# ==========================================
# صفحات المستفيد
# ==========================================
@app.route('/beneficiary')
def beneficiary_landing():
    return render_template('beneficiary_landing.html')

@app.route('/beneficiary/register', methods=['GET', 'POST'])
def beneficiary_register():
    if request.method == 'POST':
        applicant_name = request.form.get('applicant_name', '').strip()
        phone          = request.form.get('phone', '').strip()
        address        = request.form.get('address', '').strip()
        request_type   = request.form.get('request_type', '').strip()
        item_requested = request.form.get('item_requested', '').strip()
        description    = request.form.get('description', '').strip()
        family_members = request.form.get('family_members', '').strip() or None

        if not all([applicant_name, phone, address, request_type, item_requested, description]):
            flash('يرجى تعبئة جميع الحقول المطلوبة', 'danger')
            return render_template('beneficiary_register.html')
        try:
            conn = get_db(); cur = conn.cursor(dictionary=True)
            # منع التكرار: تحقق من وجود طلب نشط بنفس الهاتف ونفس الصنف
            cur.execute("""
                SELECT id, status FROM donation_requests
                WHERE phone=%s AND item_requested=%s
                AND status NOT IN ('final_rejected')
                ORDER BY created_at DESC LIMIT 1
            """, (phone, item_requested))
            existing = cur.fetchone()
            if existing:
                cur.close(); conn.close()
                status_labels = {
                    'pending': 'قيد المراجعة',
                    'approved': 'تمت الموافقة عليه',
                    'rejected': 'مرفوض مؤقتاً وينتظر تعديل',
                    'on_the_way': 'في الطريق إليك'
                }
                status_ar = status_labels.get(existing['status'], existing['status'])
                flash(f'⚠️ لديك طلب سابق لنفس الصنف (طلب #{existing["id"]}) وحالته: {status_ar}. لا يمكن تقديم طلب مكرر.', 'warning')
                return redirect(url_for('beneficiary_track', phone=phone))
            cur2 = conn.cursor()
            cur2.execute("""INSERT INTO donation_requests
                           (applicant_name,phone,address,request_type,item_requested,description,family_members)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (applicant_name, phone, address, request_type, item_requested, description,
                         int(family_members) if family_members else None))
            req_id = cur2.lastrowid
            cur = cur2
            # Save uploaded docs
            docs = request.files.getlist('documents')
            for doc in docs:
                if doc and doc.filename and allowed_file(doc.filename):
                    safe = secure_filename(doc.filename)
                    b, e2 = os.path.splitext(safe)
                    fname = f"{b}_{int(time.time())}{e2}"
                    doc.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                    cur.execute("INSERT INTO donation_request_docs (request_id,name,filename) VALUES (%s,%s,%s)",
                                (req_id, safe, fname))
            conn.commit(); cur.close(); conn.close()
            flash(f'✅ تم إرسال طلبك بنجاح! يمكنك متابعة الطلب برقم هاتفك.', 'success')
            return redirect(url_for('beneficiary_track', phone=phone))
        except Exception as e:
            logger.error(f"خطأ beneficiary_register: {e}")
            flash('حدث خطأ أثناء إرسال الطلب، حاول مرة أخرى', 'danger')
    return render_template('beneficiary_register.html')

@app.route('/beneficiary/track')
def beneficiary_track():
    phone = request.args.get('phone', '').strip()
    reqs = None
    if phone:
        try:
            conn = get_db(); cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM donation_requests WHERE phone=%s ORDER BY created_at DESC", (phone,))
            reqs = cur.fetchall()
            for r in reqs:
                cur.execute("SELECT * FROM donation_request_docs WHERE request_id=%s", (r['id'],))
                r['documents'] = cur.fetchall()
            cur.close(); conn.close()
        except Exception as e:
            logger.error(f"خطأ track: {e}")
            reqs = []
    return render_template('beneficiary_track.html', requests=reqs, search_phone=phone)

# ==========================================
# طلبات التبرع العينية
# ==========================================
REQUEST_TYPE_ICONS = {
    'ثلاجة':         ('❄️', '#3498db'),
    'أجهزة كهربائية': ('🔌', '#9b59b6'),
    'تجهيز عروسة':   ('💍', '#e91e8c'),
    'أثاث':          ('🛋️', '#e07b2a'),
    'ملابس':         ('👗', '#2ecc71'),
    'غسالة':         ('🫧', '#1abc9c'),
}

def get_req_type_meta(request_type):
    for key, (icon, color) in REQUEST_TYPE_ICONS.items():
        if key in request_type:
            return icon, color
    return '📦', '#888888'

@app.route('/admin/donation-requests')
@admin_required_session
def admin_donation_requests():
    status_filter = request.args.get('status', '').strip()
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        # Counts
        cur.execute("SELECT status, COUNT(*) AS c FROM donation_requests GROUP BY status")
        raw_counts = {r['status']: r['c'] for r in cur.fetchall()}
        counts = {
            'total': sum(raw_counts.values()),
            'pending': raw_counts.get('pending', 0),
            'approved': raw_counts.get('approved', 0),
            'rejected': raw_counts.get('rejected', 0),
            'final_rejected': raw_counts.get('final_rejected', 0),
            'on_the_way': raw_counts.get('on_the_way', 0),
        }
        # Requests
        sql = "SELECT * FROM donation_requests"
        params = []
        if status_filter:
            sql += " WHERE status=%s"
            params.append(status_filter)
        sql += " ORDER BY created_at DESC"
        cur.execute(sql, tuple(params))
        reqs = cur.fetchall()
        # Attach docs + icons
        for r in reqs:
            cur.execute("SELECT * FROM donation_request_docs WHERE request_id=%s", (r['id'],))
            r['documents'] = cur.fetchall()
            r['type_icon'], r['type_color'] = get_req_type_meta(r['request_type'] + ' ' + r['item_requested'])
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ donation_requests: {e}")
        reqs, counts = [], {'total':0,'pending':0,'approved':0,'rejected':0,'final_rejected':0,'on_the_way':0}
    return render_template('admin/donation_requests.html', requests=reqs,
                           counts=counts, status_filter=status_filter)

@app.route('/admin/donation-request/<int:req_id>/update', methods=['POST'])
@admin_required_session
def admin_update_donation_request(req_id):
    action = request.form.get('action', '')
    admin_note = request.form.get('admin_note', '').strip()
    status_map = {
        'approve': 'approved',
        'reject_note': 'rejected',
        'final_reject': 'final_rejected',
        'on_the_way': 'on_the_way',
    }
    new_status = status_map.get(action)
    if not new_status:
        flash('إجراء غير صحيح', 'danger')
        return redirect(url_for('admin_donation_requests'))
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE donation_requests SET status=%s, admin_note=%s WHERE id=%s",
                    (new_status, admin_note if admin_note else None, req_id))
        conn.commit(); cur.close(); conn.close()
        msgs = {
            'approved': '✅ تمت الموافقة على الطلب',
            'rejected': '🔄 تم رفض الطلب مع إرسال ملاحظة للمتقدم',
            'final_rejected': '❌ تم الرفض النهائي للطلب',
            'on_the_way': '🚚 تم تحديث حالة الطلب إلى "في الطريق"',
        }
        flash(msgs.get(new_status, 'تم التحديث'), 'success')
    except Exception as e:
        logger.error(f"خطأ update request: {e}")
        flash('حدث خطأ أثناء التحديث', 'danger')
    return redirect(url_for('admin_donation_requests'))

# ==========================================
# حذف طلب التبرع (admin only)
# ==========================================
@app.route('/admin/donation-request/<int:req_id>/delete', methods=['POST'])
@admin_required_session
def admin_delete_donation_request(req_id):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM donation_request_docs WHERE request_id=%s", (req_id,))
        cur.execute("DELETE FROM donation_requests WHERE id=%s", (req_id,))
        conn.commit(); cur.close(); conn.close()
        flash("🗑️ تم حذف الطلب بنجاح", "success")
    except Exception as e:
        logger.error(f"خطأ delete request: {e}")
        flash("حدث خطأ أثناء الحذف", "danger")
    return redirect(url_for('admin_donation_requests'))

# ==========================================
# صفحات المدير — حملات + طلبات التبرع
# ==========================================
@app.route('/manager/campaigns')
@manager_required
def manager_campaigns():
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT c.*, COUNT(camp.id) AS campaign_count
                       FROM charities c LEFT JOIN campaigns camp ON c.id=camp.charity_id
                       GROUP BY c.id ORDER BY c.id ASC""")
        charities = cur.fetchall()
        for ch in charities:
            cur.execute("SELECT * FROM campaigns WHERE charity_id=%s ORDER BY created_at DESC", (ch['id'],))
            ch['campaigns'] = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e); charities = []
    return render_template('admin/manager_campaigns.html', charities=charities)

@app.route('/manager/campaign/add', methods=['GET', 'POST'])
@manager_required
def manager_add_campaign():
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM charities ORDER BY name"); charities = cur.fetchall()
        if request.method == 'POST':
            charity_id  = request.form.get('charity_id')
            title       = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            goal_amount = request.form.get('goal_amount', '0').strip() or '0'
            category    = request.form.get('category', 'عام').strip()
            if not title or not description or not charity_id:
                flash('يرجى تعبئة الحقول المطلوبة', 'danger')
            else:
                img = save_image('image'); image_name = img or 'default.jpg'
                try: goal = float(goal_amount)
                except: goal = 0.0
                cur2 = conn.cursor()
                cur2.execute("INSERT INTO campaigns (charity_id,title,description,goal_amount,image,category) VALUES (%s,%s,%s,%s,%s,%s)",
                             (charity_id, title, description, goal, image_name, category))
                conn.commit(); cur2.close()
                flash(f'✅ تم إضافة حملة "{title}" بنجاح!', 'success')
                cur.close(); conn.close()
                return redirect(url_for('manager_campaigns'))
        cur.close(); conn.close()
        return render_template('admin/manager_add_campaign.html', charities=charities)
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('manager_campaigns'))

@app.route('/manager/campaign/edit/<int:camp_id>', methods=['GET', 'POST'])
@manager_required
def manager_edit_campaign(camp_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM campaigns WHERE id=%s", (camp_id,)); campaign = cur.fetchone()
        cur.execute("SELECT * FROM charities ORDER BY name"); charities = cur.fetchall()
        if not campaign:
            cur.close(); conn.close()
            return redirect(url_for('manager_campaigns'))
        if request.method == 'POST':
            charity_id  = request.form.get('charity_id')
            title       = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            goal_amount = request.form.get('goal_amount', '0').strip() or '0'
            category    = request.form.get('category', 'عام').strip()
            img = save_image('image'); image_name = img or campaign['image']
            try: goal = float(goal_amount)
            except: goal = 0.0
            cur2 = conn.cursor()
            cur2.execute("UPDATE campaigns SET charity_id=%s,title=%s,description=%s,goal_amount=%s,image=%s,category=%s WHERE id=%s",
                         (charity_id, title, description, goal, image_name, category, camp_id))
            conn.commit(); cur2.close(); cur.close(); conn.close()
            flash('✅ تم تعديل الحملة بنجاح!', 'success')
            return redirect(url_for('manager_campaigns'))
        cur.close(); conn.close()
        return render_template('admin/manager_edit_campaign.html', campaign=campaign, charities=charities)
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('manager_campaigns'))

@app.route('/manager/campaign/delete/<int:camp_id>', methods=['POST'])
@manager_required
def manager_delete_campaign(camp_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT title FROM campaigns WHERE id=%s", (camp_id,)); row = cur.fetchone()
        cur2 = conn.cursor()
        cur2.execute("DELETE FROM campaigns WHERE id=%s", (camp_id,))
        conn.commit(); cur2.close(); cur.close(); conn.close()
        flash(f'✅ تم حذف الحملة "{row["title"] if row else ""}"', 'success')
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
    return redirect(url_for('manager_campaigns'))

@app.route('/manager/donation-requests')
@manager_required
def manager_donation_requests():
    status_filter = request.args.get('status', '').strip()
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT status, COUNT(*) AS c FROM donation_requests GROUP BY status")
        raw_counts = {r['status']: r['c'] for r in cur.fetchall()}
        counts = {
            'total': sum(raw_counts.values()),
            'pending': raw_counts.get('pending', 0),
            'approved': raw_counts.get('approved', 0),
            'rejected': raw_counts.get('rejected', 0),
            'final_rejected': raw_counts.get('final_rejected', 0),
            'on_the_way': raw_counts.get('on_the_way', 0),
        }
        sql = "SELECT * FROM donation_requests"
        params = []
        if status_filter:
            sql += " WHERE status=%s"; params.append(status_filter)
        sql += " ORDER BY created_at DESC"
        cur.execute(sql, tuple(params)); reqs = cur.fetchall()
        for r in reqs:
            cur.execute("SELECT * FROM donation_request_docs WHERE request_id=%s", (r['id'],))
            r['documents'] = cur.fetchall()
            r['type_icon'], r['type_color'] = get_req_type_meta(r['request_type'] + ' ' + r['item_requested'])
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e); reqs, counts = [], {'total':0,'pending':0,'approved':0,'rejected':0,'final_rejected':0,'on_the_way':0}
    return render_template('admin/manager_donation_requests.html', requests=reqs, counts=counts, status_filter=status_filter)

@app.route('/manager/donation-request/<int:req_id>/update', methods=['POST'])
@manager_required
def manager_update_donation_request(req_id):
    action = request.form.get('action', '')
    admin_note = request.form.get('admin_note', '').strip()
    status_map = {'approve': 'approved', 'reject_note': 'rejected', 'final_reject': 'final_rejected', 'on_the_way': 'on_the_way'}
    new_status = status_map.get(action)
    if not new_status:
        flash('إجراء غير صحيح', 'danger')
        return redirect(url_for('manager_donation_requests'))
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE donation_requests SET status=%s, admin_note=%s WHERE id=%s",
                    (new_status, admin_note if admin_note else None, req_id))
        conn.commit(); cur.close(); conn.close()
        msgs = {'approved': '✅ تمت الموافقة', 'rejected': '🔄 تم إرسال ملاحظة للمتقدم',
                'final_rejected': '❌ تم الرفض النهائي', 'on_the_way': '🚚 تم تحديث الحالة إلى في الطريق'}
        flash(msgs.get(new_status, 'تم التحديث'), 'success')
    except Exception as e:
        logger.error(e); flash('حدث خطأ', 'danger')
    return redirect(url_for('manager_donation_requests'))


# ==========================================
# حملات منصة العطاء (منفصلة عن حملات الجمعيات)
# ==========================================
@app.route('/manager/platform-campaigns')
@manager_required
def manager_platform_campaigns():
    """حملات المنصة الخاصة - منفصلة عن حملات الجمعيات"""
    status_filter = request.args.get('status', '').strip()
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        if status_filter:
            cur.execute("SELECT * FROM platform_campaigns WHERE status=%s ORDER BY created_at DESC", (status_filter,))
        else:
            cur.execute("SELECT * FROM platform_campaigns ORDER BY created_at DESC")
        campaigns = cur.fetchall()
        cur.execute("SELECT status, COUNT(*) AS c FROM platform_campaigns GROUP BY status")
        counts = {r['status']: r['c'] for r in cur.fetchall()}
        counts['total'] = sum(counts.values())
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e); campaigns, counts = [], {'total':0}
    return render_template('admin/manager_platform_campaigns.html',
                           campaigns=campaigns, counts=counts, status_filter=status_filter)


@app.route('/manager/platform-campaign/add', methods=['GET', 'POST'])
@manager_required
def manager_add_platform_campaign():
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        goal_amount = request.form.get('goal_amount', '0').strip() or '0'
        category    = request.form.get('category', 'عام').strip()
        if not title or not description:
            flash('العنوان والوصف مطلوبان.', 'danger')
            return render_template('admin/manager_add_platform_campaign.html')
        img = save_image('image'); image_name = img or 'default.jpg'
        try: goal = float(goal_amount)
        except: goal = 0.0
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("""INSERT INTO platform_campaigns (title,description,goal_amount,image,category,created_by)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (title, description, goal, image_name, category, session.get('admin','')))
            conn.commit(); cur.close(); conn.close()
            flash(f'✅ تم إضافة حملة "{title}" بنجاح!', 'success')
            return redirect(url_for('manager_platform_campaigns'))
        except Exception as e:
            logger.error(e); flash(f'خطأ: {e}', 'danger')
    return render_template('admin/manager_add_platform_campaign.html')


@app.route('/manager/platform-campaign/edit/<int:camp_id>', methods=['GET', 'POST'])
@manager_required
def manager_edit_platform_campaign(camp_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute('SELECT * FROM platform_campaigns WHERE id=%s', (camp_id,))
        campaign = cur.fetchone()
        if not campaign:
            cur.close(); conn.close()
            flash('الحملة غير موجودة', 'danger')
            return redirect(url_for('manager_platform_campaigns'))
        if request.method == 'POST':
            title            = request.form.get('title','').strip()
            description      = request.form.get('description','').strip()
            goal_amount      = request.form.get('goal_amount','0').strip() or '0'
            collected_amount = request.form.get('collected_amount','0').strip() or '0'
            category         = request.form.get('category','عام').strip()
            status           = request.form.get('status','active').strip()
            img = save_image('image'); image_name = img or campaign['image']
            try: goal = float(goal_amount)
            except: goal = 0.0
            try: collected = float(collected_amount)
            except: collected = 0.0
            cur2 = conn.cursor()
            cur2.execute('UPDATE platform_campaigns SET title=%s,description=%s,goal_amount=%s,collected_amount=%s,image=%s,category=%s,status=%s WHERE id=%s',
                (title,description,goal,collected,image_name,category,status,camp_id))
            conn.commit(); cur2.close(); cur.close(); conn.close()
            flash('✅ تم تعديل الحملة بنجاح!', 'success')
            return redirect(url_for('manager_platform_campaigns'))
        cur.close(); conn.close()
        return render_template('admin/manager_edit_platform_campaign.html', campaign=campaign)
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('manager_platform_campaigns'))

@app.route('/manager/platform-campaign/delete/<int:camp_id>', methods=['POST'])
@manager_required
def manager_delete_platform_campaign(camp_id):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM platform_campaigns WHERE id=%s", (camp_id,))
        conn.commit(); cur.close(); conn.close()
        flash('✅ تم حذف الحملة.', 'success')
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
    return redirect(url_for('manager_platform_campaigns'))

# ==========================================
# صلاحيات المدير — الجمعيات الشريكة
# ==========================================
@app.route('/manager/charities')
@manager_required
def manager_charities():
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT c.*, COUNT(camp.id) AS campaign_count
                       FROM charities c LEFT JOIN campaigns camp ON c.id=camp.charity_id
                       GROUP BY c.id ORDER BY c.id ASC""")
        charities = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e); charities = []
    return render_template('admin/manager_charities.html', charities=charities)

@app.route('/manager/charity/add', methods=['GET', 'POST'])
@manager_required
def manager_add_charity():
    if request.method == 'POST':
        name        = request.form.get('name','').strip()
        description = request.form.get('description','').strip()
        fields      = request.form.get('fields','').strip()
        stat1_num   = request.form.get('stat1_num','').strip()
        stat1_label = request.form.get('stat1_label','').strip()
        stat2_num   = request.form.get('stat2_num','').strip()
        stat2_label = request.form.get('stat2_label','').strip()
        stat3_num   = request.form.get('stat3_num','').strip()
        stat3_label = request.form.get('stat3_label','').strip()
        if not name or not description:
            flash('اسم الجمعية والوصف مطلوبان.', 'danger')
            return render_template('admin/manager_add_charity.html')
        img = save_image('image'); image_name = img or 'default.jpg'
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("""INSERT INTO charities
                (name,description,image,fields,stat1_num,stat1_label,stat2_num,stat2_label,stat3_num,stat3_label)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (name,description,image_name,fields,stat1_num,stat1_label,
                 stat2_num,stat2_label,stat3_num,stat3_label))
            conn.commit(); cur.close(); conn.close()
            flash(f'✅ تم إضافة جمعية "{name}" بنجاح!', 'success')
            return redirect(url_for('manager_charities'))
        except Exception as e:
            logger.error(e); flash(f'خطأ: {e}', 'danger')
    return render_template('admin/manager_add_charity.html')

@app.route('/manager/charity/edit/<int:cid>', methods=['GET', 'POST'])
@manager_required
def manager_edit_charity(cid):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM charities WHERE id=%s", (cid,))
        charity = cur.fetchone()
        if not charity:
            cur.close(); conn.close()
            flash('الجمعية غير موجودة', 'danger')
            return redirect(url_for('manager_charities'))
        if request.method == 'POST':
            name        = request.form.get('name','').strip()
            description = request.form.get('description','').strip()
            fields      = request.form.get('fields','').strip()
            stat1_num   = request.form.get('stat1_num','').strip()
            stat1_label = request.form.get('stat1_label','').strip()
            stat2_num   = request.form.get('stat2_num','').strip()
            stat2_label = request.form.get('stat2_label','').strip()
            stat3_num   = request.form.get('stat3_num','').strip()
            stat3_label = request.form.get('stat3_label','').strip()
            img = save_image('image'); image_name = img or charity['image']
            cur2 = conn.cursor()
            cur2.execute("""UPDATE charities SET name=%s,description=%s,image=%s,fields=%s,
                stat1_num=%s,stat1_label=%s,stat2_num=%s,stat2_label=%s,stat3_num=%s,stat3_label=%s
                WHERE id=%s""",
                (name,description,image_name,fields,stat1_num,stat1_label,
                 stat2_num,stat2_label,stat3_num,stat3_label,cid))
            conn.commit(); cur2.close(); cur.close(); conn.close()
            flash('✅ تم تعديل بيانات الجمعية بنجاح!', 'success')
            return redirect(url_for('manager_charities'))
        cur.close(); conn.close()
        return render_template('admin/manager_edit_charity.html', charity=charity)
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('manager_charities'))

# ==========================================
# أخطاء
# ==========================================
@app.errorhandler(404)
def not_found(e): return render_template('404.html'), 404

@app.errorhandler(413)
def file_too_large(e):
    flash("حجم الملف أكبر من 5MB", "danger")
    return redirect(request.referrer or url_for('landing'))

@app.errorhandler(500)
def server_error(e):
    logger.error(f"خطأ 500: {e}"); flash("حدث خطأ داخلي", "danger")
    return redirect(url_for('landing'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

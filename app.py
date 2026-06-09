import os
import uuid
import logging
import time
import secrets
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
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
# Email config — set via environment variables
app.config['MAIL_SERVER']   = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT']     = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_FROM']     = os.environ.get('MAIL_FROM', 'noreply@ataagiving.org')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
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

def full_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin' not in session:
            flash("يجب تسجيل الدخول كمشرف", "warning")
            return redirect(url_for('unified_login'))
        if session.get('admin_role') != 'admin':
            flash("ليس لديك صلاحية لهذا الإجراء", "danger")
            return redirect(url_for('admin_inventory'))
        return f(*args, **kwargs)
    return decorated

@app.context_processor
def inject_globals():
    return {
        'is_full_admin': session.get('admin_role') == 'admin'
    }

# ==========================================
# صفحة حملات المنصة العامة
# ==========================================
@app.route('/campaigns')
def platform_campaigns_public():
    status_filter = request.args.get('status', '').strip()
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        sql = "SELECT pc.*, COALESCE(dc.donor_count,0) AS donor_count FROM platform_campaigns pc LEFT JOIN (SELECT platform_campaign_id, COUNT(*) AS donor_count FROM donations WHERE platform_campaign_id IS NOT NULL GROUP BY platform_campaign_id) dc ON dc.platform_campaign_id = pc.id ORDER BY pc.is_urgent DESC, pc.created_at DESC"
        params = []
        if status_filter:
            sql += " WHERE pc.status=%s"
            params.append(status_filter)
        else:
            sql += " WHERE pc.status != 'paused'"
        sql += " ORDER BY pc.created_at DESC"
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
# صفحة الجمعيات الشريكة العامة
# ==========================================
@app.route('/charities')
def public_charities():
    charities = []
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT c.*,
                COUNT(DISTINCT camp.id) AS camp_count,
                COUNT(DISTINCT d.id) AS total_donations
            FROM charities c
            LEFT JOIN campaigns camp ON c.id = camp.charity_id
            LEFT JOIN donations d ON d.charity_id = c.id
            GROUP BY c.id ORDER BY c.id ASC
        """)
        charities = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ في صفحة الجمعيات: {e}")
    return render_template('public_charities.html', charities=charities)

# ==========================================
# صفحة الجمعية الواحدة العامة
# ==========================================
@app.route('/charity/<int:cid>')
def public_charity_detail(cid):
    charity = None
    campaigns = []
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM charities WHERE id=%s", (cid,))
        charity = cur.fetchone()
        if charity:
            cur.execute("""
                SELECT * FROM campaigns
                WHERE charity_id=%s ORDER BY created_at DESC
            """, (cid,))
            campaigns = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ في صفحة الجمعية: {e}")
    if not charity:
        return render_template('404.html'), 404
    return render_template('public_charity_detail.html', charity=charity, campaigns=campaigns)

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
    # ✅ تحقق من الأدمن/المدير أولاً قبل Flask-Login
    if 'admin' in session:
        if session.get('admin_role') == 'manager':
            return redirect(url_for('manager_dashboard'))
        return redirect(url_for('admin_dashboard'))
    if current_user.is_authenticated:
        if current_user.role == 'beneficiary':
            return redirect(url_for('beneficiary_landing'))
        return redirect(url_for('donor_home'))

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
                session.permanent = True
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
            if user.role == 'beneficiary':
                return redirect(request.args.get('next') or url_for('beneficiary_landing'))
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
            role = request.form.get('role', 'donor')
            if role not in ('donor', 'beneficiary'):
                role = 'donor'
            db_orm.session.add(User(username=username, password_hash=generate_password_hash(password), role=role))
            db_orm.session.commit()
            flash('✅ تم إنشاء حسابك بنجاح! سجّل الدخول الآن.', 'success')
            return redirect(url_for('unified_login'))
    return render_template('signup.html')

# ==========================================
# Dark Mode & Language Toggle
# ==========================================
@app.route('/set_theme', methods=['POST'])
def set_theme():
    current = session.get('theme', 'light')
    session['theme'] = 'dark' if current == 'light' else 'light'
    session.permanent = True
    return redirect(request.referrer or url_for('landing'))

@app.route('/set_lang', methods=['POST'])
def set_lang():
    current = session.get('lang', 'ar')
    session['lang'] = 'en' if current == 'ar' else 'ar'
    session.permanent = True
    return redirect(request.referrer or url_for('landing'))


# ──────────────────────────────────────────────────────
# PASSWORD RESET — نسيت كلمة المرور
# ──────────────────────────────────────────────────────
def send_reset_email(to_email, reset_code):
    """إرسال كود إعادة تعيين كلمة المرور"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'إعادة تعيين كلمة المرور — منصة العطاء'
        msg['From']    = app.config['MAIL_FROM']
        msg['To']      = to_email
        html = f"""
        <div dir="rtl" style="font-family:Tajawal,sans-serif;max-width:500px;margin:auto;padding:30px;background:#f9fafb;border-radius:12px;">
            <h2 style="color:#1565C0;">منصة العطاء 💙</h2>
            <p>تلقينا طلب إعادة تعيين كلمة مرورك.</p>
            <div style="background:#EFF6FF;border:2px solid #BFDBFE;border-radius:10px;padding:20px;text-align:center;margin:20px 0;">
                <p style="margin:0;font-size:14px;color:#64748b;">كود إعادة التعيين:</p>
                <h1 style="color:#1565C0;letter-spacing:6px;font-size:32px;margin:10px 0;">{reset_code}</h1>
                <p style="margin:0;font-size:12px;color:#94a3b8;">صالح لمدة 15 دقيقة</p>
            </div>
            <p style="font-size:13px;color:#94a3b8;">إذا لم تطلب إعادة التعيين، تجاهل هذا الإيميل.</p>
        </div>"""
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as s:
            s.starttls()
            s.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            s.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        if not email:
            flash('يرجى إدخال البريد الإلكتروني', 'danger')
            return render_template('forgot_password.html')
        try:
            conn = get_db(); cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, email FROM users WHERE email=%s AND status='active'", (email,))
            user = cur.fetchone()
            if not user:
                # للأمان — نعرض نفس الرسالة سواء وجد أو لا
                flash('إذا كان البريد مسجلاً، ستصلك رسالة خلال دقائق.', 'info')
                cur.close(); conn.close()
                return redirect(url_for('forgot_password'))
            code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            expires = datetime.now() + timedelta(minutes=15)
            cur.execute("UPDATE users SET reset_code=%s, reset_expires=%s WHERE id=%s",
                        (code, expires, user['id']))
            conn.commit(); cur.close(); conn.close()
            send_reset_email(email, code)
            session['reset_email'] = email
            flash('تم إرسال كود إعادة التعيين إلى بريدك الإلكتروني.', 'success')
            return redirect(url_for('reset_password'))
        except Exception as e:
            logger.error(f"forgot_password: {e}")
            flash('حدث خطأ، حاول مرة أخرى', 'danger')
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = session.get('reset_email','')
    if not email:
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        code     = request.form.get('code','').strip()
        new_pw   = request.form.get('new_password','').strip()
        confirm  = request.form.get('confirm_password','').strip()
        if not all([code, new_pw, confirm]):
            flash('يرجى تعبئة جميع الحقول', 'danger')
            return render_template('reset_password.html', email=email)
        if new_pw != confirm:
            flash('كلمتا المرور غير متطابقتين', 'danger')
            return render_template('reset_password.html', email=email)
        if len(new_pw) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
            return render_template('reset_password.html', email=email)
        try:
            conn = get_db(); cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, reset_code, reset_expires FROM users WHERE email=%s", (email,))
            user = cur.fetchone()
            if not user or user['reset_code'] != code:
                flash('الكود غير صحيح', 'danger')
                cur.close(); conn.close()
                return render_template('reset_password.html', email=email)
            if datetime.now() > user['reset_expires']:
                flash('انتهت صلاحية الكود، اطلب كوداً جديداً', 'warning')
                cur.close(); conn.close()
                return redirect(url_for('forgot_password'))
            hashed = generate_password_hash(new_pw)
            cur.execute("UPDATE users SET password=%s, reset_code=NULL, reset_expires=NULL WHERE id=%s",
                        (hashed, user['id']))
            conn.commit(); cur.close(); conn.close()
            session.pop('reset_email', None)
            flash('✅ تم تغيير كلمة المرور بنجاح! يمكنك الدخول الآن.', 'success')
            return redirect(url_for('unified_login'))
        except Exception as e:
            logger.error(f"reset_password: {e}")
            flash('حدث خطأ، حاول مرة أخرى', 'danger')
    return render_template('reset_password.html', email=email)


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
    platform_campaigns = []
    charity_campaigns = []
    total_donations = 0
    campaigns_count = 0
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM platform_campaigns WHERE status='active' ORDER BY is_urgent DESC, created_at DESC LIMIT 6")
        platform_campaigns = cur.fetchall()
        cur.execute("""
            SELECT camp.*, ch.name AS charity_name, ch.image AS charity_image
            FROM campaigns camp JOIN charities ch ON camp.charity_id = ch.id
            ORDER BY camp.created_at DESC LIMIT 6
        """)
        charity_campaigns = cur.fetchall()
        # إجمالي تبرعات المستخدم الحالي
        cur.execute("SELECT COALESCE(SUM(amount),0) AS total FROM donations WHERE donor_email=%s AND status='completed'", (current_user.email,))
        row = cur.fetchone()
        total_donations = row['total'] if row else 0
        # عدد الحملات التي تبرع لها
        cur.execute("SELECT COUNT(DISTINCT campaign_title) AS cnt FROM donations WHERE donor_email=%s AND status='completed'", (current_user.email,))
        row2 = cur.fetchone()
        campaigns_count = row2['cnt'] if row2 else 0
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ donor_home: {e}")
    return render_template('donor/home.html', username=current_user.username,
                           donations=[], platform_campaigns=platform_campaigns,
                           charity_campaigns=charity_campaigns,
                           total_donations=total_donations,
                           campaigns_count=campaigns_count)

@app.route('/donor/donate', methods=['GET', 'POST'])
@login_required
def donor_donate():
    # جلب التصنيفات والطلبات المتاحة (pending) للمتبرع يختار
    item_categories = []
    open_requests   = []
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, name FROM item_categories ORDER BY name")
        item_categories = cur.fetchall()
        cur.execute("""
            SELECT r.id, r.title, r.quantity, ic.name AS category_name
            FROM in_kind_requests r
            JOIN item_categories ic ON r.category_id = ic.id
            WHERE r.status = 'pending'
            ORDER BY r.created_at DESC
        """)
        open_requests = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ جلب بيانات التبرع: {e}")

    if request.method == 'POST':
        category_id = request.form.get('category_id', '').strip()
        description = request.form.get('description', '').strip()
        quantity    = request.form.get('quantity', '1').strip()
        request_id  = request.form.get('request_id', '').strip() or None

        if not all([category_id, description]):
            flash('يرجى تعبئة جميع الحقول المطلوبة', 'danger')
            return render_template('donor/donate.html',
                                   username=current_user.username,
                                   item_categories=item_categories,
                                   open_requests=open_requests)
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("""
                INSERT INTO in_kind_donations
                    (donor_id, category_id, request_id, description, quantity, status)
                VALUES (%s, %s, %s, %s, %s, 'available')
            """, (current_user.id, int(category_id), int(request_id) if request_id else None,
                    description, int(quantity) if quantity.isdigit() else 1))
            # إذا اختار المتبرع طلباً بعينه، حدّث الطلب لـ matched
            if request_id:
                cur.execute(
                    "UPDATE in_kind_requests SET status='matched' WHERE id=%s AND status='pending'",
                    (int(request_id),)
                )
                # حدّث التبرع لـ matched أيضاً
                cur.execute(
                    "UPDATE in_kind_donations SET status='matched', request_id=%s WHERE id=LAST_INSERT_ID()",
                    (int(request_id),)
                )
            conn.commit(); cur.close(); conn.close()
            flash('✅ شكراً! تم تسجيل تبرعك بنجاح وسيتم التواصل معك لترتيب الاستلام. 🙏', 'success')
            return redirect(url_for('donor_my_donations'))
        except Exception as e:
            logger.error(f"خطأ donor_donate: {e}")
            flash('حدث خطأ أثناء تسجيل التبرع، حاول مرة أخرى', 'danger')
    return render_template('donor/donate.html', username=current_user.username,
                           item_categories=item_categories, open_requests=open_requests)

@app.route('/donor/my-donations')
@login_required
def donor_my_donations():
    user_donations = []
    total_donations = 0
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT d.id, d.description, d.quantity, d.status, d.created_at,
                   ic.name AS category_name,
                   r.title AS matched_request,
                   del.status AS delivery_status,
                   del.carrier_name, del.tracking_code, del.delivered_at
            FROM in_kind_donations d
            JOIN item_categories ic ON d.category_id = ic.id
            LEFT JOIN in_kind_requests r ON d.request_id = r.id
            LEFT JOIN deliveries del ON del.donation_id = d.id
            WHERE d.donor_id = %s
            ORDER BY d.created_at DESC
        """, (current_user.id,))
        user_donations = cur.fetchall()
        total_donations = len(user_donations)
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ donor_my_donations: {e}")
    return render_template('donor/my_donations.html', username=current_user.username,
                           donations=user_donations, total_donations=total_donations)

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
        cur.execute("SELECT COUNT(*) AS t FROM in_kind_requests WHERE status='pending'"); pending_requests = cur.fetchone()['t']
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

        hbase = """SELECT h.id,h.item_id,h.action,h.timestamp,i.item_name,i.unique_code,c.name AS category,
                          dr.applicant_name AS beneficiary_name, dr.phone AS beneficiary_phone
                   FROM history h JOIN inventory i ON h.item_id=i.id
                   JOIN categories c ON i.category_id=c.id
                   LEFT JOIN request_items ri ON ri.item_id=i.id
                   LEFT JOIN donation_requests dr ON dr.id=ri.request_id AND dr.id=(
                       SELECT MAX(dr2.id) FROM request_items ri2
                       JOIN donation_requests dr2 ON dr2.id=ri2.request_id
                       WHERE ri2.item_id=i.id
                   )
                   WHERE 1=1"""
        hp = []
        if history_query:
            hbase += " AND (i.item_name LIKE %s OR i.unique_code LIKE %s)"
            hp.extend([f"%{history_query}%", f"%{history_query}%"])
        if history_action_filter: hbase += " AND h.action=%s"; hp.append(history_action_filter)
        hbase += " ORDER BY h.timestamp DESC LIMIT 100"
        cursor.execute(hbase, tuple(hp)); history = cursor.fetchall()
        cursor.execute("SELECT * FROM categories ORDER BY name"); cats = cursor.fetchall()
        cursor.execute("SELECT * FROM subcategories ORDER BY category_id,name"); subs = cursor.fetchall()
        cursor.close(); conn.close()
        return render_template('admin/inventory.html', items=items, counts=counts, history=history,
                               history_query=history_query, history_action_filter=history_action_filter,
                               categories=cats, subcategories=subs)
    except Exception as e:
        logger.error(f"خطأ inventory: {e}"); flash("خطأ في تحميل المخزون", "danger")
        return render_template('admin/inventory.html', items=[], counts={}, history=[], history_query="", history_action_filter="", categories=[], subcategories=[])

@app.route('/admin/add_category', methods=['POST'])
@full_admin_required
def admin_add_category():
    from flask import jsonify
    name = request.json.get('name','').strip()
    if not name:
        return jsonify({'error': 'الاسم مطلوب'}), 400
    try:
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("INSERT IGNORE INTO categories (name) VALUES (%s)", (name,))
        conn.commit()
        cursor.execute("SELECT id, name FROM categories WHERE name=%s", (name,))
        cat = cursor.fetchone()
        cursor.close(); conn.close()
        return jsonify({'id': cat['id'], 'name': cat['name']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/add_subcategory', methods=['POST'])
@full_admin_required
def admin_add_subcategory():
    from flask import jsonify
    name = request.json.get('name','').strip()
    category_id = request.json.get('category_id')
    if not name or not category_id:
        return jsonify({'error': 'البيانات مطلوبة'}), 400
    try:
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("INSERT IGNORE INTO subcategories (name, category_id) VALUES (%s,%s)", (name, category_id))
        conn.commit()
        cursor.execute("SELECT id, name FROM subcategories WHERE name=%s AND category_id=%s", (name, category_id))
        sub = cursor.fetchone()
        cursor.close(); conn.close()
        return jsonify({'id': sub['id'], 'name': sub['name']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/add_item', methods=['GET', 'POST'])
@full_admin_required
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

@app.route('/admin/deliver/<int:item_id>', methods=['GET', 'POST'])
@full_admin_required
def admin_deliver(item_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT i.id, i.item_name, i.unique_code, i.status, i.image,
                              c.name AS category, s.name AS subcategory
                       FROM inventory i
                       JOIN categories c ON i.category_id = c.id
                       LEFT JOIN subcategories s ON i.subcategory_id = s.id
                       WHERE i.id = %s""", (item_id,))
        item = cur.fetchone()
        if not item:
            flash("الصنف غير موجود", "danger")
            return redirect(url_for('admin_inventory'))

        # جلب المستفيد المرتبط بهذا الصنف (إن وجد)
        cur.execute("""SELECT dr.applicant_name, dr.phone, dr.address, dr.id AS req_id
                       FROM request_items ri
                       JOIN donation_requests dr ON dr.id = ri.request_id
                       WHERE ri.item_id = %s
                       ORDER BY dr.id DESC LIMIT 1""", (item_id,))
        beneficiary = cur.fetchone()

        if request.method == 'POST':
            if item['status'] in ('available', 'returned'):
                cur.execute("UPDATE inventory SET status='delivered' WHERE id=%s", (item_id,))
                cur.execute("INSERT INTO history (item_id,unique_code,action) VALUES (%s,%s,'deliver')", (item_id, item['unique_code']))
                conn.commit()
                flash(f"✅ تم تسليم '{item['item_name']}'", 'success')
            cur.close(); conn.close()
            return redirect(url_for('admin_inventory') + '#history')

        cur.close(); conn.close()
        return render_template('admin/deliver_confirm.html', item=item, beneficiary=beneficiary)
    except Exception as e:
        logger.error(e); flash("خطأ", 'danger')
        return redirect(url_for('admin_inventory'))

@app.route('/admin/delete_item/<int:item_id>', methods=['POST'])
@full_admin_required
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
@full_admin_required
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
@full_admin_required
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
@full_admin_required
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
@full_admin_required
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
@full_admin_required
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
@full_admin_required
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
@full_admin_required
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
        if session.get('admin_role') not in ('manager', 'admin'):
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
        cur.execute("SELECT COUNT(*) AS t FROM platform_campaigns WHERE status='completed'"); completed_campaigns = cur.fetchone()['t']
        cur.execute("""
            SELECT ch.id, ch.name, ch.fields AS category,
                   COUNT(ca.id) AS campaigns_count
            FROM charities ch
            LEFT JOIN campaigns ca ON ca.charity_id = ch.id
            GROUP BY ch.id ORDER BY campaigns_count DESC
        """)
        charities_list = cur.fetchall()
        cur.execute("""
            SELECT pc.id, pc.title, pc.category, pc.status,
                   pc.goal_amount, pc.collected_amount,
                   'منصة العطاء' AS charity_name
            FROM platform_campaigns pc ORDER BY pc.id DESC
        """)
        campaigns_list = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"manager_dashboard error: {e}")
        total_charities = total_platform_campaigns = active_campaigns = completed_campaigns = 0
        charities_list = []; campaigns_list = []
    return render_template('admin/manager_dashboard.html',
                           total_charities=total_charities,
                           total_platform_campaigns=total_platform_campaigns,
                           active_campaigns=active_campaigns,
                           completed_campaigns=completed_campaigns,
                           charities_list=charities_list,
                           campaigns_list=campaigns_list)

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

@app.route('/beneficiary/choice')
def beneficiary_choice():
    return render_template('beneficiary_choice.html')

@app.route('/beneficiary')
def beneficiary_landing():
    return render_template('beneficiary_landing.html')

@app.route('/beneficiary/register', methods=['GET', 'POST'])
def beneficiary_register():
    # جلب تصنيفات التبرعات العينية من قاعدة البيانات
    categories = []
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, name FROM item_categories ORDER BY name")
        categories = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ جلب item_categories: {e}")

    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        category_id = request.form.get('category_id', '').strip()
        description = request.form.get('description', '').strip()
        quantity    = request.form.get('quantity', '1').strip()
        # للتوافق مع الـ template القديم — نقرأ item_requested كـ title إذا فارغ
        if not title:
            title = request.form.get('item_requested', '').strip()

        if not all([title, category_id, description]):
            flash('يرجى تعبئة جميع الحقول المطلوبة', 'danger')
            return render_template('beneficiary_register.html', categories=categories)

        # المستفيد لازم يكون مسجّل دخول
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً لتقديم طلب مساعدة', 'warning')
            return redirect(url_for('unified_login'))

        if current_user.role != 'beneficiary':
            flash('هذه الخدمة متاحة للمستفيدين فقط', 'warning')
            return redirect(url_for('donor_home'))

        try:
            conn = get_db(); cur = conn.cursor(dictionary=True)
            # منع التكرار: تحقق من وجود طلب نشط بنفس المستفيد ونفس الصنف
            cur.execute("""
                SELECT id, status FROM in_kind_requests
                WHERE beneficiary_id=%s AND category_id=%s
                AND status NOT IN ('fulfilled')
                ORDER BY created_at DESC LIMIT 1
            """, (current_user.id, int(category_id)))
            existing = cur.fetchone()
            if existing:
                cur.close(); conn.close()
                status_labels = {
                    'pending':  'قيد المراجعة',
                    'matched':  'تمت المطابقة',
                }
                status_ar = status_labels.get(existing['status'], existing['status'])
                flash(f'⚠️ لديك طلب سابق لنفس الصنف (طلب #{existing["id"]}) وحالته: {status_ar}. لا يمكن تقديم طلب مكرر.', 'warning')
                return redirect(url_for('beneficiary_track'))
            # حالة طبية عاجلة؟
            is_urgent = 1 if request.form.get('is_urgent') == '1' else 0
            # حفظ الطلب في donation_requests (نظام الطلبات الرئيسي)
            applicant_name = current_user.username
            phone          = request.form.get('phone','').strip() or '—'
            address        = request.form.get('address','').strip() or '—'
            family_members = request.form.get('family_members','1').strip()
            cur2 = conn.cursor()
            cur2.execute("""
                INSERT INTO donation_requests
                    (applicant_name, phone, address, request_type, item_requested,
                     description, family_members, status, is_urgent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s)
            """, (applicant_name, phone, address,
                   'حالة طبية عاجلة' if is_urgent else 'طلب مساعدة',
                   title, description,
                   int(family_members) if family_members.isdigit() else 1,
                   is_urgent))
            conn.commit(); cur2.close(); conn.close()
            if is_urgent:
                flash('🚨 تم إرسال طلبك العاجل بنجاح! سيتم مراجعته بأولوية قصوى.', 'success')
            else:
                flash('✅ تم إرسال طلبك بنجاح! يمكنك متابعة حالته من صفحة تتبع الطلب.', 'success')
            return redirect(url_for('beneficiary_track'))
        except Exception as e:
            logger.error(f"خطأ beneficiary_register: {e}")
            flash('حدث خطأ أثناء إرسال الطلب، حاول مرة أخرى', 'danger')
    return render_template('beneficiary_register.html', categories=categories)


@app.route('/beneficiary/confirm_received', methods=['POST'])
def beneficiary_confirm_received():
    phone = request.form.get('phone','').strip()
    req_id = request.form.get('request_id','').strip()
    if not phone or not req_id:
        flash('يرجى إدخال رقم الهاتف ورقم الطلب', 'danger')
        return redirect(url_for('beneficiary_track'))
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id FROM donation_requests
            WHERE id=%s AND phone=%s AND status='on_the_way'
        """, (int(req_id), phone))
        req = cur.fetchone()
        if not req:
            flash('⚠️ لم يتم العثور على الطلب أو رقم الهاتف غير صحيح', 'danger')
            cur.close(); conn.close()
            return redirect(url_for('beneficiary_track'))
        cur.execute("""
            UPDATE donation_requests
            SET status='received', received_at=NOW()
            WHERE id=%s
        """, (int(req_id),))
        conn.commit(); cur.close(); conn.close()
        flash('✅ تم تأكيد الاستلام بنجاح! شكراً لك.', 'success')
    except Exception as e:
        logger.error(f'خطأ confirm_received: {e}')
        flash('حدث خطأ، حاول مرة أخرى', 'danger')
    return redirect(url_for('beneficiary_track'))

@app.route('/beneficiary/track')
def beneficiary_track():
    search_phone = request.args.get('phone','').strip()
    reqs = []
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        if search_phone:
            cur.execute("""
                SELECT id, applicant_name, phone, item_requested, description,
                       status, is_urgent, created_at, received_at, admin_note
                FROM donation_requests
                WHERE phone=%s
                ORDER BY is_urgent DESC, created_at DESC
            """, (search_phone,))
        elif current_user.is_authenticated and current_user.role == 'beneficiary':
            cur.execute("""
                SELECT id, applicant_name, phone, item_requested, description,
                       status, is_urgent, created_at, received_at, admin_note
                FROM donation_requests
                WHERE applicant_name=%s
                ORDER BY is_urgent DESC, created_at DESC
            """, (current_user.username,))
        reqs = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ track: {e}")
    return render_template('beneficiary_track.html', requests=reqs, search_phone=search_phone)

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
        # Counts from in_kind_requests
        cur.execute("SELECT status, COUNT(*) AS c FROM in_kind_requests GROUP BY status")
        raw_counts = {r['status']: r['c'] for r in cur.fetchall()}
        counts = {
            'total':     sum(raw_counts.values()),
            'pending':   raw_counts.get('pending',   0),
            'matched':   raw_counts.get('matched',   0),
            'fulfilled': raw_counts.get('fulfilled', 0),
        }
        # Requests with user + category info
        sql = """
            SELECT r.id, r.title, r.description, r.quantity, r.status, r.created_at,
                   ic.name AS category_name,
                   u.full_name AS beneficiary_name, u.phone, u.email,
                   d.id AS delivery_id, d.status AS delivery_status,
                   d.carrier_name, d.tracking_code
            FROM in_kind_requests r
            JOIN item_categories ic ON r.category_id = ic.id
            JOIN users u ON r.beneficiary_id = u.id
            LEFT JOIN in_kind_donations ikd ON ikd.request_id = r.id
            LEFT JOIN deliveries d ON d.donation_id = ikd.id
        """
        params = []
        if status_filter:
            sql += " WHERE r.status=%s"
            params.append(status_filter)
        sql += " ORDER BY r.created_at DESC"
        cur.execute(sql, tuple(params))
        reqs = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(f"خطأ donation_requests: {e}")
        reqs, counts = [], {'total':0,'pending':0,'matched':0,'fulfilled':0}
    return render_template('admin/donation_requests.html', requests=reqs,
                           counts=counts, status_filter=status_filter)

@app.route('/admin/donation-request/<int:req_id>/approve', methods=['GET', 'POST'])
@admin_required_session
def admin_approve_request(req_id):
    """الموافقة على الطلب: ينشئ in_kind_donation مرتبط ثم delivery"""
    conn = get_db(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT r.*, ic.name AS category_name,
                   u.full_name AS beneficiary_name, u.phone, u.address
            FROM in_kind_requests r
            JOIN item_categories ic ON r.category_id = ic.id
            JOIN users u ON r.beneficiary_id = u.id
            WHERE r.id=%s
        """, (req_id,))
        req = cur.fetchone()
        if not req:
            flash('الطلب غير موجود', 'danger')
            return redirect(url_for('admin_donation_requests'))

        if request.method == 'POST':
            pickup_address   = request.form.get('pickup_address', '').strip()
            delivery_address = request.form.get('delivery_address', req.get('address','')).strip()
            carrier_name     = request.form.get('carrier_name', '').strip() or None
            tracking_code    = request.form.get('tracking_code', '').strip() or None

            cur2 = conn.cursor()
            # أنشئ in_kind_donation تمثّل التوصيل الإداري
            cur2.execute("""
                INSERT INTO in_kind_donations
                    (donor_id, category_id, request_id, description, quantity, status)
                VALUES (
                    (SELECT id FROM admins WHERE role='admin' LIMIT 1),
                    %s, %s, 'توصيل إداري', %s, 'matched'
                )
            """, (req['category_id'], req_id, req['quantity']))
            donation_id = cur2.lastrowid

            # أنشئ delivery record
            cur2.execute("""
                INSERT INTO deliveries
                    (donation_id, pickup_address, delivery_address, carrier_name, tracking_code, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
            """, (donation_id, pickup_address or 'مستودع المنصة',
                  delivery_address, carrier_name, tracking_code))

            # حدّث حالة الطلب لـ matched
            cur2.execute("UPDATE in_kind_requests SET status='matched' WHERE id=%s", (req_id,))
            conn.commit(); cur2.close(); conn.close()
            flash('✅ تمت الموافقة وإنشاء سجل التوصيل بنجاح', 'success')
            return redirect(url_for('admin_donation_requests'))

        cur.close(); conn.close()
        return render_template('admin/approve_request.html', req=req)
    except Exception as e:
        logger.error(f"خطأ approve_request: {e}")
        flash('حدث خطأ', 'danger')
        return redirect(url_for('admin_donation_requests'))


@app.route('/admin/donation-request/<int:req_id>/update', methods=['POST'])
@admin_required_session
def admin_update_donation_request(req_id):
    action = request.form.get('action', '')
    # in_kind_requests only supports: pending / matched / fulfilled
    status_map = {
        'fulfill':    'fulfilled',
        'pending':    'pending',
    }
    new_status = status_map.get(action)
    if not new_status:
        flash('إجراء غير صحيح', 'danger')
        return redirect(url_for('admin_donation_requests'))
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE in_kind_requests SET status=%s WHERE id=%s", (new_status, req_id))
        # إذا fulfilled — حدّث deliveries المرتبطة
        if new_status == 'fulfilled':
            cur.execute("""
                UPDATE deliveries d
                JOIN in_kind_donations ikd ON d.donation_id = ikd.id
                SET d.status='delivered', d.delivered_at=NOW()
                WHERE ikd.request_id=%s
            """, (req_id,))
            cur.execute("""
                UPDATE in_kind_donations SET status='delivered'
                WHERE request_id=%s
            """, (req_id,))
        conn.commit(); cur.close(); conn.close()
        msgs = {
            'fulfilled': '✅ تم تأكيد استلام المتبرع به وإتمام التوصيل',
            'pending':   '🔄 تم إعادة الطلب لقيد المراجعة',
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
        # الحذف CASCADE — deliveries وin_kind_donations سيُحذفان تلقائياً
        cur.execute("DELETE FROM in_kind_requests WHERE id=%s", (req_id,))
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

@app.route('/manager/charity/<int:cid>/campaigns')
@manager_required
def manager_charity_campaigns(cid):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM charities WHERE id=%s", (cid,))
        charity = cur.fetchone()
        if not charity:
            flash('الجمعية غير موجودة', 'danger')
            return redirect(url_for('manager_charities'))
        cur.execute("""SELECT * FROM campaigns WHERE charity_id=%s ORDER BY created_at DESC""", (cid,))
        campaigns = cur.fetchall()
        # إحصائيات
        total = len(campaigns)
        active = sum(1 for c in campaigns if c.get('status') == 'active')
        completed = sum(1 for c in campaigns if c.get('status') == 'completed')
        paused = sum(1 for c in campaigns if c.get('status') == 'paused')
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e)
        charity = None; campaigns = []
        total = active = completed = paused = 0
    return render_template('admin/manager_charity_campaigns.html',
                           charity=charity, campaigns=campaigns,
                           total=total, active=active,
                           completed=completed, paused=paused)

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
                status    = request.form.get('status', 'active')
                collected = float(request.form.get('collected_amount', '0') or '0')
                cur2.execute("INSERT INTO campaigns (charity_id,title,description,goal_amount,collected_amount,status,image,category) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                             (charity_id, title, description, goal, collected, status, image_name, category))
                conn.commit(); cur2.close()
                flash(f'✅ تم إضافة حملة "{title}" بنجاح!', 'success')
                cur.close(); conn.close()
                cid_arg = request.form.get('charity_id')
                return redirect(url_for('manager_charity_campaigns', cid=cid_arg) if cid_arg else url_for('manager_campaigns'))
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
            status    = request.form.get('status', campaign.get('status','active'))
            collected = float(request.form.get('collected_amount','0') or '0')
            cur2.execute("UPDATE campaigns SET charity_id=%s,title=%s,description=%s,goal_amount=%s,collected_amount=%s,status=%s,image=%s,category=%s WHERE id=%s",
                         (charity_id, title, description, goal, collected, status, image_name, category, camp_id))
            conn.commit(); cur2.close(); cur.close(); conn.close()
            flash('✅ تم تعديل الحملة بنجاح!', 'success')
            return redirect(url_for('manager_campaigns'))
        cur.close(); conn.close()
        return render_template('admin/manager_edit_campaign.html', campaign=campaign, charities=charities)
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('manager_campaigns'))

@app.route('/manager/campaign/delete/<int:camp_id>', methods=['GET','POST'])
@manager_required
def manager_delete_campaign(camp_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT c.*, ch.name AS charity_name FROM campaigns c LEFT JOIN charities ch ON ch.id=c.charity_id WHERE c.id=%s", (camp_id,))
        campaign = cur.fetchone()
        if not campaign:
            cur.close(); conn.close()
            return redirect(url_for('manager_campaigns'))
        if request.method == 'POST':
            cur2 = conn.cursor()
            cur2.execute("DELETE FROM campaigns WHERE id=%s", (camp_id,))
            conn.commit(); cur2.close(); cur.close(); conn.close()
            flash(f'✅ تم حذف الحملة "{campaign["title"]}" نهائياً', 'success')
            return redirect(url_for('manager_campaigns'))
        cur.close(); conn.close()
        return render_template('admin/manager_delete_campaign_confirm.html', campaign=campaign, camp_type='charity')
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
        return redirect(url_for('manager_campaigns'))

@app.route('/manager/donation-requests')
@manager_required
def manager_donation_requests():
    status_filter = request.args.get('status', '').strip()
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT status, COUNT(*) AS c FROM in_kind_requests GROUP BY status")
        raw_counts = {r['status']: r['c'] for r in cur.fetchall()}
        counts = {
            'total':     sum(raw_counts.values()),
            'pending':   raw_counts.get('pending',   0),
            'matched':   raw_counts.get('matched',   0),
            'fulfilled': raw_counts.get('fulfilled', 0),
        }
        sql = """
            SELECT r.id, r.title, r.description, r.quantity, r.status, r.created_at,
                   ic.name AS category_name,
                   u.full_name AS beneficiary_name, u.phone, u.email,
                   d.id AS delivery_id, d.status AS delivery_status,
                   d.carrier_name, d.tracking_code
            FROM in_kind_requests r
            JOIN item_categories ic ON r.category_id = ic.id
            JOIN users u ON r.beneficiary_id = u.id
            LEFT JOIN in_kind_donations ikd ON ikd.request_id = r.id
            LEFT JOIN deliveries d ON d.donation_id = ikd.id
        """
        params = []
        if status_filter:
            sql += " WHERE r.status=%s"; params.append(status_filter)
        sql += " ORDER BY r.created_at DESC"
        cur.execute(sql, tuple(params))
        reqs = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e)
        reqs, counts = [], {'total':0,'pending':0,'matched':0,'fulfilled':0}
    return render_template('admin/manager_donation_requests.html', requests=reqs, counts=counts, status_filter=status_filter)

@app.route('/manager/donors')
@manager_required
def manager_donors():
    search = request.args.get('q','').strip()
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS t FROM users WHERE role='donor'"); total_donors = cur.fetchone()['t']
        cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM donations WHERE status='completed'"); total_amount = cur.fetchone()['t']
        cur.execute("SELECT COUNT(*) AS t FROM donations"); total_ops = cur.fetchone()['t']
        sql = ("SELECT u.id, u.full_name, u.email, u.username, u.phone, u.address, u.status, u.created_at,"
               " COUNT(d.id) AS donation_count,"
               " COALESCE(SUM(d.amount),0) AS total_donated,"
               " MAX(d.created_at) AS last_donation"
               " FROM users u LEFT JOIN donations d ON d.user_id = u.id"
               " WHERE u.role='donor'")
        params = []
        if search:
            sql += " AND (u.full_name LIKE %s OR u.email LIKE %s OR u.username LIKE %s)"
            params += [f'%{search}%']*3
        sql += " GROUP BY u.id ORDER BY total_donated DESC"
        cur.execute(sql, params)
        donors = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e)
        donors, total_donors, total_amount, total_ops = [], 0, 0, 0
    return render_template('admin/manager_donors.html',
                           donors=donors, total_donors=total_donors,
                           total_amount=total_amount, total_ops=total_ops,
                           search=search)

@app.route('/manager/donations-log')
@manager_required
def manager_donations_log():
    search = request.args.get('q','').strip()
    status_filter = request.args.get('status','').strip()
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS t FROM donations"); total_ops = cur.fetchone()['t']
        cur.execute("SELECT COALESCE(SUM(amount),0) AS t FROM donations WHERE status='completed'"); total_amount = cur.fetchone()['t']
        cur.execute("SELECT COALESCE(AVG(amount),0) AS t FROM donations WHERE status='completed'"); avg_amount = cur.fetchone()['t']
        sql = "SELECT * FROM donations WHERE 1=1"
        params = []
        if search:
            sql += " AND (donor_name LIKE %s OR tx_id LIKE %s OR campaign_title LIKE %s)"
            params += [f'%{search}%']*3
        if status_filter:
            sql += " AND status=%s"; params.append(status_filter)
        sql += " ORDER BY created_at DESC"
        cur.execute(sql, params)
        donations = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        logger.error(e)
        donations, total_ops, total_amount, avg_amount = [], 0, 0, 0
    return render_template('admin/manager_donations_log.html',
                           donations=donations, total_ops=total_ops,
                           total_amount=total_amount, avg_amount=avg_amount,
                           search=search, status_filter=status_filter)

@app.route('/manager/donation-request/<int:req_id>/update', methods=['POST'])
@manager_required
def manager_update_donation_request(req_id):
    action = request.form.get('action', '')
    status_map = {'fulfill': 'fulfilled', 'pending': 'pending', 'matched': 'matched'}
    new_status = status_map.get(action)
    if not new_status:
        flash('إجراء غير صحيح', 'danger')
        return redirect(url_for('manager_donation_requests'))
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE in_kind_requests SET status=%s WHERE id=%s", (new_status, req_id))
        if new_status == 'fulfilled':
            cur.execute("""
                UPDATE deliveries d
                JOIN in_kind_donations ikd ON d.donation_id = ikd.id
                SET d.status='delivered', d.delivered_at=NOW()
                WHERE ikd.request_id=%s
            """, (req_id,))
            cur.execute("UPDATE in_kind_donations SET status='delivered' WHERE request_id=%s", (req_id,))
        conn.commit(); cur.close(); conn.close()
        msgs = {'fulfilled': '✅ تم تأكيد التوصيل وإتمام الطلب',
                'matched':   '🔗 تم تحديث الحالة إلى مطابق',
                'pending':   '🔄 تم إعادة الطلب للمراجعة'}
        flash(msgs.get(new_status, 'تم التحديث'), 'success')
    except Exception as e:
        logger.error(e); flash('حدث خطأ', 'danger')
    return redirect(url_for('manager_donation_requests'))


@app.route('/admin/delivery/<int:delivery_id>/update', methods=['POST'])
@admin_required_session
def admin_update_delivery(delivery_id):
    """تحديث حالة التوصيل من الأدمن"""
    new_status    = request.form.get('delivery_status', '').strip()
    carrier_name  = request.form.get('carrier_name', '').strip() or None
    tracking_code = request.form.get('tracking_code', '').strip() or None
    valid = {'pending', 'in_transit', 'delivered'}
    if new_status not in valid:
        flash('حالة غير صحيحة', 'danger')
        return redirect(url_for('admin_donation_requests'))
    try:
        conn = get_db(); cur = conn.cursor()
        delivered_at = 'NOW()' if new_status == 'delivered' else 'NULL'
        cur.execute(f"""
            UPDATE deliveries
            SET status=%s,
                carrier_name=COALESCE(%s, carrier_name),
                tracking_code=COALESCE(%s, tracking_code),
                delivered_at=IF(%s='delivered', NOW(), delivered_at)
            WHERE id=%s
        """, (new_status, carrier_name, tracking_code, new_status, delivery_id))
        # إذا delivered — حدّث الطلب والتبرع
        if new_status == 'delivered':
            cur.execute("""
                UPDATE in_kind_requests r
                JOIN in_kind_donations ikd ON ikd.request_id = r.id
                JOIN deliveries d ON d.donation_id = ikd.id
                SET r.status='fulfilled', ikd.status='delivered'
                WHERE d.id=%s
            """, (delivery_id,))
        conn.commit(); cur.close(); conn.close()
        flash({'pending': '⏳ تم تحديث الحالة إلى قيد الانتظار',
               'in_transit': '🚚 تم تحديث الحالة إلى في الطريق',
               'delivered':  '✅ تم تأكيد التوصيل النهائي'}.get(new_status, 'تم التحديث'), 'success')
    except Exception as e:
        logger.error(f"خطأ update delivery: {e}")
        flash('حدث خطأ', 'danger')
    return redirect(url_for('admin_donation_requests'))


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
        is_urgent = 1 if request.form.get('is_urgent') == '1' else 0
        img = save_image('image'); image_name = img or 'default.jpg'
        try: goal = float(goal_amount)
        except: goal = 0.0
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("""INSERT INTO platform_campaigns (title,description,goal_amount,image,category,created_by,is_urgent)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (title, description, goal, image_name, category, session.get('admin',''), is_urgent))
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

@app.route('/manager/platform-campaign/delete/<int:camp_id>', methods=['GET','POST'])
@manager_required
def manager_delete_platform_campaign(camp_id):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM platform_campaigns WHERE id=%s", (camp_id,))
        campaign = cur.fetchone()
        if not campaign:
            cur.close(); conn.close()
            return redirect(url_for('manager_platform_campaigns'))
        if request.method == 'POST':
            cur2 = conn.cursor()
            cur2.execute("DELETE FROM platform_campaigns WHERE id=%s", (camp_id,))
            conn.commit(); cur2.close(); cur.close(); conn.close()
            flash(f'✅ تم حذف الحملة "{campaign["title"]}" نهائياً', 'success')
            return redirect(url_for('manager_platform_campaigns'))
        cur.close(); conn.close()
        return render_template('admin/manager_delete_campaign_confirm.html', campaign=campaign, camp_type='platform')
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

@app.route('/manager/charity/delete/<int:cid>', methods=['POST'])
@manager_required
def manager_delete_charity(cid):
    try:
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT name FROM charities WHERE id=%s", (cid,))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            flash('الجمعية غير موجودة', 'danger')
            return redirect(url_for('manager_charities'))
        cur2 = conn.cursor()
        cur2.execute("DELETE FROM charities WHERE id=%s", (cid,))
        conn.commit(); cur2.close(); cur.close(); conn.close()
        flash(f'✅ تم حذف جمعية "{row["name"]}" نهائياً', 'success')
    except Exception as e:
        logger.error(e); flash(f'خطأ: {e}', 'danger')
    return redirect(url_for('manager_charities'))

# ==========================================
# كيف يعمل عطاء
# ==========================================
@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

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

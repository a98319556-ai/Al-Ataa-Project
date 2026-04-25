-- =============================================
-- منصة العطاء الموحدة - قاعدة البيانات
-- ataa_platform
-- =============================================

CREATE DATABASE IF NOT EXISTS ataa_platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ataa_platform;

-- =============================================
-- جدول المشرفين (Admin)
-- =============================================
CREATE TABLE IF NOT EXISTS admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'admin'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO admins (username, password, role) VALUES
('admin', 'admin123', 'admin'),
('manager', 'manager123', 'manager');

-- =============================================
-- جدول المتبرعين (Donors via Flask-Login)
-- =============================================
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    full_name VARCHAR(100),
    role VARCHAR(10) DEFAULT 'donor',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- جداول المخزن
-- =============================================
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO categories (name) VALUES
('الأثاث'), ('الأجهزة الكهربائية'), ('ملابس');

CREATE TABLE IF NOT EXISTS subcategories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category_id INT,
    UNIQUE KEY (name, category_id),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO subcategories (name, category_id) VALUES
('ملابس رجالي شتوي', 3), ('ملابس حريمي شتوي', 3), ('ملابس أطفال شتوي', 3),
('ملابس رجالي صيفي', 3), ('ملابس حريمي صيفي', 3), ('ملابس أطفال صيفي', 3),
('ملابس رجالي ربيعي', 3), ('ملابس حريمي ربيعي', 3), ('ملابس أطفال ربيعي', 3),
('ملابس رجالي خريفي', 3), ('ملابس حريمي خريفي', 3), ('ملابس أطفال خريفي', 3);

CREATE TABLE IF NOT EXISTS inventory (
    id INT AUTO_INCREMENT PRIMARY KEY,
    item_name VARCHAR(255) NOT NULL,
    description TEXT,
    category_id INT NOT NULL,
    subcategory_id INT DEFAULT NULL,
    quantity INT NOT NULL DEFAULT 1,
    status ENUM('available','delivered','returned','deleted') DEFAULT 'available',
    image VARCHAR(255) DEFAULT NULL,
    unique_code VARCHAR(36) NOT NULL DEFAULT (UUID()),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY (unique_code),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    FOREIGN KEY (subcategory_id) REFERENCES subcategories(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    item_id INT NOT NULL,
    action ENUM('add','deliver','delete','returned','available') NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unique_code VARCHAR(36),
    FOREIGN KEY (item_id) REFERENCES inventory(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- جداول الجمعيات والحملات
-- =============================================
CREATE TABLE IF NOT EXISTS charities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    image VARCHAR(255) DEFAULT 'default.jpg',
    fields VARCHAR(500) DEFAULT '',
    stat1_num VARCHAR(50) DEFAULT '',
    stat1_label VARCHAR(100) DEFAULT '',
    stat2_num VARCHAR(50) DEFAULT '',
    stat2_label VARCHAR(100) DEFAULT '',
    stat3_num VARCHAR(50) DEFAULT '',
    stat3_label VARCHAR(100) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS campaigns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    charity_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    goal_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    image VARCHAR(255) DEFAULT 'default.jpg',
    category VARCHAR(100) DEFAULT 'عام',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (charity_id) REFERENCES charities(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- بيانات تجريبية للجمعيات
INSERT INTO charities (name, description, image, fields, stat1_num, stat1_label, stat2_num, stat2_label, stat3_num, stat3_label) VALUES
('جمعية رسالة', 'أكبر جمعية تطوعية في مصر، تأسست عام 1999. تعمل في مجالات الغذاء والتعليم وكفالة الأيتام والرعاية الصحية.', 'default.jpg', 'مساعدات اجتماعية,كفالة أيتام,علاج,تعليم,توزيع ملابس,توزيع غذاء', '1200+', 'متبرع شهرياً', '22', 'فرع في مصر', '300+', 'متطوع'),
('مصر الخير', 'مؤسسة كبيرة تعمل في التعليم والصحة والتنمية مع شبكة واسعة من المستشفيات والمدارس.', 'default.jpg', 'تعليم,صحة,مساعدات,تنمية,مشروعات صغيرة', '10', 'مستشفيات', '50', 'مدرسة', '2000+', 'متبرع شهرياً'),
('بنك الطعام المصري', 'متخصص في توزيع الطعام والمساعدات الغذائية على الأسر المحتاجة في جميع المحافظات.', 'default.jpg', 'توزيع طعام,دعم الأسر الفقيرة,وجبات جافة,وجبات ساخنة', '10 مليون', 'وجبة سنوياً', 'كل', 'المحافظات', '50+', 'شريك');

-- حملات
INSERT INTO campaigns (charity_id, title, description, goal_amount, category) VALUES
(1, 'كفالة يتيم', 'كفالة شهرية لطفل يتيم تشمل الطعام والملابس والتعليم والرعاية الصحية.', 30000, 'أيتام'),
(1, 'كيس ملابس شتوية', 'ملابس شتوية جديدة للأسر الفقيرة.', 50000, 'ملابس'),
(2, 'منحة دراسية', 'منح دراسية للطلاب المتفوقين غير القادرين.', 100000, 'تعليم'),
(2, 'وحدة صحية متنقلة', 'وحدة صحية لخدمة المناطق النائية.', 300000, 'صحة'),
(3, 'كرتونة غذائية', 'كرتونة غذائية للأسر الفقيرة.', 150000, 'غذاء'),
(3, 'وجبات ساخنة', 'وجبات ساخنة يومية للمحتاجين.', 80000, 'غذاء');

-- =============================================
-- جدول طلبات التبرع العينية
-- =============================================
-- =============================================
-- جدول حملات المنصة (منفصل عن حملات الجمعيات)
-- =============================================
CREATE TABLE IF NOT EXISTS platform_campaigns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    goal_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    collected_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    image VARCHAR(255) DEFAULT 'default.jpg',
    category VARCHAR(100) DEFAULT 'عام',
    status ENUM('active','completed','paused') DEFAULT 'active',
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_pending_request (phone, item_requested(50), status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- بيانات تجريبية لحملات المنصة
INSERT INTO platform_campaigns (title, description, goal_amount, category, status, created_by) VALUES
('تجهيز وحدة غسيل كلوي', 'توفير أجهزة غسيل كلوي لمستشفى قصر العيني لخدمة المرضى المحتاجين يومياً.', 473000, 'صحة', 'active', 'admin'),
('سداد ديون غارمات', 'مساعدة الأسر المحتاجة في سداد ديونها وإخراجها من ضائقتها المالية.', 120000, 'غارمات', 'active', 'admin'),
('وصلات مياه للقرى', 'توصيل مياه الشرب النقية للقرى المحرومة في محافظة الفيوم.', 115000, 'بنية تحتية', 'active', 'admin');

CREATE TABLE IF NOT EXISTS donation_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    applicant_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    address TEXT NOT NULL,
    request_type VARCHAR(100) NOT NULL,
    item_requested VARCHAR(255) NOT NULL,
    description TEXT,
    family_members INT DEFAULT NULL,
    status ENUM('pending','approved','rejected','final_rejected','on_the_way') DEFAULT 'pending',
    admin_note TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS donation_request_docs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    FOREIGN KEY (request_id) REFERENCES donation_requests(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- بيانات تجريبية
INSERT INTO donation_requests (applicant_name, phone, address, request_type, item_requested, description, family_members, status) VALUES
('أم محمد', '01012345678', 'القاهرة، شبرا - شارع الجمهورية', 'أجهزة كهربائية', 'ثلاجة للأسرة', 'الثلاجة الحالية معطوبة منذ ٦ أشهر وعندي ٥ أطفال صغار', 6, 'pending'),
('السيد أحمد علي', '01198765432', 'الجيزة، إمبابة - شارع السودان', 'تجهيز عروسة', 'غرفة نوم كاملة وتجهيزات المطبخ', 'ابنتي على وشك الزواج ولا نقدر على تأمين التجهيزات', 4, 'pending'),
('فاطمة حسن', '01234567890', 'الإسكندرية، العجمي', 'أثاث', 'سرير وخزانة ملابس', 'أنا أرملة ومعي أطفال ونحتاج أثاث أساسي', 3, 'approved'),
('عم سيد', '01567891234', 'الفيوم، إبشواي', 'أجهزة كهربائية', 'غسالة', 'نحتاج غسالة لعائلة مكونة من ٧ أفراد', 7, 'on_the_way'),
('مريم إبراهيم', '01099887766', 'أسيوط، المنصورة', 'تجهيز عروسة', 'كامل تجهيزات العروسة', 'يتيمة وتحتاج مساعدة كاملة', 2, 'rejected');

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

INSERT IGNORE INTO admins (username, password, role) VALUES
('admin', 'admin123', 'admin'),
('manager', 'manager123', 'manager');

-- =============================================
-- جدول المتبرعين (Donors via Flask-Login)
-- =============================================
CREATE TABLE IF NOT EXISTS users (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    username     VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    email        VARCHAR(100),
    full_name    VARCHAR(100),
    role         VARCHAR(10) DEFAULT 'donor',
    phone        VARCHAR(20) DEFAULT NULL,
    address      TEXT DEFAULT NULL,
    status       ENUM('active','suspended') DEFAULT 'active',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- جداول المخزن
-- =============================================
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO categories (name) VALUES
('الأثاث'), ('الأجهزة الكهربائية'), ('ملابس');

CREATE TABLE IF NOT EXISTS subcategories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category_id INT,
    UNIQUE KEY (name, category_id),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO subcategories (name, category_id) VALUES
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
    id          INT AUTO_INCREMENT PRIMARY KEY,
    admin_id    INT DEFAULT NULL,
    name        VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    phone       VARCHAR(20) DEFAULT NULL,
    address     TEXT DEFAULT NULL,
    status      ENUM('active','inactive') DEFAULT 'active',
    image       VARCHAR(255) DEFAULT 'default.jpg',
    fields      VARCHAR(500) DEFAULT '',
    stat1_num   VARCHAR(50) DEFAULT '',
    stat1_label VARCHAR(100) DEFAULT '',
    stat2_num   VARCHAR(50) DEFAULT '',
    stat2_label VARCHAR(100) DEFAULT '',
    stat3_num   VARCHAR(50) DEFAULT '',
    stat3_label VARCHAR(100) DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS campaigns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    charity_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    goal_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    collected_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    status ENUM('active','completed','paused') DEFAULT 'active',
    image VARCHAR(255) DEFAULT 'default.jpg',
    category VARCHAR(100) DEFAULT 'عام',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (charity_id) REFERENCES charities(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- بيانات تجريبية للجمعيات
INSERT IGNORE INTO charities (name, description, image, fields, stat1_num, stat1_label, stat2_num, stat2_label, stat3_num, stat3_label) VALUES
('جمعية رسالة', 'أكبر جمعية تطوعية في مصر، تأسست عام 1999. تعمل في مجالات الغذاء والتعليم وكفالة الأيتام والرعاية الصحية.', 'default.jpg', 'مساعدات اجتماعية,كفالة أيتام,علاج,تعليم,توزيع ملابس,توزيع غذاء', '1200+', 'متبرع شهرياً', '22', 'فرع في مصر', '300+', 'متطوع'),
('مصر الخير', 'مؤسسة كبيرة تعمل في التعليم والصحة والتنمية مع شبكة واسعة من المستشفيات والمدارس.', 'default.jpg', 'تعليم,صحة,مساعدات,تنمية,مشروعات صغيرة', '10', 'مستشفيات', '50', 'مدرسة', '2000+', 'متبرع شهرياً'),
('بنك الطعام المصري', 'متخصص في توزيع الطعام والمساعدات الغذائية على الأسر المحتاجة في جميع المحافظات.', 'default.jpg', 'توزيع طعام,دعم الأسر الفقيرة,وجبات جافة,وجبات ساخنة', '10 مليون', 'وجبة سنوياً', 'كل', 'المحافظات', '50+', 'شريك');

-- حملات
INSERT IGNORE INTO campaigns (charity_id, title, description, goal_amount, category) VALUES
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
INSERT IGNORE INTO platform_campaigns (title, description, goal_amount, category, status, created_by) VALUES
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
INSERT IGNORE INTO donation_requests (applicant_name, phone, address, request_type, item_requested, description, family_members, status) VALUES
('أم محمد', '01012345678', 'القاهرة، شبرا - شارع الجمهورية', 'أجهزة كهربائية', 'ثلاجة للأسرة', 'الثلاجة الحالية معطوبة منذ ٦ أشهر وعندي ٥ أطفال صغار', 6, 'pending'),
('السيد أحمد علي', '01198765432', 'الجيزة، إمبابة - شارع السودان', 'تجهيز عروسة', 'غرفة نوم كاملة وتجهيزات المطبخ', 'ابنتي على وشك الزواج ولا نقدر على تأمين التجهيزات', 4, 'pending'),
('فاطمة حسن', '01234567890', 'الإسكندرية، العجمي', 'أثاث', 'سرير وخزانة ملابس', 'أنا أرملة ومعي أطفال ونحتاج أثاث أساسي', 3, 'approved'),
('عم سيد', '01567891234', 'الفيوم، إبشواي', 'أجهزة كهربائية', 'غسالة', 'نحتاج غسالة لعائلة مكونة من ٧ أفراد', 7, 'on_the_way'),
('مريم إبراهيم', '01099887766', 'أسيوط، المنصورة', 'تجهيز عروسة', 'كامل تجهيزات العروسة', 'يتيمة وتحتاج مساعدة كاملة', 2, 'rejected');


-- =============================================
-- جدول تصنيفات التبرعات العينية (schema الأكاديمي)
-- =============================================
CREATE TABLE IF NOT EXISTS item_categories (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(80) NOT NULL UNIQUE,
    description TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO item_categories (name, description) VALUES
('ملابس','ملابس وأحذية'),('طعام','مواد غذائية'),
('أثاث','أثاث منزلي'),('كتب','كتب ومراجع'),
('أجهزة','أجهزة كهربائية'),('أدوية','مستلزمات طبية'),
('لوازم مدرسية','أدوات كتابية'),('أخرى','أصناف متنوعة');

-- =============================================
-- جدول طلبات التبرع العينية (requests)
-- =============================================
CREATE TABLE IF NOT EXISTS in_kind_requests (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    beneficiary_id INT NOT NULL,
    category_id    INT NOT NULL,
    title          VARCHAR(200) NOT NULL,
    description    TEXT DEFAULT NULL,
    quantity       INT DEFAULT 1,
    status         ENUM('pending','matched','fulfilled') DEFAULT 'pending',
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (beneficiary_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id)    REFERENCES item_categories(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- جدول التبرعات العينية (in_kind_donations)
-- =============================================
CREATE TABLE IF NOT EXISTS in_kind_donations (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    donor_id    INT NOT NULL,
    category_id INT NOT NULL,
    request_id  INT DEFAULT NULL,
    description TEXT DEFAULT NULL,
    quantity    INT DEFAULT 1,
    status      ENUM('available','matched','delivered') DEFAULT 'available',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id)    REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES item_categories(id),
    FOREIGN KEY (request_id)  REFERENCES in_kind_requests(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- جدول التوصيل (deliveries)
-- =============================================
CREATE TABLE IF NOT EXISTS deliveries (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    donation_id      INT NOT NULL,
    pickup_address   TEXT NOT NULL,
    delivery_address TEXT NOT NULL,
    carrier_name     VARCHAR(100) DEFAULT NULL,
    tracking_code    VARCHAR(100) DEFAULT NULL,
    status           ENUM('pending','in_transit','delivered') DEFAULT 'pending',
    delivered_at     DATETIME DEFAULT NULL,
    FOREIGN KEY (donation_id) REFERENCES in_kind_donations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- جدول التبرعات المالية
-- =============================================
CREATE TABLE IF NOT EXISTS donations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tx_id VARCHAR(20) NOT NULL UNIQUE,
    user_id INT DEFAULT NULL,
    donor_name VARCHAR(100) NOT NULL,
    donor_email VARCHAR(100),
    donor_phone VARCHAR(20),
    campaign_id INT DEFAULT NULL,
    platform_campaign_id INT DEFAULT NULL,
    charity_id INT DEFAULT NULL,
    campaign_title VARCHAR(255),
    charity_name VARCHAR(100),
    amount DECIMAL(10,2) NOT NULL,
    payment_method ENUM('بطاقة','محفظة إلكترونية','تحويل بنكي','نقداً') DEFAULT 'بطاقة',
    status ENUM('completed','pending','failed') DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- بيانات تجريبية للتبرعات
INSERT IGNORE INTO donations (tx_id,donor_name,donor_email,donor_phone,campaign_title,charity_name,amount,payment_method,status,created_at) VALUES
('TX-10231','أحمد محمد علي','ahmed@example.com','+20 100 123 4567','تجهيز وحدة غسيل كلوي','جمعية رعاية المرضى',1500,'بطاقة','completed','2025-05-06 14:32:00'),
('TX-10230','فاطمة الزهراء','fatima@example.com','+20 101 234 5678','كسوة العيد للأيتام','دار الأيتام',500,'محفظة إلكترونية','completed','2025-05-06 11:08:00'),
('TX-10229','يوسف إبراهيم','youssef@example.com','+20 102 345 6789','إفطار صائم','منصة العطاء',250,'بطاقة','completed','2025-05-05 19:55:00'),
('TX-10228','مريم سعيد','mariam@example.com','+20 103 456 7890','سداد ديون الغارمات','جمعية المودة',3000,'تحويل بنكي','pending','2025-05-05 09:12:00'),
('TX-10227','خالد عبد الرحمن','khaled@example.com','+20 104 567 8901','تجهيز وحدة غسيل كلوي','جمعية رعاية المرضى',5000,'بطاقة','completed','2025-05-04 22:01:00'),
('TX-10226','نور الهدى','nour@example.com','+20 105 678 9012','مشروع الإسكان','منصة العطاء',750,'محفظة إلكترونية','failed','2025-05-04 16:44:00'),
('TX-10225','عمر شريف','omar@example.com','+20 106 789 0123','علاج طارئ','جمعية رعاية المرضى',2200,'بطاقة','completed','2025-05-04 10:20:00'),
('TX-10224','هدى مصطفى','hoda@example.com','+20 107 890 1234','كفالة يتيم','دار الأيتام',600,'تحويل بنكي','completed','2025-05-03 13:30:00'),
('TX-10223','سامي حسن','sami@example.com','+20 108 901 2345','منح دراسية','صندوق الطلاب',1800,'بطاقة','completed','2025-05-02 17:10:00'),
('TX-10222','رانيا عادل','rania@example.com','+20 109 012 3456','كسوة الشتاء','منصة العطاء',900,'محفظة إلكترونية','completed','2025-05-01 09:00:00');


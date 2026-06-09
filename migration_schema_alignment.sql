-- ================================================================
-- Migration: محاذاة قاعدة البيانات مع الـ schema الأكاديمي
-- شغّل هذا الملف مرة واحدة في phpMyAdmin
-- ================================================================

-- 1. إضافة الأعمدة الناقصة لجدول users
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS phone   VARCHAR(20) DEFAULT NULL AFTER email,
    ADD COLUMN IF NOT EXISTS address TEXT DEFAULT NULL        AFTER phone,
    ADD COLUMN IF NOT EXISTS status  ENUM('active','suspended') DEFAULT 'active' AFTER address;

-- 2. إضافة الأعمدة الناقصة لجدول charities
ALTER TABLE charities
    ADD COLUMN IF NOT EXISTS admin_id INT DEFAULT NULL        AFTER id,
    ADD COLUMN IF NOT EXISTS phone    VARCHAR(20) DEFAULT NULL AFTER description,
    ADD COLUMN IF NOT EXISTS address  TEXT DEFAULT NULL        AFTER phone,
    ADD COLUMN IF NOT EXISTS status   ENUM('active','inactive') DEFAULT 'active' AFTER address;

-- 3. جدول item_categories (تصنيفات التبرعات العينية - منفصل عن المخزن)
CREATE TABLE IF NOT EXISTS item_categories (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(80) NOT NULL UNIQUE,
    description TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO item_categories (name, description) VALUES
('ملابس',    'ملابس وأحذية جديدة أو نظيفة'),
('طعام',     'مواد غذائية وعلب معلبة'),
('أثاث',     'أثاث منزلي وإكسسوارات'),
('كتب',      'كتب مدرسية وقصص أطفال'),
('أجهزة',   'أجهزة كهربائية وإلكترونية'),
('أدوية',   'أدوية ومستلزمات طبية'),
('لوازم مدرسية', 'حقائب وأدوات كتابية'),
('أخرى',    'أصناف متنوعة أخرى');

-- 4. جدول requests (طلبات التبرع العينية من المستفيدين)
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

-- 5. جدول donations العيني (منفصل عن جدول donations المالي الموجود)
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

-- 6. جدول deliveries (تتبع التوصيل)
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

-- 7. Indexes الموصى بها في الـ document
CREATE INDEX IF NOT EXISTS idx_users_role           ON users(role);
CREATE INDEX IF NOT EXISTS idx_inkind_donor_status  ON in_kind_donations(donor_id, status);
CREATE INDEX IF NOT EXISTS idx_inkind_cat           ON in_kind_donations(category_id);
CREATE INDEX IF NOT EXISTS idx_requests_ben_status  ON in_kind_requests(beneficiary_id, status);
CREATE INDEX IF NOT EXISTS idx_requests_cat         ON in_kind_requests(category_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_status    ON deliveries(status);

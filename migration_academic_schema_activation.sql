-- ============================================================
-- Migration: تفعيل الـ Schema الأكاديمي في منصة العطاء
-- يُشغَّل مرة واحدة على قاعدة بيانات ataa_platform
-- ============================================================

USE ataa_platform;

-- 1. إضافة admin_note لـ in_kind_requests (للتوافق مع الـ UI)
ALTER TABLE in_kind_requests
    ADD COLUMN IF NOT EXISTS admin_note TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- 2. السماح لـ in_kind_donations بقبول donor_id من users
--    (الأدمن يُسجّل تبرعات إدارية باسم المنصة)
--    نضيف صف للمنصة في users إذا لم يوجد
INSERT IGNORE INTO users (id, username, password_hash, full_name, role, status)
VALUES (0, 'platform_admin', 'N/A', 'منصة العطاء', 'admin', 'active');

-- 3. تأكد أن item_categories فيها البيانات
INSERT IGNORE INTO item_categories (name, description) VALUES
('ملابس',         'ملابس وأحذية'),
('طعام',          'مواد غذائية'),
('أثاث',          'أثاث منزلي'),
('كتب',           'كتب ومراجع'),
('أجهزة كهربائية','أجهزة كهربائية'),
('أدوية',         'مستلزمات طبية'),
('لوازم مدرسية',  'أدوات كتابية'),
('أخرى',          'أصناف متنوعة');

-- 4. بيانات تجريبية: مستفيد تجريبي
INSERT IGNORE INTO users (username, password_hash, full_name, role, phone, status)
VALUES ('beneficiary_test', '$2b$12$demohashedpassword123', 'مستفيد تجريبي', 'beneficiary', '01012345678', 'active');

-- 5. بيانات تجريبية: طلبات عينية
INSERT IGNORE INTO in_kind_requests (beneficiary_id, category_id, title, description, quantity, status)
SELECT u.id, ic.id, 'ملابس شتوية للأطفال', 'عائلة مكونة من 4 أطفال تحتاج ملابس شتوية', 4, 'pending'
FROM users u, item_categories ic
WHERE u.username='beneficiary_test' AND ic.name='ملابس'
LIMIT 1;

SELECT 'Migration applied successfully' AS result;

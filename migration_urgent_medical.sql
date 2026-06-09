-- ============================================================
-- Migration: إضافة حالة طبية عاجلة + تأكيد الاستلام
-- ============================================================

-- 1. إضافة عمود is_urgent لجدول donation_requests
ALTER TABLE donation_requests
    ADD COLUMN IF NOT EXISTS is_urgent TINYINT(1) DEFAULT 0 COMMENT 'حالة طبية عاجلة';

-- 2. إضافة عمود received_at لتأكيد الاستلام
ALTER TABLE donation_requests
    ADD COLUMN IF NOT EXISTS received_at TIMESTAMP NULL DEFAULT NULL COMMENT 'وقت تأكيد الاستلام';

-- 3. إضافة status جديد 'received' في الـ ENUM
ALTER TABLE donation_requests
    MODIFY COLUMN status ENUM('pending','approved','rejected','final_rejected','on_the_way','received') DEFAULT 'pending';

-- 4. إضافة index على is_urgent لسرعة الاستعلام
ALTER TABLE donation_requests
    ADD INDEX IF NOT EXISTS idx_urgent (is_urgent, status);

-- 5. إضافة is_urgent لجدول platform_campaigns
ALTER TABLE platform_campaigns
    ADD COLUMN IF NOT EXISTS is_urgent TINYINT(1) DEFAULT 0 COMMENT 'حملة عاجلة';

ALTER TABLE platform_campaigns
    ADD INDEX IF NOT EXISTS idx_pc_urgent (is_urgent, status);

-- 6. إضافة أعمدة reset password
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS reset_code VARCHAR(10) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS reset_expires DATETIME DEFAULT NULL;

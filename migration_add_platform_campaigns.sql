-- ================================================
-- Migration: إضافة جدول حملات المنصة ومنع التكرار
-- شغّل هذا الملف لو عندك قاعدة بيانات موجودة
-- ================================================

USE ataa_platform;

-- 1. جدول حملات منصة العطاء
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. منع تكرار طلبات التبرع (نفس الهاتف + نفس الصنف في حالة نشطة)

-- أولاً: إزالة الـ unique key لو موجودة من قبل (تجنب التعارض)
SET @exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE table_schema = DATABASE()
      AND table_name = 'donation_requests'
      AND index_name = 'unique_pending_request'
);
SET @sql := IF(@exists > 0,
    'ALTER TABLE donation_requests DROP INDEX unique_pending_request',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ثانياً: حذف السجلات المكررة — نحتفظ بأقدم واحدة فقط لكل (phone, item_requested, status)
DELETE dr FROM donation_requests dr
INNER JOIN donation_requests dr2
    ON  dr.phone          = dr2.phone
    AND dr.item_requested = dr2.item_requested
    AND dr.status         = dr2.status
    AND dr.id             > dr2.id;

-- ثالثاً: إضافة الـ unique key بعد ما تأكدنا إن مفيش duplicates
ALTER TABLE donation_requests
ADD UNIQUE KEY unique_pending_request (phone, item_requested(50), status);

-- 3. بيانات تجريبية لحملات المنصة
INSERT IGNORE INTO platform_campaigns (title, description, goal_amount, category, status, created_by) VALUES
('تجهيز وحدة غسيل كلوي', 'توفير أجهزة غسيل كلوي لمستشفى قصر العيني لخدمة المرضى المحتاجين يومياً.', 473000, 'صحة', 'active', 'admin'),
('سداد ديون غارمات', 'مساعدة الأسر المحتاجة في سداد ديونها وإخراجها من ضائقتها المالية.', 120000, 'غارمات', 'active', 'admin'),
('وصلات مياه للقرى', 'توصيل مياه الشرب النقية للقرى المحرومة في محافظة الفيوم.', 115000, 'بنية تحتية', 'active', 'admin');

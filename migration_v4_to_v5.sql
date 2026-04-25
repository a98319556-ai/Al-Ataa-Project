-- =============================================
-- Migration: v4 → v5 (شغّل هذا فقط لو عندك قاعدة بيانات قديمة)
-- =============================================

-- جدول طلبات التبرع (لو مش موجود)
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

-- بيانات تجريبية (اختياري)
INSERT IGNORE INTO donation_requests (applicant_name, phone, address, request_type, item_requested, description, family_members, status) VALUES
('أم محمد', '01012345678', 'القاهرة، شبرا', 'أجهزة كهربائية', 'ثلاجة', 'الثلاجة معطوبة منذ 6 أشهر', 6, 'pending'),
('أحمد علي', '01198765432', 'الجيزة، إمبابة', 'تجهيز عروسة', 'غرفة نوم وتجهيزات مطبخ', 'ابنتي على وشك الزواج', 4, 'pending'),
('فاطمة حسن', '01234567890', 'الإسكندرية', 'أثاث', 'سرير وخزانة', 'أرملة مع أطفال', 3, 'approved'),
('عم سيد', '01567891234', 'الفيوم', 'أجهزة كهربائية', 'غسالة', 'عائلة من 7 أفراد', 7, 'on_the_way'),
('مريم إبراهيم', '01099887766', 'أسيوط', 'تجهيز عروسة', 'كامل تجهيزات العروسة', 'يتيمة تحتاج مساعدة', 2, 'rejected');

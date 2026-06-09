-- =============================================
-- Migration: جدول request_items
-- يربط طلبات التبرع بالأصناف الصادرة من المخزن
-- =============================================

CREATE TABLE IF NOT EXISTS request_items (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    request_id   INT NOT NULL,
    item_id      INT NOT NULL,
    assigned_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES donation_requests(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id)    REFERENCES inventory(id)         ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- إضافة action جديد في history لتمييز الأصناف الصادرة للمستفيدين
-- (history.action بيقبل 'assign_to_request' بجانب القديمة)
ALTER TABLE history
    MODIFY COLUMN action ENUM('add','deliver','delete','returned','available','assign_to_request') NOT NULL;

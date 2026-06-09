-- إضافة عمود collected_amount و status لجدول campaigns
ALTER TABLE campaigns
    ADD COLUMN IF NOT EXISTS collected_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS status ENUM('active','completed','paused') DEFAULT 'active';

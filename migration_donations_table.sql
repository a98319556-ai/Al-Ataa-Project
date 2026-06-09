-- تشغيل هذا الملف مرة واحدة في phpMyAdmin
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

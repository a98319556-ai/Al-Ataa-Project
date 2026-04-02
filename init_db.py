import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

cur.executescript("""

CREATE TABLE admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
);

CREATE TABLE charities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    image TEXT,
    fields TEXT
);

CREATE TABLE campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    charity_id INTEGER,
    title TEXT,
    description TEXT,
    goal_amount REAL,
    category TEXT
);

INSERT INTO admins (username, password) VALUES ('admin', 'admin123');

""")

conn.commit()
conn.close()

print("Database Created ✅")
import os
import sqlite3

try:
    import psycopg2
except ImportError:
    psycopg2 = None

DB_NAME = "budget.db"
DATABASE_URL = os.environ.get("DATABASE_URL")

class Database:
    def __init__(self):
        self.is_postgres = bool(DATABASE_URL and psycopg2)
        if self.is_postgres:
            self.conn = psycopg2.connect(DATABASE_URL)
            self.conn.autocommit = True
            self.cursor = self.conn.cursor()
        else:
            self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            self.cursor = self.conn.cursor()
        self.create_tables()

    def execute(self, query, params=()):
        if self.is_postgres:
            query = query.replace("?", "%s")
            if "INTEGER PRIMARY KEY AUTOINCREMENT" in query:
                query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            if "BOOLEAN DEFAULT 0" in query:
                query = query.replace("BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE")
        
        self.cursor.execute(query, params)
        if not self.is_postgres:
            self.conn.commit()

    def create_tables(self):
        self.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        self.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                image_path TEXT,
                is_recurring BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        if self.is_postgres:
            self.cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='expenses'")
            columns = [info[0] for info in self.cursor.fetchall()]
        else:
            self.cursor.execute("PRAGMA table_info(expenses)")
            columns = [info[1] for info in self.cursor.fetchall()]
            
        if "image_path" not in columns:
            self.execute("ALTER TABLE expenses ADD COLUMN image_path TEXT")
        if "is_recurring" not in columns:
            self.execute("ALTER TABLE expenses ADD COLUMN is_recurring BOOLEAN DEFAULT 0")

    def register_user(self, username, password):
        try:
            self.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            return True
        except Exception: # Catch IntegrityError from either library
            return False

    def login_user(self, username, password):
        self.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, password))
        result = self.cursor.fetchone()
        if result:
            return result[0]
        return None

    def update_password(self, username, new_password):
        self.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not self.cursor.fetchone():
            return False
        self.execute("UPDATE users SET password = ? WHERE username = ?", (new_password, username))
        return True

    def add_expense(self, user_id, date, amount, category, name, image_path=None, is_recurring=False):
        if self.is_postgres:
            self.cursor.execute(
                "INSERT INTO expenses (user_id, date, amount, category, name, image_path, is_recurring) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (user_id, date, amount, category, name, image_path, is_recurring)
            )
            return self.cursor.fetchone()[0]
        else:
            self.execute("INSERT INTO expenses (user_id, date, amount, category, name, image_path, is_recurring) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (user_id, date, amount, category, name, image_path, is_recurring))
            return self.cursor.lastrowid

    def get_expenses_by_month(self, user_id, year, month):
        month_str = f"{year:04d}-{month:02d}"
        self.execute("SELECT date, amount, category FROM expenses WHERE user_id = ? AND date LIKE ?", (user_id, f"{month_str}%"))
        return self.cursor.fetchall()

    def get_expenses_by_date(self, user_id, date):
        query = "SELECT id, amount, category, name, CASE WHEN image_path IS NOT NULL AND image_path != '' THEN 1 ELSE 0 END as has_image, is_recurring FROM expenses WHERE user_id = ? AND date = ?"
        self.execute(query, (user_id, date))
        return self.cursor.fetchall()

    def get_expenses_by_category(self, user_id, category):
        query = "SELECT id, date, amount, name, CASE WHEN image_path IS NOT NULL AND image_path != '' THEN 1 ELSE 0 END as has_image, is_recurring FROM expenses WHERE user_id = ? AND category = ? ORDER BY date DESC"
        self.execute(query, (user_id, category))
        return self.cursor.fetchall()

    def update_expense(self, expense_id, user_id, date, amount, category, name, is_recurring=False):
        self.execute("UPDATE expenses SET date = ?, amount = ?, category = ?, name = ?, is_recurring = ? WHERE id = ? AND user_id = ?",
                            (date, amount, category, name, is_recurring, expense_id, user_id))

    def delete_expense(self, expense_id, user_id):
        self.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))

    def get_receipt(self, expense_id, user_id):
        self.execute("SELECT image_path FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
        result = self.cursor.fetchone()
        return result[0] if result else None

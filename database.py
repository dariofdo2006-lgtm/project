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
        
        self.execute('''
            CREATE TABLE IF NOT EXISTS calculator_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                data TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, type)
            )
        ''')
        
        self.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                currency_symbol TEXT DEFAULT '₹',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        self.execute('''
            CREATE TABLE IF NOT EXISTS custom_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                cat_type TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, name, cat_type)
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
            if self.is_postgres:
                self.cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s) RETURNING id", (username, password))
                user_id = self.cursor.fetchone()[0]
            else:
                self.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                user_id = self.cursor.lastrowid
            
            self.seed_default_categories(user_id)
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
        query = "SELECT id, date, amount, category, name, CASE WHEN image_path IS NOT NULL AND image_path != '' THEN 1 ELSE 0 END as has_image, is_recurring FROM expenses WHERE user_id = ? AND category = ? ORDER BY date DESC"
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

    def save_calculator_state(self, user_id, calc_type, data):
        if self.is_postgres:
            query = "INSERT INTO calculator_data (user_id, type, data) VALUES (%s, %s, %s) ON CONFLICT(user_id, type) DO UPDATE SET data=EXCLUDED.data"
        else:
            query = "REPLACE INTO calculator_data (user_id, type, data) VALUES (?, ?, ?)"
        self.execute(query, (user_id, calc_type, data))

    def get_calculator_state(self, user_id, calc_type):
        self.execute("SELECT data FROM calculator_data WHERE user_id = ? AND type = ?", (user_id, calc_type))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def get_settings(self, user_id):
        self.execute("SELECT currency_symbol FROM user_settings WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else "₹"
        
    def update_settings(self, user_id, currency):
        if self.is_postgres:
            query = "INSERT INTO user_settings (user_id, currency_symbol) VALUES (%s, %s) ON CONFLICT(user_id) DO UPDATE SET currency_symbol=EXCLUDED.currency_symbol"
        else:
            query = "REPLACE INTO user_settings (user_id, currency_symbol) VALUES (?, ?)"
        self.execute(query, (user_id, currency))

    def seed_default_categories(self, user_id):
        expense_cats = ["Rent", "Grocery", "Food", "Water", "Electricity", "Transportation", "Clothing", "Online Shopping", "Hospital", "Education", "Insurance", "Entertainment", "Credit Card", "Emergency Fund", "Investment", "Other"]
        income_cats = ["Wages", "Interest/dividends", "Miscellaneous", "Gift"]
        for cat in expense_cats:
            self.add_category(user_id, cat, 'expense')
        for cat in income_cats:
            self.add_category(user_id, cat, 'income')

    def get_categories(self, user_id, cat_type=None):
        self.execute("SELECT count(*) FROM custom_categories WHERE user_id = ?", (user_id,))
        if self.cursor.fetchone()[0] == 0:
            self.seed_default_categories(user_id)
            
        if cat_type:
            self.execute("SELECT name FROM custom_categories WHERE user_id = ? AND cat_type = ? ORDER BY id", (user_id, cat_type))
        else:
            self.execute("SELECT name, cat_type FROM custom_categories WHERE user_id = ? ORDER BY id", (user_id,))
        return [row[0] for row in self.cursor.fetchall()] if cat_type else self.cursor.fetchall()

    def add_category(self, user_id, name, cat_type):
        try:
            if self.is_postgres:
                self.cursor.execute("INSERT INTO custom_categories (user_id, name, cat_type) VALUES (%s, %s, %s)", (user_id, name, cat_type))
            else:
                self.execute("INSERT INTO custom_categories (user_id, name, cat_type) VALUES (?, ?, ?)", (user_id, name, cat_type))
            return True
        except Exception:
            return False

    def delete_category(self, user_id, name, cat_type):
        self.execute("DELETE FROM custom_categories WHERE user_id = ? AND name = ? AND cat_type = ?", (user_id, name, cat_type))

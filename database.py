import sqlite3

DB_NAME = "budget.db"

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                image_path TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        # Migration for returning users (add image_path if it doesn't exist)
        self.cursor.execute("PRAGMA table_info(expenses)")
        columns = [info[1] for info in self.cursor.fetchall()]
        if "image_path" not in columns:
            self.cursor.execute("ALTER TABLE expenses ADD COLUMN image_path TEXT")

        self.conn.commit()

    def register_user(self, username, password):
        try:
            self.cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def login_user(self, username, password):
        self.cursor.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, password))
        result = self.cursor.fetchone()
        if result:
            return result[0]
        return None

    def update_password(self, username, new_password):
        self.cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not self.cursor.fetchone():
            return False
        self.cursor.execute("UPDATE users SET password = ? WHERE username = ?", (new_password, username))
        self.conn.commit()
        return True

    def add_expense(self, user_id, date, amount, category, name, image_path=None):
        self.cursor.execute("INSERT INTO expenses (user_id, date, amount, category, name, image_path) VALUES (?, ?, ?, ?, ?, ?)",
                            (user_id, date, amount, category, name, image_path))
        self.conn.commit()

    def get_expenses_by_month(self, user_id, year, month):
        month_str = f"{year:04d}-{month:02d}"
        self.cursor.execute("SELECT date, amount, category FROM expenses WHERE user_id = ? AND date LIKE ?", (user_id, f"{month_str}%"))
        return self.cursor.fetchall()

    def get_expenses_by_date(self, user_id, date):
        self.cursor.execute("SELECT id, amount, category, name, image_path FROM expenses WHERE user_id = ? AND date = ?", (user_id, date))
        return self.cursor.fetchall()

    def get_expenses_by_category(self, user_id, category):
        self.cursor.execute("SELECT id, date, amount, name, image_path FROM expenses WHERE user_id = ? AND category = ? ORDER BY date DESC", (user_id, category))
        return self.cursor.fetchall()

    def update_expense(self, expense_id, user_id, date, amount, category, name, image_path=None):
        self.cursor.execute("UPDATE expenses SET date = ?, amount = ?, category = ?, name = ?, image_path = ? WHERE id = ? AND user_id = ?",
                            (date, amount, category, name, image_path, expense_id, user_id))
        self.conn.commit()

    def delete_expense(self, expense_id, user_id):
        self.cursor.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
        self.conn.commit()

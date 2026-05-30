import os
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
import calendar

DISABLE_FIREBASE = os.environ.get("DISABLE_FIREBASE", "").lower() in {"1", "true", "yes"}

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    import pymongo
except ImportError:
    pymongo = None

try:
    if DISABLE_FIREBASE:
        raise RuntimeError("Firebase disabled by DISABLE_FIREBASE")
    from firebase_config import db as firestore_db
    from firebase_admin import firestore
    FIREBASE_AVAILABLE = True
except Exception as exc:
    FIREBASE_AVAILABLE = False
    firestore_db = None
    firestore = None
    FIREBASE_INIT_ERROR = exc
else:
    FIREBASE_INIT_ERROR = None

DB_NAME = os.environ.get("SQLITE_DB_NAME", "budget.db")
DATABASE_URL = os.environ.get("DATABASE_URL")
MONGO_URI = os.environ.get("MONGO_URI")
REQUIRE_FIREBASE = os.environ.get("REQUIRE_FIREBASE", "").lower() in {"1", "true", "yes"}

class Database:
    def __init__(self):
        if REQUIRE_FIREBASE and not FIREBASE_AVAILABLE:
            raise RuntimeError(f"Firebase is required but unavailable: {FIREBASE_INIT_ERROR!r}")

        self.is_firebase = FIREBASE_AVAILABLE
        self.is_mongo = bool(MONGO_URI and pymongo and not self.is_firebase)
        self.is_postgres = bool(DATABASE_URL and psycopg2 and not self.is_mongo and not self.is_firebase)
        
        if self.is_firebase:
            self.db = firestore_db
        elif self.is_mongo:
            self.mongo_client = pymongo.MongoClient(MONGO_URI)
            self.db = self.mongo_client.get_default_database(default='budget_calendar')
            self.seed_mongo_indexes()
        elif self.is_postgres:
            self.conn = psycopg2.connect(DATABASE_URL)
            self.conn.autocommit = True
            self.cursor = self.conn.cursor()
            self.create_tables()
        else:
            self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.create_tables()

    def backend_name(self):
        if self.is_firebase:
            return "firebase"
        if self.is_mongo:
            return "mongo"
        if self.is_postgres:
            return "postgres"
        return "sqlite"

    def get_next_sequence(self, name):
        if self.is_firebase:
            transaction = self.db.transaction()
            counter_ref = self.db.collection('counters').document(name)
            
            @firestore.transactional
            def increment_counter(transaction, counter_ref):
                snapshot = counter_ref.get(transaction=transaction)
                if not snapshot.exists:
                    transaction.set(counter_ref, {'seq': 1})
                    return 1
                else:
                    new_seq = snapshot.get('seq') + 1
                    transaction.update(counter_ref, {'seq': new_seq})
                    return new_seq
                    
            return increment_counter(transaction, counter_ref)
        elif self.is_mongo:
            ret = self.db.counters.find_one_and_update(
                {"_id": name},
                {"$inc": {"seq": 1}},
                upsert=True,
                return_document=pymongo.ReturnDocument.AFTER
            )
            return ret["seq"]
        return None

    def seed_mongo_indexes(self):
        self.db.users.create_index("username", unique=True)
        self.db.custom_categories.create_index([("user_id", 1), ("name", 1), ("cat_type", 1)], unique=True)
        self.db.calculator_data.create_index([("user_id", 1), ("type", 1)], unique=True)

    def _same_user_id(self, left, right):
        return str(left) == str(right)

    def _firebase_expense_ref_for_user(self, expense_id, user_id):
        doc_ref = self.db.collection('expenses').document(str(expense_id))
        doc = doc_ref.get()
        if not doc.exists:
            return None

        data = doc.to_dict()
        if not self._same_user_id(data.get("user_id"), user_id):
            return None

        return doc_ref

    def _password_matches(self, stored_password, password):
        try:
            return check_password_hash(stored_password or "", password or "")
        except ValueError:
            return False

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
        hashed_password = generate_password_hash(password)
        try:
            if self.is_firebase:
                # Check if username exists
                users = self.db.collection('users').where("username", "==", username).get()
                if len(users) > 0:
                    return False
                user_id = self.get_next_sequence("user_id")
                self.db.collection('users').document(str(user_id)).set({
                    "id": user_id,
                    "username": username,
                    "password": hashed_password
                })
                self.seed_default_categories(user_id)
                return True
            elif self.is_mongo:
                if self.db.users.find_one({"username": username}):
                    return False
                user_id = self.get_next_sequence("user_id")
                self.db.users.insert_one({
                    "id": user_id,
                    "username": username,
                    "password": hashed_password
                })
                self.seed_default_categories(user_id)
                return True
            elif self.is_postgres:
                self.cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s) RETURNING id", (username, hashed_password))
                user_id = self.cursor.fetchone()[0]
                self.seed_default_categories(user_id)
                return True
            else:
                self.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
                user_id = self.cursor.lastrowid
                self.seed_default_categories(user_id)
                return True
        except Exception as e: # Catch errors and log them
            import traceback
            traceback.print_exc()
            return False

    def login_user(self, username, password):
        if self.is_firebase:
            users = self.db.collection('users').where("username", "==", username).get()
            if not users:
                return None
            user = users[0].to_dict()
            stored_password = user.get("password", "")
                
            user_id = user.get("id", users[0].id)
            # Try to cast user_id to int if it looks like one, to match sqlite behavior
            if isinstance(user_id, str) and user_id.isdigit():
                user_id = int(user_id)

            if self._password_matches(stored_password, password):
                return user_id
            return None
        elif self.is_mongo:
            user = self.db.users.find_one({"username": username})
            if not user:
                return None
            stored_password = user.get("password", "")
            if self._password_matches(stored_password, password):
                return user["id"]
            return None

        self.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        result = self.cursor.fetchone()
        if not result:
            return None
        user_id, stored_password = result[0], result[1]
        if self._password_matches(stored_password, password):
            return user_id
        return None

    def update_password(self, username, new_password):
        hashed_password = generate_password_hash(new_password)
        if self.is_firebase:
            users = self.db.collection('users').where("username", "==", username).get()
            if not users:
                return False
            self.db.collection('users').document(users[0].id).update({"password": hashed_password})
            return True
        elif self.is_mongo:
            result = self.db.users.update_one({"username": username}, {"$set": {"password": hashed_password}})
            return result.modified_count > 0

        self.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not self.cursor.fetchone():
            return False
        self.execute("UPDATE users SET password = ? WHERE username = ?", (hashed_password, username))
        return True

    def add_expense(self, user_id, date, amount, category, name, image_path=None, is_recurring=False):
        if self.is_firebase:
            expense_id = self.get_next_sequence("expense_id")
            self.db.collection('expenses').document(str(expense_id)).set({
                "id": expense_id,
                "user_id": user_id,
                "date": date,
                "amount": amount,
                "category": category,
                "name": name,
                "image_path": image_path,
                "is_recurring": is_recurring
            })
            return expense_id
        elif self.is_mongo:
            expense_id = self.get_next_sequence("expense_id")
            self.db.expenses.insert_one({
                "id": expense_id,
                "user_id": user_id,
                "date": date,
                "amount": amount,
                "category": category,
                "name": name,
                "image_path": image_path,
                "is_recurring": is_recurring
            })
            return expense_id

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
        if self.is_firebase:
            _, last_day = calendar.monthrange(year, month)
            start_date = f"{year:04d}-{month:02d}-01"
            end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
            docs = self.db.collection('expenses').where("user_id", "==", user_id).where("date", ">=", start_date).where("date", "<=", end_date).stream()
            expenses = [doc.to_dict() for doc in docs]
            return [(e["date"], e["amount"], e["category"]) for e in expenses]

        month_str = f"{year:04d}-{month:02d}"
        if self.is_mongo:
            expenses = self.db.expenses.find({
                "user_id": user_id,
                "date": {"$regex": f"^{month_str}"}
            })
            return [(e["date"], e["amount"], e["category"]) for e in expenses]

        self.execute("SELECT date, amount, category FROM expenses WHERE user_id = ? AND date LIKE ?", (user_id, f"{month_str}%"))
        return self.cursor.fetchall()

    def get_expenses_by_date(self, user_id, date):
        if self.is_firebase:
            docs = self.db.collection('expenses').where("user_id", "==", user_id).where("date", "==", date).stream()
            expenses = [doc.to_dict() for doc in docs]
            return [(e["id"], e["date"], e["amount"], e["category"], e["name"], 1 if e.get("image_path") else 0, e.get("is_recurring", False)) for e in expenses]
        elif self.is_mongo:
            expenses = self.db.expenses.find({"user_id": user_id, "date": date})
            return [(e["id"], e["date"], e["amount"], e["category"], e["name"], 1 if e.get("image_path") else 0, e.get("is_recurring", False)) for e in expenses]

        query = "SELECT id, date, amount, category, name, CASE WHEN image_path IS NOT NULL AND image_path != '' THEN 1 ELSE 0 END as has_image, is_recurring FROM expenses WHERE user_id = ? AND date = ?"
        self.execute(query, (user_id, date))
        return self.cursor.fetchall()

    def get_expenses_by_month_detailed(self, user_id, year, month):
        if self.is_firebase:
            _, last_day = calendar.monthrange(year, month)
            start_date = f"{year:04d}-{month:02d}-01"
            end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
            docs = self.db.collection('expenses').where("user_id", "==", user_id).where("date", ">=", start_date).where("date", "<=", end_date).stream()
            expenses = sorted([doc.to_dict() for doc in docs], key=lambda x: x.get('date', ''), reverse=True)
            return [
                (e["id"], e["date"], e["amount"], e["category"], e["name"], 1 if e.get("image_path") else 0, e.get("is_recurring", False))
                for e in expenses
            ]

        month_str = f"{year:04d}-{month:02d}"
        if self.is_mongo:
            expenses = self.db.expenses.find({
                "user_id": user_id,
                "date": {"$regex": f"^{month_str}"}
            }).sort("date", pymongo.DESCENDING)
            return [
                (e["id"], e["date"], e["amount"], e["category"], e["name"], 1 if e.get("image_path") else 0, e.get("is_recurring", False))
                for e in expenses
            ]

        query = "SELECT id, date, amount, category, name, CASE WHEN image_path IS NOT NULL AND image_path != '' THEN 1 ELSE 0 END as has_image, is_recurring FROM expenses WHERE user_id = ? AND date LIKE ? ORDER BY date DESC, id DESC"
        self.execute(query, (user_id, f"{month_str}%"))
        return self.cursor.fetchall()

    def get_expenses_by_category(self, user_id, category):
        if self.is_firebase:
            docs = self.db.collection('expenses').where("user_id", "==", user_id).where("category", "==", category).stream()
            expenses = [doc.to_dict() for doc in docs]
            expenses.sort(key=lambda x: x.get('date', ''), reverse=True)
            return [(e["id"], e["date"], e["amount"], e["category"], e["name"], 1 if e.get("image_path") else 0, e.get("is_recurring", False)) for e in expenses]
        elif self.is_mongo:
            expenses = self.db.expenses.find({"user_id": user_id, "category": category}).sort("date", pymongo.DESCENDING)
            return [(e["id"], e["date"], e["amount"], e["category"], e["name"], 1 if e.get("image_path") else 0, e.get("is_recurring", False)) for e in expenses]

        query = "SELECT id, date, amount, category, name, CASE WHEN image_path IS NOT NULL AND image_path != '' THEN 1 ELSE 0 END as has_image, is_recurring FROM expenses WHERE user_id = ? AND category = ? ORDER BY date DESC"
        self.execute(query, (user_id, category))
        return self.cursor.fetchall()

    def update_expense(self, expense_id, user_id, date, amount, category, name, is_recurring=False):
        if self.is_firebase:
            doc_ref = self._firebase_expense_ref_for_user(expense_id, user_id)
            if not doc_ref:
                return False
            doc_ref.update({
                "date": date,
                "amount": amount,
                "category": category,
                "name": name,
                "is_recurring": is_recurring
            })
            return True
        elif self.is_mongo:
            result = self.db.expenses.update_one(
                {"id": expense_id, "user_id": user_id},
                {"$set": {
                    "date": date,
                    "amount": amount,
                    "category": category,
                    "name": name,
                    "is_recurring": is_recurring
                }}
            )
            return result.matched_count > 0

        self.execute("UPDATE expenses SET date = ?, amount = ?, category = ?, name = ?, is_recurring = ? WHERE id = ? AND user_id = ?",
                            (date, amount, category, name, is_recurring, expense_id, user_id))
        return self.cursor.rowcount > 0

    def delete_expense(self, expense_id, user_id):
        if self.is_firebase:
            doc_ref = self._firebase_expense_ref_for_user(expense_id, user_id)
            if not doc_ref:
                return False
            doc_ref.delete()
            return True
        elif self.is_mongo:
            result = self.db.expenses.delete_one({"id": expense_id, "user_id": user_id})
            return result.deleted_count > 0

        self.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
        return self.cursor.rowcount > 0

    def get_receipt(self, expense_id, user_id):
        if self.is_firebase:
            doc = self.db.collection('expenses').document(str(expense_id)).get()
            if doc.exists and doc.to_dict().get("user_id") == user_id:
                return doc.to_dict().get("image_path")
            return None
        elif self.is_mongo:
            expense = self.db.expenses.find_one({"id": expense_id, "user_id": user_id})
            return expense.get("image_path") if expense else None

        self.execute("SELECT image_path FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def save_calculator_state(self, user_id, calc_type, data):
        if self.is_firebase:
            doc_id = f"{user_id}_{calc_type}"
            self.db.collection('calculator_data').document(doc_id).set({
                "user_id": user_id,
                "type": calc_type,
                "data": data
            })
            return
        elif self.is_mongo:
            self.db.calculator_data.update_one(
                {"user_id": user_id, "type": calc_type},
                {"$set": {"data": data}},
                upsert=True
            )
            return

        if self.is_postgres:
            query = "INSERT INTO calculator_data (user_id, type, data) VALUES (%s, %s, %s) ON CONFLICT(user_id, type) DO UPDATE SET data=EXCLUDED.data"
        else:
            query = "REPLACE INTO calculator_data (user_id, type, data) VALUES (?, ?, ?)"
        self.execute(query, (user_id, calc_type, data))

    def get_calculator_state(self, user_id, calc_type):
        if self.is_firebase:
            doc_id = f"{user_id}_{calc_type}"
            doc = self.db.collection('calculator_data').document(doc_id).get()
            return doc.to_dict().get("data") if doc.exists else None
        elif self.is_mongo:
            state = self.db.calculator_data.find_one({"user_id": user_id, "type": calc_type})
            return state.get("data") if state else None

        self.execute("SELECT data FROM calculator_data WHERE user_id = ? AND type = ?", (user_id, calc_type))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def get_settings(self, user_id):
        if self.is_firebase:
            doc = self.db.collection('user_settings').document(str(user_id)).get()
            return doc.to_dict().get("currency_symbol", "₹") if doc.exists else "₹"
        elif self.is_mongo:
            settings = self.db.user_settings.find_one({"user_id": user_id})
            return settings.get("currency_symbol", "₹") if settings else "₹"

        self.execute("SELECT currency_symbol FROM user_settings WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else "₹"
        
    def update_settings(self, user_id, currency):
        if self.is_firebase:
            self.db.collection('user_settings').document(str(user_id)).set({
                "user_id": user_id,
                "currency_symbol": currency
            })
            return
        elif self.is_mongo:
            self.db.user_settings.update_one(
                {"user_id": user_id},
                {"$set": {"currency_symbol": currency}},
                upsert=True
            )
            return

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
        if self.is_firebase:
            docs = self.db.collection('custom_categories').where("user_id", "==", user_id).stream()
            cats = [doc.to_dict() for doc in docs]
            if len(cats) == 0:
                self.seed_default_categories(user_id)
                docs = self.db.collection('custom_categories').where("user_id", "==", user_id).stream()
                cats = [doc.to_dict() for doc in docs]
                
            cats.sort(key=lambda x: x.get('id', 0))
            if cat_type:
                return [c["name"] for c in cats if c.get("cat_type") == cat_type]
            else:
                return [(c["name"], c["cat_type"]) for c in cats]
        elif self.is_mongo:
            count = self.db.custom_categories.count_documents({"user_id": user_id})
            if count == 0:
                self.seed_default_categories(user_id)
            
            if cat_type:
                cats = self.db.custom_categories.find({"user_id": user_id, "cat_type": cat_type}).sort("_id", 1)
                return [c["name"] for c in cats]
            else:
                cats = self.db.custom_categories.find({"user_id": user_id}).sort("_id", 1)
                return [(c["name"], c["cat_type"]) for c in cats]

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
            if self.is_firebase:
                doc_id = f"{user_id}_{name}_{cat_type}"
                self.db.collection('custom_categories').document(doc_id).set({
                    "user_id": user_id,
                    "name": name,
                    "cat_type": cat_type,
                    "id": self.get_next_sequence("category_id")
                })
                return True
            elif self.is_mongo:
                self.db.custom_categories.update_one(
                    {"user_id": user_id, "name": name, "cat_type": cat_type},
                    {"$set": {"user_id": user_id, "name": name, "cat_type": cat_type}},
                    upsert=True
                )
                return True

            if self.is_postgres:
                self.cursor.execute("INSERT INTO custom_categories (user_id, name, cat_type) VALUES (%s, %s, %s)", (user_id, name, cat_type))
            else:
                self.execute("INSERT INTO custom_categories (user_id, name, cat_type) VALUES (?, ?, ?)", (user_id, name, cat_type))
            return True
        except Exception:
            return False

    def delete_category(self, user_id, name, cat_type):
        if self.is_firebase:
            doc_id = f"{user_id}_{name}_{cat_type}"
            self.db.collection('custom_categories').document(doc_id).delete()
            return
        elif self.is_mongo:
            self.db.custom_categories.delete_one({"user_id": user_id, "name": name, "cat_type": cat_type})
            return

        self.execute("DELETE FROM custom_categories WHERE user_id = ? AND name = ? AND cat_type = ?", (user_id, name, cat_type))

    # --- New Helper Methods to avoid raw SQL in app.py ---

    def get_recurring_expenses(self, user_id, month_str):
        if self.is_firebase:
            year, month = map(int, month_str.split('-'))
            _, last_day = calendar.monthrange(year, month)
            start_date = f"{year:04d}-{month:02d}-01"
            end_date = f"{year:04d}-{month:02d}-{last_day:02d}"

            docs = self.db.collection('expenses').where("user_id", "==", user_id).where("is_recurring", "==", True).where("date", ">=", start_date).where("date", "<=", end_date).stream()
            expenses = [doc.to_dict() for doc in docs]
            return [(e["amount"], e["category"], e["name"], e.get("image_path"), e["date"]) for e in expenses]
        elif self.is_mongo:
            expenses = self.db.expenses.find({
                "user_id": user_id,
                "is_recurring": True,
                "date": {"$regex": f"^{month_str}"}
            })
            return [(e["amount"], e["category"], e["name"], e.get("image_path"), e["date"]) for e in expenses]

        self.execute("SELECT amount, category, name, image_path, date FROM expenses WHERE user_id = ? AND is_recurring = 1 AND date LIKE ?", (user_id, f"{month_str}%"))
        return self.cursor.fetchall()

    def count_recurring_expenses(self, user_id, month_str):
        if self.is_firebase:
            year, month = map(int, month_str.split('-'))
            _, last_day = calendar.monthrange(year, month)
            start_date = f"{year:04d}-{month:02d}-01"
            end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
            
            docs = self.db.collection('expenses').where("user_id", "==", user_id).where("is_recurring", "==", True).where("date", ">=", start_date).where("date", "<=", end_date).stream()
            return sum(1 for _ in docs)
        elif self.is_mongo:
            return self.db.expenses.count_documents({
                "user_id": user_id,
                "is_recurring": True,
                "date": {"$regex": f"^{month_str}"}
            })

        self.execute("SELECT count(*) FROM expenses WHERE user_id = ? AND is_recurring = 1 AND date LIKE ?", (user_id, f"{month_str}%"))
        return self.cursor.fetchone()[0]

    def update_expense_receipt(self, expense_id, user_id, image_path):
        if self.is_firebase:
            doc_ref = self._firebase_expense_ref_for_user(expense_id, user_id)
            if not doc_ref:
                return False
            doc_ref.update({
                "image_path": image_path
            })
            return True
        elif self.is_mongo:
            result = self.db.expenses.update_one(
                {"id": expense_id, "user_id": user_id},
                {"$set": {"image_path": image_path}}
            )
            return result.matched_count > 0

        self.execute("UPDATE expenses SET image_path = ? WHERE id = ? AND user_id = ?", (image_path, expense_id, user_id))
        return self.cursor.rowcount > 0

    def get_all_expenses_for_export(self, user_id):
        if self.is_firebase:
            docs = self.db.collection('expenses').where("user_id", "==", user_id).stream()
            expenses = [doc.to_dict() for doc in docs]
            expenses.sort(key=lambda x: x.get('date', ''), reverse=True)
            return [(e["date"], e["amount"], e["category"], e["name"]) for e in expenses]
        elif self.is_mongo:
            expenses = self.db.expenses.find({"user_id": user_id}).sort("date", pymongo.DESCENDING)
            return [(e["date"], e["amount"], e["category"], e["name"]) for e in expenses]

        self.execute("SELECT date, amount, category, name FROM expenses WHERE user_id = ? ORDER BY date DESC", (user_id,))
        return self.cursor.fetchall()

    def get_expenses_by_date_range(self, user_id, start_date, end_date):
        if self.is_firebase:
            docs = self.db.collection('expenses').where("user_id", "==", user_id).where("date", ">=", start_date).where("date", "<=", end_date).stream()
            expenses = [e.to_dict() for e in docs]
            expenses.sort(key=lambda x: x.get('date', ''), reverse=True)
            return [(e["date"], e["amount"], e["category"], e["name"]) for e in expenses]
        elif self.is_mongo:
            expenses = self.db.expenses.find({
                "user_id": user_id,
                "date": {"$gte": start_date, "$lte": end_date}
            }).sort("date", pymongo.DESCENDING)
            return [(e["date"], e["amount"], e["category"], e["name"]) for e in expenses]

        self.execute("SELECT date, amount, category, name FROM expenses WHERE user_id = ? AND date >= ? AND date <= ? ORDER BY date DESC", (user_id, start_date, end_date))
        return self.cursor.fetchall()

    def search_expenses(self, user_id, query):
        if self.is_firebase:
            docs = self.db.collection('expenses').where("user_id", "==", user_id).stream()
            query_lower = query.lower()
            expenses = []
            for doc in docs:
                data = doc.to_dict()
                if query_lower in data.get('name', '').lower() or query_lower in data.get('category', '').lower():
                    expenses.append(data)
            expenses.sort(key=lambda x: x.get('date', ''), reverse=True)
            return [(e["id"], e["date"], e["amount"], e["category"], e["name"], 1 if e.get("image_path") else 0, e.get("is_recurring", False)) for e in expenses]
        elif self.is_mongo:
            expenses = self.db.expenses.find({
                "user_id": user_id,
                "$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"category": {"$regex": query, "$options": "i"}}
                ]
            }).sort("date", pymongo.DESCENDING)
            return [(e["id"], e["date"], e["amount"], e["category"], e["name"], 1 if e.get("image_path") else 0, e.get("is_recurring", False)) for e in expenses]

        search_pattern = f"%{query}%"
        self.execute("""
            SELECT id, date, amount, category, name, CASE WHEN image_path IS NOT NULL AND image_path != '' THEN 1 ELSE 0 END as has_image, is_recurring 
            FROM expenses 
            WHERE user_id = ? AND (name LIKE ? OR category LIKE ?) 
            ORDER BY date DESC
        """, (user_id, search_pattern, search_pattern))
        return self.cursor.fetchall()

import customtkinter as ctk # type: ignore
import sqlite3
import calendar
import os
import json
import threading
from datetime import datetime
from tkinter import messagebox, filedialog
from typing import Dict

try:
    import google.generativeai as genai # type: ignore
    from PIL import Image # type: ignore
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

try:
    from fpdf import FPDF # type: ignore
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

# --- Corporate Theme Colors ---
COLOR_BG = "#000000"
COLOR_PANEL = "#0A0A0A"
COLOR_NAV = "#000000"
COLOR_TEXT = "#FFFFFF"
COLOR_TEXT_NAV = "#FFFFFF"
COLOR_TEXT_MUTED = "#888888"
COLOR_ACCENT = "#3B82F6"
COLOR_ACCENT_HOVER = "#2563EB"
COLOR_BORDER = "#333333"
COLOR_DANGER = "#EF4444"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CATEGORIES = [
    "Rent", "Grocery", "Food", "Water", "Electricity", "Transportation", 
    "Clothing", "Online Shopping", "Hospital", "Education", "Insurance", 
    "Entertainment", "Credit Card", "Emergency Fund", "Investment", "Other"
]

DB_NAME = "budget.db"



class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME)
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



class TopNavigationBar(ctk.CTkFrame):
    def __init__(self, master, title="Budget Calendar", show_logout=False, on_logout=None):
        super().__init__(master, fg_color=COLOR_NAV, corner_radius=0, height=70) # type: ignore
        self.pack(fill="x", side="top")
        self.pack_propagate(False)

        # Logo / Title with more breathing room
        self.logo_label = ctk.CTkLabel(
            self, 
            text=f"❖ {title.upper()}", 
            font=ctk.CTkFont(family="Helvetica", size=22, weight="bold"), 
            text_color=COLOR_TEXT_NAV
        )
        self.logo_label.pack(side="left", padx=40)
        
        # Right side actions container
        self.actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.actions_frame.pack(side="right", padx=40, fill="y")

        # Sign Out with premium outline style
        if show_logout and on_logout:
            self.logout_btn = ctk.CTkButton(
                self.actions_frame, 
                text="SIGN OUT", 
                width=110,
                height=34,
                font=ctk.CTkFont(family="Inter", size=12, weight="bold"),
                fg_color="transparent", 
                border_width=1, 
                border_color=COLOR_BORDER,
                text_color=COLOR_TEXT_NAV, 
                hover_color=COLOR_BG,
                command=on_logout
            )
            self.logout_btn.pack(side="left", pady=18)



class LoginWindow(ctk.CTkFrame):
    def __init__(self, master, on_login_success):
        super().__init__(master, fg_color=COLOR_BG) # type: ignore
        self.master = master
        self.on_login_success = on_login_success
        self.db = Database()

        self.pack(fill="both", expand=True)
        
        # Explicit dark style colors for layout
        bg_dark = "#0B0B0C"
        panel_dark = "#15161A"
        border_dark = "#2A2B30"
        text_light = "#FFFFFF"
        text_muted = "#8E8E93"
        # Single Centered Layout
        brand_blue = "#3B82F6"
        self.form_frame = ctk.CTkFrame(self, fg_color=bg_dark, corner_radius=0)
        self.form_frame.pack(fill="both", expand=True)

        # UI Elements in form_frame
        self.center_container = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.center_container.place(relx=0.5, rely=0.5, anchor="center")

        self.title_label = ctk.CTkLabel(self.center_container, text="Sign In", font=ctk.CTkFont(size=36, weight="bold"), text_color=text_light)
        self.title_label.pack(anchor="w", pady=(0, 45))
        
        self.user_label = ctk.CTkLabel(self.center_container, text="User Name", font=ctk.CTkFont(size=12, weight="bold"), text_color=text_light)
        self.user_label.pack(anchor="w", pady=(0, 8))

        self.username_entry = ctk.CTkEntry(self.center_container, placeholder_text="✉  Enter User Name", width=340, height=45, corner_radius=6, border_color=border_dark, border_width=1, fg_color=bg_dark, text_color=text_light, placeholder_text_color=text_muted)
        self.username_entry.pack(pady=(0, 25))

        self.pass_label = ctk.CTkLabel(self.center_container, text="Password", font=ctk.CTkFont(size=12, weight="bold"), text_color=text_light)
        self.pass_label.pack(anchor="w", pady=(0, 8))

        self.password_entry = ctk.CTkEntry(self.center_container, placeholder_text="🔒  Enter Password", show="*", width=340, height=45, corner_radius=6, border_color=border_dark, border_width=1, fg_color=bg_dark, text_color=text_light, placeholder_text_color=text_muted)
        self.password_entry.pack(pady=(0, 15))
        
        # Bind Enter key to sign in
        self.username_entry.bind("<Return>", lambda e: self.handle_action())
        self.password_entry.bind("<Return>", lambda e: self.handle_action())

        self.forgot_btn = ctk.CTkButton(self.center_container, text="FORGOT PASSWORD?", font=ctk.CTkFont(size=10, weight="bold"), text_color=text_muted, fg_color="transparent", hover_color=panel_dark, width=120, anchor="w", command=lambda: self.switch_mode("forgot"))
        self.forgot_btn.pack(anchor="w", pady=(0, 35))

        self.status_label = ctk.CTkLabel(self.center_container, text="", font=ctk.CTkFont(size=12))
        self._msg_timer = None

        self.action_btn = ctk.CTkButton(self.center_container, text="SIGN IN", command=self.handle_action, width=340, height=45, corner_radius=6, font=ctk.CTkFont(weight="bold", size=14), fg_color=brand_blue, hover_color="#2563EB", text_color="white")
        self.action_btn.pack(pady=(0, 20))

        # Bottom Frame for Signup
        self.bottom_frame = ctk.CTkFrame(self.center_container, fg_color="transparent")
        self.bottom_frame.pack(pady=(20, 0))
        
        self.switch_lbl = ctk.CTkLabel(self.bottom_frame, text="Don't have an account?", font=ctk.CTkFont(size=12), text_color=text_muted)
        self.switch_lbl.pack(side="left", padx=(0, 5))
        
        self.switch_btn = ctk.CTkButton(self.bottom_frame, text="Sign up", command=lambda: self.switch_mode("register"), width=60, height=30, fg_color="transparent", text_color=text_light, font=ctk.CTkFont(size=12), hover_color=panel_dark)
        self.switch_btn.pack(side="left")

        self.current_mode = "login"
        self.switch_mode("login")

    def switch_mode(self, mode):
        self.current_mode = mode
        self.username_entry.delete(0, 'end')
        self.password_entry.delete(0, 'end')
        if self.status_label.winfo_ismapped():
            self.status_label.pack_forget()
        
        if mode == "login":
            self.title_label.configure(text="Sign In")
            self.pass_label.configure(text="Password")
            self.username_entry.configure(placeholder_text="✉  Enter User Name")
            self.password_entry.configure(placeholder_text="🔒  Enter Password")
            if not self.forgot_btn.winfo_ismapped():
                self.forgot_btn.pack(anchor="w", pady=(0, 35), before=self.action_btn)
            self.action_btn.configure(text="SIGN IN")
            self.switch_lbl.configure(text="Don't have an account?")
            self.switch_btn.configure(text="Sign up", command=lambda: self.switch_mode("register"))
        elif mode == "register":
            self.title_label.configure(text="Create Account")
            self.pass_label.configure(text="Password")
            self.username_entry.configure(placeholder_text="✉  Enter User Name")
            self.password_entry.configure(placeholder_text="🔒  Create Password")
            if self.forgot_btn.winfo_ismapped():
                self.forgot_btn.pack_forget()
            self.action_btn.configure(text="SIGN UP")
            self.switch_lbl.configure(text="Already have an account?")
            self.switch_btn.configure(text="Sign In", command=lambda: self.switch_mode("login"))
        elif mode == "forgot":
            self.title_label.configure(text="Reset Password")
            self.pass_label.configure(text="New Password")
            self.username_entry.configure(placeholder_text="✉  Enter User Name")
            self.password_entry.configure(placeholder_text="🔒  Enter New Password")
            if self.forgot_btn.winfo_ismapped():
                self.forgot_btn.pack_forget()
            self.action_btn.configure(text="RESET PASSWORD")
            self.switch_lbl.configure(text="Remember your password?")
            self.switch_btn.configure(text="Sign In", command=lambda: self.switch_mode("login"))

    def show_message(self, msg, is_error=True):
        color = COLOR_DANGER if is_error else "#10B981"
        self.status_label.configure(text=msg, text_color=color)
        if not self.status_label.winfo_ismapped():
            self.status_label.pack(pady=(0, 15), before=self.action_btn)
        
        if self._msg_timer:
            self.after_cancel(self._msg_timer)
        self._msg_timer = self.after(3000, lambda: self.status_label.pack_forget())

    def handle_action(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            self.show_message("Please fill out all fields.", is_error=True)
            return

        if self.current_mode == "login":
            user_id = self.db.login_user(username, password)
            if user_id:
                self.on_login_success(user_id)
            else:
                self.show_message("Invalid username or password.", is_error=True)
        elif self.current_mode == "register":
            if self.db.register_user(username, password):
                self.show_message("Account created successfully! You can now log in.", is_error=False)
                self.after(1500, lambda: self.switch_mode("login"))
            else:
                self.show_message("Username already exists.", is_error=True)
        elif self.current_mode == "forgot":
            if self.db.update_password(username, password):
                self.show_message("Password updated successfully!", is_error=False)
                self.after(1500, lambda: self.switch_mode("login"))
            else:
                self.show_message("Username not found.", is_error=True)


class AddExpenseModal(ctk.CTkFrame):
    def __init__(self, master, current_date, user_id, on_expense_added, default_category="Food", 
                 expense_id=None, expense_name="", expense_amount="", is_edit=False, expense_image_path=None):
        super().__init__(master, width=400, height=570, corner_radius=12, fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER) # type: ignore
        self.pack_propagate(False)
        self.place(relx=0.5, rely=0.5, anchor="center")
        
        self.master = master
        self.current_date = current_date
        self.user_id = user_id
        self.on_expense_added = on_expense_added
        self.expense_id = expense_id
        self.is_edit = is_edit
        self.image_path = expense_image_path
        self.default_category = default_category
        self.db = Database()

        self.grab_set()

        # Keyboard shortcuts
        self.bind("<Escape>", lambda e: self.destroy_modal())
        # We don't bind <Return> to the whole modal because we want the text box to work normally,
        # but we bind it specifically to the entries.
        
        # UI
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent", height=60)
        self.header_frame.pack(fill="x", padx=20, pady=(20, 10))
        self.header_frame.pack_propagate(False)
        
        # The prompt asked for "their name only there", setting title to the Category Name
        self.title_label = ctk.CTkLabel(self.header_frame, text=default_category, font=ctk.CTkFont(size=20, weight="bold"), text_color=COLOR_TEXT)
        self.title_label.pack(side="left")

        self.form_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.form_frame.pack(fill="both", expand=True, padx=30)

        # 1. Amount
        self.amount_entry = ctk.CTkEntry(self.form_frame, placeholder_text="Amount", width=350, height=40, border_color=COLOR_BORDER, fg_color=COLOR_BG, text_color=COLOR_TEXT)
        self.amount_entry.pack(pady=8)

        # 2. Date
        self.date_entry = ctk.CTkEntry(self.form_frame, placeholder_text="Date (YYYY-MM-DD)", width=350, height=40, border_color=COLOR_BORDER, fg_color=COLOR_BG, text_color=COLOR_TEXT)
        self.date_entry.pack(pady=8)
        self.date_entry.insert(0, self.current_date)
        self.date_entry.configure(state="readonly")
        self.date_entry.bind("<Button-1>", lambda e: self.open_date_picker())

        # 3. Total
        self.total_entry = ctk.CTkEntry(self.form_frame, placeholder_text="Total", width=350, height=40, border_color=COLOR_BORDER, fg_color=COLOR_BG, text_color=COLOR_TEXT)
        self.total_entry.pack(pady=8)
        if expense_amount != "":
            self.total_entry.insert(0, str(expense_amount))

        # Bind Enter key to entries
        for entry in [self.amount_entry, self.total_entry]:
            entry.bind("<Return>", lambda e: self.save_expense())

        # 4. List of Item (multiline text box, allows pressing enter to come down)
        self.items_textbox = ctk.CTkTextbox(self.form_frame, width=350, height=100, border_color=COLOR_BORDER, border_width=1, fg_color=COLOR_BG, text_color=COLOR_TEXT)
        self.items_textbox.pack(pady=8)
        if expense_name:
            self.items_textbox.insert("0.0", expense_name)

        self.ai_btn = ctk.CTkButton(self.form_frame, text="Upload Receipt (AI Magic) 🤖", command=self.upload_receipt, width=350, height=35, fg_color=COLOR_BG, text_color=COLOR_TEXT_MUTED, border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BORDER)
        self.ai_btn.pack(pady=5)

        # Attach Bill Image Section
        self.bill_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.bill_frame.pack(fill="x", pady=5)
        
        self.attach_btn = ctk.CTkButton(self.bill_frame, text="Attach Bill Image 📎", command=self.select_bill_image, width=170, height=35, fg_color=COLOR_BG, text_color=COLOR_TEXT, border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BORDER)
        self.attach_btn.pack(side="left")
        
        bill_text = "Bill attached" if self.image_path else "No bill selected"
        self.bill_label = ctk.CTkLabel(self.bill_frame, text=bill_text, font=ctk.CTkFont(size=12, slant="italic"), text_color=COLOR_TEXT_MUTED)
        self.bill_label.pack(side="left", padx=10)

        self.buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.buttons_frame.pack(fill="x", padx=30, pady=(10, 30))


        self.submit_btn = ctk.CTkButton(self.buttons_frame, text="Save Expense", command=self.save_expense, width=180, height=40, font=ctk.CTkFont(weight="bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER)
        self.submit_btn.pack(side="right", padx=(10, 0))

        self.cancel_btn = ctk.CTkButton(self.buttons_frame, text="Cancel", command=self.destroy_modal, width=160, height=40, fg_color="transparent", border_width=1, border_color=COLOR_BORDER, text_color=COLOR_TEXT, hover_color=COLOR_BG)
        self.cancel_btn.pack(side="right")

    def destroy_modal(self):
        self.grab_release()
        self.destroy()

    def upload_receipt(self):
        if not HAS_GENAI:
            messagebox.showerror("Dependency Missing", "Please restart the app. I was just installing google-generativeai in the background.")
            return

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            dialog = ctk.CTkInputDialog(text="Enter your free Gemini API Key from Google AI Studio:", title="API Key Required")
            api_key = dialog.get_input()
            if not api_key:
                return
            os.environ["GEMINI_API_KEY"] = api_key

        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg;*.jpeg;*.png")])
        if not file_path:
            return

        self.ai_btn.configure(text="Processing...", state="disabled")
        self.update()

        t = threading.Thread(target=self.process_receipt, args=(api_key, file_path))
        t.start()

    def process_receipt(self, api_key, file_path):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            image = Image.open(file_path)

            prompt = """
            Analyze this receipt/bill. Extract the following details:
            - Store/Expense Name (keep it short)
            - Total Amount (just the number, no currency symbol)
            - Category (pick one: Food, Transport, Utilities, Entertainment, Other)

            Respond ONLY with a valid JSON object in this exact format:
            {"name": "Store Name", "amount": 12.34, "category": "Food"}
            """

            response = model.generate_content([prompt, image])
            text = response.text
            
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            self.after(0, self.update_fields_from_ai, data)
        except Exception as e:
            self.after(0, self.show_ai_error, str(e))

    def update_fields_from_ai(self, data):
        self.ai_btn.configure(text="Upload Receipt (AI Magic) \U0001F916", state="normal")
        
        self.items_textbox.delete("0.0", 'end')
        self.items_textbox.insert("0.0", data.get('name', ''))

        self.total_entry.delete(0, 'end')
        self.total_entry.insert(0, str(data.get('amount', '')))

        messagebox.showinfo("Success", "Receipt processed! Verify details and click Save.")

    def show_ai_error(self, error_message):
        self.ai_btn.configure(text="Upload Receipt (AI Magic) \U0001F916", state="normal")
        messagebox.showerror("AI Error", f"Failed to process image:\n{error_message}")

    def save_expense(self):
        date_str = self.date_entry.get().strip()
        amount_str = self.amount_entry.get().strip()
        total_str = self.total_entry.get().strip()
        items = self.items_textbox.get("0.0", "end").strip()

        final_amount_str = total_str if total_str else amount_str

        if not final_amount_str:
            messagebox.showerror("Error", "Please fill out Total or Amount.")
            return

        try:
            amount = float(final_amount_str)
        except ValueError:
            messagebox.showerror("Error", "Total/Amount must be a valid number.")
            return

        name_parts = []
        if amount_str and amount_str != final_amount_str:
            name_parts.append(f"Amount: {amount_str}")
        if items:
            name_parts.append(items)
            
        final_name = "\n".join(name_parts).strip()
        if not final_name:
            final_name = "Items"

        category = self.default_category

        if self.is_edit:
            self.db.update_expense(self.expense_id, self.user_id, date_str, amount, category, final_name, self.image_path)
        else:
            self.db.add_expense(self.user_id, date_str, amount, category, final_name, self.image_path)
            
        self.on_expense_added()
        self.destroy_modal()

    def open_date_picker(self):
        DatePickerModal(self, self.date_entry.get().strip(), self.set_date)

    def set_date(self, date_str):
        self.date_entry.configure(state="normal")
        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, date_str)
        self.date_entry.configure(state="readonly")

    def select_bill_image(self):
        file_path = filedialog.askopenfilename(
            title="Select Bill/Receipt Image",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.bmp"),
                ("All Files", "*.*")
            ]
        )
        if file_path:
            self.image_path = file_path
            self.bill_label.configure(text=f"Attached: {os.path.basename(file_path)}")


class DatePickerModal(ctk.CTkFrame):
    def __init__(self, master, current_date_str, on_date_selected):
        super().__init__(master, width=350, height=400, corner_radius=12, fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER) # type: ignore
        self.pack_propagate(False)
        self.place(relx=0.5, rely=0.5, anchor="center")
        
        try:
            d_obj = datetime.strptime(current_date_str, "%Y-%m-%d")
            self.current_year = d_obj.year
            self.current_month = d_obj.month
            self.selected_date = current_date_str
        except:
            now = datetime.now()
            self.current_year = now.year
            self.current_month = now.month
            self.selected_date = now.strftime("%Y-%m-%d")
            
        self.on_date_selected = on_date_selected

        self.grab_set()
        
        # Keyboard shortcuts
        self.bind("<Escape>", lambda e: self.destroy_modal())

        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", pady=20, padx=20)
        
        self.prev_btn = ctk.CTkButton(self.header_frame, text="<", width=40, font=ctk.CTkFont(weight="bold"), fg_color=COLOR_BG, text_color=COLOR_TEXT, hover_color=COLOR_BORDER, command=self.prev_month)
        self.prev_btn.pack(side="left")
        
        self.month_lbl = ctk.CTkLabel(self.header_frame, text="", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_TEXT)
        self.month_lbl.pack(side="left", expand=True)

        self.next_btn = ctk.CTkButton(self.header_frame, text=">", width=40, font=ctk.CTkFont(weight="bold"), fg_color=COLOR_BG, text_color=COLOR_TEXT, hover_color=COLOR_BORDER, command=self.next_month)
        self.next_btn.pack(side="right")
        
        self.close_btn = ctk.CTkButton(self.header_frame, text="X", width=40, height=40, font=ctk.CTkFont(weight="bold"), fg_color="transparent", text_color=COLOR_TEXT_MUTED, hover_color=COLOR_BG, command=self.destroy_modal)
        self.close_btn.pack(side="right", padx=(0, 10))

        # Days Grid
        self.cal_grid = ctk.CTkFrame(self, fg_color="transparent")
        self.cal_grid.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        for i in range(7):
            self.cal_grid.grid_columnconfigure(i, weight=1)
            
        days = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
        for i, day in enumerate(days):
            lbl = ctk.CTkLabel(self.cal_grid, text=day, font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_MUTED)
            lbl.grid(row=0, column=i, pady=(0, 10))

        self.day_buttons = []
        self.refresh_calendar()

    def prev_month(self):
        self.current_month -= 1
        if self.current_month < 1:
            self.current_month = 12
            self.current_year -= 1
        self.refresh_calendar()

    def next_month(self):
        self.current_month += 1
        if self.current_month > 12:
            self.current_month = 1
            self.current_year += 1
        self.refresh_calendar()

    def refresh_calendar(self):
        month_name = calendar.month_name[self.current_month]
        self.month_lbl.configure(text=f"{month_name} {self.current_year}")

        for widget in self.day_buttons:
            widget.destroy()
        self.day_buttons.clear()

        cal = calendar.monthcalendar(self.current_year, self.current_month)
        
        for row_idx, week in enumerate(cal):
            for col_idx, day in enumerate(week):
                if day != 0:
                    date_str = f"{self.current_year:04d}-{self.current_month:02d}-{day:02d}"
                    is_selected = (date_str == self.selected_date)
                    
                    fg_color = COLOR_ACCENT if is_selected else COLOR_BG
                    text_color = "white" if is_selected else COLOR_TEXT
                    hover_color = COLOR_ACCENT_HOVER if is_selected else COLOR_BORDER
                    
                    btn = ctk.CTkButton(self.cal_grid, text=str(day), width=40, height=40, corner_radius=8, 
                                        font=ctk.CTkFont(size=16, weight="bold"),
                                        fg_color=fg_color, text_color=text_color, hover_color=hover_color,
                                        command=lambda d=date_str: self.select_date(d))
                    btn.grid(row=row_idx+1, column=col_idx, padx=2, pady=2)
                    self.day_buttons.append(btn)

    def select_date(self, date_str):
        self.on_date_selected(date_str)
        self.destroy_modal()

    def destroy_modal(self):
        self.grab_release()
        self.destroy()


class MonthPickerModal(ctk.CTkFrame):
    def __init__(self, master, current_month, current_year, on_date_selected):
        super().__init__(master, width=400, height=350, corner_radius=12, fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER) # type: ignore
        self.grid_propagate(False)
        self.place(relx=0.5, rely=0.5, anchor="center")
        self.current_month = current_month
        self.current_year = current_year
        self.on_date_selected = on_date_selected

        # Grab focus to prevent interaction with the background
        self.grab_set()
        
        # Keyboard shortcuts
        self.bind("<Escape>", lambda e: self.destroy_modal())

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header for Year
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, pady=20, padx=20, sticky="ew")
        self.header_frame.grid_columnconfigure(1, weight=1)

        self.prev_year_btn = ctk.CTkButton(self.header_frame, text="<", width=40, height=40, font=ctk.CTkFont(weight="bold"), fg_color=COLOR_BG, text_color=COLOR_TEXT, hover_color=COLOR_BORDER, command=self.prev_year)
        self.prev_year_btn.grid(row=0, column=0)

        self.year_lbl = ctk.CTkLabel(self.header_frame, text=str(self.current_year), font=ctk.CTkFont(size=22, weight="bold"), text_color=COLOR_TEXT)
        self.year_lbl.grid(row=0, column=1)

        self.next_year_btn = ctk.CTkButton(self.header_frame, text=">", width=40, height=40, font=ctk.CTkFont(weight="bold"), fg_color=COLOR_BG, text_color=COLOR_TEXT, hover_color=COLOR_BORDER, command=self.next_year)
        self.next_year_btn.grid(row=0, column=2)

        self.close_btn = ctk.CTkButton(self.header_frame, text="X", width=40, height=40, font=ctk.CTkFont(weight="bold"), fg_color="transparent", text_color=COLOR_TEXT_MUTED, hover_color=COLOR_BG, command=self.destroy_modal)
        self.close_btn.grid(row=0, column=3, padx=(10, 0))

        # Grid for Months
        self.months_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.months_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))

        self.months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        for i in range(4):
            self.months_frame.grid_rowconfigure(i, weight=1)
        for i in range(3):
            self.months_frame.grid_columnconfigure(i, weight=1)

        self.month_buttons = []
        for i in range(12):
            row = i // 3
            col = i % 3
            btn = ctk.CTkButton(self.months_frame, text="", font=ctk.CTkFont(weight="bold"),
                                command=lambda m=(i+1): self.select_month(m))
            btn.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            self.month_buttons.append(btn)
            
        self.refresh_months()

    def refresh_months(self):
        monthly_totals = {i: 0 for i in range(1, 13)}
        if hasattr(self.master, 'db') and hasattr(self.master, 'user_id'):
            for m in range(1, 13):
                raw = self.master.db.get_expenses_by_month(self.master.user_id, self.current_year, m)
                for _, amt in raw:
                    monthly_totals[m] += amt
                    
        for i, month in enumerate(self.months):
            is_current = (i + 1) == self.current_month
            fg_color = COLOR_ACCENT if is_current else COLOR_BG
            text_color = "white" if is_current else COLOR_TEXT
            hover_color = COLOR_ACCENT_HOVER if is_current else COLOR_BORDER
            
            val = monthly_totals.get(i+1, 0)
            btn_text = f"{month}\n₹{val:g}" if val > 0 else month
            
            self.month_buttons[i].configure(text=btn_text, fg_color=fg_color, hover_color=hover_color, text_color=text_color)

    def prev_year(self):
        self.current_year -= 1
        self.year_lbl.configure(text=str(self.current_year))
        self.refresh_months()

    def next_year(self):
        self.current_year += 1
        self.year_lbl.configure(text=str(self.current_year))
        self.refresh_months()

    def select_month(self, month):
        self.on_date_selected(self.current_year, month)
        self.destroy_modal()

    def destroy_modal(self):
        self.grab_release()
        self.destroy()


class MenuItem(ctk.CTkFrame):
    def __init__(self, master, icon, text, has_chevron=True, is_active=False, command=None):
        super().__init__(master, fg_color="transparent", height=42, corner_radius=8, cursor="hand2") # type: ignore
        self.pack_propagate(False)
        self.command = command
        
        self.text_col_normal = COLOR_TEXT_MUTED
        self.text_col_active = COLOR_ACCENT
        self.text_col = self.text_col_active if is_active else self.text_col_normal
        
        self.icon_lbl = ctk.CTkLabel(self, text=icon, font=ctk.CTkFont(size=18), text_color=self.text_col, width=30, anchor="center")
        self.icon_lbl.pack(side="left", padx=(15, 10))
        
        self.text_lbl = ctk.CTkLabel(self, text=text.strip(), font=ctk.CTkFont(family="Inter", size=14), text_color=self.text_col)
        self.text_lbl.pack(side="left")
        
        if has_chevron:
            self.chev_lbl = ctk.CTkLabel(self, text="›", font=ctk.CTkFont(size=18), text_color=COLOR_BORDER)
            self.chev_lbl.pack(side="right", padx=15)
        else:
            self.chev_lbl = None
            
        widgets = [self, self.icon_lbl, self.text_lbl]
        if self.chev_lbl:
            widgets.append(self.chev_lbl)
        for w in widgets:
            w.bind("<Button-1>", self.on_click)
            w.bind("<Enter>", self.on_enter)
            w.bind("<Leave>", self.on_leave)
            
        self.is_active = is_active
        
    def on_enter(self, e):
        if not self.is_active:
            self.text_lbl.configure(text_color=self.text_col_active)
            self.icon_lbl.configure(text_color=self.text_col_active)
            if self.chev_lbl:
                self.chev_lbl.configure(text_color=self.text_col_active)
            
    def on_leave(self, e):
        if not self.is_active:
            self.text_lbl.configure(text_color=self.text_col_normal)
            self.icon_lbl.configure(text_color=self.text_col_normal)
            if self.chev_lbl:
                self.chev_lbl.configure(text_color=COLOR_BORDER)
            
    def on_click(self, e):
        if self.command:
            self.command()


class SidebarMenu(ctk.CTkScrollableFrame):
    def __init__(self, master, current_view="Home", on_nav=None, **kwargs):
        super().__init__(master, fg_color=COLOR_PANEL, width=220, corner_radius=0, **kwargs) # type: ignore
        self.pack(side="left", fill="y")
        self.on_nav = on_nav
        
        expense_items = [
            ("🏢", "Rent", False),
            ("🥦", "Grocery", False),
            ("🍔", "Food", False),
            ("💧", "Water", False),
            ("⚡", "Electricity", False),
            ("🚗", "Transportation", False),
            ("👕", "Clothing", False),
            ("🛒", "Online Shopping", False),
            ("🏥", "Hospital", False),
            ("🎓", "Education", False),
            ("☂", "Insurance", False),
            ("🎬", "Entertainment", False),
            ("💳", "Credit Card", False),
            ("📍", "Emergency Fund", False),
            ("💰", "Investment", False),
            ("📦", "Other", False),
        ]
        
        income_items = [
            ("💼", "Wages", False),
            ("📈", "Interest/dividends", False),
            ("✨", "Miscellaneous", False),
            ("🎁", "Gift", False),
        ]
        
        ctk.CTkFrame(self, fg_color="transparent", height=10).pack()
        
        self.buttons = []
        
        # Home Button
        self.home_btn = MenuItem(self, icon="🏠", text="Home", has_chevron=False, is_active=(current_view == "Home"), command=lambda: self.on_nav("Home") if self.on_nav else None)
        self.home_btn.pack(fill="x", pady=2, padx=5)
        self.buttons.append(self.home_btn)

        ctk.CTkFrame(self, fg_color="transparent", height=10).pack()

        # Expenses Caret Button
        self.expenses_expanded = False
        self.expenses_caret_btn = MenuItem(self, icon="💰", text="Expenses", has_chevron=True, is_active=False, command=self.toggle_expenses)
        self.expenses_caret_btn.pack(fill="x", pady=2, padx=5)

        # Expenses Frame (hidden by default)
        self.expenses_frame = ctk.CTkFrame(self, fg_color="transparent")
        
        for icon, text, chevron in expense_items:
            is_active = (text == current_view)
            cmd = (lambda t=text: self.on_nav(t)) if self.on_nav else None
            btn = MenuItem(self.expenses_frame, icon=icon, text=text, has_chevron=chevron, is_active=is_active, command=cmd)
            btn.pack(fill="x", pady=2, padx=(20, 5))
            self.buttons.append(btn)
            if is_active:
                self.expenses_expanded = True
                
        if self.expenses_expanded:
            self.expenses_frame.pack(fill="x")
            self.expenses_caret_btn.chev_lbl.configure(text="˅")
        else:
            self.expenses_caret_btn.chev_lbl.configure(text="›")

        ctk.CTkFrame(self, fg_color="transparent", height=10).pack()

        # Income Caret Button
        self.income_expanded = False
        self.income_caret_btn = MenuItem(self, icon="📥", text="Income", has_chevron=True, is_active=False, command=self.toggle_income)
        self.income_caret_btn.pack(fill="x", pady=2, padx=5)

        # Income Frame (hidden by default)
        self.income_frame = ctk.CTkFrame(self, fg_color="transparent")
        
        for icon, text, chevron in income_items:
            is_active = (text == current_view)
            cmd = (lambda t=text: self.on_nav(t)) if self.on_nav else None
            btn = MenuItem(self.income_frame, icon=icon, text=text, has_chevron=chevron, is_active=is_active, command=cmd)
            btn.pack(fill="x", pady=2, padx=(20, 5))
            self.buttons.append(btn)
            if is_active:
                self.income_expanded = True
                
        if self.income_expanded:
            self.income_frame.pack(fill="x")
            self.income_caret_btn.chev_lbl.configure(text="˅")
        else:
            self.income_caret_btn.chev_lbl.configure(text="›")

        ctk.CTkFrame(self, fg_color="transparent", height=10).pack()

        # Yearly Report Button
        self.yearly_btn = MenuItem(self, icon="📊", text="Yearly Report", has_chevron=False, is_active=(current_view == "Yearly Report"), command=lambda: self.on_nav("Yearly Report") if self.on_nav else None)
        self.yearly_btn.pack(fill="x", pady=2, padx=5)
        self.buttons.append(self.yearly_btn)

    def toggle_expenses(self):
        self.expenses_expanded = not self.expenses_expanded
        if self.expenses_expanded:
            self.expenses_frame.pack(fill="x", after=self.expenses_caret_btn)
            self.expenses_caret_btn.chev_lbl.configure(text="")
        else:
            self.expenses_frame.pack_forget()
            self.expenses_caret_btn.chev_lbl.configure(text="›")

    def toggle_income(self):
        self.income_expanded = not self.income_expanded
        if self.income_expanded:
            self.income_frame.pack(fill="x", after=self.income_caret_btn)
            self.income_caret_btn.chev_lbl.configure(text="")
        else:
            self.income_frame.pack_forget()
            self.income_caret_btn.chev_lbl.configure(text="›")

    def set_active(self, view_name):
        for btn in self.buttons:
            is_active = (btn.text_lbl.cget("text") == view_name)
            btn.is_active = is_active
            if is_active:
                btn.text_lbl.configure(text_color=btn.text_col_active)
                btn.icon_lbl.configure(text_color=btn.text_col_active)
                if btn.chev_lbl:
                    btn.chev_lbl.configure(text_color=btn.text_col_active)
            else:
                btn.text_lbl.configure(text_color=btn.text_col_normal)
                btn.icon_lbl.configure(text_color=btn.text_col_normal)
                if btn.chev_lbl:
                    btn.chev_lbl.configure(text_color=COLOR_BORDER)





class HomeView(ctk.CTkFrame):
    def __init__(self, master, user_id):
        super().__init__(master, fg_color="transparent") # type: ignore
        self.user_id = user_id
        self.db = Database()
        
        now = datetime.now()
        self.current_year = now.year
        self.current_month = now.month
        self.selected_date = now.strftime("%Y-%m-%d")
        self.month_expenses = {}

        self.pack(fill="both", expand=True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=400)
        self.grid_rowconfigure(0, weight=1)

        # Calendar Area
        self.calendar_panel = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        self.calendar_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        self.calendar_panel.grid_columnconfigure(0, weight=1)
        self.calendar_panel.grid_rowconfigure(1, weight=1)

        self.cal_header = ctk.CTkFrame(self.calendar_panel, fg_color="transparent")
        self.cal_header.grid(row=0, column=0, sticky="ew", padx=30, pady=30)
        
        self.prev_btn = ctk.CTkButton(self.cal_header, text="<", width=40, height=40, font=ctk.CTkFont(weight="bold"), fg_color=COLOR_BG, text_color=COLOR_TEXT, hover_color=COLOR_BORDER, command=self.prev_month)
        self.prev_btn.pack(side="left")

        self.month_lbl = ctk.CTkButton(self.cal_header, text="", font=ctk.CTkFont(size=24, weight="bold"),
                                       fg_color="transparent", text_color=COLOR_TEXT, hover_color=COLOR_BG,
                                       cursor="hand2", command=self.open_month_picker)
        self.month_lbl.pack(side="left", expand=True)

        self.next_btn = ctk.CTkButton(self.cal_header, text=">", width=40, height=40, font=ctk.CTkFont(weight="bold"), fg_color=COLOR_BG, text_color=COLOR_TEXT, hover_color=COLOR_BORDER, command=self.next_month)
        self.next_btn.pack(side="right")

        self.cal_grid = ctk.CTkFrame(self.calendar_panel, fg_color="transparent")
        self.cal_grid.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 30))
        for i in range(7):
            self.cal_grid.grid_columnconfigure(i, weight=1)
        for i in range(7):
            self.cal_grid.grid_rowconfigure(i, weight=1)

        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        for i, day in enumerate(days):
            lbl = ctk.CTkLabel(self.cal_grid, text=day.upper(), font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED)
            lbl.grid(row=0, column=i, pady=(0, 10))

        self.cal_cells = []

        # Sidebar Area
        self.sidebar_panel = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        self.sidebar_panel.grid(row=0, column=1, sticky="nsew")
        
        self.sidebar_header = ctk.CTkFrame(self.sidebar_panel, fg_color="transparent")
        self.sidebar_header.pack(fill="x", padx=30, pady=(30, 10))
        
        self.sidebar_title = ctk.CTkLabel(self.sidebar_header, text="Monthly Summary", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLOR_TEXT)
        self.sidebar_title.pack(side="left")

        self.divider = ctk.CTkFrame(self.sidebar_panel, height=1, fg_color=COLOR_BORDER)
        self.divider.pack(fill="x", padx=30, pady=10)

        # Summary Stats Area
        self.stats_frame = ctk.CTkFrame(self.sidebar_panel, fg_color="transparent")
        self.stats_frame.pack(fill="x", padx=30, pady=10)

        # Total Income
        self.income_lbl_title = ctk.CTkLabel(self.stats_frame, text="Total Income", font=ctk.CTkFont(size=14), text_color=COLOR_TEXT_MUTED)
        self.income_lbl_title.grid(row=0, column=0, sticky="w", pady=5)
        self.income_lbl_val = ctk.CTkLabel(self.stats_frame, text="₹0.00", font=ctk.CTkFont(size=18, weight="bold"), text_color="#10B981") # Green
        self.income_lbl_val.grid(row=0, column=1, sticky="e", pady=5, padx=(20, 0))

        # Total Expenses
        self.expenses_lbl_title = ctk.CTkLabel(self.stats_frame, text="Total Expenses", font=ctk.CTkFont(size=14), text_color=COLOR_TEXT_MUTED)
        self.expenses_lbl_title.grid(row=1, column=0, sticky="w", pady=5)
        self.expenses_lbl_val = ctk.CTkLabel(self.stats_frame, text="₹0.00", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_DANGER) # Red
        self.expenses_lbl_val.grid(row=1, column=1, sticky="e", pady=5, padx=(20, 0))

        # Cash Short/Extra
        self.cash_lbl_title = ctk.CTkLabel(self.stats_frame, text="Cash short/extra", font=ctk.CTkFont(size=14), text_color=COLOR_TEXT_MUTED)
        self.cash_lbl_title.grid(row=2, column=0, sticky="w", pady=5)
        self.cash_lbl_val = ctk.CTkLabel(self.stats_frame, text="₹0.00", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_TEXT)
        self.cash_lbl_val.grid(row=2, column=1, sticky="e", pady=5, padx=(20, 0))

        self.stats_frame.grid_columnconfigure(0, weight=1)

        self.divider2 = ctk.CTkFrame(self.sidebar_panel, height=1, fg_color=COLOR_BORDER)
        self.divider2.pack(fill="x", padx=30, pady=10)

        self.expenses_scrollable = ctk.CTkScrollableFrame(self.sidebar_panel, fg_color="transparent")
        self.expenses_scrollable.pack(fill="both", expand=True, padx=20, pady=10)

        self.add_expense_btn = ctk.CTkButton(self.sidebar_panel, text="+ Add", command=self.open_add_expense, height=45, font=ctk.CTkFont(weight="bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER)
        self.add_expense_btn.pack(pady=30, padx=30, fill="x")

        self.refresh_data()

    def prev_month(self):
        self.current_month -= 1
        if self.current_month < 1:
            self.current_month = 12
            self.current_year -= 1
        self.refresh_data()

    def next_month(self):
        self.current_month += 1
        if self.current_month > 12:
            self.current_month = 1
            self.current_year += 1
        self.refresh_data()

    def refresh_data(self):
        month_name = calendar.month_name[self.current_month]
        self.month_lbl.configure(text=f"{month_name} {self.current_year}")

        raw_expenses = self.db.get_expenses_by_month(self.user_id, self.current_year, self.current_month)
        self.month_expenses = {}
        
        total_income = 0.0
        total_expenses = 0.0
        income_categories = ["Wages", "Interest/dividends", "Miscellaneous", "Gift"]

        for raw_date, raw_amount, raw_category in raw_expenses:
            date_str = str(raw_date)
            amount_val = float(raw_amount)
            category_str = str(raw_category)
            if category_str in income_categories:
                total_income = float(total_income) + amount_val  # type: ignore
            else:
                total_expenses = float(total_expenses) + amount_val  # type: ignore
                self.month_expenses[date_str] = self.month_expenses.get(date_str, 0.0) + amount_val

        # Update stats
        self.income_lbl_val.configure(text=f"₹{total_income:.2f}")
        self.expenses_lbl_val.configure(text=f"₹{total_expenses:.2f}")
        
        cash_diff = float(total_income) - float(total_expenses)
        cash_color = "#10B981" if cash_diff >= 0 else COLOR_DANGER
        self.cash_lbl_val.configure(text=f"₹{cash_diff:.2f}", text_color=cash_color)

        for widget in self.cal_cells:
            widget.destroy()
        self.cal_cells.clear()

        cal = calendar.monthcalendar(self.current_year, self.current_month)
        
        for row_idx, week in enumerate(cal):
            for col_idx, day in enumerate(week):
                if day != 0:
                    date_str = f"{self.current_year:04d}-{self.current_month:02d}-{day:02d}"
                    cell_frame = ctk.CTkFrame(self.cal_grid, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
                    cell_frame.grid(row=row_idx+1, column=col_idx, padx=4, pady=4, sticky="nsew")
                    self.cal_cells.append(cell_frame)

                    bg_color = "#000000"
                    text_col = "#FFFFFF"
                    
                    if date_str == self.selected_date:
                        bg_color = "#FFFFFF"
                        text_col = "#000000"
                        cell_frame.configure(fg_color=bg_color, border_color="#FFFFFF") 
                    else:
                        cell_frame.configure(fg_color=bg_color, border_color="#333333")
                    
                    lbl = ctk.CTkLabel(cell_frame, text=str(day), font=ctk.CTkFont(weight="bold", size=14), text_color=text_col)
                    lbl.pack(anchor="ne", padx=10, pady=5)

                    if date_str in self.month_expenses:
                        exp_color = "#000000" if date_str == self.selected_date else "#FFFFFF"
                        amt = self.month_expenses[date_str]
                        display_text = f"₹{amt:g}" if amt < 1000 else f"₹{amt/1000:.1f}k".replace(".0k", "k")
                        exp_lbl = ctk.CTkLabel(cell_frame, text=display_text, font=ctk.CTkFont(size=10, weight="bold"), text_color=exp_color)
                        exp_lbl.pack(anchor="se", padx=5, pady=(0, 5), side="bottom")

                    for w in [cell_frame, lbl, exp_lbl] if date_str in self.month_expenses else [cell_frame, lbl]:
                        w.bind("<Button-1>", lambda e, d=date_str: self.select_date(d))
                        w.configure(cursor="hand2")

        self.refresh_sidebar()

    def select_date(self, date_str):
        self.selected_date = date_str
        self.refresh_data()

    def refresh_sidebar(self):
        d_obj = datetime.strptime(self.selected_date, "%Y-%m-%d")
        
        for widget in self.expenses_scrollable.winfo_children():
            widget.destroy()

        date_header = ctk.CTkLabel(self.expenses_scrollable, text=f"Daily Transactions: {d_obj.strftime('%a, %b %d')}", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_ACCENT)
        date_header.pack(anchor="w", padx=10, pady=(0, 10))

        expenses = self.db.get_expenses_by_date(self.user_id, self.selected_date)
        
        if not expenses:
            lbl = ctk.CTkLabel(self.expenses_scrollable, text="No expenses found for this date.", text_color=COLOR_TEXT_MUTED, font=ctk.CTkFont(size=14))
            lbl.pack(pady=20)
            return

        total = 0
        for e_id, amount, category, name, image_path in expenses:
            total += amount
            item_frame = ctk.CTkFrame(self.expenses_scrollable, fg_color=COLOR_BG, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
            item_frame.pack(fill="x", pady=6, padx=10)
            
            top_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
            top_frame.pack(fill="x", padx=15, pady=(15, 5))
            
            n_lbl = ctk.CTkLabel(top_frame, text=name, font=ctk.CTkFont(size=15, weight="bold"), text_color=COLOR_TEXT)
            n_lbl.pack(side="left")
            
            a_lbl = ctk.CTkLabel(top_frame, text=f"₹{amount:.2f}", text_color=COLOR_DANGER, font=ctk.CTkFont(size=16, weight="bold"))
            a_lbl.pack(side="right")
            
            bot_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
            bot_frame.pack(fill="x", padx=15, pady=(0, 15))
            
            c_lbl = ctk.CTkLabel(bot_frame, text=category.upper(), font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED)
            c_lbl.pack(side="left")

            # Actions Frame
            actions_frame = ctk.CTkFrame(bot_frame, fg_color="transparent")
            actions_frame.pack(side="right")
            
            if image_path:
                view_btn = ctk.CTkButton(actions_frame, text="View Bill", width=60, height=20, font=ctk.CTkFont(size=10, weight="bold"), fg_color="transparent", text_color=COLOR_TEXT, hover_color=COLOR_PANEL, command=lambda p=image_path: self.view_bill_image(p))
                view_btn.pack(side="left", padx=(0, 5))
            
            edit_btn = ctk.CTkButton(actions_frame, text="Edit", width=40, height=20, font=ctk.CTkFont(size=10, weight="bold"), fg_color="transparent", text_color=COLOR_ACCENT, hover_color=COLOR_PANEL, command=lambda e=e_id, n=name, a=amount, c=category, d=self.selected_date, ip=image_path: self.open_edit_expense(e, n, a, c, d, ip))
            edit_btn.pack(side="left", padx=(0, 5))
            
            del_btn = ctk.CTkButton(actions_frame, text="Delete", width=40, height=20, font=ctk.CTkFont(size=10, weight="bold"), fg_color="transparent", text_color=COLOR_DANGER, hover_color=COLOR_PANEL, command=lambda e=e_id, n=name, a=amount: self.delete_expense(e, n, a))
            del_btn.pack(side="left")

        sum_frame = ctk.CTkFrame(self.expenses_scrollable, fg_color="transparent")
        sum_frame.pack(fill="x", pady=20, padx=10)
        
        tot_title = ctk.CTkLabel(sum_frame, text="Total", font=ctk.CTkFont(size=16), text_color=COLOR_TEXT_MUTED)
        tot_title.pack(side="left")

        tot_lbl = ctk.CTkLabel(sum_frame, text=f"₹{total:.2f}", font=ctk.CTkFont(size=22, weight="bold"), text_color=COLOR_TEXT)
        tot_lbl.pack(side="right")

    def delete_expense(self, expense_id, name, amount):
        if messagebox.askyesno("Confirm", f"Are you sure you want to delete '{name}' (₹{amount:.2f})?"):
            self.db.delete_expense(expense_id, self.user_id)
            self.refresh_data()
            
    def open_edit_expense(self, expense_id, name, amount, category, date_str, image_path):
        AddExpenseModal(self, date_str, self.user_id, self.refresh_data, default_category=category, 
                        expense_id=expense_id, expense_name=name, expense_amount=amount, is_edit=True, expense_image_path=image_path)

    def open_month_picker(self):
        MonthPickerModal(self, self.current_month, self.current_year, self.set_month_year)

    def set_month_year(self, year, month):
        self.current_year = year
        self.current_month = month
        self.refresh_data()

    def open_add_expense(self):
        AddExpenseModal(self, self.selected_date, self.user_id, self.refresh_data)

class CategoryView(ctk.CTkFrame):
    def __init__(self, master, user_id, category):
        super().__init__(master, fg_color="transparent") # type: ignore
        self.user_id = user_id
        self.category = category
        self.db = Database()
        
        self.pack(fill="both", expand=True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=400)
        self.grid_rowconfigure(0, weight=1)

        # Main List Area
        self.list_panel = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        self.list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        
        self.list_header = ctk.CTkFrame(self.list_panel, fg_color="transparent")
        self.list_header.pack(fill="x", padx=30, pady=30)
        
        title_text = f"❖ {category} Expenses" if category not in ["Wages", "Interest/dividends", "Miscellaneous", "Gift"] else f"❖ {category} Income"
        self.title_lbl = ctk.CTkLabel(self.list_header, text=title_text, font=ctk.CTkFont(size=24, weight="bold"), text_color=COLOR_TEXT)
        self.title_lbl.pack(side="left")

        self.expenses_scrollable = ctk.CTkScrollableFrame(self.list_panel, fg_color="transparent")
        self.expenses_scrollable.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Sidebar Area
        self.sidebar_panel = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        self.sidebar_panel.grid(row=0, column=1, sticky="nsew")
        
        self.sidebar_header = ctk.CTkFrame(self.sidebar_panel, fg_color="transparent")
        self.sidebar_header.pack(fill="x", padx=30, pady=(30, 10))
        
        self.sidebar_title = ctk.CTkLabel(self.sidebar_header, text="Summary", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLOR_TEXT)
        self.sidebar_title.pack(side="left")

        self.divider = ctk.CTkFrame(self.sidebar_panel, height=1, fg_color=COLOR_BORDER)
        self.divider.pack(fill="x", padx=30, pady=10)
        
        self.stats_frame = ctk.CTkFrame(self.sidebar_panel, fg_color="transparent")
        self.stats_frame.pack(fill="x", padx=30, pady=20)
        
        self.tot_title = ctk.CTkLabel(self.stats_frame, text="Total Spent", font=ctk.CTkFont(size=16), text_color=COLOR_TEXT_MUTED)
        self.tot_title.pack(anchor="w")

        self.tot_lbl = ctk.CTkLabel(self.stats_frame, text="₹0.00", font=ctk.CTkFont(size=32, weight="bold"), text_color=COLOR_TEXT)
        self.tot_lbl.pack(anchor="w", pady=(5, 0))

        self.add_expense_btn = ctk.CTkButton(self.sidebar_panel, text=f"+ Add {category}", command=self.open_add_expense, height=45, font=ctk.CTkFont(weight="bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER)
        self.add_expense_btn.pack(pady=30, padx=30, fill="x", side="bottom")

        self.refresh_data()

    def refresh_data(self):
        for widget in self.expenses_scrollable.winfo_children():
            widget.destroy()

        expenses = self.db.get_expenses_by_category(self.user_id, self.category)
        
        if not expenses:
            lbl = ctk.CTkLabel(self.expenses_scrollable, text=f"No expenses found for {self.category}.", text_color=COLOR_TEXT_MUTED, font=ctk.CTkFont(size=14))
            lbl.pack(pady=40)
            self.tot_lbl.configure(text="₹0.00")
            return

        total = 0
        for e_id, date_str, amount, name, image_path in expenses:
            total += amount
            item_frame = ctk.CTkFrame(self.expenses_scrollable, fg_color=COLOR_BG, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
            item_frame.pack(fill="x", pady=6, padx=10)
            
            top_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
            top_frame.pack(fill="x", padx=15, pady=(15, 5))
            
            n_lbl = ctk.CTkLabel(top_frame, text=name, font=ctk.CTkFont(size=16, weight="bold"), text_color=COLOR_TEXT)
            n_lbl.pack(side="left")
            
            a_lbl = ctk.CTkLabel(top_frame, text=f"₹{amount:.2f}", text_color=COLOR_DANGER, font=ctk.CTkFont(size=18, weight="bold"))
            a_lbl.pack(side="right")
            
            bot_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
            bot_frame.pack(fill="x", padx=15, pady=(0, 15))
            
            d_obj = datetime.strptime(date_str, "%Y-%m-%d")
            d_lbl = ctk.CTkLabel(bot_frame, text=d_obj.strftime("%b %d, %Y"), font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_MUTED)
            d_lbl.pack(side="left")

            # Actions Frame
            actions_frame = ctk.CTkFrame(bot_frame, fg_color="transparent")
            actions_frame.pack(side="right")
            
            if image_path:
                view_btn = ctk.CTkButton(actions_frame, text="View Bill", width=60, height=20, font=ctk.CTkFont(size=10, weight="bold"), fg_color="transparent", text_color=COLOR_TEXT, hover_color=COLOR_PANEL, command=lambda p=image_path: self.view_bill_image(p))
                view_btn.pack(side="left", padx=(0, 5))
            
            edit_btn = ctk.CTkButton(actions_frame, text="Edit", width=40, height=20, font=ctk.CTkFont(size=10, weight="bold"), fg_color="transparent", text_color=COLOR_ACCENT, hover_color=COLOR_PANEL, command=lambda e=e_id, n=name, a=amount, c=self.category, d=date_str, ip=image_path: self.open_edit_expense(e, n, a, c, d, ip))
            edit_btn.pack(side="left", padx=(0, 5))
            
            del_btn = ctk.CTkButton(actions_frame, text="Delete", width=40, height=20, font=ctk.CTkFont(size=10, weight="bold"), fg_color="transparent", text_color=COLOR_DANGER, hover_color=COLOR_PANEL, command=lambda e=e_id, n=name, a=amount: self.delete_expense(e, n, a))
            del_btn.pack(side="left")

        self.tot_lbl.configure(text=f"₹{total:.2f}")

    def delete_expense(self, expense_id, name, amount):
        if messagebox.askyesno("Confirm", f"Are you sure you want to delete '{name}' (₹{amount:.2f})?"):
            self.db.delete_expense(expense_id, self.user_id)
            self.refresh_data()
            
    def open_edit_expense(self, expense_id, name, amount, category, date_str, image_path):
        AddExpenseModal(self, date_str, self.user_id, self.refresh_data, default_category=category, 
                        expense_id=expense_id, expense_name=name, expense_amount=amount, is_edit=True, expense_image_path=image_path)

    def view_bill_image(self, image_path):
        if not os.path.exists(image_path):
            messagebox.showerror("Error", "Image file not found.")
            return
            
        top = ctk.CTkToplevel(self)
        top.title("View Bill")
        top.geometry("600x800")
        top.configure(fg_color=COLOR_PANEL)
        
        try:
            pil_img = Image.open(image_path)
            
            # Simple resize to fit window roughly
            img_w, img_h = pil_img.size
            ratio = min(560/img_w, 760/img_h)
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)
            
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_w, new_h))
            lbl = ctk.CTkLabel(top, text="", image=ctk_img)
            lbl.pack(expand=True, padx=20, pady=20)
        except Exception as e:
            messagebox.showerror("Error", f"Could not load image: {e}")
            top.destroy()

    def open_add_expense(self):
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        AddExpenseModal(self, date_str, self.user_id, self.refresh_data, default_category=self.category)


# --- Yearly Report View ---
class YearlyReportView(ctk.CTkFrame):
    def __init__(self, master, user_id, db):
        super().__init__(master, fg_color="transparent") # type: ignore
        self.user_id = user_id
        self.db = db
        self.current_year = datetime.now().year
        self.income_categories = ["Wages", "Interest/dividends", "Miscellaneous", "Gift"]
        
        self.pack(fill="both", expand=True)
        
        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", pady=(0, 20))
        
        self.title_lbl = ctk.CTkLabel(self.header_frame, text=f"Yearly Report - {self.current_year}", font=ctk.CTkFont(size=24, weight="bold"), text_color=COLOR_TEXT)
        self.title_lbl.pack(side="left")
        
        self.download_btn = ctk.CTkButton(self.header_frame, text="Download PDF", font=ctk.CTkFont(weight="bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=self.download_pdf)
        self.download_btn.pack(side="right")
        
        self.year_controls = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.year_controls.pack(side="right", padx=20)
        
        self.prev_btn = ctk.CTkButton(self.year_controls, text="<", width=30, command=self.prev_year)
        self.prev_btn.pack(side="left", padx=5)
        self.next_btn = ctk.CTkButton(self.year_controls, text=">", width=30, command=self.next_year)
        self.next_btn.pack(side="left", padx=5)
        
        self.table_frame = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12, border_color=COLOR_BORDER, border_width=1)
        self.table_frame.pack(fill="both", expand=True, pady=10)
        
        self.refresh_data()
        
    def prev_year(self):
        self.current_year -= 1
        self.title_lbl.configure(text=f"Yearly Report - {self.current_year}")
        self.refresh_data()
        
    def next_year(self):
        self.current_year += 1
        self.title_lbl.configure(text=f"Yearly Report - {self.current_year}")
        self.refresh_data()
        
    def get_data(self):
        expenses_monthly = {cat: {m: 0.0 for m in range(1, 13)} for cat in CATEGORIES}
        expenses_total_monthly = {m: 0.0 for m in range(1, 13)}
        income_monthly = {cat: {m: 0.0 for m in range(1, 13)} for cat in self.income_categories}
        
        for m in range(1, 13):
            raw = self.db.get_expenses_by_month(self.user_id, self.current_year, m)
            for _, raw_amt, raw_cat in raw:
                amt_val = float(raw_amt)
                cat_str = str(raw_cat)
                if cat_str in self.income_categories:
                    income_monthly[cat_str][m] += amt_val
                else:
                    if cat_str in expenses_monthly:
                        expenses_monthly[cat_str][m] += amt_val
                    else:
                        if "Other" in expenses_monthly:
                            expenses_monthly["Other"][m] += amt_val
                    expenses_total_monthly[m] += amt_val
        return expenses_monthly, expenses_total_monthly, income_monthly

    def refresh_data(self):
        for widget in self.table_frame.winfo_children():
            widget.destroy()
            
        expenses_monthly, expenses_total_monthly, income_monthly = self.get_data()
        months_headers = ["Category", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Year"]
        
        self.table_frame.grid_columnconfigure(0, weight=2)
        for i in range(1, 14):
            self.table_frame.grid_columnconfigure(i, weight=1)
            
        self.row_idx = 0
        
        lbl = ctk.CTkLabel(self.table_frame, text="Expenses", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_ACCENT)
        lbl.grid(row=self.row_idx, column=0, sticky="w", pady=(15, 5), padx=10)
        self.row_idx += 1
        
        for i, h in enumerate(months_headers):
            text = "  " + h if i == 0 else h
            lbl = ctk.CTkLabel(self.table_frame, text=text, font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_ACCENT, anchor="w" if i==0 else "center")
            lbl.grid(row=self.row_idx, column=i, pady=5, padx=2, sticky="nsew")
        self.row_idx += 1
        
        def add_row(title, data_dict=None, list_data=None, is_total=False):
            bg_color = COLOR_BORDER if is_total else (COLOR_BG if self.row_idx % 2 == 0 else "#111111")
            
            for i in range(14):
                text = ""
                if i == 0:
                    text = "  " + title
                elif i < 13:
                    if data_dict:
                        text = f"₹{data_dict[i]:.2f}"
                    elif list_data:
                        text = f"₹{list_data[i-1]:.2f}"
                else:
                    if data_dict:
                        text = f"₹{sum(data_dict.values()):.2f}"
                    elif list_data:
                        text = f"₹{sum(list_data):.2f}"
                
                anchor = "w" if i == 0 else "center"
                lbl = ctk.CTkLabel(self.table_frame, text=text, fg_color=bg_color, corner_radius=0, font=ctk.CTkFont(size=12, weight="bold" if is_total else "normal"), text_color=COLOR_TEXT, anchor=anchor)
                lbl.grid(row=self.row_idx, column=i, sticky="nsew", padx=1, pady=1, ipady=5)
            self.row_idx += 1
            
        for cat in CATEGORIES:
            if any(v != 0 for v in expenses_monthly[cat].values()):
                add_row(cat, data_dict=expenses_monthly[cat])
            
        add_row("Total", data_dict=expenses_total_monthly, is_total=True)
        
        inc_totals_by_m = {m: 0.0 for m in range(1, 13)}
        for cat in self.income_categories:
            for m in range(1, 13):
                inc_totals_by_m[m] += income_monthly[cat][m]
                
        lbl = ctk.CTkLabel(self.table_frame, text="Income", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_ACCENT)
        lbl.grid(row=self.row_idx, column=0, sticky="w", pady=(25, 5), padx=10)
        self.row_idx += 1
        
        for i, h in enumerate(months_headers):
            text = "  " + h if i == 0 else h
            lbl = ctk.CTkLabel(self.table_frame, text=text, font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_ACCENT, anchor="w" if i==0 else "center")
            lbl.grid(row=self.row_idx, column=i, pady=5, padx=2, sticky="nsew")
        self.row_idx += 1
        
        for cat in self.income_categories:
            if any(v != 0 for v in income_monthly[cat].values()):
                add_row(cat, data_dict=income_monthly[cat])
            
        add_row("Total", data_dict=inc_totals_by_m, is_total=True)

    def download_pdf(self):
        if not HAS_FPDF:
            messagebox.showerror("Error", "FPDF Library not found. Cannot generate PDF.")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"Budget_Report_{self.current_year}.pdf",
            title="Save Yearly Report as PDF"
        )
        if not file_path:
            return
            
        try:
            self._create_pdf(file_path)
            messagebox.showinfo("Success", f"PDF successfully saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save PDF:\n{str(e)}")
            
    def _create_pdf(self, output_path):
        expenses_monthly, expenses_total_monthly, income_monthly = self.get_data()
        
        pdf = FPDF(orientation='L', unit='mm', format='A4') 
        pdf.add_page()
        pdf.set_font("helvetica", style="B", size=16)
        pdf.cell(0, 10, f"Yearly Report - {self.current_year}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        
        months_headers = ["Category", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Year"]
        col_w_cat = 45
        col_w_month = 18
        
        def draw_row(cells, is_header=False, is_bold=False):
            pdf.set_font("helvetica", style="B" if (is_header or is_bold) else "", size=9)
            if is_header:
                pdf.set_text_color(200, 0, 0)
                pdf.set_fill_color(255, 255, 255)
            else:
                pdf.set_text_color(0, 0, 0)
                pdf.set_fill_color(210, 225, 240)
            
            fill = not is_header
            for idx, text in enumerate(cells):
                w = col_w_cat if idx == 0 else col_w_month
                pdf.cell(w, 8, txt=str(text), border=1, fill=fill, align="C" if idx > 0 else "L")
            pdf.ln()

        pdf.set_font("helvetica", style="B", size=14)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 10, "Expenses", new_x="LMARGIN", new_y="NEXT")
        
        draw_row(["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Year"], is_header=True)
        
        for cat in CATEGORIES:
            if any(v != 0 for v in expenses_monthly[cat].values()):
                row = [cat]
                cat_year_total: float = 0.0
                for m in range(1, 13):
                    val = expenses_monthly[cat][m]
                    row.append(f"Rs. {val:,.2f}")
                    cat_year_total += val
                row.append(f"Rs. {cat_year_total:,.2f}")
                draw_row(row)
            
        exp_row = ["Total"]
        total_exp_year: float = 0.0
        for m in range(1, 13):
            val = expenses_total_monthly[m]
            exp_row.append(f"Rs. {val:,.2f}")
            total_exp_year += val
        exp_row.append(f"Rs. {total_exp_year:,.2f}")
        
        pdf.set_font("helvetica", style="B", size=9)
        pdf.set_text_color(255, 255, 255)
        pdf.set_fill_color(120, 120, 120)
        for idx, text in enumerate(exp_row):
            w = col_w_cat if idx == 0 else col_w_month
            pdf.cell(w, 8, txt=str(text), border=1, fill=True, align="C" if idx > 0 else "L")
        pdf.ln()
        
        inc_totals_by_m = {m: 0.0 for m in range(1, 13)}
        for cat in self.income_categories:
            for m in range(1, 13):
                inc_totals_by_m[m] += income_monthly[cat][m]
                
        pdf.ln(10)
        
        pdf.set_font("helvetica", style="B", size=14)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 10, "Income", new_x="LMARGIN", new_y="NEXT")
        
        draw_row(months_headers, is_header=True)
        
        year_total_income = 0.0
        for cat in self.income_categories:
            if any(v != 0 for v in income_monthly[cat].values()):  # type: ignore
                row = [cat]
                cat_year_total = 0.0
                for m in range(1, 13):
                    val = income_monthly[cat][m]  # type: ignore
                    row.append(f"Rs. {val:,.2f}")
                    cat_year_total = cat_year_total + val  # type: ignore
                row.append(f"Rs. {cat_year_total:,.2f}")
                year_total_income = year_total_income + cat_year_total  # type: ignore
                draw_row(row)
            
        total_inc_row = ["Total"]
        for m in range(1, 13):
            total_inc_row.append(f"Rs. {inc_totals_by_m[m]:,.2f}")
        total_inc_row.append(f"Rs. {year_total_income:,.2f}")
        
        pdf.set_font("helvetica", style="B", size=9)
        pdf.set_text_color(255, 255, 255)
        pdf.set_fill_color(120, 120, 120)
        for idx, text in enumerate(total_inc_row):
            w = col_w_cat if idx == 0 else col_w_month
            pdf.cell(w, 8, txt=str(text), border=1, fill=True, align="C" if idx > 0 else "L")
        pdf.ln()

        # Save to file
        pdf.output(output_path)

class MainAppWindow(ctk.CTkFrame):
    def __init__(self, master, user_id, on_logout):
        super().__init__(master, fg_color=COLOR_BG) # type: ignore
        self.user_id = user_id
        self.on_logout = on_logout
        self.db = Database()
        self.current_view_name = "Home"
        self.view_widget = None

        self.pack(fill="both", expand=True)

        TopNavigationBar(self, show_logout=True, on_logout=self.on_logout)

        self.sidebar_menu = SidebarMenu(self, current_view=self.current_view_name, on_nav=self.switch_view)

        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.switch_view("Home")

    def switch_view(self, view_name):
        self.current_view_name = view_name
        
        if hasattr(self, "sidebar_menu") and self.sidebar_menu:
            self.sidebar_menu.set_active(view_name)
            
        if self.view_widget:
            self.view_widget.destroy() # type: ignore

        if view_name == "Home":
            self.view_widget = HomeView(self.content_container, self.user_id)
        elif view_name == "Yearly Report":
            self.view_widget = YearlyReportView(self.content_container, self.user_id, self.db)
        else:
            self.view_widget = CategoryView(self.content_container, self.user_id, view_name)

class App(ctk.CTk):
    def __init__(self):
        super().__init__() # type: ignore
        self.title("Budget Calendar")
        self.geometry("1400x900")
        self.minsize(900, 600)
        self.configure(fg_color=COLOR_BG)

        # Maximize window on startup
        try:
            self.state("zoomed")
        except Exception:
            self.attributes("-zoomed", True)

        self.current_user_id = None
        self.current_view = None

        self.show_login()

    def show_login(self):
        if self.current_view:
            self.current_view.destroy() # type: ignore
        self.current_view = LoginWindow(self, self.on_login_success)

    def on_login_success(self, user_id):
        self.current_user_id = user_id
        if self.current_view:
            self.current_view.destroy() # type: ignore
        self.current_view = MainAppWindow(self, self.current_user_id, self.show_login)


if __name__ == "__main__":
    app = App()
    app.mainloop()

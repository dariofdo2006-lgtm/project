import os
import calendar
from fpdf import FPDF
import io
import base64
from datetime import datetime
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from database import Database

app = Flask(__name__)
# In production, set this from an environment variable!
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "budget_calendar_super_secret")

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
# Only makedirs here if you want it on launch, otherwise just ensure it
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Create a single database instance
db = Database()

def process_recurring_expenses(user_id):
    now = datetime.now()
    cur_year, cur_month = now.year, now.month
    prev_month, prev_year = (12, cur_year - 1) if cur_month == 1 else (cur_month - 1, cur_year)
        
    prev_month_str = f"{prev_year:04d}-{prev_month:02d}"
    db.execute("SELECT amount, category, name, image_path, date FROM expenses WHERE user_id = ? AND is_recurring = 1 AND date LIKE ?", (user_id, f"{prev_month_str}%"))
    prev_expenses = db.cursor.fetchall()
    
    cur_month_str = f"{cur_year:04d}-{cur_month:02d}"
    db.execute("SELECT count(*) FROM expenses WHERE user_id = ? AND is_recurring = 1 AND date LIKE ?", (user_id, f"{cur_month_str}%"))
    count = db.cursor.fetchone()[0]
    
    if count == 0 and prev_expenses:
        for exp in prev_expenses:
            try:
                day = exp[4].split("-")[2]
                new_date = f"{cur_year:04d}-{cur_month:02d}-{day}"
                db.add_expense(user_id, new_date, exp[0], exp[1], exp[2], exp[3], True)
            except Exception:
                pass

@app.context_processor
def inject_global_vars():
    if "user_id" in session:
        user_id = session["user_id"]
        currency = db.get_settings(user_id)
        expense_cats = db.get_categories(user_id, 'expense')
        income_cats = db.get_categories(user_id, 'income')
        return dict(
            currency=currency,
            categories=expense_cats,
            income_categories=income_cats
        )
    return dict(categories=[], income_categories=[], currency="₹")

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    now = datetime.now()
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)
    selected_date = request.args.get("date", now.strftime("%Y-%m-%d"))
    
    # Base data
    raw_expenses = db.get_expenses_by_month(user_id, year, month)
    
    total_income = 0.0
    total_expenses = 0.0
    
    # Process monthly numbers
    income_categories = db.get_categories(user_id, 'income')
    for row in raw_expenses:
        _, amount, category = row
        if category in income_categories:
            total_income += amount
        else:
            total_expenses += amount
            
    cash_diff = total_income - total_expenses
    
    # Get daily specific expenses
    daily_expenses = db.get_expenses_by_date(user_id, selected_date)
    
    return render_template(
        "index.html",
        year=year,
        month=month,
        selected_date=selected_date,
        month_name=calendar.month_name[month],
        total_income=total_income,
        total_expenses=total_expenses,
        cash_diff=cash_diff,
        daily_expenses=daily_expenses,
        active_view='home'
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.json
        username = data.get("username")
        password = data.get("password")
        
        user_id = db.login_user(username, password)
        if user_id:
            session["user_id"] = user_id
            try:
                process_recurring_expenses(user_id)
            except Exception as e:
                print(f"Recurring processing failed: {e}")
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Invalid username or password"})
        
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    
    if db.register_user(username, password):
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Username already exists"})

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))

@app.route("/api/expense", methods=["POST"])
def add_expense():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
        
    data = request.json
    user_id = session["user_id"]
    date = data.get("date")
    try:
        amount = float(data.get("amount") or 0)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid amount"}), 400
    category = data.get("category")
    name = data.get("name")
    is_recurring = data.get("is_recurring", False)
    
    if not (date and amount and category and name):
        return jsonify({"success": False, "message": "All fields required"}), 400
        
    expense_id = db.add_expense(user_id, date, amount, category, name, None, is_recurring)
    return jsonify({"success": True, "id": expense_id})

@app.route("/api/expense/<int:expense_id>/receipt", methods=["POST"])
def upload_receipt(expense_id):
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    
    if 'file' not in request.files:
        return jsonify({"success": False}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False}), 400
        
    encoded_string = base64.b64encode(file.read()).decode('utf-8')
    data_uri = f"data:{file.mimetype};base64,{encoded_string}"
    
    db.execute("UPDATE expenses SET image_path = ? WHERE id = ? AND user_id = ?", (data_uri, expense_id, session["user_id"]))
    
    return jsonify({"success": True})

@app.route("/api/receipt/<int:expense_id>")
def view_receipt(expense_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    receipt_data = db.get_receipt(expense_id, session["user_id"])
    if not receipt_data:
        return "No receipt found", 404
        
    return f'<html><body style="margin:0;display:flex;justify-content:center;align-items:center;background:#000;"><img src="{receipt_data}" style="max-width:100%;max-height:100vh;"></body></html>'

@app.route("/api/expense/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
        
    db.delete_expense(expense_id, session["user_id"])
    return jsonify({"success": True})

@app.route("/api/expense/<int:expense_id>", methods=["PUT"])
def update_expense(expense_id):
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
        
    data = request.json
    user_id = session["user_id"]
    date = data.get("date")
    try:
        amount = float(data.get("amount") or 0)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid amount"}), 400
    category = data.get("category")
    name = data.get("name")
    is_recurring = data.get("is_recurring", False)
    
    if not (date and amount and category and name):
        return jsonify({"success": False, "message": "All fields required"}), 400
        
    db.update_expense(expense_id, user_id, date, amount, category, name, is_recurring)
    return jsonify({"success": True})

@app.route("/category/<path:category_name>")
def category_view(category_name):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    expenses = db.get_expenses_by_category(user_id, category_name)
    
    return render_template(
        "category.html",
        category_name=category_name,
        expenses=expenses,
        active_view=category_name
    )

@app.route("/api/export")
def export_pdf():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    user_id = session["user_id"]
    db.execute("SELECT date, amount, category, name FROM expenses WHERE user_id = ? ORDER BY date DESC", (user_id,))
    rows = db.cursor.fetchall()
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Budget Export", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)
    
    pdf.set_font("helvetica", size=10)
    with pdf.table() as table:
        header_row = table.row()
        for header in ["Date", "Amount", "Category", "Description"]:
            header_row.cell(header)
        for data_row in rows:
            table_row = table.row()
            for datum in data_row:
                table_row.cell(str(datum))
    
    pdf_bytes = bytes(pdf.output())
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-disposition": "attachment; filename=budget_export.pdf"}
    )

@app.route("/search")
def search_view():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    user_id = session["user_id"]
    q = request.args.get("q", "")
    
    search_pattern = f"%{q}%"
    db.execute("""
        SELECT id, date, amount, category, name, CASE WHEN image_path IS NOT NULL AND image_path != '' THEN 1 ELSE 0 END as has_image, is_recurring 
        FROM expenses 
        WHERE user_id = ? AND (name LIKE ? OR category LIKE ?) 
        ORDER BY date DESC
    """, (user_id, search_pattern, search_pattern))
    
    expenses = db.cursor.fetchall()
    
    return render_template(
        "category.html",
        category_name=f'Search Results for "{q}"',
        expenses=expenses,
        active_view="search"
    )

@app.route("/yearly")
def yearly_view():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    user_id = session["user_id"]
    now = datetime.now()
    year = request.args.get("year", now.year, type=int)
    
    yearly_income = 0.0
    yearly_expenses = 0.0
    monthly_incomes = []
    monthly_expenses = []
    
    income_categories = db.get_categories(user_id, 'income')
    for m in range(1, 13):
        raw_expenses = db.get_expenses_by_month(user_id, year, m)
        m_inc = 0.0
        m_exp = 0.0
        for _, amount, category in raw_expenses:
            if category in income_categories:
                m_inc += amount
            else:
                m_exp += amount
        monthly_incomes.append(m_inc)
        monthly_expenses.append(m_exp)
        yearly_income += m_inc
        yearly_expenses += m_exp
                
    return render_template(
        "yearly.html",
        year=year,
        yearly_income=yearly_income,
        yearly_expenses=yearly_expenses,
        monthly_incomes=monthly_incomes,
        monthly_expenses=monthly_expenses,
        active_view="yearly"
    )

@app.route("/api/calculator/save", methods=["POST"])
def save_calculator():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    data = request.json
    calc_type = data.get("type")
    config_data = data.get("data")
    
    if not calc_type or not config_data:
        return jsonify({"success": False, "message": "Missing fields"}), 400
        
    db.save_calculator_state(session["user_id"], calc_type, json.dumps(config_data))
    return jsonify({"success": True})

@app.route("/calculator")
def calculator_view():
    if "user_id" not in session:
        return redirect(url_for("login"))
        
    calc_type = request.args.get("type", "standard")
    saved_state = db.get_calculator_state(session["user_id"], calc_type) or 'null'
        
    return render_template(
        "calculator.html",
        active_view=f"calculator_{calc_type}",
        calc_type=calc_type,
        saved_state=saved_state
    )

@app.route("/settings")
def settings_view():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    return render_template("settings.html", active_view="settings")

@app.route("/api/settings/currency", methods=["POST"])
def update_currency():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    currency = request.json.get("currency_symbol", "₹")
    currency = currency[:3] # Limit to 3 chars
    db.update_settings(session["user_id"], currency)
    return jsonify({"success": True})

@app.route("/api/categories", methods=["POST"])
def add_custom_category():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    name = request.json.get("name", "").strip()
    cat_type = request.json.get("type", "expense")
    if not name or cat_type not in ["expense", "income"]:
        return jsonify({"success": False, "message": "Invalid parameters"}), 400
        
    db.add_category(session["user_id"], name, cat_type)
    return jsonify({"success": True})

@app.route("/api/categories/<cat_type>/<name>", methods=["DELETE"])
def delete_custom_category(cat_type, name):
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
        
    db.delete_category(session["user_id"], name, cat_type)
    return jsonify({"success": True})

if __name__ == "__main__":
    import threading
    import socket
    import traceback

    port = 5000
    # Check if port 5000 is occupied (by a previous crashed/zombie process)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sock.connect_ex(('127.0.0.1', port)) == 0:
        port = 5005
    sock.close()

    def open_browser():
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            # Automatically launches Microsoft Edge with the correct port
            os.system(f'start msedge "http://127.0.0.1:{port}/"')
            
    threading.Timer(1.5, open_browser).start()
    
    try:
        app.run(debug=True, host="0.0.0.0", port=port)
    except Exception as e:
        with open("crash.log", "w") as f:
            f.write("The application crashed while starting. Error:\n\n")
            traceback.print_exc(file=f)
        os.system("start notepad crash.log")

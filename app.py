import os
import calendar
import io
import base64
import secrets
from datetime import datetime, timedelta
import json
import csv
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response, g
from werkzeug.exceptions import RequestEntityTooLarge

def load_env_file(path=".env"):
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env_file()

from database import Database
from ocr import scan_receipt_locally

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    FPDF = None
    HAS_FPDF = False

# Try to import pandas for Excel export
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    pd = None
    import logging
    logging.warning("Pandas not installed. Excel export will not work.")

app = Flask(__name__)
# In production, set this from an environment variable!
secret_key = os.environ.get("FLASK_SECRET_KEY")
if secret_key:
    app.secret_key = secret_key
else:
    # Generate a secure random key for development
    import secrets
    app.secret_key = secrets.token_urlsafe(32)
    import logging
    logging.warning("Using auto-generated secret key. Set FLASK_SECRET_KEY environment variable in production!")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

@app.before_request
def redirect_www():
    """Redirect www to non-www domain with 301."""
    if request.host.startswith('www.'):
        new_url = request.url.replace('www.', '', 1)
        return redirect(new_url, code=301)


UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
# Only makedirs here if you want it on launch, otherwise just ensure it
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Create a single database instance
db = Database()
ALLOWED_RECEIPT_MIMETYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token

def validate_csrf():
    sent_token = request.headers.get("X-CSRF-Token")
    expected_token = session.get("csrf_token")
    if not expected_token or not sent_token or not secrets.compare_digest(sent_token, expected_token):
        return False
    return True

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"success": False, "message": "Unauthorized"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def process_recurring_expenses(user_id):
    now = datetime.now()
    cur_year, cur_month = now.year, now.month
    prev_month, prev_year = (12, cur_year - 1) if cur_month == 1 else (cur_month - 1, cur_year)
        
    prev_month_str = f"{prev_year:04d}-{prev_month:02d}"
    prev_expenses = db.get_recurring_expenses(user_id, prev_month_str)
    
    cur_month_str = f"{cur_year:04d}-{cur_month:02d}"
    count = db.count_recurring_expenses(user_id, cur_month_str)
    
    if count == 0 and prev_expenses:
        for exp in prev_expenses:
            try:
                source_date = datetime.strptime(exp[4], "%Y-%m-%d")
                last_day_of_month = calendar.monthrange(cur_year, cur_month)[1]
                target_day = min(source_date.day, last_day_of_month)
                new_date = f"{cur_year:04d}-{cur_month:02d}-{target_day:02d}"
                db.add_expense(user_id, new_date, exp[0], exp[1], exp[2], exp[3], True)
            except Exception as e:
                import logging
                logging.warning(f"Recurring expense copy skipped: {e}")

def get_cached_categories(user_id, cat_type=None):
    if not hasattr(g, 'categories_cache'):
        g.categories_cache = db.get_categories(user_id)
    if cat_type:
        return [c[0] for c in g.categories_cache if c[1] == cat_type]
    return g.categories_cache

def get_cached_settings(user_id):
    if not hasattr(g, 'settings_cache'):
        g.settings_cache = db.get_settings(user_id)
    return g.settings_cache

@app.context_processor
def inject_global_vars():
    backend_name = db.backend_name()
    show_backend_badge = os.environ.get("SHOW_BACKEND_BADGE", "1").lower() in {"1", "true", "yes"}
    if "user_id" in session:
        user_id = session["user_id"]
        try:
            currency = get_cached_settings(user_id)
            expense_cats = get_cached_categories(user_id, 'expense')
            income_cats = get_cached_categories(user_id, 'income')
            return dict(
                currency=currency,
                categories=expense_cats,
                income_categories=income_cats,
                csrf_token=get_csrf_token(),
                backend_name=backend_name,
                show_backend_badge=show_backend_badge
            )
        except Exception:
            app.logger.exception("Failed to load user context")

    return dict(
        categories=[],
        income_categories=[],
        currency="₹",
        csrf_token=get_csrf_token(),
        backend_name=backend_name,
        show_backend_badge=show_backend_badge
    )
@app.context_processor
def inject_backend_vars():
    return dict(
        backend_name=db.backend_name(),
        show_backend_badge=os.environ.get("SHOW_BACKEND_BADGE", "1").lower() in {"1", "true", "yes"}
    )

@app.route("/api/health")
def health():
    return jsonify({
        "success": True,
        "backend": db.backend_name(),
        "firebase": db.is_firebase,
        "pdf_export": HAS_FPDF,
        "excel_export": HAS_PANDAS
    })

@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(_e):
    return jsonify({"success": False, "message": "File too large (max 4MB)."}), 413

@app.route("/")
@login_required
def index():
    user_id = session["user_id"]
    try:
        process_recurring_expenses(user_id)
        now = datetime.now()
        year = request.args.get("year", now.year, type=int)
        month = request.args.get("month", now.month, type=int)
        if month is None or month < 1 or month > 12:
            month = now.month
        selected_date = request.args.get("date", now.strftime("%Y-%m-%d"))

        # Base data
        raw_expenses = db.get_expenses_by_month(user_id, year, month)

        total_income = 0.0
        total_expenses = 0.0

        # Process monthly numbers
        income_categories = get_cached_categories(user_id, 'income')
        for row in raw_expenses:
            _, amount, category = row
            if category in income_categories:
                total_income += amount
            else:
                total_expenses += amount

        cash_diff = total_income - total_expenses

        # Get all transactions for the current month (for right-side list)
        monthly_expenses = db.get_expenses_by_month_detailed(user_id, year, month)

        return render_template(
            "index.html",
            year=year,
            month=month,
            selected_date=selected_date,
            month_name=calendar.month_name[month],
            total_income=total_income,
            total_expenses=total_expenses,
            cash_diff=cash_diff,
            monthly_expenses=monthly_expenses,
            active_view='home'
        )
    except Exception:
        app.logger.exception("Failed to render dashboard")
        now = datetime.now()
        year = request.args.get("year", now.year, type=int)
        month = request.args.get("month", now.month, type=int)
        if month is None or month < 1 or month > 12:
            month = now.month
        selected_date = request.args.get("date", now.strftime("%Y-%m-%d"))
        return render_template(
            "index.html",
            year=year,
            month=month,
            selected_date=selected_date,
            month_name=calendar.month_name[month],
            total_income=0.0,
            total_expenses=0.0,
            cash_diff=0.0,
            monthly_expenses=[],
            active_view='home'
        )
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not validate_csrf():
            return jsonify({"success": False, "message": "Invalid CSRF token"}), 403

        data = request.json or {}
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"success": False, "message": "Username and password are required"}), 400
        
        try:
            user_id = db.login_user(username, password)
        except Exception:
            app.logger.exception("Login failed")
            user_id = None
            
        if user_id is not None:
            session["user_id"] = user_id
            session["username"] = username
            return jsonify({"success": True, "message": "Login successful"})
        else:
            return jsonify({"success": False, "message": "Invalid username or password"})
        
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403

    data = request.json or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400
    
    if db.register_user(username, password):
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Username already exists"})

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))

@app.route("/api/expense", methods=["POST"])
@login_required
def add_expense():
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403
        
    data = request.json
    user_id = session["user_id"]
    date = data.get("date")
    try:
        amount_raw = data.get("amount")
        if amount_raw is None or amount_raw == "":
            return jsonify({"success": False, "message": "Amount is required"}), 400
        amount = float(amount_raw)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid amount"}), 400
    category = data.get("category")
    name = data.get("name")
    is_recurring = data.get("is_recurring", False)
    
    if not date or not category or not name:
        return jsonify({"success": False, "message": "All fields required"}), 400
        
    expense_id = db.add_expense(user_id, date, amount, category, name, None, is_recurring)
    return jsonify({"success": True, "id": expense_id})

@app.route("/api/expense/<int:expense_id>/receipt", methods=["POST"])
@login_required
def upload_receipt(expense_id):
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403
    
    if 'file' not in request.files:
        return jsonify({"success": False}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False}), 400
    if file.mimetype not in ALLOWED_RECEIPT_MIMETYPES:
        return jsonify({"success": False, "message": "Unsupported file type"}), 400
        
    file_bytes = file.read()
    if not file_bytes:
        return jsonify({"success": False, "message": "Empty file"}), 400
    encoded_string = base64.b64encode(file_bytes).decode('utf-8')
    data_uri = f"data:{file.mimetype};base64,{encoded_string}"
    
    if not db.update_expense_receipt(expense_id, session["user_id"], data_uri):
        return jsonify({"success": False, "message": "Receipt target not found"}), 404
    
    return jsonify({"success": True})

@app.route("/api/receipt/scan", methods=["POST"])
@login_required
def scan_receipt():
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "message": "No file selected"}), 400
    if file.mimetype not in ALLOWED_RECEIPT_MIMETYPES:
        return jsonify({"success": False, "message": "Unsupported file type"}), 400

    file_bytes = file.read()
    if not file_bytes:
        return jsonify({"success": False, "message": "Empty file"}), 400

    scanned, err = scan_receipt_locally(file_bytes)
    if err:
        return jsonify({"success": False, "message": err}), 400

    name = str(scanned.get("name", "")).strip()
    raw_amount = scanned.get("amount", "")
    try:
        amount = float(raw_amount)
    except (ValueError, TypeError):
        amount = None
    category = str(scanned.get("category", "")).strip()

    return jsonify({
        "success": True,
        "data": {
            "name": name,
            "amount": amount,
            "category": category
        }
    })

@app.route("/api/receipt/<int:expense_id>")
@login_required
def view_receipt(expense_id):
    receipt_data = db.get_receipt(expense_id, session["user_id"])
    if not receipt_data:
        return "No receipt found", 404
        
    return f'<html><body style="margin:0;display:flex;justify-content:center;align-items:center;background:#000;"><img src="{receipt_data}" style="max-width:100%;max-height:100vh;"></body></html>'

@app.route("/api/expense/<int:expense_id>", methods=["DELETE"])
@login_required
def delete_expense(expense_id):
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403
        
    if not db.delete_expense(expense_id, session["user_id"]):
        return jsonify({"success": False, "message": "Transaction not found"}), 404
    return jsonify({"success": True})

@app.route("/api/expense/<int:expense_id>", methods=["PUT"])
@login_required
def update_expense(expense_id):
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403
        
    data = request.json
    user_id = session["user_id"]
    date = data.get("date")
    try:
        amount_raw = data.get("amount")
        if amount_raw is None or amount_raw == "":
            return jsonify({"success": False, "message": "Amount is required"}), 400
        amount = float(amount_raw)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid amount"}), 400
    category = data.get("category")
    name = data.get("name")
    is_recurring = data.get("is_recurring", False)
    
    if not date or not category or not name:
        return jsonify({"success": False, "message": "All fields required"}), 400
        
    if not db.update_expense(expense_id, user_id, date, amount, category, name, is_recurring):
        return jsonify({"success": False, "message": "Transaction not found"}), 404
    return jsonify({"success": True})

@app.route("/category/<path:category_name>")
@login_required
def category_view(category_name):
    user_id = session["user_id"]
    expenses = db.get_expenses_by_category(user_id, category_name)
    
    return render_template(
        "category.html",
        category_name=category_name,
        expenses=expenses,
        active_view=category_name
    )

@app.route("/api/export")
@login_required
def export_pdf():
    if not HAS_FPDF:
        return jsonify({"success": False, "message": "PDF export requires fpdf2 to be installed"}), 503
        
    user_id = session["user_id"]
    rows = db.get_all_expenses_for_export(user_id)
    
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

@app.route("/api/export/excel")
@login_required
def export_excel():
    if not HAS_PANDAS:
        return jsonify({"success": False, "message": "Excel export requires pandas and openpyxl to be installed"}), 503
    
    try:
        user_id = session["user_id"]
        
        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date and end_date:
            rows = db.get_expenses_by_date_range(user_id, start_date, end_date)
            filename = f"budget_export_{start_date}_to_{end_date}.xlsx"
        else:
            rows = db.get_all_expenses_for_export(user_id)
            filename = "budget_export.xlsx"
        
        if not rows:
            return jsonify({"success": False, "message": "No data to export"})
        
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=["Date", "Amount", "Category", "Description"])
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Budget Data', index=False)
            
            # Add summary sheet
            summary_data = {
                'Category': df['Category'].value_counts().index.tolist(),
                'Count': df['Category'].value_counts().values.tolist(),
                'Total Amount': df.groupby('Category')['Amount'].sum().values.tolist()
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    
    except Exception as e:
        return jsonify({"success": False, "message": f"Excel export failed: {str(e)}"})

@app.route("/api/export/csv")
@login_required
def export_csv():
    user_id = session["user_id"]
    
    # Get date range from query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date and end_date:
        # Export for date range
        rows = db.get_expenses_by_date_range(user_id, start_date, end_date)
        filename = f"budget_export_{start_date}_to_{end_date}.csv"
    else:
        # Export all data
        rows = db.get_all_expenses_for_export(user_id)
        filename = "budget_export.csv"
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(["Date", "Amount", "Category", "Description"])
    
    # Write data
    for row in rows:
        writer.writerow(row)
    
    # Convert to bytes
    csv_bytes = output.getvalue().encode('utf-8')
    
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@app.route("/api/export/json")
@login_required
def export_json():
    user_id = session["user_id"]
    
    # Get date range from query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date and end_date:
        rows = db.get_expenses_by_date_range(user_id, start_date, end_date)
        filename = f"budget_export_{start_date}_to_{end_date}.json"
    else:
        rows = db.get_all_expenses_for_export(user_id)
        filename = "budget_export.json"
    
    # Convert to JSON format
    data = {
        "export_date": datetime.now().isoformat(),
        "user_id": user_id,
        "date_range": {
            "start": start_date,
            "end": end_date
        } if start_date and end_date else None,
        "expenses": [
            {
                "date": row[0],
                "amount": row[1],
                "category": row[2],
                "description": row[3]
            }
            for row in rows
        ],
        "summary": {
            "total_expenses": len(rows),
            "total_amount": sum(row[1] for row in rows),
            "categories": list(set(row[2] for row in rows)),
            "date_range": {
                "start": min(row[0] for row in rows) if rows else None,
                "end": max(row[0] for row in rows) if rows else None
            }
        }
    }
    
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    json_bytes = json_str.encode('utf-8')
    
    return Response(
        json_bytes,
        mimetype="application/json",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@app.route("/api/export/report")
@login_required
def export_report():
    if not HAS_FPDF:
        return jsonify({"success": False, "message": "PDF report requires fpdf2 to be installed"}), 503
    
    try:
        user_id = session["user_id"]
        
        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date and end_date:
            rows = db.get_expenses_by_date_range(user_id, start_date, end_date)
            filename = f"budget_report_{start_date}_to_{end_date}.pdf"
        else:
            rows = db.get_all_expenses_for_export(user_id)
            filename = "budget_report.pdf"
        
        if not rows:
            return jsonify({"success": False, "message": "No data to generate report"})
        
        # Generate summary statistics
        total_amount = sum(row[1] for row in rows)
        category_totals = {}
        category_counts = {}
        
        for row in rows:
            category = row[2]
            amount = row[1]
            category_totals[category] = category_totals.get(category, 0) + amount
            category_counts[category] = category_counts.get(category, 0) + 1
        
        # Create enhanced PDF report
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", "B", 20)
        pdf.cell(0, 15, "Budget Analysis Report", new_x="LMARGIN", new_y="NEXT", align="C")
        
        # Add date range if specified
        if start_date and end_date:
            pdf.set_font("helvetica", size=12)
            pdf.cell(0, 8, f"Date Range: {start_date} to {end_date}", new_x="LMARGIN", new_y="NEXT", align="C")
            pdf.ln(5)
        
        pdf.ln(5)
        
        # Summary section
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(0, 10, "Summary", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", size=11)
        pdf.cell(0, 8, f"Total Transactions: {len(rows)}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"Total Amount: ₹{total_amount:,.2f}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)
        
        # Category breakdown
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(0, 10, "Category Breakdown", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", size=10)
        
        with pdf.table() as table:
            header_row = table.row()
            header_row.cell("Category")
            header_row.cell("Count")
            header_row.cell("Total Amount")
            header_row.cell("Percentage")
            
            for category, amount in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
                count = category_counts[category]
                percentage = (amount / total_amount * 100) if total_amount > 0 else 0
                
                data_row = table.row()
                data_row.cell(category)
                data_row.cell(str(count))
                data_row.cell(f"₹{amount:,.2f}")
                data_row.cell(f"{percentage:.1f}%")
        
        pdf.ln(10)
        
        # Recent transactions
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(0, 10, "Recent Transactions (Last 20)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", size=9)
        
        with pdf.table() as table:
            header_row = table.row()
            header_row.cell("Date")
            header_row.cell("Amount")
            header_row.cell("Category")
            header_row.cell("Description")
            
            for row in rows[:20]:  # Last 20 transactions
                data_row = table.row()
                for datum in row:
                    # Truncate long descriptions
                    datum_str = str(datum)
                    if len(datum_str) > 30:
                        data_row.cell(datum_str[:30] + "...")
                    else:
                        data_row.cell(datum_str)
        
        pdf_bytes = bytes(pdf.output())
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    
    except Exception as e:
        return jsonify({"success": False, "message": f"Report generation failed: {str(e)}"})

@app.route("/search")
@login_required
def search_view():
    user_id = session["user_id"]
    q = request.args.get("q", "")
    
    expenses = db.search_expenses(user_id, q)
    
    return render_template(
        "category.html",
        category_name=f'Search Results for "{q}"',
        expenses=expenses,
        active_view="search"
    )

@app.route("/yearly")
@login_required
def yearly_view():
    user_id = session["user_id"]
    now = datetime.now()
    year = request.args.get("year", now.year, type=int)
    
    yearly_income = 0.0
    yearly_expenses = 0.0
    monthly_incomes = []
    monthly_expenses = []
    
    income_categories = get_cached_categories(user_id, 'income')
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
@login_required
def save_calculator():
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403
    
    data = request.json
    calc_type = data.get("type")
    config_data = data.get("data")
    
    if not calc_type or not config_data:
        return jsonify({"success": False, "message": "Missing fields"}), 400
        
    db.save_calculator_state(session["user_id"], calc_type, json.dumps(config_data))
    return jsonify({"success": True})

@app.route("/calculator")
@login_required
def calculator_view():
    calc_type = request.args.get("type", "standard")
    saved_state = db.get_calculator_state(session["user_id"], calc_type) or 'null'
        
    return render_template(
        "calculator.html",
        active_view=f"calculator_{calc_type}",
        calc_type=calc_type,
        saved_state=saved_state
    )

@app.route("/settings")
@login_required
def settings_view():
    return render_template("settings.html", active_view="settings")

@app.route("/api/settings/currency", methods=["POST"])
@login_required
def update_currency():
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403
    currency = request.json.get("currency_symbol", "₹")
    currency = currency[:3] # Limit to 3 chars
    db.update_settings(session["user_id"], currency)
    return jsonify({"success": True})

@app.route("/api/categories", methods=["POST"])
@login_required
def add_custom_category():
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403
    name = request.json.get("name", "").strip()
    cat_type = request.json.get("type", "expense")
    if not name or cat_type not in ["expense", "income"]:
        return jsonify({"success": False, "message": "Invalid parameters"}), 400
        
    db.add_category(session["user_id"], name, cat_type)
    return jsonify({"success": True})

@app.route("/api/categories/<cat_type>/<name>", methods=["DELETE"])
@login_required
def delete_custom_category(cat_type, name):
    if not validate_csrf():
        return jsonify({"success": False, "message": "Invalid CSRF token"}), 403
        
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
        debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
        app.run(debug=debug, host="0.0.0.0", port=port)
    except Exception as e:
        with open("crash.log", "w") as f:
            f.write("The application crashed while starting. Error:\n\n")
            traceback.print_exc(file=f)
        os.system("start notepad crash.log")

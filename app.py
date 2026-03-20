import os
import calendar
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from database import Database

app = Flask(__name__)
# In production, set this from an environment variable!
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "budget_calendar_super_secret")

# Create a single database instance
db = Database()

CATEGORIES = [
    "Rent", "Grocery", "Food", "Water", "Electricity", "Transportation", 
    "Clothing", "Online Shopping", "Hospital", "Education", "Insurance", 
    "Entertainment", "Credit Card", "Emergency Fund", "Investment", "Other"
]
INCOME_CATEGORIES = ["Wages", "Interest/dividends", "Miscellaneous", "Gift"]

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
    for row in raw_expenses:
        _, amount, category = row
        if category in INCOME_CATEGORIES:
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
        categories=CATEGORIES,
        income_categories=INCOME_CATEGORIES
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
    amount = float(data.get("amount", 0))
    category = data.get("category")
    name = data.get("name")
    
    if not (date and amount and category and name):
        return jsonify({"success": False, "message": "All fields required"}), 400
        
    db.add_expense(user_id, date, amount, category, name)
    return jsonify({"success": True})

@app.route("/api/expense/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
        
    db.delete_expense(expense_id, session["user_id"])
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")

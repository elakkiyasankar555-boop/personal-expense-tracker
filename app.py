import os
import re
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, g
)
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash


# -------------------------
# Flask configuration
# -------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "expense-tracker-secret-key-change-this"
)

CSRFProtect(app)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "expense_tracker.db")


# -------------------------
# Categories
# -------------------------

INCOME_CATEGORIES = [
    "Salary",
    "Pocket Money",
    "Business Income",
    "Freelancing",
    "Other Income"
]

EXPENSE_CATEGORIES = [
    "Food",
    "Travel",
    "Shopping",
    "Education",
    "Medical",
    "Entertainment",
    "Bills",
    "Others"
]


# -------------------------
# Database connection
# -------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    connection = sqlite3.connect(DATABASE)
    connection.execute("PRAGMA foreign_keys = ON")

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    for table in ("income", "expenses"):
        connection.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

    connection.commit()
    connection.close()


# -------------------------
# Template filters
# -------------------------

@app.template_filter("money")
def money(value):
    try:
        return "₹{:,.2f}".format(float(value or 0))
    except (ValueError, TypeError):
        return "₹0.00"


# -------------------------
# Login protection
# -------------------------

def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


# -------------------------
# Home page
# -------------------------

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))
    return render_template(
        f"add_{kind}.html",
        categories=categories,
        page_title=page_title,
        values=values,
        current_year=date.today().isoformat()
    )


# -------------------------
# Register
# -------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("register"))

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        db = get_db()

        existing_user = db.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            flash("This email is already registered. Please login.", "warning")
            return redirect(url_for("login"))

        hashed_password = generate_password_hash(password)

        try:
            db.execute(
                """
                INSERT INTO users (full_name, email, password)
                VALUES (?, ?, ?)
                """,
                (full_name, email, hashed_password)
            )
            db.commit()
            flash("Account created successfully! Please login.", "success")
            return redirect(url_for("login"))

        except sqlite3.Error:
            db.rollback()
            flash("Unable to create account. Please try again.", "danger")

    return render_template("register.html")


# -------------------------
# Login
# -------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]

            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


# -------------------------
# Logout
# -------------------------

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# -------------------------
# Get transaction totals
# -------------------------

def get_total(table, user_id, month=None):
    db = get_db()

    if month:
        result = db.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM {table}
            WHERE user_id = ? AND substr(date, 1, 7) = ?
            """,
            (user_id, month)
        ).fetchone()
    else:
        result = db.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM {table}
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

    return float(result["total"])


# -------------------------
# Dashboard
# -------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    current_month = date.today().strftime("%Y-%m")
    month_name = date.today().strftime("%B %Y")

    total_income = get_total("income", user_id)
    total_expenses = get_total("expenses", user_id)
    balance = total_income - total_expenses

    month_income = get_total("income", user_id, current_month)
    month_expense = get_total("expenses", user_id, current_month)
    month_balance = month_income - month_expense

    db = get_db()

    recent_income = db.execute(
        """
        SELECT id, title, category, amount, date,
               description, 'Income' AS kind
        FROM income WHERE user_id = ?
        """,
        (user_id,)
    ).fetchall()

    recent_expenses = db.execute(
        """
        SELECT id, title, category, amount, date,
               description, 'Expense' AS kind
        FROM expenses WHERE user_id = ?
        """,
        (user_id,)
    ).fetchall()

    recent = sorted(
        list(recent_income) + list(recent_expenses),
        key=lambda item: item["date"],
        reverse=True
    )[:5]

    return render_template(
        "index.html",
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance,
        month_income=month_income,
        month_expense=month_expense,
        month_balance=month_balance,
        month_name=month_name,
        recent=recent
    )


# -------------------------
# Add income and expense
# -------------------------


@app.route("/add/<kind>", methods=["GET", "POST"])
@login_required
def add_transaction(kind):

    if kind not in ["income", "expense"]:
        return redirect(url_for("dashboard"))

    if kind == "income":
        table = "income"
        categories = INCOME_CATEGORIES
        page_title = "Add Income"
    else:
        table = "expenses"
        categories = EXPENSE_CATEGORIES
        page_title = "Add Expense"

    values = {
        "title": "",
        "category": "",
        "amount": "",
        "date": date.today().isoformat(),
        "description": ""
    }

    if request.method == "POST":

        values["title"] = request.form.get("title", "").strip()
        values["category"] = request.form.get("category", "").strip()
        values["amount"] = request.form.get("amount", "").strip()
        values["date"] = request.form.get("date", "").strip()
        values["description"] = request.form.get("description", "").strip()

        title = values["title"]
        category = values["category"]
        amount_text = values["amount"]
        transaction_date = values["date"]
        description = values["description"]

        if kind == "expense":
            category = "Others"

        try:
            amount = float(amount_text)
        except (ValueError, TypeError):
            flash("Please enter a valid amount.", "danger")
            return render_template(
                f"add_{kind}.html",
                categories=categories,
                page_title=page_title,
                values=values,
                current_year=date.today().year
            )

        if not title:
            flash("Please enter a title.", "danger")
            return render_template(
                f"add_{kind}.html",
                categories=categories,
                page_title=page_title,
                values=values,
                current_year=date.today().year
            )

        if kind == "income" and category not in categories:
            flash("Please select a valid income category.", "danger")
            return render_template(
                f"add_{kind}.html",
                categories=categories,
                page_title=page_title,
                values=values,
                current_year=date.today().year
            )

        if amount <= 0:
            flash("Amount must be greater than zero.", "danger")
            return render_template(
                f"add_{kind}.html",
                categories=categories,
                page_title=page_title,
                values=values,
                current_year=date.today().year
            )

        try:
            parsed_date = datetime.strptime(
                transaction_date, "%Y-%m-%d"
            ).date()

            if parsed_date > date.today():
                flash("Future dates are not allowed.", "danger")
                return render_template(
                    f"add_{kind}.html",
                    categories=categories,
                    page_title=page_title,
                    values=values,
                    current_year=date.today().year
                )

        except ValueError:
            flash("Please enter a valid date.", "danger")
            return render_template(
                f"add_{kind}.html",
                categories=categories,
                page_title=page_title,
                values=values,
                current_year=date.today().year
            )

        db = get_db()

        db.execute(
            f"""
            INSERT INTO {table}
            (user_id, title, category, amount, date, description)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                title,
                category,
                amount,
                transaction_date,
                description
            )
        )

        db.commit()

        flash(f"{page_title} saved successfully!", "success")
        return redirect(url_for("dashboard"))

    # This return handles GET requests and displays the form
    return render_template(
        f"add_{kind}.html",
        categories=categories,
        page_title=page_title,
        values=values,
        current_year=date.today().year
    )

# -------------------------
# Delete transaction
# -------------------------

def delete_transaction(kind, transaction_id):
    table = "income" if kind == "income" else "expenses"
    db = get_db()

    db.execute(
        f"DELETE FROM {table} WHERE id = ? AND user_id = ?",
        (transaction_id, session["user_id"])
    )
    db.commit()

    flash("Transaction deleted successfully.", "success")
    return redirect(url_for("transactions"))


@app.route("/income/delete/<int:transaction_id>", methods=["POST"])
@login_required
def delete_income(transaction_id):
    return delete_transaction("income", transaction_id)


@app.route("/expense/delete/<int:transaction_id>", methods=["POST"])
@login_required
def delete_expense(transaction_id):
    return delete_transaction("expense", transaction_id)


# -------------------------
# Transactions
# -------------------------

@app.route("/transactions")
@login_required
def transactions():
    user_id = session["user_id"]
    db = get_db()

    income_rows = db.execute(
        """
        SELECT id, title, category, amount, date, description,
               'Income' AS kind
        FROM income WHERE user_id = ?
        """,
        (user_id,)
    ).fetchall()

    expense_rows = db.execute(
        """
        SELECT id, title, category, amount, date, description,
               'Expense' AS kind
        FROM expenses WHERE user_id = ?
        """,
        (user_id,)
    ).fetchall()

    all_transactions = sorted(
        list(income_rows) + list(expense_rows),
        key=lambda item: item["date"],
        reverse=True
    )

    return render_template(
    "transactions.html",
    transactions=all_transactions,
    items=all_transactions,
    filters={
        "q": "",
        "type": "all",
        "category": "",
        "from_date": "",
        "to_date": ""
    }
)
    
# -------------------------
# Reports
# -------------------------

@app.route("/reports")
@login_required
def reports():
    user_id = session["user_id"]
    db = get_db()

    income_rows = db.execute(
        """
        SELECT date, amount FROM income
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchall()

    expense_rows = db.execute(
        """
        SELECT date, amount FROM expenses
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchall()

    total_income = get_total("income", user_id)
    total_expenses = get_total("expenses", user_id)

    return render_template(
        "reports.html",
        total_income=total_income,
        total_expenses=total_expenses,
        balance=total_income - total_expenses,
        income_rows=income_rows,
        expense_rows=expense_rows
    )


# -------------------------
# Chart API
# -------------------------

@app.route("/api/chart-data")
@login_required
def chart_data():
    user_id = session["user_id"]
    db = get_db()

    income_rows = db.execute(
        """
        SELECT substr(date, 1, 7) AS month,
               SUM(amount) AS total
        FROM income
        WHERE user_id = ?
        GROUP BY month
        ORDER BY month
        """,
        (user_id,)
    ).fetchall()

    expense_rows = db.execute(
        """
        SELECT substr(date, 1, 7) AS month,
               SUM(amount) AS total
        FROM expenses
        WHERE user_id = ?
        GROUP BY month
        ORDER BY month
        """,
        (user_id,)
    ).fetchall()

    income_data = {
        row["month"]: row["total"] for row in income_rows
    }
    expense_data = {
        row["month"]: row["total"] for row in expense_rows
    }

    months = sorted(set(income_data) | set(expense_data))

    return jsonify({
        "labels": months,
        "income": [income_data.get(month, 0) for month in months],
        "expenses": [expense_data.get(month, 0) for month in months]
    })


# -------------------------
# Error handlers
# -------------------------

@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    return render_template(
        "error.html",
        error_code=400,
        error_message="Your form session expired or the CSRF token is missing. Refresh the page and try again."
    ), 400


@app.errorhandler(404)
def page_not_found(error):
    return render_template(
        "error.html",
        error_code=404,
        error_message="The page you are looking for was not found."
    ), 404


@app.errorhandler(500)
def internal_server_error(error):
    return render_template(
        "error.html",
        error_code=500,
        error_message="Something went wrong. Please try again."
    ), 500


# -------------------------
# Start application
# -------------------------

init_db()

if __name__ == "__main__":
    app.run(debug=True)
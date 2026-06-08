from flask import Blueprint, request, render_template, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from app.database import get_db

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("auth.dashboard"))
    return render_template("home.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("auth.dashboard"))
        
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ? AND is_active = 1", (email,)
            ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("auth.dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    with get_db() as conn:
        courses = conn.execute("SELECT id, code, name FROM courses ORDER BY code").fetchall()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        reg_number = request.form.get("registration_number", "").strip().upper()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        course_id = request.form.get("course_id")
        if not all([full_name, reg_number, email, password, course_id]):
            flash("All fields are required.", "danger")
            return render_template("register.html", courses=courses)
        with get_db() as conn:
            if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
                flash("Email already registered.", "danger")
                return render_template("register.html", courses=courses)
            if conn.execute(
                "SELECT id FROM users WHERE registration_number = ?", (reg_number,)
            ).fetchone():
                flash("Registration number already exists.", "danger")
                return render_template("register.html", courses=courses)
            course = conn.execute(
                "SELECT department_id FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            conn.execute(
                """INSERT INTO users (email, password_hash, full_name, role, registration_number, course_id, department_id)
                   VALUES (?, ?, ?, 'student', ?, ?, ?)""",
                (
                    email,
                    generate_password_hash(password),
                    full_name,
                    reg_number,
                    course_id,
                    course["department_id"] if course else None,
                ),
            )
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("register.html", courses=courses)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    with get_db() as conn:
        departments = conn.execute("SELECT id, name FROM departments ORDER BY name").fetchall()
    
    if request.method == "POST":
        step = int(request.form.get("step", "1"))
        
        if step == 1:
            email = request.form.get("email", "").strip().lower()
            role = request.form.get("role", "student")
            registration_number = request.form.get("registration_number", "").strip().upper()
            department_id = request.form.get("department_id")
            
            with get_db() as conn:
                if role == "student":
                    user = conn.execute(
                        "SELECT * FROM users WHERE role='student' AND email = ? AND registration_number = ?",
                        (email, registration_number)
                    ).fetchone()
                else:
                    user = conn.execute(
                        "SELECT * FROM users WHERE role='lecturer' AND email = ? AND department_id = ?",
                        (email, department_id)
                    ).fetchone()
            
            if user:
                return render_template(
                    "forgot_password.html",
                    step=2,
                    user_id=user["id"],
                    departments=departments
                )
            
            flash("Invalid email or security verification details.", "danger")
            return render_template(
                "forgot_password.html",
                step=1,
                email=email,
                role=role,
                registration_number=registration_number,
                department_id=department_id,
                departments=departments
            )
            
        elif step == 2:
            user_id = request.form.get("user_id")
            password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")
            
            if not password or len(password) < 6:
                flash("Password must be at least 6 characters long.", "danger")
                return render_template("forgot_password.html", step=2, user_id=user_id, departments=departments)
                
            if password != confirm_password:
                flash("Passwords do not match.", "danger")
                return render_template("forgot_password.html", step=2, user_id=user_id, departments=departments)
                
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(password), user_id)
                )
            flash("Password updated successfully! Please log in.", "success")
            return redirect(url_for("auth.login"))
            
    return render_template("forgot_password.html", step=1, departments=departments)


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
        
    role = session.get("role")
    if role == "student":
        return redirect(url_for("student.student_dashboard"))
    if role == "lecturer":
        return redirect(url_for("lecturer.lecturer_dashboard"))
    return redirect(url_for("admin.admin_dashboard"))

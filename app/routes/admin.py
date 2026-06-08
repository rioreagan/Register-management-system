from flask import Blueprint, request, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from app.database import get_db
from app.auth import login_required, get_current_user

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/admin")
@login_required("admin")
def admin_dashboard():
    with get_db() as conn:
        stats = {
            "students": conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
            "lecturers": conn.execute("SELECT COUNT(*) FROM users WHERE role='lecturer'").fetchone()[0],
            "courses": conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
            "course_units": conn.execute("SELECT COUNT(*) FROM course_units").fetchone()[0],
            "sessions": conn.execute("SELECT COUNT(*) FROM lecture_sessions").fetchone()[0],
            "attendance_records": conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0],
        }
        total_possible = conn.execute(
            """SELECT COUNT(*) FROM (
                SELECT ls.id, u.id as sid FROM lecture_sessions ls
                JOIN course_units cu ON ls.course_unit_id = cu.id
                JOIN users u ON u.course_id = cu.course_id AND u.role='student'
            )"""
        ).fetchone()[0]
        actual = stats["attendance_records"]
        overall_pct = round((actual / total_possible) * 100, 1) if total_possible else 0
        
        course_stats = conn.execute(
            """SELECT c.name, c.code,
                      COUNT(DISTINCT ls.id) as sessions,
                      COUNT(a.id) as marks,
                      (SELECT COUNT(*) FROM users WHERE course_id=c.id AND role='student') as students
               FROM courses c
               LEFT JOIN course_units cu ON cu.course_id = c.id
               LEFT JOIN lecture_sessions ls ON ls.course_unit_id = cu.id
               LEFT JOIN attendance a ON a.session_id = ls.id
               GROUP BY c.id ORDER BY c.code"""
        ).fetchall()
        
    return render_template(
        "admin/dashboard.html", stats=stats, overall_pct=overall_pct, course_stats=course_stats
    )


@admin_bp.route("/admin/users", methods=["GET", "POST"])
@login_required("admin")
def admin_users():
    with get_db() as conn:
        courses = conn.execute("SELECT * FROM courses ORDER BY code").fetchall()
        departments = conn.execute("SELECT * FROM departments ORDER BY name").fetchall()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add":
                conn.execute(
                    """INSERT INTO users (email, password_hash, full_name, role, registration_number, course_id, department_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        request.form.get("email", "").strip().lower(),
                        generate_password_hash(request.form.get("password", "password123")),
                        request.form.get("full_name", "").strip(),
                        request.form.get("role"),
                        request.form.get("registration_number") or None,
                        request.form.get("course_id") or None,
                        request.form.get("department_id") or None,
                    ),
                )
                flash("User added.", "success")
            elif action == "toggle":
                uid = request.form.get("user_id")
                conn.execute(
                    "UPDATE users SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id = ? AND role != 'admin'",
                    (uid,),
                )
                flash("User status updated.", "success")
            elif action == "delete":
                uid = request.form.get("user_id")
                # Delete student attendance records
                conn.execute("DELETE FROM attendance WHERE student_id = ?", (uid,))
                # Delete user notifications
                conn.execute("DELETE FROM notifications WHERE user_id = ?", (uid,))
                # Delete lecturer sessions and their associated attendance
                conn.execute("DELETE FROM attendance WHERE session_id IN (SELECT id FROM lecture_sessions WHERE lecturer_id = ?)", (uid,))
                conn.execute("DELETE FROM lecture_sessions WHERE lecturer_id = ?", (uid,))
                # Delete the user record
                conn.execute("DELETE FROM users WHERE id = ? AND role != 'admin'", (uid,))
                flash("User deleted successfully.", "success")
        users = conn.execute(
            """SELECT u.*, c.name as course_name, d.name as department_name
               FROM users u LEFT JOIN courses c ON u.course_id=c.id
               LEFT JOIN departments d ON u.department_id=d.id
               WHERE u.role != 'admin' ORDER BY u.role, u.full_name"""
        ).fetchall()
    return render_template("admin/users.html", users=users, courses=courses, departments=departments)


@admin_bp.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
@login_required("admin")
def admin_edit_user(user_id):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ? AND role != 'admin'", (user_id,)).fetchone()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.admin_users"))
            
        courses = conn.execute("SELECT * FROM courses ORDER BY code").fetchall()
        departments = conn.execute("SELECT * FROM departments ORDER BY name").fetchall()
        
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password")
            
            # Validation: Email must not conflict with another user
            existing = conn.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id)).fetchone()
            if existing:
                flash("Email address is already registered to another user.", "danger")
                return render_template("admin/edit_user.html", user=user, courses=courses, departments=departments)
                
            if user["role"] == "student":
                reg_no = request.form.get("registration_number", "").strip().upper()
                course_id = request.form.get("course_id")
                
                # Validation: Reg No must not conflict
                existing_reg = conn.execute("SELECT id FROM users WHERE registration_number = ? AND id != ?", (reg_no, user_id)).fetchone()
                if existing_reg:
                    flash("Registration number is already registered to another student.", "danger")
                    return render_template("admin/edit_user.html", user=user, courses=courses, departments=departments)
                
                # Find course department
                dept = conn.execute("SELECT department_id FROM courses WHERE id = ?", (course_id,)).fetchone()
                dept_id = dept["department_id"] if dept else None
                
                conn.execute(
                    """UPDATE users
                       SET full_name = ?, email = ?, registration_number = ?, course_id = ?, department_id = ?
                       WHERE id = ?""",
                    (full_name, email, reg_no, course_id, dept_id, user_id)
                )
            else:  # lecturer
                dept_id = request.form.get("department_id")
                conn.execute(
                    """UPDATE users
                       SET full_name = ?, email = ?, department_id = ?
                       WHERE id = ?""",
                    (full_name, email, dept_id, user_id)
                )
                
            # Optional password update
            if password and len(password.strip()) > 0:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(password), user_id)
                )
                
            flash("User profile updated successfully.", "success")
            return redirect(url_for("admin.admin_users"))
            
    return render_template("admin/edit_user.html", user=user, courses=courses, departments=departments)


@admin_bp.route("/admin/courses", methods=["GET", "POST"])
@login_required("admin")
def admin_courses():
    with get_db() as conn:
        faculties = conn.execute("SELECT * FROM faculties ORDER BY name").fetchall()
        departments = conn.execute(
            """SELECT d.*, f.name as faculty_name FROM departments d
               LEFT JOIN faculties f ON d.faculty_id = f.id ORDER BY d.name"""
        ).fetchall()
        courses = conn.execute(
            """SELECT c.*, d.name as department_name FROM courses c
               LEFT JOIN departments d ON c.department_id = d.id ORDER BY c.code"""
        ).fetchall()
        course_units = conn.execute(
            """SELECT cu.*, c.code as course_code, d.name as department_name FROM course_units cu
               JOIN courses c ON cu.course_id = c.id
               JOIN departments d ON c.department_id = d.id ORDER BY cu.code"""
        ).fetchall()

        if request.method == "POST":
            action = request.form.get("action")
            if action == "add_faculty":
                fac_name = request.form.get("fac_name", "").strip()
                if fac_name:
                    conn.execute("INSERT OR IGNORE INTO faculties (name) VALUES (?)", (fac_name,))
                    flash("Faculty added.", "success")
            elif action == "add_department":
                dept_name = request.form.get("dept_name", "").strip()
                faculty_id = request.form.get("faculty_id")
                if dept_name and faculty_id:
                    conn.execute("INSERT OR IGNORE INTO departments (name, faculty_id) VALUES (?, ?)", (dept_name, faculty_id))
                    flash("Department added.", "success")
            elif action == "add_course":
                code = request.form.get("code", "").strip().upper()
                name = request.form.get("name", "").strip()
                department_id = request.form.get("department_id")
                if code and name and department_id:
                    conn.execute("INSERT OR IGNORE INTO courses (code, name, department_id) VALUES (?, ?, ?)", (code, name, department_id))
                    flash("Degree Program added.", "success")
            elif action == "add_course_unit":
                cu_code = request.form.get("cu_code", "").strip().upper()
                cu_name = request.form.get("cu_name", "").strip()
                course_id = request.form.get("course_id")
                if cu_code and cu_name and course_id:
                    conn.execute("INSERT OR IGNORE INTO course_units (code, name, course_id) VALUES (?, ?, ?)", (cu_code, cu_name, course_id))
                    flash("Course Unit added.", "success")
            return redirect(url_for("admin.admin_courses"))

    return render_template(
        "admin/courses.html",
        faculties=faculties,
        departments=departments,
        courses=courses,
        course_units=course_units
    )

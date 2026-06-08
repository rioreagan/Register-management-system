from functools import wraps
from flask import session, flash, redirect, url_for
from app.database import get_db

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login"))
            if role and session.get("role") != role:
                flash("Access denied.", "danger")
                return redirect(url_for("auth.dashboard"))
            return f(*args, **kwargs)

        return wrapped

    return decorator


def get_current_user():
    if "user_id" not in session:
        return None
    with get_db() as conn:
        return conn.execute(
            """SELECT u.*, c.name as course_name, c.code as course_code, d.name as department_name, f.name as faculty_name
               FROM users u
               LEFT JOIN courses c ON u.course_id = c.id
               LEFT JOIN departments d ON u.department_id = d.id
               LEFT JOIN faculties f ON d.faculty_id = f.id
               WHERE u.id = ?""",
            (session["user_id"],),
        ).fetchone()


def get_dynamic_token(session_code, offset=0):
    import hashlib
    import time
    time_step = int(time.time() / 30) + offset
    raw = f"{session_code}-{time_step}"
    return hashlib.sha256(raw.encode()).hexdigest()[:6].upper()


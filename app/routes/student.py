from flask import Blueprint, request, render_template, redirect, url_for, session, flash
from app.database import get_db
from app.auth import login_required, get_current_user, get_dynamic_token

student_bp = Blueprint("student", __name__)

@student_bp.route("/student")
@login_required("student")
def student_dashboard():
    user = get_current_user()
    from datetime import datetime
    with get_db() as conn:
        total_sessions = conn.execute(
            """SELECT COUNT(*) FROM lecture_sessions ls
               JOIN course_units cu ON ls.course_unit_id = cu.id
               WHERE cu.course_id = ? AND ls.end_time < ?""",
            (user["course_id"], datetime.now().isoformat()),
        ).fetchone()[0]
        
        open_sessions = conn.execute(
            """SELECT ls.*, cu.name as course_name FROM lecture_sessions ls
               JOIN course_units cu ON ls.course_unit_id = cu.id
               WHERE cu.course_id = ? AND ls.is_open = 1""",
            (user["course_id"],),
        ).fetchall()
        
        notifications = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
            (session["user_id"],),
        ).fetchall()
        
        attended = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE student_id = ?",
            (session["user_id"],),
        ).fetchone()[0]
        
        attendance_pct = round((attended / total_sessions) * 100, 1) if total_sessions else 0
        
    return render_template(
        "student/dashboard.html",
        user=user,
        total_sessions=total_sessions,
        open_sessions=open_sessions,
        notifications=notifications,
        attended=attended,
        attendance_pct=attendance_pct,
    )


@student_bp.route("/student/scan", methods=["GET", "POST"])
@login_required("student")
def student_scan():
    user = get_current_user()
    if request.method == "POST":
        code = request.form.get("session_code", "").strip().upper()
        token = request.form.get("dynamic_token", "").strip().upper()
        
        # Scanned QR codes contain "BASE_CODE-DYNAMIC_TOKEN"
        if "-" in code:
            parts = code.split("-")
            code = parts[0].strip().upper()
            token = parts[1].strip().upper()
            
        if not code or not token:
            flash("Both Session Code and Dynamic OTP are required.", "danger")
            return redirect(url_for("student.student_scan"))
            
        with get_db() as conn:
            sess = conn.execute(
                """SELECT ls.*, cu.course_id, c.code as program_code FROM lecture_sessions ls
                   JOIN course_units cu ON ls.course_unit_id = cu.id
                   JOIN courses c ON cu.course_id = c.id
                   WHERE ls.session_code = ?""",
                (code,),
            ).fetchone()
            if not sess:
                flash("Invalid session code. Please check the code or scan again.", "danger")
                return redirect(url_for("student.student_scan"))
                
            if not sess["is_open"]:
                flash("This lecture session has already closed/expired.", "danger")
                return redirect(url_for("student.student_scan"))
                
            if sess["course_id"] != user["course_id"]:
                flash(f"Access denied: This session is for {sess['program_code']} students.", "danger")
                return redirect(url_for("student.student_scan"))
                
            # Validate token against current and previous time steps
            token_curr = get_dynamic_token(sess["session_code"], offset=0)
            token_prev = get_dynamic_token(sess["session_code"], offset=-1)
            
            if token not in (token_curr, token_prev):
                flash("Dynamic OTP has expired. Please scan the newly generated QR code.", "danger")
                return redirect(url_for("student.student_scan"))
            
            existing = conn.execute(
                "SELECT id FROM attendance WHERE session_id = ? AND student_id = ?",
                (sess["id"], session["user_id"]),
            ).fetchone()
            if existing:
                flash("Attendance already marked.", "warning")
                return redirect(url_for("student.student_dashboard"))
                
            conn.execute(
                "INSERT INTO attendance (session_id, student_id, method) VALUES (?, ?, 'QR')",
                (sess["id"], session["user_id"]),
            )
            flash("Attendance marked successfully!", "success")
        return redirect(url_for("student.student_dashboard"))
    return render_template("student/scan.html")


@student_bp.route("/student/mark/<int:session_id>", methods=["POST"])
@login_required("student")
def mark_attendance(session_id):
    user = get_current_user()
    method = request.form.get("method", "button")
    token = request.form.get("dynamic_token", "").strip().upper()
    
    if not token:
        flash("Dynamic OTP is required to register attendance.", "danger")
        return redirect(url_for("student.student_dashboard"))
        
    with get_db() as conn:
        sess = conn.execute(
            """SELECT ls.*, cu.course_id, c.code as program_code FROM lecture_sessions ls
               JOIN course_units cu ON ls.course_unit_id = cu.id
               JOIN courses c ON cu.course_id = c.id
               WHERE ls.id = ?""",
            (session_id,),
        ).fetchone()
        if not sess:
            flash("Session not found.", "danger")
            return redirect(url_for("student.student_dashboard"))
            
        if not sess["is_open"]:
            flash("This lecture session has already closed/expired.", "danger")
            return redirect(url_for("student.student_dashboard"))
            
        if sess["course_id"] != user["course_id"]:
            flash(f"Access denied: This session is for {sess['program_code']} students.", "danger")
            return redirect(url_for("student.student_dashboard"))
            
        # Validate dynamic token
        token_curr = get_dynamic_token(sess["session_code"], offset=0)
        token_prev = get_dynamic_token(sess["session_code"], offset=-1)
        
        if token not in (token_curr, token_prev):
            flash("Invalid or expired Dynamic OTP. Check the projector screen.", "danger")
            return redirect(url_for("student.student_dashboard"))
            
        existing = conn.execute(
            "SELECT id FROM attendance WHERE session_id = ? AND student_id = ?",
            (session_id, session["user_id"]),
        ).fetchone()
        if existing:
            flash("Attendance already marked.", "warning")
            return redirect(url_for("student.student_dashboard"))
            
        conn.execute(
            "INSERT INTO attendance (session_id, student_id, method) VALUES (?, ?, ?)",
            (session_id, session["user_id"], method),
        )
        flash("Attendance recorded.", "success")
    return redirect(url_for("student.student_dashboard"))


@student_bp.route("/student/history")
@login_required("student")
def student_history():
    with get_db() as conn:
        records = conn.execute(
            """SELECT ls.title, ls.start_time, cu.name as course_name,
                      a.marked_at, a.method
               FROM attendance a
               JOIN lecture_sessions ls ON a.session_id = ls.id
               JOIN course_units cu ON ls.course_unit_id = cu.id
               WHERE a.student_id = ? ORDER BY ls.start_time DESC""",
            (session["user_id"],),
        ).fetchall()
    return render_template("student/history.html", records=records)


@student_bp.route("/student/notifications/read/<int:nid>")
@login_required("student")
def read_notification(nid):
    with get_db() as conn:
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
            (nid, session["user_id"]),
        )
    return redirect(url_for("student.student_dashboard"))

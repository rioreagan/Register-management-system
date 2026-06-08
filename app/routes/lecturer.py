import io
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, request, render_template, redirect, url_for, session, flash, jsonify, send_file
from app.database import get_db
from app.auth import login_required, get_current_user, get_dynamic_token

lecturer_bp = Blueprint("lecturer", __name__)

@lecturer_bp.route("/lecturer")
@login_required("lecturer")
def lecturer_dashboard():
    user = get_current_user()
    with get_db() as conn:
        sessions = conn.execute(
            """SELECT ls.*, cu.name as course_name,
                      (SELECT COUNT(*) FROM attendance WHERE session_id = ls.id) as present_count
               FROM lecture_sessions ls
               JOIN course_units cu ON ls.course_unit_id = cu.id
               WHERE ls.lecturer_id = ?
               ORDER BY ls.start_time DESC LIMIT 10""",
            (user["id"],),
        ).fetchall()
        
        # Get course units offered by courses in the lecturer's department
        course_units = conn.execute(
            """SELECT cu.id, cu.code, cu.name, c.code as course_code
               FROM course_units cu
               JOIN courses c ON cu.course_id = c.id
               WHERE c.department_id = ? ORDER BY cu.code""",
            (user["department_id"],)
        ).fetchall()
        
    return render_template(
        "lecturer/dashboard.html", user=user, sessions=sessions, course_units=course_units
    )


@lecturer_bp.route("/lecturer/session/create", methods=["POST"])
@login_required("lecturer")
def create_session():
    title = request.form.get("title", "").strip()
    course_unit_id = request.form.get("course_unit_id")
    duration = int(request.form.get("duration", 60))
    if not title or not course_unit_id:
        flash("Title and course unit are required.", "danger")
        return redirect(url_for("lecturer.lecturer_dashboard"))
    start = datetime.now()
    end = start + timedelta(minutes=duration)
    code = secrets.token_hex(4).upper()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO lecture_sessions (title, course_unit_id, lecturer_id, session_code, start_time, end_time)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                title,
                course_unit_id,
                session["user_id"],
                code,
                start.isoformat(),
                end.isoformat(),
            ),
        )
    flash(f"Lecture session created. Code: {code}", "success")
    return redirect(url_for("lecturer.lecturer_dashboard"))


@lecturer_bp.route("/lecturer/session/<int:session_id>/live")
@login_required("lecturer")
def session_live(session_id):
    with get_db() as conn:
        sess = conn.execute(
            """SELECT ls.*, cu.name as course_name, cu.course_id FROM lecture_sessions ls
               JOIN course_units cu ON ls.course_unit_id = cu.id
               WHERE ls.id = ? AND ls.lecturer_id = ?""",
            (session_id, session["user_id"]),
        ).fetchone()
        if not sess:
            flash("Session not found.", "danger")
            return redirect(url_for("lecturer.lecturer_dashboard"))
        attendees = conn.execute(
            """SELECT u.full_name, u.registration_number, a.marked_at, a.method
               FROM attendance a
               JOIN users u ON a.student_id = u.id
               WHERE a.session_id = ?
               ORDER BY a.marked_at DESC""",
            (session_id,),
        ).fetchall()
        
        # Enrolled = students enrolled in the degree program of this course unit
        enrolled = conn.execute(
            "SELECT COUNT(*) FROM users WHERE course_id = ? AND role = 'student' AND is_active = 1",
            (sess["course_id"],),
        ).fetchone()[0]
        
    return render_template(
        "lecturer/live.html", sess=sess, attendees=attendees, enrolled=enrolled
    )


@lecturer_bp.route("/api/session/<int:session_id>/attendees")
@login_required("lecturer")
def api_attendees(session_id):
    with get_db() as conn:
        sess = conn.execute(
            "SELECT id, course_unit_id FROM lecture_sessions WHERE id = ? AND lecturer_id = ?",
            (session_id, session["user_id"]),
        ).fetchone()
        if not sess:
            return jsonify({"error": "Not found"}), 404
        attendees = conn.execute(
            """SELECT u.full_name, u.registration_number, a.marked_at, a.method
               FROM attendance a JOIN users u ON a.student_id = u.id
               WHERE a.session_id = ? ORDER BY a.marked_at DESC""",
            (session_id,),
        ).fetchall()
        count = len(attendees)
        
        enrolled = conn.execute(
            """SELECT COUNT(*) FROM users WHERE role='student' AND course_id = (
                SELECT course_id FROM course_units WHERE id = (
                    SELECT course_unit_id FROM lecture_sessions WHERE id = ?
                )
            )""",
            (session_id,),
        ).fetchone()[0]
        
    return jsonify({
        "count": count,
        "enrolled": enrolled,
        "attendees": [
            {
                "full_name": a["full_name"],
                "registration_number": a["registration_number"],
                "marked_at": a["marked_at"],
                "method": a["method"],
            }
            for a in attendees
        ],
    })


@lecturer_bp.route("/lecturer/reports")
@login_required("lecturer")
def lecturer_reports():
    course_unit_id = request.args.get("course_unit_id", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    student_q = request.args.get("student", "").strip()
    user = get_current_user()
    with get_db() as conn:
        # Get course units offered in the lecturer's department
        course_units = conn.execute(
            """SELECT cu.id, cu.code, cu.name
               FROM course_units cu
               JOIN courses c ON cu.course_id = c.id
               WHERE c.department_id = ? ORDER BY cu.code""",
            (user["department_id"],)
        ).fetchall()
        
        query = """
            SELECT ls.title, ls.start_time, cu.name as course_name, c.code as course_code,
                   u.full_name, u.registration_number, a.marked_at, a.method
            FROM attendance a
            JOIN lecture_sessions ls ON a.session_id = ls.id
            JOIN course_units cu ON ls.course_unit_id = cu.id
            JOIN courses c ON cu.course_id = c.id
            JOIN users u ON a.student_id = u.id
            WHERE ls.lecturer_id = ?
        """
        params = [session["user_id"]]
        if course_unit_id:
            query += " AND ls.course_unit_id = ?"
            params.append(course_unit_id)
        if date_from:
            query += " AND date(ls.start_time) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(ls.start_time) <= date(?)"
            params.append(date_to)
        if student_q:
            query += " AND (u.full_name LIKE ? OR u.registration_number LIKE ?)"
            params.extend([f"%{student_q}%", f"%{student_q}%"])
        query += " ORDER BY ls.start_time DESC, u.full_name"
        records = conn.execute(query, params).fetchall()
        
    return render_template(
        "lecturer/reports.html",
        records=records,
        course_units=course_units,
        filters={"course_unit_id": course_unit_id, "date_from": date_from, "date_to": date_to, "student": student_q},
    )


@lecturer_bp.route("/lecturer/reports/export/<fmt>")
@login_required("lecturer")
def export_reports(fmt):
    course_unit_id = request.args.get("course_unit_id", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    student_q = request.args.get("student", "").strip()
    with get_db() as conn:
        query = """
            SELECT ls.title, ls.start_time, cu.name as course_name, c.code as course_code,
                   u.full_name, u.registration_number, a.marked_at, a.method
            FROM attendance a
            JOIN lecture_sessions ls ON a.session_id = ls.id
            JOIN course_units cu ON ls.course_unit_id = cu.id
            JOIN courses c ON cu.course_id = c.id
            JOIN users u ON a.student_id = u.id
            WHERE ls.lecturer_id = ?
        """
        params = [session["user_id"]]
        if course_unit_id:
            query += " AND ls.course_unit_id = ?"
            params.append(course_unit_id)
        if date_from:
            query += " AND date(ls.start_time) >= date(?)"
            params.append(date_from)
        if date_to:
            query += " AND date(ls.start_time) <= date(?)"
            params.append(date_to)
        if student_q:
            query += " AND (u.full_name LIKE ? OR u.registration_number LIKE ?)"
            params.extend([f"%{student_q}%", f"%{student_q}%"])
        query += " ORDER BY ls.start_time DESC"
        records = conn.execute(query, params).fetchall()

    if fmt == "excel":
        try:
            from openpyxl import Workbook
        except ImportError:
            flash("Excel export requires openpyxl.", "danger")
            return redirect(url_for("lecturer.lecturer_reports"))
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance"
        ws.append(["Lecture", "Date", "Program", "Unit", "Student", "Reg No", "Marked At", "Method"])
        for r in records:
            ws.append([
                r["title"], r["start_time"], r["course_code"], r["course_name"],
                r["full_name"], r["registration_number"], r["marked_at"], r["method"],
            ])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="attendance_report.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # PDF
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        flash("PDF export requires reportlab.", "danger")
        return redirect(url_for("lecturer.lecturer_reports"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = [Paragraph("Attendance Report", styles["Title"]), Spacer(1, 12)]
    data = [["Lecture", "Date", "Program", "Unit", "Student", "Reg No", "Marked At", "Method"]]
    for r in records:
        data.append([
            r["title"][:20], str(r["start_time"])[:10], r["course_code"][:10], r["course_name"][:15],
            r["full_name"][:20], r["registration_number"], str(r["marked_at"])[:16], r["method"],
        ])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    elements.append(table)
    doc.build(elements)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="attendance_report.pdf", mimetype="application/pdf")


@lecturer_bp.route("/lecturer/session/<int:session_id>/qr")
@login_required("lecturer")
def session_qr(session_id):
    with get_db() as conn:
        sess = conn.execute(
            """SELECT ls.*, cu.name as course_name FROM lecture_sessions ls
               JOIN course_units cu ON ls.course_unit_id = cu.id
               WHERE ls.id = ? AND ls.lecturer_id = ?""",
            (session_id, session["user_id"]),
        ).fetchone()
    if not sess:
        flash("Session not found.", "danger")
        return redirect(url_for("lecturer.lecturer_dashboard"))
        
    initial_token = get_dynamic_token(sess["session_code"])
    import time
    sec_rem = 30 - int(time.time() % 30)
    
    return render_template("lecturer/qr.html", sess=sess, initial_token=initial_token, sec_rem=sec_rem)

"""
Lecture Attendance Registration System - single file edition with Faculty -> Dept -> Program -> Unit hierarchy.
Run: python attendance.py
"""
import io
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from jinja2 import DictLoader, select_autoescape
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-in-production-lecture-attendance")
DATABASE = os.path.join(BASE_DIR, "attendance.db")
LOW_ATTENDANCE_THRESHOLD = 75


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS faculties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                faculty_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (faculty_id) REFERENCES faculties(id)
            );

            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                department_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (department_id) REFERENCES departments(id)
            );

            CREATE TABLE IF NOT EXISTS course_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                course_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id)
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'lecturer', 'admin')),
                registration_number TEXT,
                course_id INTEGER, -- Refers to degree/program (courses)
                department_id INTEGER, -- Refers to department
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id),
                FOREIGN KEY (department_id) REFERENCES departments(id)
            );

            CREATE TABLE IF NOT EXISTS lecture_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                course_unit_id INTEGER NOT NULL,
                lecturer_id INTEGER NOT NULL,
                session_code TEXT NOT NULL UNIQUE,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                is_open INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_unit_id) REFERENCES course_units(id),
                FOREIGN KEY (lecturer_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                method TEXT DEFAULT 'button',
                UNIQUE(session_id, student_id),
                FOREIGN KEY (session_id) REFERENCES lecture_sessions(id),
                FOREIGN KEY (student_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


def seed_demo_data():
    with get_db() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return

        # 1. Seed Faculties
        conn.execute("INSERT OR IGNORE INTO faculties (name) VALUES ('Faculty of Science')")
        conn.execute("INSERT OR IGNORE INTO faculties (name) VALUES ('Faculty of Engineering')")
        
        fac_sci = conn.execute("SELECT id FROM faculties WHERE name='Faculty of Science'").fetchone()[0]
        fac_eng = conn.execute("SELECT id FROM faculties WHERE name='Faculty of Engineering'").fetchone()[0]

        # 2. Seed Departments
        conn.execute("INSERT OR IGNORE INTO departments (name, faculty_id) VALUES ('Department of Computer Science', ?)", (fac_sci,))
        conn.execute("INSERT OR IGNORE INTO departments (name, faculty_id) VALUES ('Department of Electrical Engineering', ?)", (fac_eng,))
        
        dept_cs = conn.execute("SELECT id FROM departments WHERE name='Department of Computer Science'").fetchone()[0]

        # 3. Seed Programs (Degree Courses)
        conn.execute("INSERT OR IGNORE INTO courses (code, name, department_id) VALUES ('BITC', 'Bachelor of Information Technology and Computing', ?)", (dept_cs,))
        conn.execute("INSERT OR IGNORE INTO courses (code, name, department_id) VALUES ('BIS', 'Bachelor of Information Systems', ?)", (dept_cs,))
        
        prog_bitc = conn.execute("SELECT id FROM courses WHERE code='BITC'").fetchone()[0]
        prog_bis = conn.execute("SELECT id FROM courses WHERE code='BIS'").fetchone()[0]

        # 4. Seed Course Units (Subjects under Programs)
        conn.execute("INSERT OR IGNORE INTO course_units (code, name, course_id) VALUES ('COMP-APP', 'Computer Applications', ?)", (prog_bitc,))
        conn.execute("INSERT OR IGNORE INTO course_units (code, name, course_id) VALUES ('DB-SYS', 'Database Management Systems', ?)", (prog_bitc,))
        conn.execute("INSERT OR IGNORE INTO course_units (code, name, course_id) VALUES ('SOFT-ENG', 'Software Engineering Principles', ?)", (prog_bis,))
        
        unit_ca = conn.execute("SELECT id FROM course_units WHERE code='COMP-APP'").fetchone()[0]

        pwd = generate_password_hash("password123")
        
        # 5. Seed Users
        conn.execute(
            """INSERT INTO users (email, password_hash, full_name, role, registration_number, course_id, department_id)
               VALUES ('admin@university.edu', ?, 'System Administrator', 'admin', NULL, NULL, NULL)""",
            (pwd,),
        )
        conn.execute(
            """INSERT INTO users (email, password_hash, full_name, role, registration_number, course_id, department_id)
               VALUES ('lecturer@university.edu', ?, 'Dr. Jane Smith', 'lecturer', NULL, NULL, ?)""",
            (pwd, dept_cs),
        )
        conn.execute(
            """INSERT INTO users (email, password_hash, full_name, role, registration_number, course_id, department_id)
               VALUES ('student@university.edu', ?, 'John Doe', 'student', 'REG2024001', ?, ?)""",
            (pwd, prog_bitc, dept_cs),
        )


def close_expired_sessions():
    now_str = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE lecture_sessions SET is_open = 0 WHERE is_open = 1 AND end_time < ?",
            (now_str,)
        )


def check_low_attendance(student_id):
    """Notify student if attendance falls below threshold."""
    with get_db() as conn:
        student = conn.execute(
            "SELECT u.id, u.full_name, c.name as course_name FROM users u LEFT JOIN courses c ON u.course_id = c.id WHERE u.id = ?",
            (student_id,),
        ).fetchone()
        if not student:
            return

        total = conn.execute(
            """SELECT COUNT(*) FROM lecture_sessions ls
               JOIN course_units cu ON ls.course_unit_id = cu.id
               JOIN users u ON u.course_id = cu.course_id
               WHERE u.id = ? AND ls.end_time < ?""",
            (student_id, datetime.now().isoformat()),
        ).fetchone()[0]
        if total == 0:
            return

        attended = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE student_id = ?",
            (student_id,),
        ).fetchone()[0]
        pct = round((attended / total) * 100, 1)

        if pct < LOW_ATTENDANCE_THRESHOLD:
            msg = f"Low attendance alert: Your attendance is {pct}% for {student['course_name'] or 'your course'}."
            existing = conn.execute(
                "SELECT id FROM notifications WHERE user_id = ? AND message LIKE 'Low attendance%' AND is_read = 0",
                (student_id,),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                    (student_id, msg),
                )


TEMPLATES = {
    "base.html": """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Lecture Attendance{% endblock %}</title>
    
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap" rel="stylesheet">
    {% block head %}{% endblock %}
<style>
:root {
    --bg: #f8fafc;
    --surface: #ffffff;
    --text: #0f172a;
    --text-muted: #64748b;
    --border: #e2e8f0;
    --primary: #004b87; /* Kyambogo Deep Blue */
    --primary-hover: #003d6e;
    --primary-glow: rgba(0, 75, 135, 0.07);
    --secondary: #d68910; /* Kyambogo Gold */
    --secondary-hover: #b0700c;
    --secondary-glow: rgba(214, 137, 16, 0.07);
    --accent: #78BE20; /* Kyambogo Green */
    --accent-glow: rgba(120, 190, 32, 0.07);
    --success: #78BE20; /* Kyambogo Green */
    --warning: #d68910; /* Kyambogo Gold */
    --danger: #dc2626;
    --radius: 12px;
    --shadow: 0 1px 3px rgba(0,0,0,.08);
    --font: 'DM Sans', system-ui, sans-serif;
}

[data-theme="dark"] {
    --bg: #080c14;
    --surface: #101624;
    --text: #f1f5f9;
    --text-muted: #94a3b8;
    --border: #1e293b;
    --shadow: 0 1px 3px rgba(0,0,0,.3);
    --primary: #0077d6; /* Kyambogo Light Blue */
    --primary-hover: #0066cc;
    --primary-glow: rgba(0, 119, 214, 0.18);
    --secondary: #e5b83b; /* Kyambogo Light Gold */
    --secondary-glow: rgba(229, 184, 59, 0.12);
    --accent: #84BD00; /* Kyambogo Green */
    --accent-glow: rgba(132, 189, 0, 0.12);
    --success: #84BD00; /* Kyambogo Green */
    --warning: #e5b83b; /* Kyambogo Gold */
}

*, *::before, *::after { box-sizing: border-box; }

body {
    margin: 0;
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    min-height: 100vh;
    background-image: 
        radial-gradient(at 0% 0%, var(--primary-glow) 0px, transparent 50%),
        radial-gradient(at 100% 0%, var(--accent-glow) 0px, transparent 50%),
        radial-gradient(at 50% 100%, var(--secondary-glow) 0px, transparent 50%);
    background-attachment: fixed;
}

.container {
    max-width: 1100px;
    margin: 0 auto;
    padding: 1.25rem;
}

/* Navbar */
.navbar {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: .75rem 1.25rem;
    background: var(--surface);
    border-bottom: 3px solid var(--warning); /* Kyambogo Gold Border */
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: var(--shadow);
}

.brand {
    font-weight: 700;
    font-size: 1.1rem;
    color: var(--text);
    text-decoration: none;
}

.nav-links {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex: 1;
    flex-wrap: wrap;
}

.nav-links a {
    color: var(--text-muted);
    text-decoration: none;
    font-size: .9rem;
}

.nav-links a:hover { color: var(--primary); }

.nav-user {
    margin-left: auto;
    font-size: .85rem;
    color: var(--text-muted);
}

.nav-toggle, .theme-toggle {
    display: none;
    background: none;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: .4rem .6rem;
    cursor: pointer;
    font-size: 1rem;
}

.theme-toggle { display: block; margin-left: .5rem; }

@media (max-width: 768px) {
    .nav-toggle { display: block; }
    .nav-links {
        display: none;
        width: 100%;
        flex-direction: column;
        align-items: flex-start;
    }
    .nav-links.open { display: flex; }
    .navbar { flex-wrap: wrap; }
}

/* Typography */
h1 { font-size: 1.75rem; margin: 0 0 .25rem; }
h2 { font-size: 1.15rem; margin: 0 0 1rem; }
.subtitle { color: var(--text-muted); margin: 0 0 1.5rem; }

/* Cards & layout */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
    margin-bottom: 1.25rem;
    box-shadow: var(--shadow);
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
}

.stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
    text-align: center;
}

.stat-card.highlight {
    border-color: var(--primary);
    background: linear-gradient(135deg, rgba(37,99,235,.08), transparent);
}

.stat-value {
    display: block;
    font-size: 2rem;
    font-weight: 700;
    color: var(--primary);
}

.stat-label {
    font-size: .8rem;
    color: var(--text-muted);
}

.grid-2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.25rem;
}

/* Forms */
.form label {
    display: block;
    font-size: .85rem;
    font-weight: 500;
    margin-bottom: .35rem;
    color: var(--text-muted);
}

.form input, .form select {
    width: 100%;
    padding: .6rem .75rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    color: var(--text);
    font-family: inherit;
    font-size: 1rem;
    margin-bottom: 1rem;
}

.form input:focus, .form select:focus {
    outline: 2px solid var(--primary);
    outline-offset: 0;
}

.form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 0 1rem;
}

.form-actions { display: flex; align-items: flex-end; gap: .5rem; margin-bottom: 1rem; }

.inline-form { display: flex; gap: .5rem; flex-wrap: wrap; }
.inline-form input { flex: 1; margin-bottom: 0; }

/* Buttons */
.btn {
    display: inline-block;
    padding: .55rem 1rem;
    border-radius: 8px;
    font-weight: 600;
    font-size: .9rem;
    text-decoration: none;
    border: none;
    cursor: pointer;
    font-family: inherit;
    transition: background .15s;
}

.btn-primary { background: var(--primary); color: #fff; }
.btn-primary:hover { background: var(--primary-hover); }

.btn-outline {
    background: transparent;
    color: var(--text);
    border: 1px solid var(--border);
}

.btn-block { width: 100%; text-align: center; }
.btn-sm { padding: .35rem .65rem; font-size: .8rem; }

.actions { white-space: nowrap; }
.actions .btn { margin-right: .25rem; }

/* Auth */
.auth-card {
    max-width: 420px;
    margin: 2rem auto;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem;
    box-shadow: var(--shadow);
}

.auth-footer { text-align: center; font-size: .9rem; color: var(--text-muted); }
.auth-footer a { color: var(--primary); }

.demo-box {
    margin-top: 1.5rem;
    padding: 1rem;
    background: var(--bg);
    border-radius: 8px;
    font-size: .85rem;
}

.demo-box ul { margin: .5rem 0 0; padding-left: 1.25rem; }

/* Tables */
.table-wrap { overflow-x: auto; }

table {
    width: 100%;
    border-collapse: collapse;
    font-size: .9rem;
}

th, td {
    padding: .65rem .75rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

th {
    font-weight: 600;
    color: var(--text-muted);
    font-size: .8rem;
    text-transform: uppercase;
    letter-spacing: .03em;
}

/* Badges & alerts */
.badge {
    display: inline-block;
    padding: .2rem .5rem;
    border-radius: 6px;
    font-size: .75rem;
    background: var(--bg);
    color: var(--text-muted);
}

.badge-success { background: var(--accent-glow); color: var(--success); }
.badge-muted { background: var(--bg); }

.alerts { margin-bottom: 1rem; }

.alert {
    padding: .75rem 1rem;
    border-radius: 8px;
    margin-bottom: .5rem;
    font-size: .9rem;
}

.alert-success { background: var(--accent-glow); color: var(--success); }
.alert-danger { background: rgba(220,38,38,.12); color: var(--danger); }
.alert-warning { background: var(--secondary-glow); color: var(--warning); }
.alert-info { background: var(--primary-glow); color: var(--primary); }

/* Session list */
.session-list { display: flex; flex-direction: column; gap: .75rem; }

.session-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: var(--bg);
    border-radius: 8px;
    flex-wrap: wrap;
}

.meta { font-size: .8rem; color: var(--text-muted); margin: .25rem 0 0; }

.hint { font-size: .85rem; color: var(--text-muted); }
.empty { color: var(--text-muted); text-align: center; padding: 1.5rem; }

/* QR */
.qr-display { text-align: center; }
.qr-display #qrcode { display: inline-block; margin: 1rem auto; }
.session-code { font-size: 1.25rem; }

.scan-card { text-align: center; }

.live-dot {
    color: var(--danger);
    font-size: .8rem;
    animation: pulse 1.5s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: .4; }
}

.notif-list { list-style: none; padding: 0; margin: 0; }
.notif-list li {
    padding: .75rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: .5rem;
    flex-wrap: wrap;
}
.notif-list li.unread { background: rgba(37,99,235,.06); }

.export-btns { display: flex; gap: .5rem; margin-top: 1rem; }

.simple-list { list-style: none; padding: 0; margin-top: 1rem; }
.simple-list li { padding: .4rem 0; border-bottom: 1px solid var(--border); }

code {
    background: var(--bg);
    padding: .15rem .4rem;
    border-radius: 4px;
    font-size: .9em;
}

.filter-form { margin-bottom: 0; }

</style>
</head>
<body>
    {% if current_user %}
    <nav class="navbar">
        <a href="{{ url_for('dashboard') }}" class="brand">📋 AttendTrack</a>
        <button class="nav-toggle" aria-label="Menu" onclick="document.querySelector('.nav-links').classList.toggle('open')">☰</button>
        <div class="nav-links">
            {% if current_user.role == 'student' %}
            <a href="{{ url_for('student_dashboard') }}">Dashboard</a>
            <a href="{{ url_for('student_scan') }}">Scan QR</a>
            <a href="{{ url_for('student_history') }}">History</a>
            {% elif current_user.role == 'lecturer' %}
            <a href="{{ url_for('lecturer_dashboard') }}">Sessions</a>
            <a href="{{ url_for('lecturer_reports') }}">Reports</a>
            {% elif current_user.role == 'admin' %}
            <a href="{{ url_for('admin_dashboard') }}">Overview</a>
            <a href="{{ url_for('admin_users') }}">Users</a>
            <a href="{{ url_for('admin_courses') }}">Academic Layout</a>
            {% endif %}
            <span class="nav-user">{{ current_user.full_name }}</span>
            <a href="{{ url_for('logout') }}" class="btn btn-sm btn-outline">Logout</a>
        </div>
        <button class="theme-toggle" onclick="toggleTheme()" title="Toggle dark mode">🌙</button>
    </nav>
    {% endif %}

    <main class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        <div class="alerts">
            {% for category, message in messages %}
            <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
        </div>
        {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>

    {% block scripts %}{% endblock %}
<script>
function toggleTheme() {
    const html = document.documentElement;
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    const btn = document.querySelector('.theme-toggle');
    if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
}

(function initTheme() {
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefersDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
    const btn = document.querySelector('.theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
})();

</script>
</body>
</html>
""",
    "home.html": """{% extends "base.html" %}
{% block title %}Home — AttendTrack{% endblock %}
{% block content %}
<div class="auth-card" style="max-width: 680px; margin: 3rem auto; text-align: center;">
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <img src="/static/kyu_logo.png" alt="Kyambogo University Logo" style="height: 100px; filter: drop-shadow(0 0 10px var(--primary-glow));">
    </div>
    <h1 style="font-size: 2.5rem; margin-bottom: 0.5rem; background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 50%, var(--secondary) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800;">📋 AttendTrack</h1>
    <p class="subtitle" style="font-size: 1.15rem; margin-bottom: 2rem;">Lecture Attendance Registration System</p>
    
    <p style="color: var(--text-muted); line-height: 1.6; margin-bottom: 2.5rem;">
        Kyambogo University's secure digital classroom check-in portal. Students can mark their presence using dynamic QR codes, lecturers can manage live courses, and administrators can monitor statistics.
    </p>
    
    <div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2.5rem; text-align: left;">
        <div class="stat-card" style="padding: 1rem; background: var(--primary-glow); border-color: var(--primary-glow);">
            <span class="stat-value" style="font-size: 1.25rem; color: var(--primary);">Students</span>
            <span class="stat-label" style="font-size: 0.8rem; color: var(--text-muted);">One-click QR code check-ins and attendance history reviews.</span>
        </div>
        <div class="stat-card" style="padding: 1rem; background: var(--secondary-glow); border-color: var(--secondary-glow);">
            <span class="stat-value" style="font-size: 1.25rem; color: var(--secondary);">Lecturers</span>
            <span class="stat-label" style="font-size: 0.8rem; color: var(--text-muted);">Generate active codes, trace live logs, and export PDF/Excel charts.</span>
        </div>
        <div class="stat-card" style="padding: 1rem; background: var(--accent-glow); border-color: var(--accent-glow);">
            <span class="stat-value" style="font-size: 1.25rem; color: var(--accent);">Admins</span>
            <span class="stat-label" style="font-size: 0.8rem; color: var(--text-muted);">Structure course catalogs, register users, and inspect campus analytics.</span>
        </div>
    </div>
    
    <div style="display: flex; gap: 1rem; justify-content: center;">
        <a href="{{ url_for('login') }}" class="btn btn-primary" style="padding: 0.7rem 2rem; font-size: 1rem;">Sign In to Portal</a>
        <a href="{{ url_for('register') }}" class="btn btn-outline" style="padding: 0.7rem 2rem; font-size: 1rem;">Student Registration</a>
    </div>
</div>
{% endblock %}
""",
    "login.html": """{% extends "base.html" %}
{% block title %}Login — AttendTrack{% endblock %}
{% block content %}
<div class="auth-card">
    <div style="text-align: center; margin-bottom: 1rem;">
        <img src="/static/kyu_logo.png" alt="Kyambogo University Logo" style="height: 70px; filter: drop-shadow(0 0 8px var(--primary-glow));">
    </div>
    <h1 style="background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 50%, var(--secondary) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; font-size: 1.8rem; margin-bottom: 0.5rem;">Welcome Back</h1>
    <p class="subtitle" style="margin-bottom: 1.5rem;">Lecture Attendance Registration System</p>
    <form method="POST" class="form">
        <label>Email</label>
        <input type="email" name="email" required placeholder="you@university.edu" autocomplete="email">
        <label>Password</label>
        <input type="password" name="password" required placeholder="••••••••" autocomplete="current-password">
        <button type="submit" class="btn btn-primary btn-block">Sign In</button>
    </form>
    <p class="auth-footer">Student? <a href="{{ url_for('register') }}">Create an account</a> | <a href="{{ url_for('forgot_password') }}">Forgot Password?</a></p>
    <div class="demo-box">
        <strong>Demo accounts</strong> (password: <code>password123</code>)
        <ul>
            <li>Admin: admin@university.edu</li>
            <li>Lecturer: lecturer@university.edu</li>
            <li>Student: student@university.edu</li>
        </ul>
    </div>
</div>
{% endblock %}
""",
    "register.html": """{% extends "base.html" %}
{% block title %}Register — AttendTrack{% endblock %}
{% block content %}
<div class="auth-card">
    <div style="text-align: center; margin-bottom: 1rem;">
        <img src="/static/kyu_logo.png" alt="Kyambogo University Logo" style="height: 70px; filter: drop-shadow(0 0 8px var(--primary-glow));">
    </div>
    <h1 style="background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 50%, var(--secondary) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; font-size: 1.8rem; margin-bottom: 0.5rem;">Student Registration</h1>
    <p class="subtitle" style="margin-bottom: 1.5rem;">Create your account to mark lecture attendance</p>
    <form method="POST" class="form">
        <label>Full Name</label>
        <input type="text" name="full_name" required placeholder="John Doe">
        <label>Registration Number</label>
        <input type="text" name="registration_number" required placeholder="REG2024001">
        <label>Email</label>
        <input type="email" name="email" required placeholder="john@university.edu">
        <label>Degree Program (Course)</label>
        <select name="course_id" required>
            <option value="">Select program</option>
            {% for c in courses %}
            <option value="{{ c.id }}">{{ c.code }} — {{ c.name }}</option>
            {% endfor %}
        </select>
        <label>Password</label>
        <input type="password" name="password" required minlength="6" placeholder="Min. 6 characters">
        <button type="submit" class="btn btn-primary btn-block">Register</button>
    </form>
    <p class="auth-footer">Already registered? <a href="{{ url_for('login') }}">Sign in</a></p>
</div>
{% endblock %}
""",
    "student/dashboard.html": """{% extends "base.html" %}
{% block title %}Student Dashboard{% endblock %}
{% block content %}
<h1>Hello, {{ user.full_name }}</h1>
<p class="subtitle">{{ user.course_code }} — {{ user.course_name }} ({{ user.department_name }})</p>

<div class="stats-grid">
    <div class="stat-card highlight">
        <span class="stat-value">{{ attendance_pct }}%</span>
        <span class="stat-label">Attendance Rate</span>
    </div>
    <div class="stat-card">
        <span class="stat-value">{{ attended }}/{{ total_sessions }}</span>
        <span class="stat-label">Sessions Attended</span>
    </div>
    <div class="stat-card">
        <span class="stat-value">{{ open_sessions|length }}</span>
        <span class="stat-label">Open Units Now</span>
    </div>
</div>

{% if attendance_pct < low_threshold and total_sessions > 0 %}
<div class="alert alert-warning">⚠️ Your attendance is below {{ low_threshold }}%. Please attend upcoming lectures.</div>
{% endif %}

{% if notifications %}
<section class="card">
    <h2>Notifications</h2>
    <ul class="notif-list">
        {% for n in notifications %}
        <li class="{% if not n.is_read %}unread{% endif %}">
            {{ n.message }}
            {% if not n.is_read %}
            <a href="{{ url_for('read_notification', nid=n.id) }}" class="btn btn-sm">Dismiss</a>
            {% endif %}
        </li>
        {% endfor %}
    </ul>
</section>
{% endif %}

<section class="card">
    <h2>Active Course Unit Check-in</h2>
    {% if open_sessions %}
    <div class="session-list">
        {% for s in open_sessions %}
        <div class="session-item">
            <div>
                <strong>{{ s.title }}</strong>
                <span class="badge badge-success">{{ s.course_name }}</span>
                <p class="meta">Ends {{ s.end_time[11:16] }}</p>
            </div>
            <form method="POST" action="{{ url_for('mark_attendance', session_id=s.id) }}" style="display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0;">
                <input type="text" name="dynamic_token" placeholder="6-digit OTP" required maxlength="6" style="text-transform: uppercase; max-width: 110px; margin-bottom: 0; padding: 0.35rem 0.5rem; font-size: 0.9rem; border: 1px solid var(--border); border-radius: 6px;">
                <input type="hidden" name="method" value="button">
                <button type="submit" class="btn btn-primary btn-sm">Verify OTP</button>
            </form>
        </div>
        {% endfor %}
    </div>
    <p class="hint">Or <a href="{{ url_for('student_scan') }}">scan the lecture QR code</a></p>
    {% else %}
    <p class="empty">No active lecture sessions right now. Check back during class time.</p>
    {% endif %}
</section>
{% endblock %}
""",
    "student/scan.html": """{% extends "base.html" %}
{% block title %}Scan QR{% endblock %}
{% block head %}
<script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
{% endblock %}
{% block content %}
<h1>Scan QR Code</h1>
<p class="subtitle">Point your camera at the lecturer's session QR code</p>

<div class="card scan-card">
    <div id="qr-reader" style="width:100%;max-width:400px;margin:0 auto;"></div>
    <p id="qr-status" class="hint">Camera will start when you allow access</p>
</div>

<div class="card">
    <h2>Or enter session code manually</h2>
    <form method="POST" class="form inline-form" id="manual-form">
        <input type="text" name="session_code" id="session_code" placeholder="Session Code (e.g. A1B2C3D4)" required style="text-transform:uppercase">
        <input type="text" name="dynamic_token" id="dynamic_token" placeholder="6-digit OTP (e.g. 5D8A3F)" required maxlength="6" style="text-transform:uppercase; margin-left: 0.5rem; max-width: 150px;">
        <button type="submit" class="btn btn-primary" style="margin-left: 0.5rem;">Submit</button>
    </form>
</div>
{% endblock %}
{% block scripts %}
<script>
document.addEventListener('DOMContentLoaded', function () {
    const codeInput = document.getElementById('session_code');
    const tokenInput = document.getElementById('dynamic_token');
    const statusEl = document.getElementById('qr-status');
    if (typeof Html5Qrcode === 'undefined') {
        if (statusEl) statusEl.textContent = 'QR library not loaded. Use manual code entry.';
        return;
    }

    const scanner = new Html5Qrcode('qr-reader');
    const config = { fps: 10, qrbox: { width: 250, height: 250 } };

    scanner.start(
        { facingMode: 'environment' },
        config,
        function (decodedText) {
            if (statusEl) statusEl.textContent = 'Code detected: ' + decodedText;
            const parts = decodedText.split('-');
            if (parts.length === 2) {
                if (codeInput) codeInput.value = parts[0].trim().toUpperCase();
                if (tokenInput) tokenInput.value = parts[1].trim().toUpperCase();
                document.getElementById('manual-form').submit();
            } else {
                if (codeInput) {
                    codeInput.value = decodedText.trim().toUpperCase();
                    codeInput.closest('form').submit();
                }
            }
            scanner.stop().catch(function () {});
        },
        function () {}
    ).catch(function () {
        if (statusEl) {
            statusEl.textContent = 'Camera unavailable. Enter the session code manually below.';
        }
    });
});
</script>
{% endblock %}
""",
    "student/history.html": """{% extends "base.html" %}
{% block title %}Attendance History{% endblock %}
{% block content %}
<h1>My Attendance History</h1>
{% if records %}
<div class="table-wrap card">
    <table>
        <thead>
            <tr><th>Lecture</th><th>Course Unit</th><th>Session Date</th><th>Marked At</th><th>Method</th></tr>
        </thead>
        <tbody>
            {% for r in records %}
            <tr>
                <td>{{ r.title }}</td>
                <td>{{ r.course_name }}</td>
                <td>{{ r.start_time[:16] }}</td>
                <td>{{ r.marked_at[:19] }}</td>
                <td><span class="badge">{{ r.method }}</span></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% else %}
<p class="empty card">No attendance records yet.</p>
{% endif %}
{% endblock %}
""",
    "lecturer/dashboard.html": """{% extends "base.html" %}
{% block title %}Lecturer Dashboard{% endblock %}
{% block content %}
<h1>Lecture Sessions</h1>
<p class="subtitle">Create and manage attendance sessions</p>

<div class="card">
    <h2>Create New Session</h2>
    <form method="POST" action="{{ url_for('create_session') }}" class="form form-grid">
        <div>
            <label>Session Title</label>
            <input type="text" name="title" required placeholder="Week 5 — Data Structures">
        </div>
        <div>
            <label>Course Unit (Subject)</label>
            <select name="course_unit_id" required>
                {% for cu in course_units %}
                <option value="{{ cu.id }}">{{ cu.code }} — {{ cu.name }} ({{ cu.course_code }})</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label>Duration (minutes)</label>
            <input type="number" name="duration" value="60" min="15" max="180">
        </div>
        <div class="form-actions">
            <button type="submit" class="btn btn-primary">Start Session</button>
        </div>
    </form>
</div>

<section class="card">
    <h2>Your Sessions</h2>
    {% if sessions %}
    <div class="table-wrap">
        <table>
            <thead>
                <tr><th>Title</th><th>Course Unit</th><th>Code</th><th>Time</th><th>Present</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody>
                {% for s in sessions %}
                <tr>
                    <td>{{ s.title }}</td>
                    <td>{{ s.course_name }}</td>
                    <td><code>{{ s.session_code }}</code></td>
                    <td>{{ s.start_time[:16] }}</td>
                    <td>{{ s.present_count }}</td>
                    <td>
                        {% if s.is_open %}
                        <span class="badge badge-success">Open</span>
                        {% else %}
                        <span class="badge badge-muted">Closed</span>
                        {% endif %}
                    </td>
                    <td class="actions">
                        <a href="{{ url_for('session_live', session_id=s.id) }}" class="btn btn-sm">Live</a>
                        <a href="{{ url_for('session_qr', session_id=s.id) }}" class="btn btn-sm btn-outline">QR</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <p class="empty">No sessions yet. Create one above.</p>
    {% endif %}
</section>
{% endblock %}
""",
    "lecturer/live.html": """{% extends "base.html" %}
{% block title %}Live — {{ sess.title }}{% endblock %}
{% block content %}\n<h1>{{ sess.title }}</h1>
<p class="subtitle">{{ sess.course_name }} · Code: <code>{{ sess.session_code }}</code></p>

<div class="stats-grid">
    <div class="stat-card highlight">
        <span class="stat-value" id="live-count">{{ attendees|length }}</span>
        <span class="stat-label">Present Now</span>
    </div>
    <div class="stat-card">
        <span class="stat-value" id="live-enrolled">{{ enrolled }}</span>
        <span class="stat-label">Enrolled Students</span>
    </div>
    <div class="stat-card">
        <span class="stat-value" id="live-pct">{% if enrolled %}{{ ((attendees|length / enrolled) * 100)|round(1) }}{% else %}0{% endif %}%</span>
        <span class="stat-label">Session Attendance</span>
    </div>
</div>

<div class="card">
    <h2>Attendees <span class="live-dot">● Live</span></h2>
    <div class="table-wrap">
        <table id="attendees-table">
            <thead>
                <tr><th>Name</th><th>Reg. No</th><th>Marked At</th><th>Method</th></tr>
            </thead>
            <tbody id="attendees-body">
                {% for a in attendees %}
                <tr>
                    <td>{{ a.full_name }}</td>
                    <td>{{ a.registration_number }}</td>
                    <td>{{ a.marked_at[:19] }}</td>
                    <td><span class="badge">{{ a.method }}</span></td>
                </tr>
                {% else %}
                <tr id="empty-row"><td colspan="4" class="empty">Waiting for students…</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
<a href="{{ url_for('lecturer_dashboard') }}" class="btn btn-outline">← Back to Sessions</a>
{% endblock %}
{% block scripts %}
<script>
function refreshAttendees() {
    if (typeof SESSION_ID === 'undefined') return;
    fetch('/api/session/' + SESSION_ID + '/attendees')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var countEl = document.getElementById('live-count');
            var enrolledEl = document.getElementById('live-enrolled');
            var pctEl = document.getElementById('live-pct');
            var tbody = document.getElementById('attendees-body');
            if (!tbody) return;

            if (countEl) countEl.textContent = data.count;
            if (enrolledEl) enrolledEl.textContent = data.enrolled;
            if (pctEl) {
                pctEl.textContent = data.enrolled
                    ? Math.round((data.count / data.enrolled) * 1000) / 10 + '%'
                    : '0%';
            }

            if (!data.attendees.length) {
                tbody.innerHTML = '<tr id="empty-row"><td colspan="4" class="empty">Waiting for students…</td></tr>';
                return;
            }

            tbody.innerHTML = data.attendees.map(function (a) {
                return '<tr><td>' + escapeHtml(a.full_name) + '</td><td>' +
                    escapeHtml(a.registration_number) + '</td><td>' +
                    (a.marked_at || '').substring(0, 19) + '</td><td><span class="badge">' +
                    escapeHtml(a.method) + '</span></td></tr>';
            }).join('');
        })
        .catch(function () {});
}

function escapeHtml(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

setInterval(refreshAttendees, 5000);
refreshAttendees();
</script>
<script>
    const SESSION_ID = {{ sess.id }};
</script>
{% endblock %}
""",
    "lecturer/qr.html": """{% extends "base.html" %}
{% block title %}QR — {{ sess.title }}{% endblock %}
{% block head %}
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
{% endblock %}
{% block content %}
<h1>Session QR Code</h1>
<p class="subtitle">{{ sess.title }} — Students scan this to mark attendance</p>

<div class="card qr-display">
    <div id="qrcode"></div>
    <p class="session-code" style="font-size: 1.5rem; margin-top: 1rem;">
        OTP: <strong id="otp-display" style="font-family: monospace; color: var(--primary);">{{ initial_token }}</strong>
    </p>
    <p class="session-code">Session Code: <strong>{{ sess.session_code }}</strong></p>
    
    <div style="max-width: 200px; margin: 1rem auto 0; background: rgba(255,255,255,0.05); height: 6px; border-radius: 3px; overflow: hidden;">
        <div id="progress-bar" style="background: var(--primary); height: 100%; width: 100%; transition: width 1s linear;"></div>
    </div>
    <p class="hint" id="timer-text" style="margin-top: 0.5rem;">Code expires in {{ sec_rem }}s</p>
</div>
<a href="{{ url_for('session_live', session_id=sess.id) }}" class="btn btn-primary">View Live Attendance</a>
<a href="{{ url_for('lecturer_dashboard') }}" class="btn btn-outline">← Back</a>
{% endblock %}
{% block scripts %}
<script>
    var qrcode = new QRCode(document.getElementById("qrcode"), {
        text: "{{ sess.session_code }}-{{ initial_token }}",
        width: 256,
        height: 256,
        colorDark: "#1e293b",
        colorLight: "#ffffff",
    });

    var sessId = {{ sess.id }};
    var baseCode = "{{ sess.session_code }}";

    // Set initial progress bar width
    var initialRem = {{ sec_rem }};
    document.getElementById('progress-bar').style.width = (initialRem / 30 * 100) + '%';

    function updateDynamicQR() {
        fetch('/api/session/' + sessId + '/dynamic_code')
            .then(r => r.json())
            .then(data => {
                var combinedCode = baseCode + "-" + data.dynamic_token;
                qrcode.clear();
                qrcode.makeCode(combinedCode);
                
                document.getElementById('otp-display').textContent = data.dynamic_token;
                
                var rem = data.seconds_remaining;
                document.getElementById('timer-text').textContent = 'Code expires in ' + rem + 's';
                document.getElementById('progress-bar').style.width = (rem / 30 * 100) + '%';
            })
            .catch(err => console.error(err));
    }

    setInterval(function() {
        var timerText = document.getElementById('timer-text');
        var bar = document.getElementById('progress-bar');
        var match = timerText.textContent.match(/\\d+/);
        if (match) {
            var rem = parseInt(match[0]) - 1;
            if (rem <= 0) {
                updateDynamicQR();
            } else {
                timerText.textContent = 'Code expires in ' + rem + 's';
                bar.style.width = (rem / 30 * 100) + '%';
            }
        }
    }, 1000);
</script>
{% endblock %}
""",
    "lecturer/reports.html": """{% extends "base.html" %}
{% block title %}Attendance Reports{% endblock %}
{% block content %}
<h1>Attendance Reports</h1>

<div class="card">
    <form method="GET" class="form form-grid filter-form">
        <div>
            <label>Course Unit</label>
            <select name="course_unit_id">
                <option value="">All units</option>
                {% for cu in course_units %}
                <option value="{{ cu.id }}" {% if filters.course_unit_id|string == cu.id|string %}selected{% endif %}>{{ cu.code }} — {{ cu.name }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label>From Date</label>
            <input type="date" name="date_from" value="{{ filters.date_from }}">
        </div>
        <div>
            <label>To Date</label>
            <input type="date" name="date_to" value="{{ filters.date_to }}">
        </div>
        <div>
            <label>Student (name or reg no)</label>
            <input type="text" name="student" value="{{ filters.student }}" placeholder="Search…">
        </div>
        <div class="form-actions">
            <button type="submit" class="btn btn-primary">Filter</button>
            <a href="{{ url_for('lecturer_reports') }}" class="btn btn-outline">Clear</a>
        </div>
    </form>
    <div class="export-btns">
        <a href="{{ url_for('export_reports', fmt='pdf', course_unit_id=filters.course_unit_id, date_from=filters.date_from, date_to=filters.date_to, student=filters.student) }}" class="btn btn-sm">Export PDF</a>
        <a href="{{ url_for('export_reports', fmt='excel', course_unit_id=filters.course_unit_id, date_from=filters.date_from, date_to=filters.date_to, student=filters.student) }}" class="btn btn-sm">Export Excel</a>
    </div>
</div>

{% if records %}
<div class="table-wrap card">
    <table>
        <thead>
            <tr><th>Lecture</th><th>Date</th><th>Program</th><th>Unit</th><th>Student</th><th>Reg No</th><th>Marked At</th><th>Method</th></tr>
        </thead>
        <tbody>
            {% for r in records %}
            <tr>
                <td>{{ r.title }}</td>
                <td>{{ r.start_time[:10] }}</td>
                <td>{{ r.course_code }}</td>
                <td>{{ r.course_name }}</td>
                <td>{{ r.full_name }}</td>
                <td>{{ r.registration_number }}</td>
                <td>{{ r.marked_at[:19] }}</td>
                <td><span class="badge">{{ r.method }}</span></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
<p class="hint">{{ records|length }} record(s) found</p>
{% else %}
<p class="empty card">No records match your filters.</p>
{% endif %}
{% endblock %}
""",
    "admin/dashboard.html": """{% extends "base.html" %}
{% block title %}Admin Dashboard{% endblock %}
{% block content %}
<h1>System Overview</h1>

<div class="stats-grid">
    <div class="stat-card highlight">
        <span class="stat-value">{{ overall_pct }}%</span>
        <span class="stat-label">Overall Attendance</span>
    </div>
    <div class="stat-card">
        <span class="stat-value">{{ stats.students }}</span>
        <span class="stat-label">Students</span>
    </div>
    <div class="stat-card">
        <span class="stat-value">{{ stats.lecturers }}</span>
        <span class="stat-label">Lecturers</span>
    </div>
    <div class="stat-card">
        <span class="stat-value">{{ stats.courses }}</span>
        <span class="stat-label">Programs (Degrees)</span>
    </div>
    <div class="stat-card">
        <span class="stat-value">{{ stats.course_units }}</span>
        <span class="stat-label">Course Units</span>
    </div>
    <div class="stat-card">
        <span class="stat-value">{{ stats.attendance_records }}</span>
        <span class="stat-label">Attendance Marks</span>
    </div>
</div>

<section class="card">
    <h2>Attendance by Program (Degree Course)</h2>
    <div class="table-wrap">
        <table>
            <thead>
                <tr><th>Program</th><th>Students Enrolled</th><th>Conducted Sessions</th><th>Marks</th><th>Rate</th></tr>
            </thead>
            <tbody>
                {% for c in course_stats %}
                <tr>
                    <td>{{ c.code }} — {{ c.name }}</td>
                    <td>{{ c.students }}</td>
                    <td>{{ c.sessions }}</td>
                    <td>{{ c.marks }}</td>
                    <td>
                        {% set possible = c.sessions * c.students %}
                        {% if possible %}{{ ((c.marks / possible) * 100)|round(1) }}%{% else %}—{% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</section>
{% endblock %}
""",
    "admin/users.html": """{% extends "base.html" %}
{% block title %}Manage Users{% endblock %}
{% block content %}
<h1>Manage Users</h1>

<div class="card">
    <h2>Add User</h2>
    <form method="POST" class="form form-grid">
        <input type="hidden" name="action" value="add">
        <div><label>Full Name</label><input type="text" name="full_name" required></div>
        <div><label>Email</label><input type="email" name="email" required></div>
        <div><label>Password</label><input type="password" name="password" value="password123"></div>
        <div>
            <label>Role</label>
            <select name="role" id="role-select" onchange="toggleStudentFields()">
                <option value="student">Student</option>
                <option value="lecturer">Lecturer</option>
            </select>
        </div>
        <div id="reg-field"><label>Registration No</label><input type="text" name="registration_number"></div>
        <div id="course-field">
            <label>Degree Program</label>
            <select name="course_id">
                <option value="">—</option>
                {% for c in courses %}<option value="{{ c.id }}">{{ c.code }}</option>{% endfor %}
            </select>
        </div>
        <div>
            <label>Department</label>
            <select name="department_id">
                <option value="">—</option>
                {% for d in departments %}<option value="{{ d.id }}">{{ d.name }}</option>{% endfor %}
            </select>
        </div>
        <div class="form-actions"><button type="submit" class="btn btn-primary">Add User</button></div>
    </form>
</div>

<div class="card table-wrap">
    <table>
        <thead>
            <tr><th>Name</th><th>Email</th><th>Role</th><th>Reg No</th><th>Program (Degree)</th><th>Status</th><th>Action</th></tr>
        </thead>
        <tbody>
            {% for u in users %}
            <tr>
                <td>{{ u.full_name }}</td>
                <td>{{ u.email }}</td>
                <td><span class="badge">{{ u.role }}</span></td>
                <td>{{ u.registration_number or '—' }}</td>
                <td>{{ u.course_name or '—' }}</td>
                <td>{% if u.is_active %}<span class="badge badge-success">Active</span>{% else %}<span class="badge badge-muted">Inactive</span>{% endif %}</td>
                <td>
                    <a href="{{ url_for('admin_edit_user', user_id=u.id) }}" class="btn btn-sm btn-outline" style="border-color: var(--primary); color: var(--primary); text-decoration: none; display: inline-block; margin-right: 0.25rem;">Edit</a>
                    <form method="POST" style="display:inline">
                        <input type="hidden" name="action" value="toggle">
                        <input type="hidden" name="user_id" value="{{ u.id }}">
                        {% if u.is_active %}
                        <button type="submit" class="btn btn-sm btn-outline" style="border-color: var(--warning); color: var(--warning);">Deactivate</button>
                        {% else %}
                        <button type="submit" class="btn btn-sm btn-outline" style="border-color: var(--success); color: var(--success);">Activate</button>
                        {% endif %}
                    </form>
                    <form method="POST" style="display:inline; margin-left: 0.25rem;" onsubmit="return confirm('Are you sure you want to delete this user? This will also remove their attendance history.');">
                        <input type="hidden" name="action" value="delete">
                        <input type="hidden" name="user_id" value="{{ u.id }}">
                        <button type="submit" class="btn btn-sm btn-outline" style="border-color: var(--danger); color: var(--danger);">Delete</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
{% block scripts %}
<script>
function toggleStudentFields() {
    const role = document.getElementById('role-select').value;
    document.getElementById('reg-field').style.display = role === 'student' ? 'block' : 'none';
    document.getElementById('course-field').style.display = role === 'student' ? 'block' : 'none';
}
toggleStudentFields();
</script>
{% endblock %}
""",
    "admin/courses.html": """{% extends "base.html" %}
{% block title %}Academic Layout{% endblock %}
{% block content %}
<h1>Academic Catalog Layout</h1>
<p class="subtitle">Govern Faculties, Departments, Programs (Degrees) and Course Units</p>

<div class="grid-2">
    <!-- 1. Add Faculty & Department -->
    <div class="card">
        <h2>Add Faculty</h2>
        <form method="POST" class="form">
            <input type="hidden" name="action" value="add_faculty">
            <label>Faculty Name</label>
            <input type="text" name="fac_name" placeholder="e.g. Faculty of Science" required>
            <button type="submit" class="btn btn-primary">Add Faculty</button>
        </form>
        <ul class="simple-list">
            {% for f in faculties %}<li>{{ f.name }}</li>{% endfor %}
        </ul>
    </div>
    
    <div class="card">
        <h2>Add Department</h2>
        <form method="POST" class="form">
            <input type="hidden" name="action" value="add_department">
            <label>Department Name</label>
            <input type="text" name="dept_name" placeholder="e.g. Computer Science" required>
            <label>Faculty</label>
            <select name="faculty_id" required>
                {% for f in faculties %}<option value="{{ f.id }}">{{ f.name }}</option>{% endfor %}
            </select>
            <button type="submit" class="btn btn-primary">Add Department</button>
        </form>
    </div>
</div>

<div class="grid-2" style="margin-top: 1.25rem;">
    <!-- 2. Add Program (Degree) & Course Unit -->
    <div class="card">
        <h2>Add Degree Program (Course)</h2>
        <form method="POST" class="form">
            <input type="hidden" name="action" value="add_course">
            <label>Program Code</label>
            <input type="text" name="code" required placeholder="BITC">
            <label>Program Title</label>
            <input type="text" name="name" required placeholder="Bachelor of Information Technology">
            <label>Assigned Department</label>
            <select name="department_id" required>
                {% for d in departments %}<option value="{{ d.id }}">{{ d.name }}</option>{% endfor %}
            </select>
            <button type="submit" class="btn btn-primary">Add Degree Program</button>
        </form>
    </div>

    <div class="card">
        <h2>Add Course Unit</h2>
        <form method="POST" class="form">
            <input type="hidden" name="action" value="add_course_unit">
            <label>Unit Code</label>
            <input type="text" name="cu_code" required placeholder="COMP-101">
            <label>Unit Name</label>
            <input type="text" name="cu_name" required placeholder="e.g. Computer Applications">
            <label>Degree Program (Parent Course)</label>
            <select name="course_id" required>
                {% for c in courses %}<option value="{{ c.id }}">{{ c.code }} - {{ c.name }}</option>{% endfor %}
            </select>
            <button type="submit" class="btn btn-primary">Add Course Unit</button>
        </form>
    </div>
</div>

<div class="card table-wrap" style="margin-top: 1.25rem;">
    <h2>Course Units Registry</h2>
    <table>
        <thead><tr><th>Unit Code</th><th>Unit Name</th><th>Degree Program</th><th>Department</th></tr></thead>
        <tbody>
            {% for cu in course_units %}
            <tr>
                <td><code>{{ cu.code }}</code></td>
                <td>{{ cu.name }}</td>
                <td>{{ cu.course_code }}</td>
                <td>{{ cu.department_name }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
""",
    "admin/edit_user.html": """{% extends "base.html" %}
{% block title %}Edit User{% endblock %}
{% block content %}
<div style="max-width: 600px; margin: 2rem auto;">
    <div class="card">
        <h2>Edit User Profile</h2>
        <form method="POST" class="form">
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.25rem; font-weight: 500;">Full Name</label>
                <input type="text" name="full_name" value="{{ user.full_name }}" required style="width: 100%; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: var(--text);">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.25rem; font-weight: 500;">Email</label>
                <input type="email" name="email" value="{{ user.email }}" required style="width: 100%; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: var(--text);">
            </div>
            
            {% if user.role == 'student' %}
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.25rem; font-weight: 500;">Registration Number</label>
                <input type="text" name="registration_number" value="{{ user.registration_number }}" required style="width: 100%; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: var(--text);">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.25rem; font-weight: 500;">Degree Program</label>
                <select name="course_id" required style="width: 100%; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: var(--text);">
                    {% for c in courses %}
                    <option value="{{ c.id }}" {% if user.course_id == c.id %}selected{% endif %}>{{ c.code }} - {{ c.name }}</option>
                    {% endfor %}
                </select>
            </div>
            {% endif %}
            
            {% if user.role == 'lecturer' %}
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.25rem; font-weight: 500;">Department</label>
                <select name="department_id" required style="width: 100%; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: var(--text);">
                    {% for d in departments %}
                    <option value="{{ d.id }}" {% if user.department_id == d.id %}selected{% endif %}>{{ d.name }}</option>
                    {% endfor %}
                </select>
            </div>
            {% endif %}
            
            <div style="margin-bottom: 1.5rem;">
                <label style="display: block; margin-bottom: 0.25rem; font-weight: 500;">New Password (leave blank to keep current password)</label>
                <input type="password" name="password" placeholder="••••••••" style="width: 100%; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: var(--text);">
            </div>
            
            <div class="form-actions" style="display: flex; gap: 0.5rem;">
                <button type="submit" class="btn btn-primary" style="flex: 1;">Save Changes</button>
                <a href="{{ url_for('admin_users') }}" class="btn btn-outline" style="flex: 1; text-decoration: none; display: flex; align-items: center; justify-content: center; text-align: center;">Cancel</a>
            </div>
        </form>
    </div>
</div>
{% endblock %}
""",
    "forgot_password.html": """{% extends "base.html" %}
{% block title %}Reset Password — AttendTrack{% endblock %}
{% block content %}
<div class="auth-card" style="max-width: 460px;">
    <div style="text-align: center; margin-bottom: 1rem;">
        <img src="/static/kyu_logo.png" alt="Kyambogo University Logo" style="height: 70px; filter: drop-shadow(0 0 8px var(--primary-glow));">
    </div>
    <h1 style="background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 50%, var(--secondary) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; font-size: 1.8rem; margin-bottom: 0.5rem; text-align: center;">Reset Password</h1>
    <p class="subtitle" style="margin-bottom: 1.5rem; text-align: center;">Verify identity to reset password</p>

    {% if step == 1 %}
    <form method="POST" class="form">
        <input type="hidden" name="step" value="1">
        <label>Email Address</label>
        <input type="email" name="email" required placeholder="you@university.edu" value="{{ email or '' }}">
        
        <label>Role</label>
        <select name="role" id="forgot-role" onchange="toggleFields()" required>
            <option value="student" {% if role == 'student' %}selected{% endif %}>Student</option>
            <option value="lecturer" {% if role == 'lecturer' %}selected{% endif %}>Lecturer</option>
        </select>
        
        <div id="reg-field" style="display: block;">
            <label>Registration Number</label>
            <input type="text" name="registration_number" placeholder="REG2024001" value="{{ registration_number or '' }}">
        </div>
        
        <div id="dept-field" style="display: none;">
            <label>Assigned Department</label>
            <select name="department_id">
                <option value="">Select Department</option>
                {% for d in departments %}
                <option value="{{ d.id }}" {% if department_id|string == d.id|string %}selected{% endif %}>{{ d.name }}</option>
                {% endfor %}
            </select>
        </div>
        
        <button type="submit" class="btn btn-primary btn-block">Verify Identity</button>
    </form>
    {% elif step == 2 %}
    <form method="POST" class="form">
        <input type="hidden" name="step" value="2">
        <input type="hidden" name="user_id" value="{{ user_id }}">
        <p style="color: var(--success); font-size: 0.9rem; margin-bottom: 1rem;">✔ Identity verified! Set your new password below.</p>
        
        <label>New Password</label>
        <input type="password" name="password" required minlength="6" placeholder="Min. 6 characters">
        
        <label>Confirm Password</label>
        <input type="password" name="confirm_password" required minlength="6" placeholder="••••••••">
        
        <button type="submit" class="btn btn-primary btn-block">Update Password</button>
    </form>
    {% endif %}
    
    <p class="auth-footer" style="margin-top: 1.5rem;"><a href="{{ url_for('login') }}">Return to Login</a></p>
</div>
{% endblock %}
{% block scripts %}
<script>
function toggleFields() {
    const role = document.getElementById('forgot-role').value;
    document.getElementById('reg-field').style.display = role === 'student' ? 'block' : 'none';
    document.getElementById('dept-field').style.display = role === 'lecturer' ? 'block' : 'none';
}
toggleFields();
</script>
{% endblock %}
"""
}

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.jinja_loader = DictLoader(TEMPLATES)
app.jinja_env.autoescape = select_autoescape(["html", "xml"])


@app.before_request
def before_request():
    close_expired_sessions()


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Access denied.", "danger")
                return redirect(url_for("dashboard"))
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


@app.context_processor
def inject_globals():
    return {
        "current_user": get_current_user(),
        "low_threshold": LOW_ATTENDANCE_THRESHOLD,
    }


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("home.html")


@app.route("/login", methods=["GET", "POST"])
def login():
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
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
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
        return redirect(url_for("login"))
    return render_template("register.html", courses=courses)


@app.route("/forgot-password", methods=["GET", "POST"])
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
            return redirect(url_for("login"))
            
    return render_template("forgot_password.html", step=1, departments=departments)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required()
def dashboard():
    role = session.get("role")
    if role == "student":
        return redirect(url_for("student_dashboard"))
    if role == "lecturer":
        return redirect(url_for("lecturer_dashboard"))
    return redirect(url_for("admin_dashboard"))


# --- Student routes ---

@app.route("/student")
@login_required("student")
def student_dashboard():
    user = get_current_user()
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


def get_dynamic_token(session_code, offset=0):
    import hashlib
    import time
    time_step = int(time.time() / 30) + offset
    raw = f"{session_code}-{time_step}"
    return hashlib.sha256(raw.encode()).hexdigest()[:6].upper()


@app.route("/api/session/<int:session_id>/dynamic_code")
@login_required()
def api_dynamic_code(session_id):
    with get_db() as conn:
        sess = conn.execute(
            "SELECT session_code, is_open FROM lecture_sessions WHERE id = ?",
            (session_id,)
        ).fetchone()
    if not sess or not sess["is_open"]:
        return jsonify({"error": "Session closed"}), 404
        
    import time
    current_time = time.time()
    sec_rem = 30 - int(current_time % 30)
    
    return jsonify({
        "session_code": sess["session_code"],
        "dynamic_token": get_dynamic_token(sess["session_code"]),
        "seconds_remaining": sec_rem
    })


@app.route("/student/scan", methods=["GET", "POST"])
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
            return redirect(url_for("student_scan"))
            
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
                return redirect(url_for("student_scan"))
                
            if not sess["is_open"]:
                flash("This lecture session has already closed/expired.", "danger")
                return redirect(url_for("student_scan"))
                
            if sess["course_id"] != user["course_id"]:
                flash(f"Access denied: This session is for {sess['program_code']} students.", "danger")
                return redirect(url_for("student_scan"))
                
            # Validate token against current and previous time steps
            token_curr = get_dynamic_token(sess["session_code"], offset=0)
            token_prev = get_dynamic_token(sess["session_code"], offset=-1)
            
            if token not in (token_curr, token_prev):
                flash("Dynamic OTP has expired. Please scan the newly generated QR code.", "danger")
                return redirect(url_for("student_scan"))
            
            existing = conn.execute(
                "SELECT id FROM attendance WHERE session_id = ? AND student_id = ?",
                (sess["id"], session["user_id"]),
            ).fetchone()
            if existing:
                flash("Attendance already marked.", "warning")
                return redirect(url_for("student_dashboard"))
                
            conn.execute(
                "INSERT INTO attendance (session_id, student_id, method) VALUES (?, ?, 'QR')",
                (sess["id"], session["user_id"]),
            )
            flash("Attendance marked successfully!", "success")
        return redirect(url_for("student_dashboard"))
    return render_template("student/scan.html")


@app.route("/student/mark/<int:session_id>", methods=["POST"])
@login_required("student")
def mark_attendance(session_id):
    user = get_current_user()
    method = request.form.get("method", "button")
    token = request.form.get("dynamic_token", "").strip().upper()
    
    if not token:
        flash("Dynamic OTP is required to register attendance.", "danger")
        return redirect(url_for("student_dashboard"))
        
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
            return redirect(url_for("student_dashboard"))
            
        if not sess["is_open"]:
            flash("This lecture session has already closed/expired.", "danger")
            return redirect(url_for("student_dashboard"))
            
        if sess["course_id"] != user["course_id"]:
            flash(f"Access denied: This session is for {sess['program_code']} students.", "danger")
            return redirect(url_for("student_dashboard"))
            
        # Validate dynamic token
        token_curr = get_dynamic_token(sess["session_code"], offset=0)
        token_prev = get_dynamic_token(sess["session_code"], offset=-1)
        
        if token not in (token_curr, token_prev):
            flash("Invalid or expired Dynamic OTP. Check the projector screen.", "danger")
            return redirect(url_for("student_dashboard"))
            
        existing = conn.execute(
            "SELECT id FROM attendance WHERE session_id = ? AND student_id = ?",
            (session_id, session["user_id"]),
        ).fetchone()
        if existing:
            flash("Attendance already marked.", "warning")
            return redirect(url_for("student_dashboard"))
            
        conn.execute(
            "INSERT INTO attendance (session_id, student_id, method) VALUES (?, ?, ?)",
            (session_id, session["user_id"], method),
        )
        flash("Attendance recorded.", "success")
    return redirect(url_for("student_dashboard"))


@app.route("/student/history")
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


@app.route("/student/notifications/read/<int:nid>")
@login_required("student")
def read_notification(nid):
    with get_db() as conn:
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
            (nid, session["user_id"]),
        )
    return redirect(url_for("student_dashboard"))


# --- Lecturer routes ---

@app.route("/lecturer")
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


@app.route("/lecturer/session/create", methods=["POST"])
@login_required("lecturer")
def create_session():
    title = request.form.get("title", "").strip()
    course_unit_id = request.form.get("course_unit_id")
    duration = int(request.form.get("duration", 60))
    if not title or not course_unit_id:
        flash("Title and course unit are required.", "danger")
        return redirect(url_for("lecturer_dashboard"))
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
    return redirect(url_for("lecturer_dashboard"))


@app.route("/lecturer/session/<int:session_id>/live")
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
            return redirect(url_for("lecturer_dashboard"))
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


@app.route("/api/session/<int:session_id>/attendees")
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


@app.route("/lecturer/reports")
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


@app.route("/lecturer/reports/export/<fmt>")
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
            return redirect(url_for("lecturer_reports"))
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
        return redirect(url_for("lecturer_reports"))

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


@app.route("/lecturer/session/<int:session_id>/qr")
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
        return redirect(url_for("lecturer_dashboard"))
        
    initial_token = get_dynamic_token(sess["session_code"])
    import time
    sec_rem = 30 - int(time.time() % 30)
    
    return render_template("lecturer/qr.html", sess=sess, initial_token=initial_token, sec_rem=sec_rem)


# --- Admin routes ---

@app.route("/admin")
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


@app.route("/admin/users", methods=["GET", "POST"])
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


@app.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
@login_required("admin")
def admin_edit_user(user_id):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ? AND role != 'admin'", (user_id,)).fetchone()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin_users"))
            
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
            return redirect(url_for("admin_users"))
            
    return render_template("admin/edit_user.html", user=user, courses=courses, departments=departments)


@app.route("/admin/courses", methods=["GET", "POST"])
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
            return redirect(url_for("admin_courses"))

    return render_template(
        "admin/courses.html",
        faculties=faculties,
        departments=departments,
        courses=courses,
        course_units=course_units
    )


if __name__ == "__main__":
    init_db()
    seed_demo_data()
    print("AttendTrack running at http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
import sqlite3
from contextlib import contextmanager
from werkzeug.security import generate_password_hash
from app.config import DATABASE

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
    from datetime import datetime
    now_str = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE lecture_sessions SET is_open = 0 WHERE is_open = 1 AND end_time < ?",
            (now_str,)
        )


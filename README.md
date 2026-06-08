# Lecture Attendance Registration System

Everything runs from **one file**: `attendance.py`

## Quick start

```bash
pip install -r requirements.txt
python attendance.py
```

Open **http://localhost:5000**

## Demo accounts (password: `password123`)

| Role     | Email                    |
|----------|--------------------------|
| Admin    | admin@university.edu     |
| Lecturer | lecturer@university.edu  |
| Student  | student@university.edu   |

## What's in the single file

- Flask backend and all routes
- SQLite database setup
- HTML templates (embedded)
- CSS and JavaScript (embedded)
- Dark mode, QR scan, live attendance, PDF/Excel export

The database file `attendance.db` is created automatically next to `attendance.py` on first run.

## Optional dependencies

- `openpyxl` — Excel export
- `reportlab` — PDF export

Both are listed in `requirements.txt`.

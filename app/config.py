import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-in-production-lecture-attendance")
DATABASE = os.path.join(BASE_DIR, "attendance.db")
LOW_ATTENDANCE_THRESHOLD = 75

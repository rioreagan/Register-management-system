import time
from flask import Blueprint, jsonify
from app.database import get_db
from app.auth import login_required, get_dynamic_token

api_bp = Blueprint("api", __name__)

@api_bp.route("/api/session/<int:session_id>/dynamic_code")
@login_required()
def api_dynamic_code(session_id):
    with get_db() as conn:
        sess = conn.execute(
            "SELECT session_code, is_open FROM lecture_sessions WHERE id = ?",
            (session_id,)
        ).fetchone()
    if not sess or not sess["is_open"]:
        return jsonify({"error": "Session closed"}), 404
        
    current_time = time.time()
    sec_rem = 30 - int(current_time % 30)
    
    return jsonify({
        "session_code": sess["session_code"],
        "dynamic_token": get_dynamic_token(sess["session_code"]),
        "seconds_remaining": sec_rem
    })

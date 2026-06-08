/**
 * seed.js
 * Lecture Attendance Registration System
 * Initializer for mock database state in LocalStorage with full Faculty -> Dept -> Program -> Unit hierarchy.
 */

const SEED_DATA = {
  faculties: [
    { id: "fac_sci", name: "Faculty of Science" },
    { id: "fac_eng", name: "Faculty of Engineering" }
  ],
  departments: [
    { id: "dept_cs", name: "Department of Computer Science", facultyId: "fac_sci" },
    { id: "dept_it", name: "Department of Information Technology", facultyId: "fac_sci" },
    { id: "dept_ba", name: "Department of Business Administration", facultyId: "fac_sci" },
    { id: "dept_ee", name: "Department of Electrical Engineering", facultyId: "fac_eng" }
  ],
  courses: [ // Represents Degree Programs (previously called courses)
    { id: "course_bitc", code: "BITC", name: "B. of Information Technology & Computing", departmentId: "dept_cs" },
    { id: "course_bis", code: "BIS", name: "B. of Information Systems", departmentId: "dept_cs" },
    { id: "course_db_degree", code: "BSc-DB", name: "BSc. in Database Systems & Analytics", departmentId: "dept_it" },
    { id: "course_mgmt", code: "BBA", name: "Bachelor of Business Administration", departmentId: "dept_ba" }
  ],
  courseUnits: [ // Represents subjects taught under degree programs
    { id: "unit_comp_app", code: "COMP-APP", name: "Computer Applications", courseId: "course_bitc" },
    { id: "unit_db_sys", code: "DB-SYS", name: "Database Management Systems", courseId: "course_bitc" },
    { id: "unit_soft_eng", code: "SOFT-ENG", name: "Software Engineering Principles", courseId: "course_bis" },
    { id: "unit_adv_db", code: "ADV-DB", name: "Advanced Databases", courseId: "course_db_degree" },
    { id: "unit_mgmt_princ", code: "MGMT-101", name: "Principles of Management", courseId: "course_mgmt" }
  ],
  users: [
    // Administrators
    { id: "user_admin", role: "admin", name: "Admin Portal", email: "admin@university.edu", regNo: "ADMIN", password: "admin", departmentId: "All" },
    
    // Lecturers
    { id: "user_smith", role: "lecturer", name: "Dr. Alan Smith", email: "smith@university.edu", regNo: "L-101", password: "123", departmentId: "dept_cs" },
    { id: "user_jones", role: "lecturer", name: "Prof. Sarah Jones", email: "jones@university.edu", regNo: "L-102", password: "123", departmentId: "dept_it" },
    { id: "user_clark", role: "lecturer", name: "Dr. Emily Clark", email: "clark@university.edu", regNo: "L-103", password: "123", departmentId: "dept_ba" },
    
    // Students (courseId refers to their enrolled Program/Degree)
    { id: "user_alice", role: "student", name: "Alice Vance", email: "alice@student.edu", regNo: "S2026-001", password: "123", courseId: "course_bitc", departmentId: "dept_cs" },
    { id: "user_bob", role: "student", name: "Bob Miller", email: "bob@student.edu", regNo: "S2026-002", password: "123", courseId: "course_bitc", departmentId: "dept_cs" },
    { id: "user_charlie", role: "student", name: "Charlie Green", email: "charlie@student.edu", regNo: "S2026-003", password: "123", courseId: "course_bis", departmentId: "dept_cs" },
    { id: "user_diana", role: "student", name: "Diana Prince", email: "diana@student.edu", regNo: "S2026-004", password: "123", courseId: "course_db_degree", departmentId: "dept_it" },
    { id: "user_evan", role: "student", name: "Evan Wright", email: "evan@student.edu", regNo: "S2026-005", password: "123", courseId: "course_mgmt", departmentId: "dept_ba" },
    { id: "user_fiona", role: "student", name: "Fiona Gallagher", email: "fiona@student.edu", regNo: "S2026-006", password: "123", courseId: "course_bitc", departmentId: "dept_cs" },
    { id: "user_george", role: "student", name: "George Costanza", email: "george@student.edu", regNo: "S2026-007", password: "123", courseId: "course_db_degree", departmentId: "dept_it" },
    { id: "user_hannah", role: "student", name: "Hannah Abbott", email: "hannah@student.edu", regNo: "S2026-008", password: "123", courseId: "course_bis", departmentId: "dept_cs" },
    { id: "user_ian", role: "student", name: "Ian Malcolm", email: "ian@student.edu", regNo: "S2026-009", password: "123", courseId: "course_bitc", departmentId: "dept_cs" },
    { id: "user_julia", role: "student", name: "Julia Roberts", email: "julia@student.edu", regNo: "S2026-010", password: "123", courseId: "course_mgmt", departmentId: "dept_ba" }
  ],
  sessions: [
    // Past Sessions for Computer Applications (unit_comp_app)
    { id: "sess_web_1", courseUnitId: "unit_comp_app", lecturerId: "user_smith", date: "2026-05-25", startTime: "09:00", endTime: "11:00", code: "WEB-78A", active: false },
    { id: "sess_web_2", courseUnitId: "unit_comp_app", lecturerId: "user_smith", date: "2026-05-28", startTime: "09:00", endTime: "11:00", code: "WEB-92X", active: false },
    { id: "sess_web_3", courseUnitId: "unit_comp_app", lecturerId: "user_smith", date: "2026-06-01", startTime: "09:00", endTime: "11:00", code: "WEB-33Q", active: false },
    
    // Past Sessions for Database Systems (unit_db_sys)
    { id: "sess_intro_1", courseUnitId: "unit_db_sys", lecturerId: "user_smith", date: "2026-05-26", startTime: "14:00", endTime: "16:00", code: "CS-41B", active: false },
    { id: "sess_intro_2", courseUnitId: "unit_db_sys", lecturerId: "user_smith", date: "2026-05-29", startTime: "14:00", endTime: "16:00", code: "CS-55Y", active: false },
    
    // Past Sessions for Advanced DB (unit_adv_db)
    { id: "sess_db_1", courseUnitId: "unit_adv_db", lecturerId: "user_jones", date: "2026-05-27", startTime: "10:30", endTime: "12:30", code: "DB-12Z", active: false },
    
    // Active / Live Session right now for Computer Applications
    { id: "sess_web_active", courseUnitId: "unit_comp_app", lecturerId: "user_smith", date: "2026-06-05", startTime: "09:00", endTime: "17:00", code: "ATT-LIVE", active: true }
  ],
  attendance: [
    // Attendance for sess_web_1
    { id: "att_1", sessionId: "sess_web_1", studentId: "user_alice", timestamp: "2026-05-25T09:05:12.124Z", status: "Present" },
    { id: "att_2", sessionId: "sess_web_1", studentId: "user_bob", timestamp: "2026-05-25T09:08:44.201Z", status: "Present" },
    { id: "att_3", sessionId: "sess_web_1", studentId: "user_fiona", timestamp: "2026-05-25T09:12:05.510Z", status: "Present" },
    { id: "att_4", sessionId: "sess_web_1", studentId: "user_ian", timestamp: "2026-05-25T09:45:00.000Z", status: "Late" },
    
    // Attendance for sess_web_2
    { id: "att_5", sessionId: "sess_web_2", studentId: "user_alice", timestamp: "2026-05-28T09:03:22.981Z", status: "Present" },
    { id: "att_6", sessionId: "sess_web_2", studentId: "user_bob", timestamp: "2026-05-28T09:04:11.455Z", status: "Present" },
    { id: "att_7", sessionId: "sess_web_2", studentId: "user_fiona", timestamp: "2026-05-28T09:10:30.222Z", status: "Present" },
    
    // Attendance for sess_web_3
    { id: "att_8", sessionId: "sess_web_3", studentId: "user_alice", timestamp: "2026-06-01T09:02:10.015Z", status: "Present" },
    { id: "att_9", sessionId: "sess_web_3", studentId: "user_bob", timestamp: "2026-06-01T09:07:33.782Z", status: "Present" },
    { id: "att_10", sessionId: "sess_web_3", studentId: "user_ian", timestamp: "2026-06-01T09:05:44.912Z", status: "Present" },
    
    // Attendance for sess_intro_1
    { id: "att_11", sessionId: "sess_intro_1", studentId: "user_charlie", timestamp: "2026-05-26T14:04:22.091Z", status: "Present" },
    { id: "att_12", sessionId: "sess_intro_1", studentId: "user_hannah", timestamp: "2026-05-26T14:06:55.124Z", status: "Present" },
    
    // Attendance for sess_intro_2
    { id: "att_13", sessionId: "sess_intro_2", studentId: "user_charlie", timestamp: "2026-05-29T14:02:11.512Z", status: "Present" },
    
    // Attendance for sess_db_1
    { id: "att_14", sessionId: "sess_db_1", studentId: "user_diana", timestamp: "2026-05-27T10:33:14.992Z", status: "Present" },
    { id: "att_15", sessionId: "sess_db_1", studentId: "user_george", timestamp: "2026-05-27T10:41:02.103Z", status: "Present" },
    
    // Live attendance marks so far
    { id: "att_live_1", sessionId: "sess_web_active", studentId: "user_bob", timestamp: "2026-06-05T09:15:30.000Z", status: "Present" }
  ]
};

// Seed function to call on load
function initializeDatabase() {
  const isSeeded = localStorage.getItem("att_sys_seeded_v2");
  if (!isSeeded) {
    console.log("Seeding LocalStorage with mock database values (v2)...");
    
    // Clear old format items
    localStorage.removeItem("att_sys_seeded");
    
    // Save new format items
    localStorage.setItem("att_sys_seeded_v2", "true");
    localStorage.setItem("att_sys_faculties", JSON.stringify(SEED_DATA.faculties));
    localStorage.setItem("att_sys_departments", JSON.stringify(SEED_DATA.departments));
    localStorage.setItem("att_sys_courses", JSON.stringify(SEED_DATA.courses)); // Courses = degree programs
    localStorage.setItem("att_sys_course_units", JSON.stringify(SEED_DATA.courseUnits)); // Course Units = subjects
    localStorage.setItem("att_sys_users", JSON.stringify(SEED_DATA.users));
    localStorage.setItem("att_sys_sessions", JSON.stringify(SEED_DATA.sessions));
    localStorage.setItem("att_sys_attendance", JSON.stringify(SEED_DATA.attendance));
  }
}

// Reset function to clear and re-seed
function resetDatabase() {
  localStorage.removeItem("att_sys_seeded_v2");
  localStorage.removeItem("att_sys_faculties");
  localStorage.removeItem("att_sys_departments");
  localStorage.removeItem("att_sys_courses");
  localStorage.removeItem("att_sys_course_units");
  localStorage.removeItem("att_sys_users");
  localStorage.removeItem("att_sys_sessions");
  localStorage.removeItem("att_sys_attendance");
  initializeDatabase();
  window.location.reload();
}

// Automatically execute on load
initializeDatabase();

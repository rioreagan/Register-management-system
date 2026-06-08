/**
 * app.js
 * Lecture Attendance Registration System
 * Core logical controller handling router, auth, database, UI, and report features
 */

// Global State
let currentUser = null;
let currentView = "home";
let activeTheme = "dark";
let charts = {}; // Track Chart.js instances

// Database Controller (LocalStorage Wrapper)
const DB = {
  get(key) {
    return JSON.parse(localStorage.getItem(`att_sys_${key}`)) || [];
  },
  save(key, data) {
    localStorage.setItem(`att_sys_${key}`, JSON.stringify(data));
  },
  
  // Entity Accessors
  getFaculties() { return this.get("faculties"); },
  getDepartments() { return this.get("departments"); },
  getCourses() { return this.get("courses"); }, // Programs
  getCourseUnits() { return this.get("course_units"); },
  getUsers() { return this.get("users"); },
  getSessions() { return this.get("sessions"); },
  getAttendance() { return this.get("attendance"); },
  
  // Entity Mutators
  saveFaculties(data) { this.save("faculties", data); },
  saveDepartments(data) { this.save("departments", data); },
  saveCourses(data) { this.save("courses", data); },
  saveCourseUnits(data) { this.save("course_units", data); },
  saveUsers(data) { this.save("users", data); },
  saveSessions(data) { this.save("sessions", data); },
  saveAttendance(data) { this.save("attendance", data); },
  
  // Queries
  findUser(emailOrReg, password) {
    const users = this.getUsers();
    return users.find(u => (u.email.toLowerCase() === emailOrReg.toLowerCase() || u.regNo.toUpperCase() === emailOrReg.toUpperCase()) && u.password === password);
  },
  
  getAttendanceWithDetails() {
    const att = this.getAttendance();
    const users = this.getUsers();
    const sessions = this.getSessions();
    const courses = this.getCourses(); // Degree programs (e.g. BITC)
    const units = this.getCourseUnits(); // Course units (e.g. Computer Applications)
    const depts = this.getDepartments();
    const facs = this.getFaculties();
    
    return att.map(record => {
      const student = users.find(u => u.id === record.studentId) || { name: "Unknown", regNo: "N/A", courseId: "" };
      const session = sessions.find(s => s.id === record.sessionId) || { courseUnitId: "", lecturerId: "", date: "", code: "" };
      const unit = units.find(u => u.id === session.courseUnitId) || { name: "Unknown Unit", code: "N/A", courseId: "" };
      const course = courses.find(c => c.id === unit.courseId) || { name: "Unknown Program", code: "N/A", departmentId: "" };
      const dept = depts.find(d => d.id === course.departmentId) || { name: "Unknown Department", facultyId: "" };
      const fac = facs.find(f => f.id === dept.facultyId) || { name: "Unknown Faculty" };
      const lecturer = users.find(u => u.id === session.lecturerId) || { name: "Unknown Lecturer" };
      
      return {
        ...record,
        studentName: student.name,
        studentReg: student.regNo,
        courseName: unit.name, // Display subject unit name
        courseCode: unit.code, // Subject unit code
        programCode: course.code, // Degree program code (BITC)
        programName: course.name,
        lecturerName: lecturer.name,
        sessionCode: session.code,
        sessionDate: session.date,
        sessionActive: session.active,
        departmentName: dept.name,
        facultyName: fac.name
      };
    });
  }
};

// Auto-check and close expired sessions
function checkSessionExpiration() {
  const sessions = DB.getSessions();
  const now = new Date();
  const timeStr = now.toTimeString().substring(0, 5); // "HH:MM"
  const dateStr = now.toISOString().substring(0, 10); // "YYYY-MM-DD"
  let changed = false;

  sessions.forEach(s => {
    if (s.active) {
      const isPastDate = s.date < dateStr;
      const isPastTime = s.date === dateStr && s.endTime < timeStr;
      if (isPastDate || isPastTime) {
        s.active = false;
        changed = true;
        showToast(`Lecture Session ${s.code} has automatically closed.`, "warning");
      }
    }
  });

  if (changed) {
    DB.saveSessions(sessions);
  }
}

// Global UI Handlers
function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  
  let icon = "check-circle";
  if (type === "error") icon = "alert-triangle";
  if (type === "warning") icon = "info";
  
  toast.innerHTML = `
    <i data-lucide="${icon}"></i>
    <span>${message}</span>
  `;
  container.appendChild(toast);
  lucide.createIcons();
  
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(-10px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Router & Views Switcher
function navigate(viewName) {
  currentView = viewName;
  checkSessionExpiration();
  
  // Hide all screens
  document.querySelectorAll(".app-screen").forEach(screen => {
    screen.style.display = "none";
  });
  
  // Show target screen
  const targetScreen = document.getElementById(`${viewName}-screen`);
  if (targetScreen) {
    targetScreen.style.display = "block";
    targetScreen.classList.add("animate-fade");
  }
  
  // Render views specific logic
  if (viewName === "student-dashboard") renderStudentDashboard();
  if (viewName === "lecturer-dashboard") renderLecturerDashboard();
  if (viewName === "admin-dashboard") renderAdminDashboard();
  if (viewName === "forgot") {
    document.getElementById("forgot-verify-form").style.display = "block";
    document.getElementById("forgot-reset-form").style.display = "none";
    document.getElementById("forgot-verify-form").reset();
    document.getElementById("forgot-reset-form").reset();
    forgotTempUser = null;
    toggleForgotRoleFields();
    
    // Populate departments dropdown
    const depts = DB.getDepartments();
    const select = document.getElementById("forgot-dept");
    if (select) {
      select.innerHTML = "";
      depts.forEach(d => {
        select.innerHTML += `<option value="${d.id}">${d.name}</option>`;
      });
    }
  }
  
  // Update Navbar UI
  updateNavbar();
}

function updateNavbar() {
  const navbar = document.getElementById("main-nav");
  if (!currentUser) {
    navbar.style.display = "none";
    return;
  }
  
  navbar.style.display = "flex";
  document.getElementById("nav-user-name").textContent = currentUser.name;
  
  // Get department info for display
  const depts = DB.getDepartments();
  const myDept = depts.find(d => d.id === currentUser.departmentId);
  const deptLabel = myDept ? ` | ${myDept.name}` : "";
  
  document.getElementById("nav-user-role").textContent = currentUser.role.toUpperCase() + deptLabel;
}

// Auth Handlers
function handleLogin(e) {
  e.preventDefault();
  const identifier = document.getElementById("login-id").value.trim();
  const pass = document.getElementById("login-pass").value;
  
  const user = DB.findUser(identifier, pass);
  if (user) {
    currentUser = user;
    showToast(`Welcome back, ${user.name}!`, "success");
    
    if (user.role === "student") navigate("student-dashboard");
    else if (user.role === "lecturer") navigate("lecturer-dashboard");
    else if (user.role === "admin") navigate("admin-dashboard");
  } else {
    showToast("Invalid credentials. Please try again.", "error");
  }
}

function handleRegister(e) {
  e.preventDefault();
  const name = document.getElementById("reg-name").value.trim();
  const regNo = document.getElementById("reg-no").value.trim().toUpperCase();
  const email = document.getElementById("reg-email").value.trim();
  const courseId = document.getElementById("reg-course").value; // Enrolled Degree Program
  const password = document.getElementById("reg-pass").value;
  
  const users = DB.getUsers();
  
  // Validations
  if (users.some(u => u.regNo === regNo)) {
    showToast("Registration Number already exists.", "error");
    return;
  }
  if (users.some(u => u.email.toLowerCase() === email.toLowerCase())) {
    showToast("Email Address is already registered.", "error");
    return;
  }
  
  const courses = DB.getCourses();
  const studentCourse = courses.find(c => c.id === courseId);
  
  const newStudent = {
    id: "user_" + Date.now(),
    role: "student",
    name,
    regNo,
    email,
    password,
    courseId, // References Degree Program (e.g. course_bitc)
    departmentId: studentCourse ? studentCourse.departmentId : "dept_cs"
  };
  
  users.push(newStudent);
  DB.saveUsers(users);
  
  showToast("Registration successful! You can now log in.", "success");
  navigate("login");
}

function logout() {
  currentUser = null;
  navigate("home");
  showToast("Logged out successfully.", "success");
}

let forgotTempUser = null;

function toggleForgotRoleFields() {
  const role = document.getElementById("forgot-role").value;
  document.getElementById("forgot-student-fields").style.display = role === "student" ? "block" : "none";
  document.getElementById("forgot-lecturer-fields").style.display = role === "lecturer" ? "block" : "none";
}

function handleForgotVerify(e) {
  e.preventDefault();
  const email = document.getElementById("forgot-email").value.trim().toLowerCase();
  const role = document.getElementById("forgot-role").value;
  const regNo = document.getElementById("forgot-reg").value.trim().toUpperCase();
  const deptId = document.getElementById("forgot-dept").value;
  
  const users = DB.getUsers();
  let foundUser = null;
  
  if (role === "student") {
    foundUser = users.find(u => u.role === "student" && u.email.toLowerCase() === email && u.regNo.toUpperCase() === regNo);
  } else if (role === "lecturer") {
    foundUser = users.find(u => u.role === "lecturer" && u.email.toLowerCase() === email && u.departmentId === deptId);
  }
  
  if (foundUser) {
    forgotTempUser = foundUser;
    document.getElementById("forgot-verify-form").style.display = "none";
    document.getElementById("forgot-reset-form").style.display = "block";
    showToast("Identity verified! Set your new password.", "success");
  } else {
    showToast("Invalid email or security verification details.", "error");
  }
}

function handleForgotReset(e) {
  e.preventDefault();
  if (!forgotTempUser) {
    showToast("Session expired. Please verify again.", "error");
    navigate("forgot");
    return;
  }
  
  const newPass = document.getElementById("forgot-new-pass").value;
  const confirmPass = document.getElementById("forgot-confirm-pass").value;
  
  if (newPass !== confirmPass) {
    showToast("Passwords do not match.", "error");
    return;
  }
  
  const users = DB.getUsers();
  const userIndex = users.findIndex(u => u.id === forgotTempUser.id);
  if (userIndex !== -1) {
    users[userIndex].password = newPass;
    DB.saveUsers(users);
    showToast("Password updated successfully! Log in now.", "success");
    forgotTempUser = null;
    navigate("login");
  } else {
    showToast("Error updating password.", "error");
  }
}

// Student Dashboard Logic
function renderStudentDashboard() {
  const courses = DB.getCourses();
  const myCourse = courses.find(c => c.id === currentUser.courseId) || { name: "Not Enrolled", code: "N/A", departmentId: "" };
  
  const depts = DB.getDepartments();
  const facs = DB.getFaculties();
  const myDept = depts.find(d => d.id === myCourse.departmentId) || { name: "General Science", facultyId: "" };
  const myFac = facs.find(f => f.id === myDept.facultyId) || { name: "Faculty of Science" };
  
  document.getElementById("student-course-name").textContent = myCourse.name;
  document.getElementById("student-course-code").textContent = myCourse.code;
  document.getElementById("student-dept").textContent = `${myDept.name} (${myFac.name})`;
  
  // Enrolled Course Units under this program
  const units = DB.getCourseUnits().filter(cu => cu.courseId === currentUser.courseId);
  const unitIds = units.map(u => u.id);
  
  // Student Attendance Stats
  const attendance = DB.getAttendance();
  // Filter sessions that belong to the student's program course units
  const sessions = DB.getSessions().filter(s => unitIds.includes(s.courseUnitId));
  const myAttendance = attendance.filter(a => a.studentId === currentUser.id);
  
  const totalClasses = sessions.length;
  const classesAttended = myAttendance.filter(a => a.status === "Present" || a.status === "Late").length;
  const attendancePct = totalClasses > 0 ? Math.round((classesAttended / totalClasses) * 100) : 0;
  
  document.getElementById("student-attended").textContent = classesAttended;
  document.getElementById("student-total").textContent = totalClasses;
  document.getElementById("student-pct").textContent = `${attendancePct}%`;
  
  const pctIndicator = document.getElementById("student-pct-card");
  if (attendancePct < 75) {
    pctIndicator.style.borderColor = "var(--danger)";
    document.getElementById("student-warning-msg").style.display = "block";
  } else {
    pctIndicator.style.borderColor = "var(--success)";
    document.getElementById("student-warning-msg").style.display = "none";
  }
  
  // Find current active lecture session for student's course units
  const activeSession = DB.getSessions().find(s => unitIds.includes(s.courseUnitId) && s.active);
  const markCard = document.getElementById("active-session-card");
  
  if (activeSession) {
    const unit = units.find(u => u.id === activeSession.courseUnitId) || { name: "Lecture Unit" };
    // Check if already marked
    const alreadyMarked = attendance.some(a => a.sessionId === activeSession.id && a.studentId === currentUser.id);
    
    if (alreadyMarked) {
      markCard.innerHTML = `
        <div class="badge badge-present mb-4">Attendance Recorded</div>
        <h3 class="mb-4">Already Checked In</h3>
        <p class="text-secondary">You have registered check-in for course unit: <strong>${unit.name}</strong>.</p>
      `;
    } else {
      markCard.innerHTML = `
        <div class="badge badge-active mb-4">Active Lecture Unit</div>
        <h3 class="mb-4">${unit.name} (${unit.code})</h3>
        <p class="text-secondary mb-4">Time: ${activeSession.startTime} - ${activeSession.endTime} | Code: <strong>${activeSession.code}</strong></p>
        <div class="flex-gap-4 justify-center">
          <button class="btn btn-primary" onclick="openQRScanner('${activeSession.code}', '${activeSession.id}')">
            <i data-lucide="qr-code"></i> Scan Lecture QR
          </button>
          <div style="width: 1px; height: 30px; background: var(--border-glass)"></div>
          <button class="btn btn-secondary" onclick="openManualCodeModal('${activeSession.code}', '${activeSession.id}')">
            Submit Code
          </button>
        </div>
      `;
      lucide.createIcons();
    }
  } else {
    markCard.innerHTML = `
      <i data-lucide="calendar-off" style="font-size: 2.5rem; color: var(--text-muted); margin-bottom: 12px;"></i>
      <h3 class="mb-4">No Active Units</h3>
      <p class="text-secondary">No active attendance check-in session is running for your degree program units.</p>
    `;
    lucide.createIcons();
  }
  
  // Render History Table
  const historyBody = document.getElementById("student-history-body");
  historyBody.innerHTML = "";
  
  if (sessions.length === 0) {
    historyBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No attendance logs found.</td></tr>`;
    return;
  }
  
  sessions.sort((a, b) => new Date(b.date + "T" + b.startTime) - new Date(a.date + "T" + a.startTime));
  
  sessions.forEach(sess => {
    const record = myAttendance.find(a => a.sessionId === sess.id);
    const unit = DB.getCourseUnits().find(cu => cu.id === sess.courseUnitId) || { name: "Unknown" };
    let statusBadge = `<span class="badge badge-absent">Absent</span>`;
    let timeText = "—";
    
    if (record) {
      statusBadge = `<span class="badge badge-${record.status.toLowerCase()}">${record.status}</span>`;
      const time = new Date(record.timestamp);
      timeText = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><strong>${sess.date}</strong></td>
      <td>${unit.name}<br><small class="text-muted">${sess.startTime} - ${sess.endTime}</small></td>
      <td>${timeText}</td>
      <td>${statusBadge}</td>
    `;
    historyBody.appendChild(row);
  });
}

// Student Attendance Submissions
function getSPADynamicToken(sessionCode, timeOffset = 0) {
  const timeStep = Math.floor(Date.now() / 30000) + timeOffset;
  const str = `${sessionCode}-${timeStep}`;
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash).toString(16).substring(0, 6).toUpperCase();
}

function openQRScanner(correctCode, sessionId) {
  const overlay = document.getElementById("qr-scanner-modal");
  overlay.classList.add("active");
  
  // Set up mock scanner action
  document.getElementById("btn-sim-scan").onclick = () => {
    overlay.classList.remove("active");
    const currentOtp = getSPADynamicToken(correctCode, 0);
    const combinedString = `${correctCode}-${currentOtp}`;
    submitAttendance(sessionId, combinedString, "Present");
  };
}

function openManualCodeModal(correctCode, sessionId) {
  const code = prompt("Please enter the dynamic 6-digit OTP currently displayed on the screen:");
  if (code === null) return; // Cancelled
  
  submitAttendance(sessionId, code.trim().toUpperCase(), "Present");
}

function submitAttendance(sessionId, input, defaultStatus) {
  const sessions = DB.getSessions();
  const session = sessions.find(s => s.id === sessionId);
  
  if (!session || !session.active) {
    showToast("Attendance is closed or session has expired.", "error");
    return;
  }

  let baseCode = session.code;
  let otp = input.trim().toUpperCase();

  if (otp.includes("-")) {
    const parts = otp.split("-");
    baseCode = parts[0].trim();
    otp = parts[1].trim();
  }

  // Validate OTP against current and previous 30s steps to handle clock drift
  const tokenCurr = getSPADynamicToken(baseCode, 0);
  const tokenPrev = getSPADynamicToken(baseCode, -1);

  if (otp !== tokenCurr && otp !== tokenPrev) {
    showToast("Invalid or expired OTP check-in code.", "error");
    return;
  }
  
  const attendance = DB.getAttendance();
  const alreadyMarked = attendance.some(a => a.sessionId === sessionId && a.studentId === currentUser.id);
  
  if (alreadyMarked) {
    showToast("You have already checked in.", "warning");
    return;
  }
  
  // Calculate if student is Late (threshold: 15 mins)
  const now = new Date();
  const [startHour, startMin] = session.startTime.split(":").map(Number);
  const lateTime = new Date();
  lateTime.setHours(startHour, startMin + 15, 0);
  
  let finalStatus = defaultStatus;
  if (now > lateTime) {
    finalStatus = "Late";
    showToast("Attendance logged, but marked LATE.", "warning");
  } else {
    showToast("Attendance marked present!", "success");
  }
  
  const newRecord = {
    id: "att_" + Date.now(),
    sessionId: sessionId,
    studentId: currentUser.id,
    timestamp: now.toISOString(),
    status: finalStatus
  };
  
  attendance.push(newRecord);
  DB.saveAttendance(attendance);
  
  renderStudentDashboard();
}

// Lecturer Dashboard Logic
let liveAttendeeInterval = null;

function renderLecturerDashboard() {
  // Available Programs in Lecturer's department
  const courses = DB.getCourses().filter(c => c.departmentId === currentUser.departmentId);
  const courseIds = courses.map(c => c.id);
  
  // Course Units belonging to those programs
  const units = DB.getCourseUnits().filter(cu => courseIds.includes(cu.courseId));
  
  const courseSelect = document.getElementById("sess-course");
  courseSelect.innerHTML = "";
  units.forEach(u => {
    const parentCourse = courses.find(c => c.id === u.courseId) || { code: "N/A" };
    courseSelect.innerHTML += `<option value="${u.id}">${u.code} - ${u.name} (${parentCourse.code})</option>`;
  });
  
  // Populate Reports filter selector
  const repCourse = document.getElementById("rep-filter-course");
  repCourse.innerHTML = `<option value="all">All Units</option>`;
  units.forEach(u => {
    repCourse.innerHTML += `<option value="${u.id}">${u.code} — ${u.name}</option>`;
  });
  
  // Live Active Session Check
  const activeSession = DB.getSessions().find(s => s.lecturerId === currentUser.id && s.active);
  const activeSessionBox = document.getElementById("lecturer-active-session-box");
  
  if (activeSession) {
    const unit = units.find(u => u.id === activeSession.courseUnitId) || { name: "Lecture Unit" };
    
    if (liveAttendeeInterval) clearInterval(liveAttendeeInterval);
    
    activeSessionBox.style.display = "block";
    activeSessionBox.innerHTML = `
      <div class="glass-card animate-scale" style="border-color: var(--primary)">
        <div class="flex-between mb-4">
          <div class="flex-gap-2">
            <span class="badge badge-active">Live Monitoring</span>
            <strong class="text-primary-color">Code: ${activeSession.code}</strong>
          </div>
          <button class="btn btn-danger btn-sm" onclick="closeSession('${activeSession.id}')">
            <i data-lucide="power"></i> Close Session
          </button>
        </div>
        <h3 class="mb-4">${unit.name}</h3>
        <p class="text-secondary mb-4">Conducted Time: ${activeSession.startTime} - ${activeSession.endTime}</p>
        
        <div class="flex-gap-4 mb-4">
          <button class="btn btn-primary btn-sm" onclick="showLiveQR('${activeSession.code}')">
            <i data-lucide="qr-code"></i> Project QR Code
          </button>
          <button class="btn btn-secondary btn-sm" onclick="simulateStudentJoin('${activeSession.id}', '${activeSession.courseUnitId}')">
            <i data-lucide="users"></i> Simulate Student Check-in
          </button>
        </div>
        
        <div style="border-top: 1px solid var(--border-glass); padding-top: 16px;">
          <h4 class="mb-4">Real-Time Attendee Queue (<span id="live-count">0</span> check-ins)</h4>
          <div class="live-attendee-feed" id="live-stream-feed"></div>
        </div>
      </div>
    `;
    lucide.createIcons();
    
    updateLiveAttendeeStream(activeSession.id);
    liveAttendeeInterval = setInterval(() => updateLiveAttendeeStream(activeSession.id), 3000);
    
  } else {
    if (liveAttendeeInterval) {
      clearInterval(liveAttendeeInterval);
      liveAttendeeInterval = null;
    }
    activeSessionBox.style.display = "none";
  }
  
  filterLecturerReports();
}

let liveQRInterval = null;

function showLiveQR(code) {
  const overlay = document.getElementById("qr-display-modal");
  const canvasHolder = document.getElementById("qr-holder");
  const otpDisplay = document.getElementById("spa-otp-display");
  const codeDisplay = document.getElementById("spa-code-display");
  const progressBar = document.getElementById("spa-qr-progress");
  const timerText = document.getElementById("spa-qr-timer");
  
  overlay.classList.add("active");
  codeDisplay.textContent = code;
  
  if (liveQRInterval) clearInterval(liveQRInterval);
  
  function updateQR() {
    const otp = getSPADynamicToken(code, 0);
    const combined = `${code}-${otp}`;
    const encodedText = encodeURIComponent(combined);
    
    canvasHolder.innerHTML = `
      <img src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodedText}&color=0f172a" alt="QR Code" />
      <div class="qr-sweep-laser"></div>
    `;
    otpDisplay.textContent = otp;
    
    const now = Date.now();
    const secRemaining = 30 - Math.floor((now % 30000) / 1000);
    timerText.textContent = `Code expires in ${secRemaining}s`;
    progressBar.style.width = `${(secRemaining / 30) * 100}%`;
  }
  
  updateQR();
  
  liveQRInterval = setInterval(() => {
    const now = Date.now();
    const secRemaining = 30 - Math.floor((now % 30000) / 1000);
    if (secRemaining <= 0 || secRemaining === 30) {
      updateQR();
    } else {
      timerText.textContent = `Code expires in ${secRemaining}s`;
      progressBar.style.width = `${(secRemaining / 30) * 100}%`;
    }
  }, 1000);
}

function simulateStudentJoin(sessionId, courseUnitId) {
  const unit = DB.getCourseUnits().find(u => u.id === courseUnitId);
  if (!unit) return;
  
  // Eligible students belong to the program of this course unit
  const eligibleStudents = DB.getUsers().filter(u => u.role === "student" && u.courseId === unit.courseId);
  const attendance = DB.getAttendance();
  
  const absentStudents = eligibleStudents.filter(stu => !attendance.some(a => a.sessionId === sessionId && a.studentId === stu.id));
  
  if (absentStudents.length === 0) {
    showToast("All eligible students have checked in!", "warning");
    return;
  }
  
  const randomStudent = absentStudents[Math.floor(Math.random() * absentStudents.length)];
  
  const newRecord = {
    id: "att_" + Date.now(),
    sessionId: sessionId,
    studentId: randomStudent.id,
    timestamp: new Date().toISOString(),
    status: Math.random() > 0.85 ? "Late" : "Present"
  };
  
  attendance.push(newRecord);
  DB.saveAttendance(attendance);
  
  showToast(`${randomStudent.name} checked in successfully.`, "success");
  updateLiveAttendeeStream(sessionId);
}

function updateLiveAttendeeStream(sessionId) {
  const records = DB.getAttendanceWithDetails().filter(r => r.sessionId === sessionId);
  const stream = document.getElementById("live-stream-feed");
  const countSpan = document.getElementById("live-count");
  
  if (!stream || !countSpan) return;
  
  countSpan.textContent = records.length;
  stream.innerHTML = "";
  
  if (records.length === 0) {
    stream.innerHTML = `<p class="text-center text-muted" style="padding: 24px;">Waiting for student sign-ins...</p>`;
    return;
  }
  
  records.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  
  records.forEach(r => {
    const time = new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const initials = r.studentName.split(" ").map(n => n[0]).join("").substring(0, 2);
    
    stream.innerHTML += `
      <div class="feed-item">
        <div class="feed-item-left">
          <div class="feed-item-avatar">${initials}</div>
          <div class="feed-item-details">
            <h4>${r.studentName}</h4>
            <p>${r.studentReg} | Program: ${r.programCode}</p>
          </div>
        </div>
        <div class="flex-gap-4">
          <span class="badge badge-${r.status.toLowerCase()}">${r.status}</span>
          <span class="feed-item-time">${time}</span>
        </div>
      </div>
    `;
  });
}

function createLectureSession(e) {
  e.preventDefault();
  const courseUnitId = document.getElementById("sess-course").value; // Course Unit selected
  const durationMin = parseInt(document.getElementById("sess-duration").value);
  
  const sessions = DB.getSessions();
  if (sessions.some(s => s.lecturerId === currentUser.id && s.active)) {
    showToast("You already have an active lecture session. Close it first.", "error");
    return;
  }
  
  const now = new Date();
  const startStr = now.toTimeString().substring(0, 5);
  const end = new Date(now.getTime() + durationMin * 60 * 1000);
  const endStr = end.toTimeString().substring(0, 5);
  
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let randomCode = "";
  for (let i = 0; i < 6; i++) {
    randomCode += chars[Math.floor(Math.random() * chars.length)];
  }
  
  const newSession = {
    id: "sess_" + Date.now(),
    courseUnitId, // References Course Unit (e.g. unit_comp_app)
    lecturerId: currentUser.id,
    date: now.toISOString().substring(0, 10),
    startTime: startStr,
    endTime: endStr,
    code: randomCode,
    active: true
  };
  
  sessions.push(newSession);
  DB.saveSessions(sessions);
  
  document.getElementById("create-session-modal").classList.remove("active");
  showToast(`Session ${randomCode} started!`, "success");
  
  renderLecturerDashboard();
}

function closeSession(sessionId) {
  const sessions = DB.getSessions();
  const session = sessions.find(s => s.id === sessionId);
  
  if (session) {
    session.active = false;
    DB.saveSessions(sessions);
    showToast("Session closed.", "warning");
    renderLecturerDashboard();
  }
}

// Lecturer Filtering and Reports
function filterLecturerReports() {
  const selectedUnit = document.getElementById("rep-filter-course").value;
  const searchName = document.getElementById("rep-search-name").value.trim().toLowerCase();
  
  const records = DB.getAttendanceWithDetails().filter(r => r.lecturerName === currentUser.name);
  const reportBody = document.getElementById("lecturer-reports-body");
  
  if (!reportBody) return;
  reportBody.innerHTML = "";
  
  const filtered = records.filter(r => {
    const matchesUnit = selectedUnit === "all" || r.sessionId === selectedUnit || r.courseUnitId === selectedUnit;
    const matchesName = r.studentName.toLowerCase().includes(searchName) || r.studentReg.toLowerCase().includes(searchName);
    return matchesUnit && matchesName;
  });
  
  if (filtered.length === 0) {
    reportBody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No records match filters.</td></tr>`;
    return;
  }
  
  filtered.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  
  filtered.forEach(r => {
    const time = new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><strong>${r.studentName}</strong><br><small class="text-muted">${r.studentReg}</small></td>
      <td>${r.courseCode}</td>
      <td>${r.programCode}</td>
      <td>${r.sessionDate}</td>
      <td><span class="badge badge-${r.status.toLowerCase()}">${r.status}</span></td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="toggleAttendanceStatus('${r.id}')">
          Modify
        </button>
      </td>
    `;
    reportBody.appendChild(row);
  });
}

function toggleAttendanceStatus(attId) {
  const attendance = DB.getAttendance();
  const record = attendance.find(a => a.id === attId);
  
  if (record) {
    const prev = record.status;
    let next = "Present";
    if (prev === "Present") next = "Late";
    else if (prev === "Late") next = "Absent";
    else next = "Present";
    
    record.status = next;
    DB.saveAttendance(attendance);
    showToast(`Status updated: ${next}.`, "success");
    renderLecturerDashboard();
  }
}

// Export Reports
function exportReportExcel() {
  const selectedUnit = document.getElementById("rep-filter-course").value;
  const searchName = document.getElementById("rep-search-name").value.trim().toLowerCase();
  
  const records = DB.getAttendanceWithDetails().filter(r => r.lecturerName === currentUser.name);
  
  const filtered = records.filter(r => {
    const matchesUnit = selectedUnit === "all" || r.sessionId === selectedUnit || r.courseUnitId === selectedUnit;
    const matchesName = r.studentName.toLowerCase().includes(searchName) || r.studentReg.toLowerCase().includes(searchName);
    return matchesUnit && matchesName;
  });
  
  if (filtered.length === 0) {
    showToast("No data to export.", "error");
    return;
  }
  
  const data = filtered.map(r => ({
    "Student Name": r.studentName,
    "Reg Number": r.studentReg,
    "Program": r.programCode,
    "Course Unit Code": r.courseCode,
    "Course Unit Name": r.courseName,
    "Date": r.sessionDate,
    "Time Marked": new Date(r.timestamp).toLocaleTimeString(),
    "Status": r.status
  }));
  
  const worksheet = XLSX.utils.json_to_sheet(data);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Attendance Report");
  
  XLSX.writeFile(workbook, `Attendance_Report_${selectedUnit}.xlsx`);
  showToast("Excel spreadsheet generated!", "success");
}

function exportReportPDF() {
  const selectedUnit = document.getElementById("rep-filter-course").value;
  const searchName = document.getElementById("rep-search-name").value.trim().toLowerCase();
  
  const records = DB.getAttendanceWithDetails().filter(r => r.lecturerName === currentUser.name);
  
  const filtered = records.filter(r => {
    const matchesUnit = selectedUnit === "all" || r.sessionId === selectedUnit || r.courseUnitId === selectedUnit;
    const matchesName = r.studentName.toLowerCase().includes(searchName) || r.studentReg.toLowerCase().includes(searchName);
    return matchesUnit && matchesName;
  });
  
  if (filtered.length === 0) {
    showToast("No data to export.", "error");
    return;
  }
  
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();
  
  doc.setFont("Helvetica", "bold");
  doc.setFontSize(20);
  doc.setTextColor(6, 182, 212);
  doc.text("University Attendance Report", 14, 20);
  
  doc.setFontSize(10);
  doc.setFont("Helvetica", "normal");
  doc.setTextColor(100, 116, 139);
  doc.text(`Generated by: ${currentUser.name} | Date: ${new Date().toLocaleDateString()}`, 14, 28);
  
  doc.line(14, 34, 196, 34);
  
  doc.setFont("Helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(15, 23, 42);
  doc.text("Student Name", 14, 42);
  doc.text("Reg No", 65, 42);
  doc.text("Program", 100, 42);
  doc.text("Course Unit", 125, 42);
  doc.text("Status", 180, 42);
  
  doc.line(14, 46, 196, 46);
  
  let y = 54;
  doc.setFont("Helvetica", "normal");
  
  filtered.forEach(r => {
    if (y > 270) {
      doc.addPage();
      y = 20;
    }
    
    doc.text(r.studentName.substring(0, 24), 14, y);
    doc.text(r.studentReg, 65, y);
    doc.text(r.programCode, 100, y);
    doc.text(r.courseCode, 125, y);
    
    if (r.status === "Present") doc.setTextColor(16, 185, 129);
    else if (r.status === "Late") doc.setTextColor(245, 158, 11);
    else doc.setTextColor(239, 68, 68);
    
    doc.text(r.status, 180, y);
    doc.setTextColor(15, 23, 42);
    
    doc.setDrawColor(241, 245, 249);
    doc.line(14, y + 4, 196, y + 4);
    y += 10;
  });
  
  doc.save(`Attendance_Report.pdf`);
  showToast("PDF report generated!", "success");
}

// Administrator Dashboard Logic
function renderAdminDashboard() {
  const users = DB.getUsers();
  const students = users.filter(u => u.role === "student");
  const lecturers = users.filter(u => u.role === "lecturer");
  const courses = DB.getCourses(); // Programs
  const units = DB.getCourseUnits();
  const attendance = DB.getAttendance();
  
  document.getElementById("stat-tot-students").textContent = students.length;
  document.getElementById("stat-tot-lecturers").textContent = lecturers.length;
  document.getElementById("stat-tot-courses").textContent = courses.length + units.length; // Show aggregate programs + units count
  
  // Calculate average attendance rate
  const allSessions = DB.getSessions();
  let overallRate = 0;
  if (allSessions.length > 0) {
    let totals = 0;
    let counts = 0;
    
    allSessions.forEach(sess => {
      // Find course unit program
      const cu = units.find(u => u.id === sess.courseUnitId);
      if (cu) {
        const enrolled = students.filter(s => s.courseId === cu.courseId).length;
        if (enrolled > 0) {
          const present = attendance.filter(a => a.sessionId === sess.id && (a.status === "Present" || a.status === "Late")).length;
          totals += (present / enrolled) * 100;
          counts++;
        }
      }
    });
    overallRate = counts > 0 ? Math.round(totals / counts) : 0;
  }
  document.getElementById("stat-overall-avg").textContent = `${overallRate}%`;
  
  renderAdminCharts(students, lecturers, courses, units, allSessions, attendance);
  renderAdminUserList();
  renderAdminCourseList();
}

function renderAdminCharts(students, lecturers, courses, units, sessions, attendance) {
  if (charts.overall) charts.overall.destroy();
  if (charts.courses) charts.courses.destroy();
  if (charts.trends) charts.trends.destroy();
  
  const ctxOverall = document.getElementById("chart-overall-rate").getContext("2d");
  const ctxCourses = document.getElementById("chart-by-courses").getContext("2d");
  const ctxTrends = document.getElementById("chart-daily-trends").getContext("2d");
  
  const averageValue = parseInt(document.getElementById("stat-overall-avg").textContent);
  charts.overall = new Chart(ctxOverall, {
    type: "doughnut",
    data: {
      labels: ["Attended", "Absent"],
      datasets: [{
        data: [averageValue, 100 - averageValue],
        backgroundColor: ["#0077d6", "rgba(166, 166, 166, 0.1)"],
        borderColor: ["#0077d6", "rgba(166, 166, 166, 0.2)"],
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      cutout: "80%"
    }
  });
  
  // Attendance by Course (Program)
  const courseLabels = [];
  const courseAverages = [];
  
  courses.forEach(c => {
    courseLabels.push(c.code);
    
    // Find all units for this program
    const pUnits = units.filter(u => u.courseId === c.id);
    const pUnitIds = pUnits.map(u => u.id);
    
    const cSessions = sessions.filter(s => pUnitIds.includes(s.courseUnitId));
    const cStudents = students.filter(s => s.courseId === c.id).length;
    
    if (cSessions.length > 0 && cStudents > 0) {
      let totals = 0;
      cSessions.forEach(s => {
        const present = attendance.filter(a => a.sessionId === s.id && (a.status === "Present" || a.status === "Late")).length;
        totals += (present / cStudents) * 100;
      });
      courseAverages.push(Math.round(totals / cSessions.length));
    } else {
      courseAverages.push(0);
    }
  });
  
  charts.courses = new Chart(ctxCourses, {
    type: "bar",
    data: {
      labels: courseLabels,
      datasets: [{
        label: "Attendance Rate %",
        data: courseAverages,
        backgroundColor: "rgba(0, 119, 214, 0.65)",
        borderColor: "#0077d6",
        borderWidth: 1,
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, max: 100, grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "var(--text-secondary)" } },
        x: { grid: { display: false }, ticks: { color: "var(--text-secondary)" } }
      },
      plugins: { legend: { display: false } }
    }
  });
  
  // Daily trends
  const days = ["05-25", "05-26", "05-27", "05-28", "05-29", "06-01", "06-05"];
  const trendsData = [];
  
  days.forEach(d => {
    const dateStr = `2026-${d}`;
    const dSessions = sessions.filter(s => s.date === dateStr);
    let dayTotal = 0;
    let count = 0;
    
    dSessions.forEach(s => {
      const cu = units.find(u => u.id === s.courseUnitId);
      if (cu) {
        const present = attendance.filter(a => a.sessionId === s.id && (a.status === "Present" || a.status === "Late")).length;
        const enrolled = students.filter(stu => stu.courseId === cu.courseId).length;
        if (enrolled > 0) {
          dayTotal += (present / enrolled) * 100;
          count++;
        }
      }
    });
    
    trendsData.push(count > 0 ? Math.round(dayTotal / count) : 80);
  });
  
  charts.trends = new Chart(ctxTrends, {
    type: "line",
    data: {
      labels: days,
      datasets: [{
        label: "Daily Average %",
        data: trendsData,
        borderColor: "#84BD00",
        backgroundColor: "rgba(132, 189, 0, 0.15)",
        fill: true,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, max: 100, grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "var(--text-secondary)" } },
        x: { grid: { display: false }, ticks: { color: "var(--text-secondary)" } }
      },
      plugins: { legend: { display: false } }
    }
  });
}

// User CRUD Management
function renderAdminUserList() {
  const users = DB.getUsers().filter(u => u.role !== "admin");
  const list = document.getElementById("admin-user-grid");
  list.innerHTML = "";
  
  const depts = DB.getDepartments();
  const courses = DB.getCourses(); // Degree programs
  
  users.forEach(u => {
    const initials = u.name.split(" ").map(n => n[0]).join("").substring(0, 2);
    
    let subLabel = "";
    if (u.role === "student") {
      const prog = courses.find(c => c.id === u.courseId) || { code: "N/A" };
      subLabel = `${u.regNo} (${prog.code})`;
    } else {
      const dept = depts.find(d => d.id === u.departmentId) || { name: "N/A" };
      subLabel = `Dept: ${dept.name}`;
    }
    
    list.innerHTML += `
      <div class="glass-card mgmt-card animate-scale">
        <div class="flex-gap-4">
          <div class="feed-item-avatar" style="width: 48px; height: 48px; border-radius: var(--radius-md); font-size: 1.2rem;">
            ${initials}
          </div>
          <div>
            <h3 style="font-size: 1.1rem;">${u.name}</h3>
            <p class="text-secondary" style="font-size: 0.85rem;">Role: <strong class="text-primary-color">${u.role.toUpperCase()}</strong></p>
            <p class="text-muted" style="font-size: 0.8rem;">${subLabel}</p>
          </div>
        </div>
        <div class="mgmt-card-actions">
          <button class="btn btn-secondary btn-sm" onclick="editUser('${u.id}')">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteUser('${u.id}')">Delete</button>
        </div>
      </div>
    `;
  });
}

function handleAddUser(e) {
  e.preventDefault();
  const name = document.getElementById("m-user-name").value.trim();
  const role = document.getElementById("m-user-role").value;
  const email = document.getElementById("m-user-email").value.trim();
  const pass = document.getElementById("m-user-pass").value;
  
  const users = DB.getUsers();
  
  let newUser = {
    id: "user_" + Date.now(),
    role,
    name,
    email,
    password: pass
  };
  
  if (role === "student") {
    const regNo = document.getElementById("m-user-reg").value.trim().toUpperCase();
    const courseId = document.getElementById("m-user-course").value;
    const courses = DB.getCourses();
    const studentCourse = courses.find(c => c.id === courseId);
    
    if (users.some(u => u.regNo === regNo)) {
      showToast("Registration Number already exists.", "error");
      return;
    }
    
    newUser.regNo = regNo;
    newUser.courseId = courseId;
    newUser.departmentId = studentCourse ? studentCourse.departmentId : "";
  } else {
    const departmentId = document.getElementById("m-user-dept").value;
    
    newUser.regNo = "N/A";
    newUser.departmentId = departmentId;
    newUser.courseId = "";
  }
  
  users.push(newUser);
  DB.saveUsers(users);
  
  document.getElementById("add-user-modal").classList.remove("active");
  // Reset fields
  document.getElementById("m-user-name").value = "";
  document.getElementById("m-user-email").value = "";
  document.getElementById("m-user-pass").value = "";
  if (document.getElementById("m-user-reg")) document.getElementById("m-user-reg").value = "";
  
  showToast(`Added ${role} ${name}!`, "success");
  renderAdminDashboard();
}

function toggleAdminAddUserFields() {
  const role = document.getElementById("m-user-role").value;
  const studentFields = document.getElementById("m-user-student-fields");
  const lecturerFields = document.getElementById("m-user-lecturer-fields");
  
  if (role === "student") {
    studentFields.style.display = "block";
    lecturerFields.style.display = "none";
    document.getElementById("m-user-reg").required = true;
    document.getElementById("m-user-course").required = true;
    document.getElementById("m-user-dept").required = false;
  } else {
    studentFields.style.display = "none";
    lecturerFields.style.display = "block";
    document.getElementById("m-user-reg").required = false;
    document.getElementById("m-user-course").required = false;
    document.getElementById("m-user-dept").required = true;
  }
}


function deleteUser(userId) {
  if (!confirm("Are you sure you want to delete this profile? All associated records (attendance, sessions, notifications) will be deleted.")) return;
  
  const users = DB.getUsers();
  const user = users.find(u => u.id === userId);
  if (!user) return;
  
  // 1. Remove from users list
  const updatedUsers = users.filter(u => u.id !== userId);
  DB.saveUsers(updatedUsers);
  
  // 2. Cascade delete based on role
  if (user.role === "student") {
    // Delete student attendance
    const attendance = DB.getAttendance().filter(a => a.studentId !== userId);
    DB.saveAttendance(attendance);
    
    // Delete student notifications
    const notifications = DB.getNotifications().filter(n => n.studentId !== userId);
    DB.saveNotifications(notifications);
  } else if (user.role === "lecturer") {
    // Find all sessions run by this lecturer
    const sessions = DB.getSessions();
    const lecturerSessions = sessions.filter(s => s.lecturerId === userId);
    const lecturerSessionIds = lecturerSessions.map(s => s.id);
    
    // Delete attendance records for these sessions
    const attendance = DB.getAttendance().filter(a => !lecturerSessionIds.includes(a.sessionId));
    DB.saveAttendance(attendance);
    
    // Delete lecturer sessions
    const updatedSessions = sessions.filter(s => s.lecturerId !== userId);
    DB.saveSessions(updatedSessions);
  }
  
  showToast("Profile removed and related records cleaned up.", "warning");
  renderAdminDashboard();
}

function editUser(userId) {
  const users = DB.getUsers();
  const user = users.find(u => u.id === userId);
  if (!user) return;
  
  // Set hidden field ID and current values
  document.getElementById("m-edit-user-id").value = user.id;
  document.getElementById("m-edit-user-name").value = user.name;
  document.getElementById("m-edit-user-role").value = user.role;
  document.getElementById("m-edit-user-email").value = user.email;
  document.getElementById("m-edit-user-pass").value = ""; // Clear password field (optional)
  
  // Render selects and display corresponding section
  const studentFields = document.getElementById("m-edit-user-student-fields");
  const lecturerFields = document.getElementById("m-edit-user-lecturer-fields");
  
  if (user.role === "student") {
    studentFields.style.display = "block";
    lecturerFields.style.display = "none";
    
    // Populate degree program course options
    const courseSelect = document.getElementById("m-edit-user-course");
    courseSelect.innerHTML = "";
    DB.getCourses().forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = `${c.code} - ${c.name}`;
      if (c.id === user.courseId) opt.selected = true;
      courseSelect.appendChild(opt);
    });
    
    document.getElementById("m-edit-user-reg").value = user.regNo || "";
    document.getElementById("m-edit-user-reg").required = true;
    document.getElementById("m-edit-user-course").required = true;
    document.getElementById("m-edit-user-dept").required = false;
  } else {
    studentFields.style.display = "none";
    lecturerFields.style.display = "block";
    
    // Populate department options
    const deptSelect = document.getElementById("m-edit-user-dept");
    deptSelect.innerHTML = "";
    DB.getDepartments().forEach(d => {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = d.name;
      if (d.id === user.departmentId) opt.selected = true;
      deptSelect.appendChild(opt);
    });
    
    document.getElementById("m-edit-user-reg").required = false;
    document.getElementById("m-edit-user-course").required = false;
    document.getElementById("m-edit-user-dept").required = true;
  }
  
  // Show the edit modal
  document.getElementById("edit-user-modal").classList.add("active");
}

function handleEditUserSave(e) {
  e.preventDefault();
  const userId = document.getElementById("m-edit-user-id").value;
  const name = document.getElementById("m-edit-user-name").value.trim();
  const email = document.getElementById("m-edit-user-email").value.trim();
  const password = document.getElementById("m-edit-user-pass").value;
  
  const users = DB.getUsers();
  const user = users.find(u => u.id === userId);
  if (!user) return;
  
  // Validation: duplicate email (check other users)
  if (users.some(u => u.id !== userId && u.email.toLowerCase() === email.toLowerCase())) {
    showToast("Email address is already taken by another user.", "error");
    return;
  }
  
  if (user.role === "student") {
    const regNo = document.getElementById("m-edit-user-reg").value.trim().toUpperCase();
    const courseId = document.getElementById("m-edit-user-course").value;
    const courses = DB.getCourses();
    const studentCourse = courses.find(c => c.id === courseId);
    
    // Validation: duplicate reg number (check other users)
    if (users.some(u => u.id !== userId && u.regNo === regNo)) {
      showToast("Registration number is already taken by another student.", "error");
      return;
    }
    
    user.regNo = regNo;
    user.courseId = courseId;
    user.departmentId = studentCourse ? studentCourse.departmentId : "";
  } else if (user.role === "lecturer") {
    const departmentId = document.getElementById("m-edit-user-dept").value;
    user.departmentId = departmentId;
  }
  
  user.name = name;
  user.email = email;
  
  // Only update password if a new one is typed
  if (password && password.trim() !== "") {
    user.password = password;
  }
  
  DB.saveUsers(users);
  
  document.getElementById("edit-user-modal").classList.remove("active");
  showToast("Profile updated successfully.", "success");
  renderAdminDashboard();
}


// Course Hierarchy Tree View Rendering
function renderAdminCourseList() {
  const facs = DB.getFaculties();
  const depts = DB.getDepartments();
  const courses = DB.getCourses(); // Degree Programs
  const units = DB.getCourseUnits(); // Course Units
  
  const container = document.getElementById("admin-course-grid");
  container.innerHTML = "";
  
  if (facs.length === 0) {
    container.innerHTML = `<p class="text-center text-muted">No academic catalog seeded.</p>`;
    return;
  }
  
  facs.forEach(f => {
    const fDepts = depts.filter(d => d.facultyId === f.id);
    
    let deptHTML = "";
    fDepts.forEach(d => {
      const dPrograms = courses.filter(c => c.departmentId === d.id);
      
      let progHTML = "";
      dPrograms.forEach(p => {
        const pUnits = units.filter(u => u.courseId === p.id);
        
        let unitHTML = "";
        pUnits.forEach(u => {
          unitHTML += `
            <div style="padding: 6px 12px; margin-top: 4px; background: rgba(255,255,255,0.02); border-radius: var(--radius-sm); border-left: 2px solid var(--accent); font-size: 0.8rem; display: flex; justify-content: space-between; align-items: center;">
              <span><strong>${u.code}</strong>: ${u.name}</span>
              <button class="btn btn-secondary btn-sm" style="padding: 2px 6px; font-size: 0.7rem;" onclick="deleteCourseUnit('${u.id}')">Remove</button>
            </div>
          `;
        });
        
        progHTML += `
          <div style="padding: 8px 12px; margin-top: 8px; background: rgba(255,255,255,0.03); border-radius: var(--radius-md); border-left: 3px solid var(--secondary);">
            <div class="flex-between">
              <span style="font-weight: 600; font-size: 0.85rem; color: var(--text-primary);">Degree: ${p.code} - ${p.name}</span>
              <button class="btn btn-danger btn-sm" style="padding: 2px 6px; font-size: 0.7rem;" onclick="deleteProgram('${p.id}')">Delete</button>
            </div>
            <div style="margin-left: 12px; margin-top: 6px; border-left: 1px dashed var(--border-glass); padding-left: 8px;">
              <span style="font-size: 0.75rem; text-transform: uppercase; color: var(--accent); font-weight: bold;">Course Units</span>
              ${unitHTML || '<p style="font-size: 0.75rem; color: var(--text-muted);">No Course Units registered</p>'}
            </div>
          </div>
        `;
      });
      
      deptHTML += `
        <div style="padding: 10px 16px; margin-top: 12px; background: var(--bg-surface); border-radius: var(--radius-md); border-left: 3px solid var(--primary);">
          <div class="flex-between">
            <span style="font-weight: 700; font-size: 0.9rem; color: var(--text-primary);"><i data-lucide="folder" style="width: 14px; height: 14px; vertical-align: middle; margin-right: 4px;"></i> Dept: ${d.name}</span>
            <button class="btn btn-secondary btn-sm" style="padding: 2px 6px; font-size: 0.7rem;" onclick="deleteDepartment('${d.id}')">Delete</button>
          </div>
          <div style="margin-left: 12px; margin-top: 8px;">
            ${progHTML || '<p style="font-size: 0.8rem; color: var(--text-muted);">No Programs registered</p>'}
          </div>
        </div>
      `;
    });
    
    container.innerHTML += `
      <div class="glass-card animate-scale" style="margin-bottom: 16px; border-color: var(--primary-glow);">
        <div class="flex-between" style="border-bottom: 1px solid var(--border-glass); padding-bottom: 8px;">
          <h3 style="font-size: 1.05rem; color: var(--primary); font-family: var(--font-display); font-weight: 800;">
            <i data-lucide="graduation-cap" style="width: 16px; height: 16px; vertical-align: middle; margin-right: 6px;"></i> ${f.name}
          </h3>
          <button class="btn btn-secondary btn-sm" style="padding: 2px 8px; font-size: 0.75rem;" onclick="deleteFaculty('${f.id}')">Delete Faculty</button>
        </div>
        <div style="padding-top: 8px;">
          ${deptHTML || '<p style="font-size: 0.8rem; color: var(--text-muted); padding: 12px;">No Departments registered</p>'}
        </div>
      </div>
    `;
  });
  
  lucide.createIcons();
}

// Seeding Academic Modals Adders
function handleAddCourse(e) {
  e.preventDefault();
  const name = document.getElementById("m-course-name").value.trim();
  const code = document.getElementById("m-course-code").value.trim().toUpperCase();
  const deptId = document.getElementById("m-course-dept").value;
  
  const courses = DB.getCourses();
  if (courses.some(c => c.code === code)) {
    showToast("Program Code already exists.", "error");
    return;
  }
  
  const newCourse = {
    id: "course_" + Date.now(),
    code,
    name,
    departmentId: deptId
  };
  
  courses.push(newCourse);
  DB.saveCourses(courses);
  
  document.getElementById("add-course-modal").classList.remove("active");
  showToast(`Degree Program ${code} Registered!`, "success");
  
  // Update register program selector dropdown
  const regCourseSelect = document.getElementById("reg-course");
  if (regCourseSelect) {
    regCourseSelect.innerHTML = "";
    courses.forEach(c => {
      regCourseSelect.innerHTML += `<option value="${c.id}">${c.code} - ${c.name}</option>`;
    });
  }
  
  renderAdminDashboard();
}

function handleAddFaculty(e) {
  e.preventDefault();
  const name = document.getElementById("m-faculty-name").value.trim();
  const facs = DB.getFaculties();
  if (facs.some(f => f.name.toLowerCase() === name.toLowerCase())) {
    showToast("Faculty name already exists.", "error");
    return;
  }
  
  const newFac = {
    id: "fac_" + Date.now(),
    name
  };
  
  facs.push(newFac);
  DB.saveFaculties(facs);
  
  document.getElementById("add-faculty-modal").classList.remove("active");
  document.getElementById("m-faculty-name").value = "";
  showToast(`Faculty ${name} Registered!`, "success");
  renderAdminDashboard();
}

function handleAddDepartment(e) {
  e.preventDefault();
  const name = document.getElementById("m-dept-name").value.trim();
  const facultyId = document.getElementById("m-dept-faculty").value;
  
  const depts = DB.getDepartments();
  if (depts.some(d => d.name.toLowerCase() === name.toLowerCase() && d.facultyId === facultyId)) {
    showToast("Department already exists in this Faculty.", "error");
    return;
  }
  
  const newDept = {
    id: "dept_" + Date.now(),
    name,
    facultyId
  };
  
  depts.push(newDept);
  DB.saveDepartments(depts);
  
  document.getElementById("add-department-modal").classList.remove("active");
  document.getElementById("m-dept-name").value = "";
  showToast(`Department ${name} Registered!`, "success");
  renderAdminDashboard();
}

function handleAddCourseUnit(e) {
  e.preventDefault();
  const code = document.getElementById("m-unit-code").value.trim().toUpperCase();
  const name = document.getElementById("m-unit-name").value.trim();
  const courseId = document.getElementById("m-unit-course").value;
  
  const units = DB.getCourseUnits();
  if (units.some(u => u.code === code)) {
    showToast("Course Unit Code already exists.", "error");
    return;
  }
  
  const newUnit = {
    id: "unit_" + Date.now(),
    code,
    name,
    courseId
  };
  
  units.push(newUnit);
  DB.saveCourseUnits(units);
  
  document.getElementById("add-course-unit-modal").classList.remove("active");
  document.getElementById("m-unit-code").value = "";
  document.getElementById("m-unit-name").value = "";
  showToast(`Course Unit ${code} Registered!`, "success");
  renderAdminDashboard();
}

// Delete CRUD Operations
function deleteFaculty(id) {
  if (!confirm("Delete this Faculty and all nested structures?")) return;
  const facs = DB.getFaculties().filter(f => f.id !== id);
  DB.saveFaculties(facs);
  showToast("Faculty deleted.", "warning");
  renderAdminDashboard();
}

function deleteDepartment(id) {
  if (!confirm("Delete this Department?")) return;
  const depts = DB.getDepartments().filter(d => d.id !== id);
  DB.saveDepartments(depts);
  showToast("Department deleted.", "warning");
  renderAdminDashboard();
}

function deleteProgram(id) {
  if (!confirm("Delete this Program?")) return;
  const progs = DB.getCourses().filter(c => c.id !== id);
  DB.saveCourses(progs);
  showToast("Program deleted.", "warning");
  renderAdminDashboard();
}

function deleteCourseUnit(id) {
  if (!confirm("Delete this Course Unit?")) return;
  const units = DB.getCourseUnits().filter(u => u.id !== id);
  DB.saveCourseUnits(units);
  showToast("Course Unit deleted.", "warning");
  renderAdminDashboard();
}

// Theme Manager
function toggleTheme() {
  const body = document.body;
  const toggleBtn = document.getElementById("btn-theme-toggle");
  
  if (activeTheme === "dark") {
    activeTheme = "light";
    body.classList.add("light-mode");
    toggleBtn.innerHTML = `<i data-lucide="moon"></i>`;
  } else {
    activeTheme = "dark";
    body.classList.remove("light-mode");
    toggleBtn.innerHTML = `<i data-lucide="sun"></i>`;
  }
  
  lucide.createIcons();
  
  if (currentUser && currentUser.role === "admin") {
    renderAdminDashboard();
  }
}

// Initial Setup & Modal Binds on Load
window.addEventListener("DOMContentLoaded", () => {
  document.body.classList.remove("light-mode");
  
  if (typeof initializeDatabase === "function") {
    initializeDatabase();
  }
  
  navigate("home");
  
  // Populate registration courses (Degree programs)
  const courses = DB.getCourses();
  const regCourseSelect = document.getElementById("reg-course");
  if (regCourseSelect && courses.length > 0) {
    regCourseSelect.innerHTML = "";
    courses.forEach(c => {
      regCourseSelect.innerHTML += `<option value="${c.id}">${c.code} - ${c.name}</option>`;
    });
  }
  
  // Form Bindings
  document.getElementById("login-form").addEventListener("submit", handleLogin);
  document.getElementById("register-form").addEventListener("submit", handleRegister);
  document.getElementById("session-form").addEventListener("submit", createLectureSession);
  
  const mUserForm = document.getElementById("m-user-form");
  if (mUserForm) mUserForm.addEventListener("submit", handleAddUser);
  
  const mEditUserForm = document.getElementById("m-edit-user-form");
  if (mEditUserForm) mEditUserForm.addEventListener("submit", handleEditUserSave);
  
  const mCourseForm = document.getElementById("m-course-form");
  if (mCourseForm) mCourseForm.addEventListener("submit", handleAddCourse);

  const mFacultyForm = document.getElementById("m-faculty-form");
  if (mFacultyForm) mFacultyForm.addEventListener("submit", handleAddFaculty);

  const mDeptForm = document.getElementById("m-department-form");
  if (mDeptForm) mDeptForm.addEventListener("submit", handleAddDepartment);

  const mCourseUnitForm = document.getElementById("m-course-unit-form");
  if (mCourseUnitForm) mCourseUnitForm.addEventListener("submit", handleAddCourseUnit);
  
  const forgotVerifyForm = document.getElementById("forgot-verify-form");
  if (forgotVerifyForm) forgotVerifyForm.addEventListener("submit", handleForgotVerify);

  const forgotResetForm = document.getElementById("forgot-reset-form");
  if (forgotResetForm) forgotResetForm.addEventListener("submit", handleForgotReset);
  
  // Modal Bindings
  document.querySelectorAll(".btn-open-modal").forEach(btn => {
    btn.addEventListener("click", () => {
      const modalId = btn.getAttribute("data-modal");
      document.getElementById(modalId).classList.add("active");
      
      // Populate admin add degree courses department selector modal
      if (modalId === "add-course-modal") {
        const depts = DB.getDepartments();
        const select = document.getElementById("m-course-dept");
        if (select) {
          select.innerHTML = "";
          depts.forEach(d => {
            select.innerHTML += `<option value="${d.id}">${d.name}</option>`;
          });
        }
      }

      // Populate admin add department faculty selector modal
      if (modalId === "add-department-modal") {
        const facs = DB.getFaculties();
        const select = document.getElementById("m-dept-faculty");
        if (select) {
          select.innerHTML = "";
          facs.forEach(f => {
            select.innerHTML += `<option value="${f.id}">${f.name}</option>`;
          });
        }
      }

      // Populate admin add course unit program selector modal
      if (modalId === "add-course-unit-modal") {
        const courses = DB.getCourses();
        const select = document.getElementById("m-unit-course");
        if (select) {
          select.innerHTML = "";
          courses.forEach(c => {
            select.innerHTML += `<option value="${c.id}">${c.code} - ${c.name}</option>`;
          });
        }
      }

      // Populate admin add user fields selector modal
      if (modalId === "add-user-modal") {
        const courses = DB.getCourses();
        const selectCourse = document.getElementById("m-user-course");
        if (selectCourse) {
          selectCourse.innerHTML = "";
          courses.forEach(c => {
            selectCourse.innerHTML += `<option value="${c.id}">${c.code} - ${c.name}</option>`;
          });
        }

        const depts = DB.getDepartments();
        const selectDept = document.getElementById("m-user-dept");
        if (selectDept) {
          selectDept.innerHTML = "";
          depts.forEach(d => {
            selectDept.innerHTML += `<option value="${d.id}">${d.name}</option>`;
          });
        }

        toggleAdminAddUserFields();
      }
    });
  });
  
  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        overlay.classList.remove("active");
        if (liveQRInterval) {
          clearInterval(liveQRInterval);
          liveQRInterval = null;
        }
      }
    });
  });
  
  document.querySelectorAll(".modal-close").forEach(btn => {
    btn.addEventListener("click", () => {
      btn.closest(".modal-overlay").classList.remove("active");
      if (liveQRInterval) {
        clearInterval(liveQRInterval);
        liveQRInterval = null;
      }
    });
  });
  
  // Lecturer Filter Keyups
  const repSearch = document.getElementById("rep-search-name");
  if (repSearch) repSearch.addEventListener("keyup", filterLecturerReports);
  
  const repCourseFilter = document.getElementById("rep-filter-course");
  if (repCourseFilter) repCourseFilter.addEventListener("change", filterLecturerReports);
  
  lucide.createIcons();
});

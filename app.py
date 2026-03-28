from flask import Flask, render_template, request, redirect, session
import mysql.connector

app = Flask(__name__)
app.secret_key = "secret_key"

# ================= DATABASE CONNECTION =================
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="college_management"
)

# ================= LOGIN =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (username, password)
        )
        user = cursor.fetchone()
        cursor.close()

        if user:
            session["user"] = user["username"]
            session["role"] = user["role"].lower()

            if session["role"] == "admin":
                return redirect("/dashboard")
            elif session["role"] == "faculty":
                return redirect("/view_students")
            elif session["role"] == "student":
                return redirect("/student_portal")

        return render_template("login.html", error="Invalid Credentials")

    return render_template("login.html")


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if session.get("role") != "admin":
        return redirect("/")

    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM students")
    total_students = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM departments")
    total_departments = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT s.student_name, AVG(m.marks) AS avg_marks
        FROM students s
        JOIN marks m ON s.student_id = m.student_id
        GROUP BY s.student_id
        ORDER BY avg_marks DESC
        LIMIT 5
    """)
    data = cursor.fetchall()   # ✅ FIXED INDENT

    names = [row["student_name"] for row in data]
    averages = [float(row["avg_marks"]) for row in data]

    cursor.close()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        total_departments=total_departments,
        names=names,
        averages=averages
    )


# ================= VIEW STUDENTS =================
@app.route("/view_students")
def view_students():

    if session.get("role") not in ["admin", "faculty"]:
        return redirect("/")

    show_f = request.args.get("show_f")
    show_p = request.args.get("show_p")

    cursor = db.cursor(dictionary=True)

    if show_f == "true":
        cursor.execute("""
            SELECT s.student_id, s.student_name, s.email,
                   d.department_name, c.course_name AS subject, m.marks
            FROM students s
            JOIN departments d ON s.department_id = d.department_id
            JOIN marks m ON s.student_id = m.student_id
            JOIN courses c ON m.course_id = c.course_id
            WHERE m.marks < 50
            GROUP BY s.student_id, c.course_id
        """)
        students = cursor.fetchall()
        cursor.close()
        return render_template("view_students.html", students=students, show_failed=True, show_passed=False)

    if show_p == "true":
        cursor.execute("""
            SELECT s.student_id, s.student_name, s.email,
                   d.department_name, c.course_name AS subject, m.marks
            FROM students s
            JOIN departments d ON s.department_id = d.department_id
            JOIN marks m ON s.student_id = m.student_id
            JOIN courses c ON m.course_id = c.course_id
            WHERE m.marks >= 50
            GROUP BY s.student_id, c.course_id
        """)
        students = cursor.fetchall()
        cursor.close()
        return render_template("view_students.html", students=students, show_failed=False, show_passed=True)

    cursor.execute("""
        SELECT s.student_id, s.student_name, s.email, d.department_name
        FROM students s
        JOIN departments d ON s.department_id = d.department_id
    """)
    students = cursor.fetchall()
    cursor.close()

    return render_template("view_students.html", students=students, show_failed=False, show_passed=False)


# ================= TOPPER ANALYTICS =================
@app.route("/topper_analytics")
def topper_analytics():
    if session.get("role") != "admin":
        return redirect("/")

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT s.student_name,
               d.department_name,
               ROUND(AVG(m.marks),2) AS average_marks,
               CASE
                   WHEN AVG(m.marks) >= 90 THEN 10
                   WHEN AVG(m.marks) >= 75 THEN 9
                   WHEN AVG(m.marks) >= 60 THEN 8
                   WHEN AVG(m.marks) >= 50 THEN 7
                   ELSE 5
               END AS gpa
        FROM students s
        JOIN departments d ON s.department_id = d.department_id
        JOIN marks m ON s.student_id = m.student_id
        GROUP BY s.student_id
        ORDER BY average_marks DESC
        LIMIT 5
    """)

    toppers = cursor.fetchall()
    cursor.close()

    return render_template("topper_analytics.html", toppers=toppers)


# ================= ATTENDANCE DAY (FIXED) =================
@app.route("/attendance_day", methods=["GET","POST"])
def attendance_day():

    if session.get("role") != "faculty":
        return redirect("/")

    cursor = db.cursor(dictionary=True)

    records = []
    history = {}

    if request.method == "POST":
        date = request.form["date"]

        cursor.execute("""
            SELECT s.student_name, c.course_name
            FROM daily_attendance a
            JOIN students s ON a.student_id = s.student_id
            JOIN courses c ON a.course_id = c.course_id
            WHERE a.date = %s AND a.status = 'Absent'
        """,(date,))
        records = cursor.fetchall()

    cursor.execute("""
        SELECT a.date, s.student_name, c.course_name
        FROM daily_attendance a
        JOIN students s ON a.student_id = s.student_id
        JOIN courses c ON a.course_id = c.course_id
        WHERE a.status = 'Absent'
        ORDER BY a.date DESC
    """)

    rows = cursor.fetchall()

    for r in rows:
        if r['date'] not in history:
            history[r['date']] = []
        history[r['date']].append({
            "student": r['student_name'],
            "subject": r['course_name']
        })

    cursor.close()

    return render_template("attendance_day.html",
                           records=records,
                           history=history)

# ================= STUDENT PORTAL =================
@app.route("/student_portal")
def student_portal():
    if session.get("role") != "student":
        return redirect("/")

    cursor = db.cursor(dictionary=True)

     cursor.execute("""
        SELECT *
        FROM students
        WHERE student_name = %s
        LIMIT 1
    """, (session.get("user"),))

student = cursor.fetchone()

    # If no match
    if not student:
        cursor.close()
        return "Student not found. Make sure username = student name"

    # Get marks
        cursor.execute("""
             SELECT c.course_name, m.marks AS marks
            FROM marks m
            JOIN courses c ON m.course_id = c.course_id
         WHERE m.student_id=%s
        """, (student["student_id"],))

    courses = cursor.fetchall()

if courses:
    total = sum([c.get("marks", 0) for c in courses])
    average = round(total / len(courses), 2)
else:
    average = 0
    # GPA
    if average >= 90:
        gpa = 10
    elif average >= 75:
        gpa = 9
    elif average >= 60:
        gpa = 8
    elif average >= 50:
        gpa = 7
    else:
        gpa = 5

    cursor.close()

    return render_template(
        "student_portal.html",
        student=student,
        courses=courses,
        average=average,
        gpa=gpa
    )
# ================= RUN APP =================
if __name__ == "__main__":
    app.run(debug=True)
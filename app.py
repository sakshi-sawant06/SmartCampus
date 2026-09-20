from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    send_from_directory
)

import sqlite3
import os
import re
import uuid

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename


# ============================================================
# FLASK CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = "SmartCampus_2026"

DATABASE = "database.db"

UPLOAD_FOLDER = os.path.join(
    app.root_path,
    "uploads"
)

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Maximum uploaded image size = 5 MB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# Create uploads folder if it does not exist
os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db():

    conn = sqlite3.connect(
        DATABASE
    )

    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    conn = get_db()

    # --------------------------------------------------------
    # STUDENTS TABLE
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL
        )
    """)


    # --------------------------------------------------------
    # ADMINS TABLE
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL
        )
    """)


    # --------------------------------------------------------
    # MASTER ISSUES TABLE
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS master_issues (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            category TEXT NOT NULL,

            location TEXT NOT NULL,

            description TEXT NOT NULL,

            priority TEXT NOT NULL,

            status TEXT DEFAULT 'Pending',

            assigned_team TEXT,

            resolution_image TEXT,

            reports_count INTEGER DEFAULT 1,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
    """)


    # --------------------------------------------------------
    # REPORTS TABLE
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            student_id INTEGER NOT NULL,

            description TEXT NOT NULL,

            location TEXT NOT NULL,

            category TEXT NOT NULL,

            priority TEXT NOT NULL,

            image TEXT,

            master_issue_id INTEGER NOT NULL,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(student_id)
                REFERENCES students(id),

            FOREIGN KEY(master_issue_id)
                REFERENCES master_issues(id)
        )
    """)


    # ========================================================
    # DATABASE UPGRADE
    # ========================================================
    # These checks allow an older database to continue working
    # if new columns were added later.
    # ========================================================

    master_columns = conn.execute(
        "PRAGMA table_info(master_issues)"
    ).fetchall()

    master_column_names = [
        column["name"]
        for column in master_columns
    ]

    if "resolution_image" not in master_column_names:

        conn.execute("""
            ALTER TABLE master_issues
            ADD COLUMN resolution_image TEXT
        """)


    report_columns = conn.execute(
        "PRAGMA table_info(reports)"
    ).fetchall()

    report_column_names = [
        column["name"]
        for column in report_columns
    ]

    if "image" not in report_column_names:

        conn.execute("""
            ALTER TABLE reports
            ADD COLUMN image TEXT
        """)


    # ========================================================
    # DEFAULT ADMIN
    # ========================================================

    admin = conn.execute(
        """
        SELECT *
        FROM admins
        WHERE username = ?
        """,
        ("admin",)
    ).fetchone()


    if not admin:

        conn.execute(
            """
            INSERT INTO admins
            (
                username,
                password
            )
            VALUES (?, ?)
            """,
            (
                "admin",
                generate_password_hash(
                    "admin123"
                )
            )
        )


    conn.commit()

    conn.close()


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(filename):

    return (
        "." in filename
        and
        filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )


# ============================================================
# CATEGORY CLASSIFICATION
# ============================================================

def classify_category(description):

    text = description.lower()


    # Electrical
    electrical_words = [
        "light",
        "electric",
        "electricity",
        "fan",
        "switch",
        "power",
        "bulb"
    ]

    if any(
        word in text
        for word in electrical_words
    ):
        return "Electrical"


    # Plumbing
    plumbing_words = [
        "water",
        "tap",
        "pipe",
        "leak",
        "toilet",
        "washroom",
        "drain"
    ]

    if any(
        word in text
        for word in plumbing_words
    ):
        return "Plumbing"


    # Cleanliness
    cleanliness_words = [
        "garbage",
        "dust",
        "dirty",
        "clean",
        "waste",
        "trash",
        "litter"
    ]

    if any(
        word in text
        for word in cleanliness_words
    ):
        return "Cleanliness"


    # Infrastructure
    infrastructure_words = [
        "chair",
        "table",
        "door",
        "window",
        "wall",
        "bench",
        "building",
        "ceiling",
        "floor"
    ]

    if any(
        word in text
        for word in infrastructure_words
    ):
        return "Infrastructure"


    # IT Support
    it_words = [
        "computer",
        "wifi",
        "internet",
        "network",
        "projector",
        "printer",
        "keyboard",
        "mouse"
    ]

    if any(
        word in text
        for word in it_words
    ):
        return "IT Support"


    return "Other"


# ============================================================
# PRIORITY CLASSIFICATION
# ============================================================

def classify_priority(
    description,
    category
):

    text = description.lower()


    high_words = [
        "danger",
        "dangerous",
        "emergency",
        "fire",
        "spark",
        "shock",
        "short circuit"
    ]


    if any(
        word in text
        for word in high_words
    ):
        return "High"


    if category in [
        "Electrical",
        "Plumbing"
    ]:
        return "High"


    if category == "Infrastructure":

        return "Medium"


    return "Low"


# ============================================================
# TOPIC EXTRACTION
# ============================================================

def extract_topic(description):

    text = description.lower()


    topics = [
        "light",
        "bulb",
        "fan",
        "switch",
        "power",
        "water",
        "tap",
        "pipe",
        "leak",
        "toilet",
        "garbage",
        "dust",
        "waste",
        "trash",
        "chair",
        "table",
        "door",
        "window",
        "computer",
        "wifi",
        "internet",
        "network",
        "projector",
        "printer"
    ]


    for topic in topics:

        if re.search(
            r"\b"
            + re.escape(topic)
            + r"\b",
            text
        ):
            return topic


    return "general"


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ============================================================
# STUDENT REGISTER
# ============================================================

@app.route(
    "/student-register",
    methods=["GET", "POST"]
)
def student_register():

    if request.method == "POST":

        name = request.form["name"].strip()

        email = request.form["email"].strip().lower()

        password = request.form["password"]


        conn = get_db()


        existing_student = conn.execute(
            """
            SELECT *
            FROM students
            WHERE email = ?
            """,
            (email,)
        ).fetchone()


        if existing_student:

            conn.close()

            return render_template(
                "student_register.html",
                error="Email already registered."
            )


        hashed_password = generate_password_hash(
            password
        )


        conn.execute(
            """
            INSERT INTO students
            (
                name,
                email,
                password
            )
            VALUES (?, ?, ?)
            """,
            (
                name,
                email,
                hashed_password
            )
        )


        conn.commit()

        conn.close()


        return redirect(
            "/student-login"
        )


    return render_template(
        "student_register.html"
    )


# ============================================================
# STUDENT LOGIN
# ============================================================

@app.route(
    "/student-login",
    methods=["GET", "POST"]
)
def student_login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()

        password = request.form["password"]


        conn = get_db()


        student = conn.execute(
            """
            SELECT *
            FROM students
            WHERE email = ?
            """,
            (email,)
        ).fetchone()


        conn.close()


        if (
            student
            and
            check_password_hash(
                student["password"],
                password
            )
        ):

            session["student_id"] = student["id"]

            session["student_name"] = student["name"]

            return redirect(
                "/student-dashboard"
            )


        return render_template(
            "student_login.html",
            error="Invalid email or password."
        )


    return render_template(
        "student_login.html"
    )


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/student-dashboard")
def student_dashboard():

    if "student_id" not in session:

        return redirect(
            "/student-login"
        )


    return render_template(
        "student_dashboard.html"
    )


# ============================================================
# REPORT ISSUE
# ============================================================

@app.route(
    "/report",
    methods=["GET", "POST"]
)
def report_issue():

    if "student_id" not in session:

        return redirect(
            "/student-login"
        )


    if request.method == "POST":

        location = request.form[
            "location"
        ].strip()


        description = request.form[
            "description"
        ].strip()


        # ----------------------------------------------------
        # AUTOMATIC ANALYSIS
        # ----------------------------------------------------

        category = classify_category(
            description
        )


        priority = classify_priority(
            description,
            category
        )


        topic = extract_topic(
            description
        )


        # ----------------------------------------------------
        # STUDENT ISSUE IMAGE
        # ----------------------------------------------------

        uploaded_image = request.files.get(
            "image"
        )

        image_filename = None


        if (
            uploaded_image
            and
            uploaded_image.filename
        ):

            if not allowed_file(
                uploaded_image.filename
            ):

                return render_template(
                    "report.html",
                    error="Only PNG, JPG and JPEG images are allowed."
                )


            original_name = secure_filename(
                uploaded_image.filename
            )


            extension = original_name.rsplit(
                ".",
                1
            )[1].lower()


            image_filename = (
                "report_"
                + uuid.uuid4().hex
                + "."
                + extension
            )


            image_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                image_filename
            )


            uploaded_image.save(
                image_path
            )


        conn = get_db()


        # ----------------------------------------------------
        # FIND EXISTING MASTER ISSUE
        # ----------------------------------------------------

        existing_issues = conn.execute(
            """
            SELECT *
            FROM master_issues
            WHERE category = ?
            AND location = ?
            AND status != 'Resolved'
            """,
            (
                category,
                location
            )
        ).fetchall()


        master_issue_id = None


        for issue in existing_issues:

            existing_topic = extract_topic(
                issue["description"]
            )


            if (
                existing_topic == topic
                or
                topic == "general"
                or
                existing_topic == "general"
            ):

                master_issue_id = issue["id"]


                conn.execute(
                    """
                    UPDATE master_issues

                    SET reports_count =
                        reports_count + 1

                    WHERE id = ?
                    """,
                    (
                        master_issue_id,
                    )
                )


                break


        # ----------------------------------------------------
        # CREATE NEW MASTER ISSUE
        # ----------------------------------------------------

        if master_issue_id is None:

            cursor = conn.execute(
                """
                INSERT INTO master_issues
                (
                    category,
                    location,
                    description,
                    priority,
                    status,
                    assigned_team,
                    resolution_image,
                    reports_count
                )
                VALUES
                (
                    ?, ?, ?, ?,
                    'Pending',
                    NULL,
                    NULL,
                    1
                )
                """,
                (
                    category,
                    location,
                    description,
                    priority
                )
            )


            master_issue_id = cursor.lastrowid


        # ----------------------------------------------------
        # SAVE STUDENT REPORT
        # ----------------------------------------------------

        conn.execute(
            """
            INSERT INTO reports
            (
                student_id,
                description,
                location,
                category,
                priority,
                image,
                master_issue_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["student_id"],
                description,
                location,
                category,
                priority,
                image_filename,
                master_issue_id
            )
        )


        conn.commit()

        conn.close()


        return redirect(
            "/my-reports"
        )


    return render_template(
        "report.html"
    )


# ============================================================
# STUDENT REPORTS / TRACKING
# ============================================================

@app.route("/my-reports")
def my_reports():

    if "student_id" not in session:

        return redirect(
            "/student-login"
        )


    conn = get_db()


    reports = conn.execute(
        """
        SELECT

            reports.*,

            master_issues.status,

            master_issues.assigned_team,

            master_issues.reports_count,

            master_issues.resolution_image

        FROM reports

        JOIN master_issues

        ON reports.master_issue_id =
           master_issues.id

        WHERE reports.student_id = ?

        ORDER BY reports.id DESC
        """,
        (
            session["student_id"],
        )
    ).fetchall()


    conn.close()


    return render_template(
        "track.html",
        reports=reports
    )


# ============================================================
# DELETE PENDING REPORT
# ============================================================

@app.route(
    "/delete-report/<int:report_id>",
    methods=["POST"]
)
def delete_report(report_id):

    if "student_id" not in session:

        return redirect(
            "/student-login"
        )


    conn = get_db()


    report = conn.execute(
        """
        SELECT *
        FROM reports
        WHERE id = ?
        AND student_id = ?
        """,
        (
            report_id,
            session["student_id"]
        )
    ).fetchone()


    if not report:

        conn.close()

        return redirect(
            "/my-reports"
        )


    master_issue = conn.execute(
        """
        SELECT *
        FROM master_issues
        WHERE id = ?
        """,
        (
            report["master_issue_id"],
        )
    ).fetchone()


    # Only pending issues can be deleted
    if (
        master_issue
        and
        master_issue["status"] == "Pending"
    ):

        # Delete student report
        conn.execute(
            """
            DELETE FROM reports
            WHERE id = ?
            """,
            (
                report_id,
            )
        )


        # Check remaining reports
        remaining = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM reports
            WHERE master_issue_id = ?
            """,
            (
                report["master_issue_id"],
            )
        ).fetchone()["count"]


        if remaining == 0:

            conn.execute(
                """
                DELETE FROM master_issues
                WHERE id = ?
                """,
                (
                    report["master_issue_id"],
                )
            )

        else:

            conn.execute(
                """
                UPDATE master_issues

                SET reports_count = ?

                WHERE id = ?
                """,
                (
                    remaining,
                    report["master_issue_id"]
                )
            )


        conn.commit()


    conn.close()


    return redirect(
        "/my-reports"
    )


# ============================================================
# SERVE UPLOADED IMAGES
# ============================================================

@app.route(
    "/uploads/<filename>"
)
def uploaded_file(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin-login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form[
            "username"
        ].strip()


        password = request.form[
            "password"
        ]


        conn = get_db()


        admin = conn.execute(
            """
            SELECT *
            FROM admins
            WHERE username = ?
            """,
            (
                username,
            )
        ).fetchone()


        conn.close()


        if (
            admin
            and
            check_password_hash(
                admin["password"],
                password
            )
        ):

            session["admin_id"] = admin["id"]

            return redirect(
                "/admin-dashboard"
            )


        return render_template(
            "admin_login.html",
            error="Invalid username or password."
        )


    return render_template(
        "admin_login.html"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin-dashboard")
def admin_dashboard():

    if "admin_id" not in session:

        return redirect(
            "/admin-login"
        )


    conn = get_db()


    issues = conn.execute(
        """
        SELECT *
        FROM master_issues
        ORDER BY id DESC
        """
    ).fetchall()


    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    total = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM master_issues
        """
    ).fetchone()["count"]


    high = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM master_issues
        WHERE priority = 'High'
        """
    ).fetchone()["count"]


    pending = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM master_issues
        WHERE status = 'Pending'
        """
    ).fetchone()["count"]


    progress = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM master_issues
        WHERE status = 'In Progress'
        """
    ).fetchone()["count"]


    resolved = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM master_issues
        WHERE status = 'Resolved'
        """
    ).fetchone()["count"]


    conn.close()


    return render_template(
        "admin_dashboard.html",
        issues=issues,
        total=total,
        high=high,
        pending=pending,
        progress=progress,
        resolved=resolved
    )


# ============================================================
# UPDATE MASTER ISSUE
# ============================================================

@app.route(
    "/update-issue/<int:issue_id>",
    methods=["POST"]
)
def update_issue(issue_id):

    if "admin_id" not in session:

        return redirect(
            "/admin-login"
        )


    status = request.form[
        "status"
    ]


    assigned_team = request.form[
        "assigned_team"
    ]


    # --------------------------------------------------------
    # RESOLUTION IMAGE
    # --------------------------------------------------------

    resolution_image = request.files.get(
        "resolution_image"
    )


    resolution_filename = None


    if (
        resolution_image
        and
        resolution_image.filename
    ):

        if not allowed_file(
            resolution_image.filename
        ):

            return redirect(
                "/admin-dashboard"
            )


        original_name = secure_filename(
            resolution_image.filename
        )


        extension = original_name.rsplit(
            ".",
            1
        )[1].lower()


        resolution_filename = (
            "resolved_"
            + uuid.uuid4().hex
            + "."
            + extension
        )


        resolution_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            resolution_filename
        )


        resolution_image.save(
            resolution_path
        )


    conn = get_db()


    # --------------------------------------------------------
    # UPDATE WITH RESOLUTION IMAGE
    # --------------------------------------------------------

    if resolution_filename:

        conn.execute(
            """
            UPDATE master_issues

            SET
                status = ?,
                assigned_team = ?,
                resolution_image = ?

            WHERE id = ?
            """,
            (
                status,
                assigned_team,
                resolution_filename,
                issue_id
            )
        )


    else:

        conn.execute(
            """
            UPDATE master_issues

            SET
                status = ?,
                assigned_team = ?

            WHERE id = ?
            """,
            (
                status,
                assigned_team,
                issue_id
            )
        )


    conn.commit()

    conn.close()


    return redirect(
        "/admin-dashboard"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True
    )

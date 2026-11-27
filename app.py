"""Flask REST service for Student & Course Enrollment using SQLite ('?' SQL) and Marshmallow."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from typing import Any

from flask import Flask, jsonify, request, url_for
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

from db import (
    course_row_to_dict,
    enrollment_row_to_dict,
    get_db,
    init_app as init_db_app,
    student_row_to_dict,
    utc_now_iso,
)
from openapi import register_swagger
from schemas import (
    course_list_schema,
    course_patch_schema,
    course_query_schema,
    course_schema,
    enrollment_list_schema,
    enrollment_patch_schema,
    enrollment_query_schema,
    enrollment_schema,
    student_list_schema,
    student_patch_schema,
    student_query_schema,
    student_schema,
)


COURSE_SELECT_SQL = """
SELECT
    c.id,
    c.code,
    c.title,
    c.credits,
    c.capacity,
    c.created_at,
    COALESCE(SUM(CASE WHEN e.status = 'enrolled' THEN 1 ELSE 0 END), 0) AS enrolled_count
FROM course AS c
LEFT JOIN enrollment AS e ON e.course_id = c.id
"""


def error_response(
    status_code: int,
    error: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: list[tuple[str, str]] | None = None,
):
    payload: dict[str, Any] = {"error": error, "message": message}
    if details is not None:
        payload["details"] = details
    resp = jsonify(payload)
    resp.status_code = status_code
    if headers:
        for key, value in headers:
            resp.headers[key] = value
    return resp


def _parse_json_object() -> tuple[dict[str, Any] | None, Any]:
    if not request.is_json:
        return None, error_response(
            415,
            "UnsupportedMediaType",
            "Content-Type must be application/json.",
        )
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response(
            400,
            "BadRequest",
            "Request body must be a valid JSON object.",
        )
    return data, None


def _build_patch_sql(
    table: str,
    updates: dict[str, Any],
    allowed_columns: tuple[str, ...],
    row_id: int,
) -> tuple[str, tuple[Any, ...]]:
    """Build a parameterized UPDATE statement using '?' placeholders from allowlisted columns."""
    assignments: list[str] = []
    params: list[Any] = []
    for col in allowed_columns:
        if col in updates:
            assignments.append(f"{col} = ?")
            params.append(updates[col])
    params.append(row_id)
    sql = f"UPDATE {table} SET {', '.join(assignments)} WHERE id = ?"
    return sql, tuple(params)


def _fetch_student(conn: sqlite3.Connection, student_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, student_number, name, email, major, created_at FROM student WHERE id = ?",
        (student_id,),
    ).fetchone()


def _fetch_course(conn: sqlite3.Connection, course_id: int) -> sqlite3.Row | None:
    return conn.execute(
        COURSE_SELECT_SQL + " WHERE c.id = ? GROUP BY c.id",
        (course_id,),
    ).fetchone()


def _fetch_enrollment(conn: sqlite3.Connection, enrollment_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, student_id, course_id, status, grade, enrolled_at, updated_at
        FROM enrollment
        WHERE id = ?
        """,
        (enrollment_id,),
    ).fetchone()


def _student_conflict_message(exc: sqlite3.IntegrityError, data: dict[str, Any]) -> str:
    msg = str(exc).lower()
    if "student.student_number" in msg or "student_number" in msg:
        return f"A student with student_number '{data.get('student_number', '')}' already exists."
    if "student.email" in msg or "email" in msg:
        return f"A student with email '{data.get('email', '')}' already exists."
    return "Student conflicts with an existing record."


def create_app(database_path: str | None = None) -> Flask:
    app = Flask(__name__)
    default_db = Path(__file__).with_name("enrollment.db").as_posix()
    app.config["DATABASE_PATH"] = database_path or os.environ.get("DATABASE_PATH") or default_db

    init_db_app(app)

    @app.errorhandler(ValidationError)
    def handle_validation_error(err: ValidationError):
        details = err.messages if isinstance(err.messages, dict) else {"_schema": err.messages}
        return error_response(400, "ValidationError", "Invalid request data.", details)

    @app.errorhandler(HTTPException)
    def handle_http_exception(err: HTTPException):
        status_code = err.code or 500
        error_name = (err.name or "HTTPError").replace(" ", "")
        headers = err.get_headers() if status_code == 405 else None
        return error_response(
            status_code,
            error_name,
            err.description or "Request error.",
            headers=headers,
        )

    @app.errorhandler(sqlite3.IntegrityError)
    def handle_integrity_error(err: sqlite3.IntegrityError):
        return error_response(409, "Conflict", f"Database constraint conflict: {err}")

    @app.errorhandler(Exception)
    def handle_unexpected_error(err: Exception):
        app.logger.exception("Unhandled error", exc_info=err)
        return error_response(500, "InternalServerError", "An unexpected error occurred.")

    # ------------------------------------------------------------------ Meta
    @app.get("/")
    def index():
        """API service metadata and available singular resource endpoints.
        ---
        get:
          tags: [Meta]
          summary: API overview
          responses:
            200:
              description: Service metadata and endpoint index
              content:
                application/json:
                  schema: ApiInfo
        """
        return (
            jsonify(
                {
                    "service": "Student & Course Enrollment REST API",
                    "docs": "/docs",
                    "openapi_json": "/openapi.json",
                    "openapi_yaml": "/openapi.yaml",
                    "health": "/api/health",
                    "endpoints": [
                        "/api/student",
                        "/api/course",
                        "/api/enrollment",
                    ],
                }
            ),
            200,
        )

    @app.get("/api/health")
    def health():
        """Verify service and SQLite database connectivity.
        ---
        get:
          tags: [Meta]
          summary: Health check
          responses:
            200:
              description: Service and SQLite database are healthy
              content:
                application/json:
                  schema: Health
        """
        conn = get_db()
        conn.execute("SELECT 1").fetchone()
        return jsonify({"status": "ok", "database": "sqlite"}), 200

    # --------------------------------------------------------------- Student
    @app.get("/api/student")
    def list_student():
        """List all students with optional major or email filters.
        ---
        get:
          tags: [Student]
          summary: List students
          parameters:
            - in: query
              name: major
              schema:
                type: string
              description: Case-insensitive partial filter on major
            - in: query
              name: email
              schema:
                type: string
              description: Case-insensitive exact filter on email
          responses:
            200:
              description: Array of student records
              content:
                application/json:
                  schema:
                    type: array
                    items: Student
            400:
              description: Invalid query parameter
              content:
                application/json:
                  schema: Error
        """
        filters = student_query_schema.load(request.args.to_dict())
        clauses: list[str] = []
        params: list[Any] = []
        if "major" in filters:
            clauses.append("LOWER(major) LIKE LOWER(?)")
            params.append(f"%{filters['major']}%")
        if "email" in filters:
            clauses.append("email = ?")
            params.append(filters["email"])

        sql = "SELECT id, student_number, name, email, major, created_at FROM student"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id"

        rows = get_db().execute(sql, tuple(params)).fetchall()
        payload = [student_row_to_dict(row) for row in rows]
        return jsonify(student_list_schema.dump(payload)), 200

    @app.post("/api/student")
    def create_student():
        """Create a new student record.
        ---
        post:
          tags: [Student]
          summary: Create a student
          requestBody:
            required: true
            content:
              application/json:
                schema: Student
          responses:
            201:
              description: Student created
              headers:
                Location:
                  schema:
                    type: string
                  description: URL of the newly created student
              content:
                application/json:
                  schema: Student
            400:
              description: Invalid JSON or Marshmallow validation error
              content:
                application/json:
                  schema: Error
            409:
              description: Duplicate student_number or email
              content:
                application/json:
                  schema: Error
            415:
              description: Content-Type is not application/json
              content:
                application/json:
                  schema: Error
        """
        raw, err = _parse_json_object()
        if err:
            return err

        validated = student_schema.load(raw)
        now = utc_now_iso()
        conn = get_db()
        try:
            cur = conn.execute(
                """
                INSERT INTO student (student_number, name, email, major, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    validated["student_number"],
                    validated["name"],
                    validated["email"],
                    validated["major"],
                    now,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            return error_response(409, "Conflict", _student_conflict_message(exc, validated))

        row = _fetch_student(conn, cur.lastrowid)
        resp = jsonify(student_schema.dump(student_row_to_dict(row)))
        resp.status_code = 201
        resp.headers["Location"] = url_for("get_student", student_id=row["id"])
        return resp

    @app.get("/api/student/<int:student_id>")
    def get_student(student_id: int):
        """Fetch a single student by ID.
        ---
        get:
          tags: [Student]
          summary: Get a student by ID
          parameters:
            - in: path
              name: student_id
              required: true
              schema:
                type: integer
          responses:
            200:
              description: Student found
              content:
                application/json:
                  schema: Student
            404:
              description: Student not found
              content:
                application/json:
                  schema: Error
        """
        row = _fetch_student(get_db(), student_id)
        if row is None:
            return error_response(404, "NotFound", f"Student {student_id} not found.")
        return jsonify(student_schema.dump(student_row_to_dict(row))), 200

    @app.put("/api/student/<int:student_id>")
    def replace_student(student_id: int):
        """Fully replace an existing student record.
        ---
        put:
          tags: [Student]
          summary: Replace a student
          parameters:
            - in: path
              name: student_id
              required: true
              schema:
                type: integer
          requestBody:
            required: true
            content:
              application/json:
                schema: Student
          responses:
            200:
              description: Student replaced
              content:
                application/json:
                  schema: Student
            400:
              description: Invalid JSON or Marshmallow validation error
              content:
                application/json:
                  schema: Error
            404:
              description: Student not found
              content:
                application/json:
                  schema: Error
            409:
              description: Duplicate student_number or email
              content:
                application/json:
                  schema: Error
            415:
              description: Content-Type is not application/json
              content:
                application/json:
                  schema: Error
        """
        conn = get_db()
        if _fetch_student(conn, student_id) is None:
            return error_response(404, "NotFound", f"Student {student_id} not found.")

        raw, err = _parse_json_object()
        if err:
            return err

        validated = student_schema.load(raw)
        try:
            conn.execute(
                """
                UPDATE student
                SET student_number = ?, name = ?, email = ?, major = ?
                WHERE id = ?
                """,
                (
                    validated["student_number"],
                    validated["name"],
                    validated["email"],
                    validated["major"],
                    student_id,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            return error_response(409, "Conflict", _student_conflict_message(exc, validated))

        row = _fetch_student(conn, student_id)
        return jsonify(student_schema.dump(student_row_to_dict(row))), 200

    @app.patch("/api/student/<int:student_id>")
    def update_student(student_id: int):
        """Partially update an existing student record.
        ---
        patch:
          tags: [Student]
          summary: Partially update a student
          parameters:
            - in: path
              name: student_id
              required: true
              schema:
                type: integer
          requestBody:
            required: true
            content:
              application/json:
                schema: StudentPatch
          responses:
            200:
              description: Student updated
              content:
                application/json:
                  schema: Student
            400:
              description: Invalid JSON, empty body, or validation error
              content:
                application/json:
                  schema: Error
            404:
              description: Student not found
              content:
                application/json:
                  schema: Error
            409:
              description: Duplicate student_number or email
              content:
                application/json:
                  schema: Error
            415:
              description: Content-Type is not application/json
              content:
                application/json:
                  schema: Error
        """
        conn = get_db()
        if _fetch_student(conn, student_id) is None:
            return error_response(404, "NotFound", f"Student {student_id} not found.")

        raw, err = _parse_json_object()
        if err:
            return err

        validated = student_patch_schema.load(raw)
        sql, params = _build_patch_sql(
            "student",
            validated,
            ("student_number", "name", "email", "major"),
            student_id,
        )
        try:
            conn.execute(sql, params)
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            return error_response(409, "Conflict", _student_conflict_message(exc, validated))

        row = _fetch_student(conn, student_id)
        return jsonify(student_schema.dump(student_row_to_dict(row))), 200

    @app.delete("/api/student/<int:student_id>")
    def delete_student(student_id: int):
        """Delete a student if no enrollment records reference them.
        ---
        delete:
          tags: [Student]
          summary: Delete a student
          parameters:
            - in: path
              name: student_id
              required: true
              schema:
                type: integer
          responses:
            204:
              description: Student deleted
            404:
              description: Student not found
              content:
                application/json:
                  schema: Error
            409:
              description: Student still has enrollment records
              content:
                application/json:
                  schema: Error
        """
        conn = get_db()
        if _fetch_student(conn, student_id) is None:
            return error_response(404, "NotFound", f"Student {student_id} not found.")

        try:
            conn.execute("DELETE FROM student WHERE id = ?", (student_id,))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return error_response(
                409,
                "Conflict",
                f"Cannot delete student {student_id} because enrollment records reference it.",
            )
        return "", 204

    # ---------------------------------------------------------------- Course
    @app.get("/api/course")
    def list_course():
        """List all courses with optional code and seat availability filters.
        ---
        get:
          tags: [Course]
          summary: List courses
          parameters:
            - in: query
              name: code
              schema:
                type: string
              description: Case-insensitive partial filter on course code
            - in: query
              name: available
              schema:
                type: boolean
              description: Set 'true' for courses with open seats, 'false' for full courses
          responses:
            200:
              description: Array of course records
              content:
                application/json:
                  schema:
                    type: array
                    items: Course
            400:
              description: Invalid query parameter
              content:
                application/json:
                  schema: Error
        """
        filters = course_query_schema.load(request.args.to_dict())
        where_clauses: list[str] = []
        having_clauses: list[str] = []
        params: list[Any] = []

        if "code" in filters:
            where_clauses.append("LOWER(c.code) LIKE LOWER(?)")
            params.append(f"%{filters['code']}%")
        if "available" in filters:
            if filters["available"]:
                having_clauses.append(
                    "COALESCE(SUM(CASE WHEN e.status = 'enrolled' THEN 1 ELSE 0 END), 0) < c.capacity"
                )
            else:
                having_clauses.append(
                    "COALESCE(SUM(CASE WHEN e.status = 'enrolled' THEN 1 ELSE 0 END), 0) >= c.capacity"
                )

        sql = COURSE_SELECT_SQL
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " GROUP BY c.id"
        if having_clauses:
            sql += " HAVING " + " AND ".join(having_clauses)
        sql += " ORDER BY c.id"

        rows = get_db().execute(sql, tuple(params)).fetchall()
        payload = [course_row_to_dict(row) for row in rows]
        return jsonify(course_list_schema.dump(payload)), 200

    @app.post("/api/course")
    def create_course():
        """Create a new course.
        ---
        post:
          tags: [Course]
          summary: Create a course
          requestBody:
            required: true
            content:
              application/json:
                schema: Course
          responses:
            201:
              description: Course created
              headers:
                Location:
                  schema:
                    type: string
                  description: URL of the newly created course
              content:
                application/json:
                  schema: Course
            400:
              description: Invalid JSON or Marshmallow validation error
              content:
                application/json:
                  schema: Error
            409:
              description: Duplicate course code
              content:
                application/json:
                  schema: Error
            415:
              description: Content-Type is not application/json
              content:
                application/json:
                  schema: Error
        """
        raw, err = _parse_json_object()
        if err:
            return err

        validated = course_schema.load(raw)
        now = utc_now_iso()
        conn = get_db()
        try:
            cur = conn.execute(
                """
                INSERT INTO course (code, title, credits, capacity, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    validated["code"],
                    validated["title"],
                    validated["credits"],
                    validated["capacity"],
                    now,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return error_response(
                409,
                "Conflict",
                f"A course with code '{validated['code']}' already exists.",
            )

        row = _fetch_course(conn, cur.lastrowid)
        resp = jsonify(course_schema.dump(course_row_to_dict(row)))
        resp.status_code = 201
        resp.headers["Location"] = url_for("get_course", course_id=row["id"])
        return resp

    @app.get("/api/course/<int:course_id>")
    def get_course(course_id: int):
        """Fetch a single course by ID.
        ---
        get:
          tags: [Course]
          summary: Get a course by ID
          parameters:
            - in: path
              name: course_id
              required: true
              schema:
                type: integer
          responses:
            200:
              description: Course found
              content:
                application/json:
                  schema: Course
            404:
              description: Course not found
              content:
                application/json:
                  schema: Error
        """
        row = _fetch_course(get_db(), course_id)
        if row is None:
            return error_response(404, "NotFound", f"Course {course_id} not found.")
        return jsonify(course_schema.dump(course_row_to_dict(row))), 200

    @app.put("/api/course/<int:course_id>")
    def replace_course(course_id: int):
        """Fully replace an existing course.
        ---
        put:
          tags: [Course]
          summary: Replace a course
          parameters:
            - in: path
              name: course_id
              required: true
              schema:
                type: integer
          requestBody:
            required: true
            content:
              application/json:
                schema: Course
          responses:
            200:
              description: Course replaced
              content:
                application/json:
                  schema: Course
            400:
              description: Invalid JSON or Marshmallow validation error
              content:
                application/json:
                  schema: Error
            404:
              description: Course not found
              content:
                application/json:
                  schema: Error
            409:
              description: Duplicate course code or capacity below active enrollments
              content:
                application/json:
                  schema: Error
            415:
              description: Content-Type is not application/json
              content:
                application/json:
                  schema: Error
        """
        conn = get_db()
        existing = _fetch_course(conn, course_id)
        if existing is None:
            return error_response(404, "NotFound", f"Course {course_id} not found.")

        raw, err = _parse_json_object()
        if err:
            return err

        validated = course_schema.load(raw)
        if validated["capacity"] < existing["enrolled_count"]:
            return error_response(
                409,
                "Conflict",
                (
                    f"Cannot reduce capacity to {validated['capacity']} below current "
                    f"active enrollment count ({existing['enrolled_count']})."
                ),
            )

        try:
            conn.execute(
                """
                UPDATE course
                SET code = ?, title = ?, credits = ?, capacity = ?
                WHERE id = ?
                """,
                (
                    validated["code"],
                    validated["title"],
                    validated["credits"],
                    validated["capacity"],
                    course_id,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return error_response(
                409,
                "Conflict",
                f"A course with code '{validated['code']}' already exists.",
            )

        row = _fetch_course(conn, course_id)
        return jsonify(course_schema.dump(course_row_to_dict(row))), 200

    @app.patch("/api/course/<int:course_id>")
    def update_course(course_id: int):
        """Partially update an existing course.
        ---
        patch:
          tags: [Course]
          summary: Partially update a course
          parameters:
            - in: path
              name: course_id
              required: true
              schema:
                type: integer
          requestBody:
            required: true
            content:
              application/json:
                schema: CoursePatch
          responses:
            200:
              description: Course updated
              content:
                application/json:
                  schema: Course
            400:
              description: Invalid JSON, empty body, or validation error
              content:
                application/json:
                  schema: Error
            404:
              description: Course not found
              content:
                application/json:
                  schema: Error
            409:
              description: Duplicate course code or capacity below active enrollments
              content:
                application/json:
                  schema: Error
            415:
              description: Content-Type is not application/json
              content:
                application/json:
                  schema: Error
        """
        conn = get_db()
        existing = _fetch_course(conn, course_id)
        if existing is None:
            return error_response(404, "NotFound", f"Course {course_id} not found.")

        raw, err = _parse_json_object()
        if err:
            return err

        validated = course_patch_schema.load(raw)
        if "capacity" in validated and validated["capacity"] < existing["enrolled_count"]:
            return error_response(
                409,
                "Conflict",
                (
                    f"Cannot reduce capacity to {validated['capacity']} below current "
                    f"active enrollment count ({existing['enrolled_count']})."
                ),
            )

        sql, params = _build_patch_sql(
            "course",
            validated,
            ("code", "title", "credits", "capacity"),
            course_id,
        )
        try:
            conn.execute(sql, params)
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return error_response(
                409,
                "Conflict",
                f"A course with code '{validated.get('code', '')}' already exists.",
            )

        row = _fetch_course(conn, course_id)
        return jsonify(course_schema.dump(course_row_to_dict(row))), 200

    @app.delete("/api/course/<int:course_id>")
    def delete_course(course_id: int):
        """Delete a course if no enrollment records reference it.
        ---
        delete:
          tags: [Course]
          summary: Delete a course
          parameters:
            - in: path
              name: course_id
              required: true
              schema:
                type: integer
          responses:
            204:
              description: Course deleted
            404:
              description: Course not found
              content:
                application/json:
                  schema: Error
            409:
              description: Course still has enrollment records
              content:
                application/json:
                  schema: Error
        """
        conn = get_db()
        if _fetch_course(conn, course_id) is None:
            return error_response(404, "NotFound", f"Course {course_id} not found.")

        try:
            conn.execute("DELETE FROM course WHERE id = ?", (course_id,))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return error_response(
                409,
                "Conflict",
                f"Cannot delete course {course_id} because enrollment records reference it.",
            )
        return "", 204

    # ------------------------------------------------------------ Enrollment
    def _validate_enrollment_references_and_capacity(
        conn: sqlite3.Connection,
        student_id: int,
        course_id: int,
        status: str,
        exclude_enrollment_id: int | None = None,
    ):
        if _fetch_student(conn, student_id) is None:
            return error_response(404, "NotFound", f"Student {student_id} not found.")

        course_row = conn.execute(
            "SELECT id, code, capacity FROM course WHERE id = ?",
            (course_id,),
        ).fetchone()
        if course_row is None:
            return error_response(404, "NotFound", f"Course {course_id} not found.")

        if status == "enrolled":
            if exclude_enrollment_id is None:
                count_row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM enrollment
                    WHERE course_id = ? AND status = 'enrolled'
                    """,
                    (course_id,),
                ).fetchone()
            else:
                count_row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM enrollment
                    WHERE course_id = ? AND status = 'enrolled' AND id != ?
                    """,
                    (course_id, exclude_enrollment_id),
                ).fetchone()
            if count_row["cnt"] >= course_row["capacity"]:
                return error_response(
                    409,
                    "Conflict",
                    f"Course '{course_row['code']}' is at full capacity ({course_row['capacity']}).",
                )
        return None

    @app.get("/api/enrollment")
    def list_enrollment():
        """List enrollments with optional student_id, course_id, and status filters.
        ---
        get:
          tags: [Enrollment]
          summary: List enrollments
          parameters:
            - in: query
              name: student_id
              schema:
                type: integer
              description: Filter by student ID
            - in: query
              name: course_id
              schema:
                type: integer
              description: Filter by course ID
            - in: query
              name: status
              schema:
                type: string
                enum: [enrolled, completed, dropped]
              description: Filter by enrollment status
          responses:
            200:
              description: Array of enrollment records
              content:
                application/json:
                  schema:
                    type: array
                    items: Enrollment
            400:
              description: Invalid query parameter
              content:
                application/json:
                  schema: Error
        """
        filters = enrollment_query_schema.load(request.args.to_dict())
        clauses: list[str] = []
        params: list[Any] = []

        if "student_id" in filters:
            clauses.append("student_id = ?")
            params.append(filters["student_id"])
        if "course_id" in filters:
            clauses.append("course_id = ?")
            params.append(filters["course_id"])
        if "status" in filters:
            clauses.append("status = ?")
            params.append(filters["status"])

        sql = "SELECT id, student_id, course_id, status, grade, enrolled_at, updated_at FROM enrollment"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id"

        rows = get_db().execute(sql, tuple(params)).fetchall()
        payload = [enrollment_row_to_dict(row) for row in rows]
        return jsonify(enrollment_list_schema.dump(payload)), 200

    @app.post("/api/enrollment")
    def create_enrollment():
        """Enroll a student in a course.
        ---
        post:
          tags: [Enrollment]
          summary: Create an enrollment
          requestBody:
            required: true
            content:
              application/json:
                schema: Enrollment
          responses:
            201:
              description: Enrollment created
              headers:
                Location:
                  schema:
                    type: string
                  description: URL of the newly created enrollment
              content:
                application/json:
                  schema: Enrollment
            400:
              description: Invalid JSON or Marshmallow validation error
              content:
                application/json:
                  schema: Error
            404:
              description: Student or course not found
              content:
                application/json:
                  schema: Error
            409:
              description: Duplicate enrollment or course at full capacity
              content:
                application/json:
                  schema: Error
            415:
              description: Content-Type is not application/json
              content:
                application/json:
                  schema: Error
        """
        raw, err = _parse_json_object()
        if err:
            return err

        validated = enrollment_schema.load(raw)
        conn = get_db()
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")

        ref_err = _validate_enrollment_references_and_capacity(
            conn,
            validated["student_id"],
            validated["course_id"],
            validated["status"],
        )
        if ref_err:
            conn.rollback()
            return ref_err

        now = utc_now_iso()
        try:
            cur = conn.execute(
                """
                INSERT INTO enrollment (student_id, course_id, status, grade, enrolled_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    validated["student_id"],
                    validated["course_id"],
                    validated["status"],
                    validated["grade"],
                    now,
                    now,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return error_response(
                409,
                "Conflict",
                (
                    f"Student {validated['student_id']} is already enrolled in "
                    f"course {validated['course_id']}."
                ),
            )

        row = _fetch_enrollment(conn, cur.lastrowid)
        resp = jsonify(enrollment_schema.dump(enrollment_row_to_dict(row)))
        resp.status_code = 201
        resp.headers["Location"] = url_for("get_enrollment", enrollment_id=row["id"])
        return resp

    @app.get("/api/enrollment/<int:enrollment_id>")
    def get_enrollment(enrollment_id: int):
        """Fetch a single enrollment by ID.
        ---
        get:
          tags: [Enrollment]
          summary: Get an enrollment by ID
          parameters:
            - in: path
              name: enrollment_id
              required: true
              schema:
                type: integer
          responses:
            200:
              description: Enrollment found
              content:
                application/json:
                  schema: Enrollment
            404:
              description: Enrollment not found
              content:
                application/json:
                  schema: Error
        """
        row = _fetch_enrollment(get_db(), enrollment_id)
        if row is None:
            return error_response(404, "NotFound", f"Enrollment {enrollment_id} not found.")
        return jsonify(enrollment_schema.dump(enrollment_row_to_dict(row))), 200

    @app.put("/api/enrollment/<int:enrollment_id>")
    def replace_enrollment(enrollment_id: int):
        """Fully replace an existing enrollment.
        ---
        put:
          tags: [Enrollment]
          summary: Replace an enrollment
          parameters:
            - in: path
              name: enrollment_id
              required: true
              schema:
                type: integer
          requestBody:
            required: true
            content:
              application/json:
                schema: Enrollment
          responses:
            200:
              description: Enrollment replaced
              content:
                application/json:
                  schema: Enrollment
            400:
              description: Invalid JSON or Marshmallow validation error
              content:
                application/json:
                  schema: Error
            404:
              description: Enrollment, student, or course not found
              content:
                application/json:
                  schema: Error
            409:
              description: Duplicate enrollment or course at full capacity
              content:
                application/json:
                  schema: Error
            415:
              description: Content-Type is not application/json
              content:
                application/json:
                  schema: Error
        """
        conn = get_db()
        if _fetch_enrollment(conn, enrollment_id) is None:
            return error_response(404, "NotFound", f"Enrollment {enrollment_id} not found.")

        raw, err = _parse_json_object()
        if err:
            return err

        validated = enrollment_schema.load(raw)
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")

        ref_err = _validate_enrollment_references_and_capacity(
            conn,
            validated["student_id"],
            validated["course_id"],
            validated["status"],
            exclude_enrollment_id=enrollment_id,
        )
        if ref_err:
            conn.rollback()
            return ref_err

        now = utc_now_iso()
        try:
            conn.execute(
                """
                UPDATE enrollment
                SET student_id = ?, course_id = ?, status = ?, grade = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    validated["student_id"],
                    validated["course_id"],
                    validated["status"],
                    validated["grade"],
                    now,
                    enrollment_id,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return error_response(
                409,
                "Conflict",
                (
                    f"Student {validated['student_id']} is already enrolled in "
                    f"course {validated['course_id']}."
                ),
            )

        row = _fetch_enrollment(conn, enrollment_id)
        return jsonify(enrollment_schema.dump(enrollment_row_to_dict(row))), 200

    @app.patch("/api/enrollment/<int:enrollment_id>")
    def update_enrollment(enrollment_id: int):
        """Partially update an existing enrollment (for example status or grade).
        ---
        patch:
          tags: [Enrollment]
          summary: Partially update an enrollment
          parameters:
            - in: path
              name: enrollment_id
              required: true
              schema:
                type: integer
          requestBody:
            required: true
            content:
              application/json:
                schema: EnrollmentPatch
          responses:
            200:
              description: Enrollment updated
              content:
                application/json:
                  schema: Enrollment
            400:
              description: Invalid JSON, empty body, or validation error
              content:
                application/json:
                  schema: Error
            404:
              description: Enrollment, student, or course not found
              content:
                application/json:
                  schema: Error
            409:
              description: Duplicate enrollment or course at full capacity
              content:
                application/json:
                  schema: Error
            415:
              description: Content-Type is not application/json
              content:
                application/json:
                  schema: Error
        """
        conn = get_db()
        existing = _fetch_enrollment(conn, enrollment_id)
        if existing is None:
            return error_response(404, "NotFound", f"Enrollment {enrollment_id} not found.")

        raw, err = _parse_json_object()
        if err:
            return err

        validated = enrollment_patch_schema.load(raw)
        final_student_id = validated.get("student_id", existing["student_id"])
        final_course_id = validated.get("course_id", existing["course_id"])
        final_status = validated.get("status", existing["status"])
        final_grade = validated["grade"] if "grade" in validated else existing["grade"]

        if final_grade is not None and final_status != "completed":
            raise ValidationError(
                {"grade": ["Grade can only be assigned when status is 'completed' (set grade to null otherwise)."]}
            )

        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")

        ref_err = _validate_enrollment_references_and_capacity(
            conn,
            final_student_id,
            final_course_id,
            final_status,
            exclude_enrollment_id=enrollment_id,
        )
        if ref_err:
            conn.rollback()
            return ref_err

        updates = dict(validated)
        updates["updated_at"] = utc_now_iso()
        sql, params = _build_patch_sql(
            "enrollment",
            updates,
            ("student_id", "course_id", "status", "grade", "updated_at"),
            enrollment_id,
        )
        try:
            conn.execute(sql, params)
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return error_response(
                409,
                "Conflict",
                f"Student {final_student_id} is already enrolled in course {final_course_id}.",
            )

        row = _fetch_enrollment(conn, enrollment_id)
        return jsonify(enrollment_schema.dump(enrollment_row_to_dict(row))), 200

    @app.delete("/api/enrollment/<int:enrollment_id>")
    def delete_enrollment(enrollment_id: int):
        """Delete an enrollment record.
        ---
        delete:
          tags: [Enrollment]
          summary: Delete an enrollment
          parameters:
            - in: path
              name: enrollment_id
              required: true
              schema:
                type: integer
          responses:
            204:
              description: Enrollment deleted
            404:
              description: Enrollment not found
              content:
                application/json:
                  schema: Error
        """
        conn = get_db()
        if _fetch_enrollment(conn, enrollment_id) is None:
            return error_response(404, "NotFound", f"Enrollment {enrollment_id} not found.")

        conn.execute("DELETE FROM enrollment WHERE id = ?", (enrollment_id,))
        conn.commit()
        return "", 204

    documented_views = [
        index,
        health,
        list_student,
        create_student,
        get_student,
        replace_student,
        update_student,
        delete_student,
        list_course,
        create_course,
        get_course,
        replace_course,
        update_course,
        delete_course,
        list_enrollment,
        create_enrollment,
        get_enrollment,
        replace_enrollment,
        update_enrollment,
        delete_enrollment,
    ]
    register_swagger(app, documented_views)

    return app


app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False)

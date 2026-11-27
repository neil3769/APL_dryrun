"""Marshmallow 4 schemas for request validation, query parameters, and serialization."""

from __future__ import annotations

from typing import Any

from marshmallow import Schema, ValidationError, fields, pre_load, validate, validates_schema


ENROLLMENT_STATUSES = ("enrolled", "completed", "dropped")
VALID_GRADES = ("A", "B", "C", "D", "E", "F")


def _strip_fields(
    data: Any,
    strip_keys: tuple[str, ...] = (),
    lower_keys: tuple[str, ...] = (),
    upper_keys: tuple[str, ...] = (),
) -> Any:
    if not isinstance(data, dict):
        return data
    copied = dict(data)
    for key in strip_keys:
        if isinstance(copied.get(key), str):
            copied[key] = copied[key].strip()
    for key in lower_keys:
        if isinstance(copied.get(key), str):
            copied[key] = copied[key].strip().lower()
    for key in upper_keys:
        if isinstance(copied.get(key), str):
            copied[key] = copied[key].strip().upper()
    return copied


class StudentSchema(Schema):
    id = fields.Int(dump_only=True, metadata={"description": "Unique student ID", "example": 1})
    student_number = fields.Str(
        required=True,
        validate=validate.Length(min=2, max=32, error="Must be between 2 and 32 characters."),
        metadata={"description": "Unique student registration code", "example": "STU-1001"},
    )
    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=120, error="Must be between 1 and 120 characters."),
        metadata={"description": "Student full name", "example": "Alice Rossi"},
    )
    email = fields.Email(
        required=True,
        validate=validate.Length(max=255),
        metadata={"description": "Unique student email address", "example": "alice@university.edu"},
    )
    major = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=120, error="Must be between 1 and 120 characters."),
        metadata={"description": "Degree major", "example": "Computer Science"},
    )
    created_at = fields.DateTime(
        format="iso",
        dump_only=True,
        metadata={"description": "UTC creation timestamp"},
    )

    @pre_load
    def normalize_fields(self, data: Any, **kwargs: Any) -> Any:
        return _strip_fields(
            data,
            strip_keys=("name", "major"),
            lower_keys=("email",),
            upper_keys=("student_number",),
        )


class StudentPatchSchema(Schema):
    student_number = fields.Str(
        validate=validate.Length(min=2, max=32, error="Must be between 2 and 32 characters."),
        metadata={"description": "Unique student registration code", "example": "STU-1001"},
    )
    name = fields.Str(
        validate=validate.Length(min=1, max=120, error="Must be between 1 and 120 characters."),
        metadata={"description": "Student full name", "example": "Alice Rossi"},
    )
    email = fields.Email(
        validate=validate.Length(max=255),
        metadata={"description": "Unique student email address", "example": "alice@university.edu"},
    )
    major = fields.Str(
        validate=validate.Length(min=1, max=120, error="Must be between 1 and 120 characters."),
        metadata={"description": "Degree major", "example": "Data Science"},
    )

    @pre_load
    def normalize_fields(self, data: Any, **kwargs: Any) -> Any:
        return _strip_fields(
            data,
            strip_keys=("name", "major"),
            lower_keys=("email",),
            upper_keys=("student_number",),
        )

    @validates_schema
    def require_non_empty_patch(self, data: dict[str, Any], **kwargs: Any) -> None:
        if not data:
            raise ValidationError(
                "At least one updatable field (student_number, name, email, major) must be provided."
            )


class StudentQuerySchema(Schema):
    major = fields.Str(
        validate=validate.Length(min=1, max=120),
        metadata={"description": "Case-insensitive partial filter on major"},
    )
    email = fields.Str(
        validate=validate.Length(min=1, max=255),
        metadata={"description": "Case-insensitive exact filter on email"},
    )

    @pre_load
    def normalize_query(self, data: Any, **kwargs: Any) -> Any:
        return _strip_fields(data, strip_keys=("major",), lower_keys=("email",))


class CourseSchema(Schema):
    id = fields.Int(dump_only=True, metadata={"description": "Unique course ID", "example": 1})
    code = fields.Str(
        required=True,
        validate=validate.Length(min=2, max=32, error="Must be between 2 and 32 characters."),
        metadata={"description": "Unique course code", "example": "CS101"},
    )
    title = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=200, error="Must be between 1 and 200 characters."),
        metadata={"description": "Course title", "example": "Distributed Systems"},
    )
    credits = fields.Int(
        required=True,
        strict=True,
        validate=validate.Range(min=1, max=30, error="Must be an integer between 1 and 30."),
        metadata={"description": "Course credit value (1-30)", "example": 6},
    )
    capacity = fields.Int(
        required=True,
        strict=True,
        validate=validate.Range(min=1, max=1000, error="Must be an integer between 1 and 1000."),
        metadata={"description": "Maximum active enrollments (>= 1)", "example": 30},
    )
    enrolled_count = fields.Int(
        dump_only=True,
        metadata={"description": "Current active enrollment count", "example": 0},
    )
    created_at = fields.DateTime(
        format="iso",
        dump_only=True,
        metadata={"description": "UTC creation timestamp"},
    )

    @pre_load
    def normalize_fields(self, data: Any, **kwargs: Any) -> Any:
        return _strip_fields(data, strip_keys=("title",), upper_keys=("code",))


class CoursePatchSchema(Schema):
    code = fields.Str(
        validate=validate.Length(min=2, max=32, error="Must be between 2 and 32 characters."),
        metadata={"description": "Unique course code", "example": "CS101"},
    )
    title = fields.Str(
        validate=validate.Length(min=1, max=200, error="Must be between 1 and 200 characters."),
        metadata={"description": "Course title", "example": "Distributed Systems"},
    )
    credits = fields.Int(
        strict=True,
        validate=validate.Range(min=1, max=30, error="Must be an integer between 1 and 30."),
        metadata={"description": "Course credit value (1-30)", "example": 6},
    )
    capacity = fields.Int(
        strict=True,
        validate=validate.Range(min=1, max=1000, error="Must be an integer between 1 and 1000."),
        metadata={"description": "Maximum active enrollments (>= 1)", "example": 40},
    )

    @pre_load
    def normalize_fields(self, data: Any, **kwargs: Any) -> Any:
        return _strip_fields(data, strip_keys=("title",), upper_keys=("code",))

    @validates_schema
    def require_non_empty_patch(self, data: dict[str, Any], **kwargs: Any) -> None:
        if not data:
            raise ValidationError(
                "At least one updatable field (code, title, credits, capacity) must be provided."
            )


class CourseQuerySchema(Schema):
    code = fields.Str(
        validate=validate.Length(min=1, max=32),
        metadata={"description": "Case-insensitive partial filter on course code"},
    )
    available = fields.Bool(
        truthy={"true", "True", "TRUE"},
        falsy={"false", "False", "FALSE"},
        metadata={"description": "Filter by open seats ('true' or 'false')"},
    )

    @pre_load
    def normalize_query(self, data: Any, **kwargs: Any) -> Any:
        return _strip_fields(data, strip_keys=("available",), upper_keys=("code",))


class EnrollmentSchema(Schema):
    id = fields.Int(dump_only=True, metadata={"description": "Unique enrollment ID", "example": 1})
    student_id = fields.Int(
        required=True,
        strict=True,
        validate=validate.Range(min=1, error="Must be a positive integer."),
        metadata={"description": "Existing student ID", "example": 1},
    )
    course_id = fields.Int(
        required=True,
        strict=True,
        validate=validate.Range(min=1, error="Must be a positive integer."),
        metadata={"description": "Existing course ID", "example": 1},
    )
    status = fields.Str(
        load_default="enrolled",
        validate=validate.OneOf(ENROLLMENT_STATUSES),
        metadata={"description": "Enrollment lifecycle status", "example": "enrolled"},
    )
    grade = fields.Str(
        load_default=None,
        allow_none=True,
        validate=validate.OneOf(VALID_GRADES),
        metadata={"description": "Final letter grade (allowed only when status is 'completed')", "example": None},
    )
    enrolled_at = fields.DateTime(
        format="iso",
        dump_only=True,
        metadata={"description": "UTC enrollment timestamp"},
    )
    updated_at = fields.DateTime(
        format="iso",
        dump_only=True,
        metadata={"description": "UTC last-updated timestamp"},
    )

    @pre_load
    def normalize_fields(self, data: Any, **kwargs: Any) -> Any:
        return _strip_fields(data, lower_keys=("status",), upper_keys=("grade",))

    @validates_schema
    def validate_grade_status(self, data: dict[str, Any], **kwargs: Any) -> None:
        status = data.get("status", "enrolled")
        grade = data.get("grade")
        if grade is not None and status != "completed":
            raise ValidationError(
                {"grade": ["Grade can only be assigned when status is 'completed'."]}
            )


class EnrollmentPatchSchema(Schema):
    student_id = fields.Int(
        strict=True,
        validate=validate.Range(min=1, error="Must be a positive integer."),
        metadata={"description": "Existing student ID", "example": 1},
    )
    course_id = fields.Int(
        strict=True,
        validate=validate.Range(min=1, error="Must be a positive integer."),
        metadata={"description": "Existing course ID", "example": 1},
    )
    status = fields.Str(
        validate=validate.OneOf(ENROLLMENT_STATUSES),
        metadata={"description": "Enrollment lifecycle status", "example": "completed"},
    )
    grade = fields.Str(
        allow_none=True,
        validate=validate.OneOf(VALID_GRADES),
        metadata={"description": "Final letter grade (allowed only when status is 'completed')", "example": "A"},
    )

    @pre_load
    def normalize_fields(self, data: Any, **kwargs: Any) -> Any:
        return _strip_fields(data, lower_keys=("status",), upper_keys=("grade",))

    @validates_schema
    def require_non_empty_patch(self, data: dict[str, Any], **kwargs: Any) -> None:
        if not data:
            raise ValidationError(
                "At least one updatable field (student_id, course_id, status, grade) must be provided."
            )


class EnrollmentQuerySchema(Schema):
    student_id = fields.Int(
        validate=validate.Range(min=1, error="Must be a positive integer."),
        metadata={"description": "Filter by student ID"},
    )
    course_id = fields.Int(
        validate=validate.Range(min=1, error="Must be a positive integer."),
        metadata={"description": "Filter by course ID"},
    )
    status = fields.Str(
        validate=validate.OneOf(ENROLLMENT_STATUSES),
        metadata={"description": "Filter by enrollment status"},
    )

    @pre_load
    def normalize_query(self, data: Any, **kwargs: Any) -> Any:
        return _strip_fields(data, lower_keys=("status",))


class ErrorSchema(Schema):
    error = fields.Str(required=True, metadata={"example": "ValidationError"})
    message = fields.Str(required=True, metadata={"example": "Invalid request payload."})
    details = fields.Dict(keys=fields.Str(), values=fields.Raw(), required=False)


class HealthSchema(Schema):
    status = fields.Str(required=True, metadata={"example": "ok"})
    database = fields.Str(required=True, metadata={"example": "sqlite"})


class ApiInfoSchema(Schema):
    service = fields.Str(required=True, metadata={"example": "Student & Course Enrollment REST API"})
    docs = fields.Str(required=True, metadata={"example": "/docs"})
    openapi_json = fields.Str(required=True, metadata={"example": "/openapi.json"})
    openapi_yaml = fields.Str(required=True, metadata={"example": "/openapi.yaml"})
    health = fields.Str(required=True, metadata={"example": "/api/health"})
    endpoints = fields.List(fields.Str(), required=True)


student_schema = StudentSchema()
student_list_schema = StudentSchema(many=True)
student_patch_schema = StudentPatchSchema()
student_query_schema = StudentQuerySchema()

course_schema = CourseSchema()
course_list_schema = CourseSchema(many=True)
course_patch_schema = CoursePatchSchema()
course_query_schema = CourseQuerySchema()

enrollment_schema = EnrollmentSchema()
enrollment_list_schema = EnrollmentSchema(many=True)
enrollment_patch_schema = EnrollmentPatchSchema()
enrollment_query_schema = EnrollmentQuerySchema()

"""Auto-generated OpenAPI 3.0.3 specification via apispec + Marshmallow + Swagger UI."""

from __future__ import annotations

from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from apispec_webframeworks.flask import FlaskPlugin
from flask import Flask, Response, jsonify
from flask_swagger_ui import get_swaggerui_blueprint

from schemas import (
    ApiInfoSchema,
    CoursePatchSchema,
    CourseSchema,
    EnrollmentPatchSchema,
    EnrollmentSchema,
    ErrorSchema,
    HealthSchema,
    StudentPatchSchema,
    StudentSchema,
)


def build_openapi_spec(app: Flask, views: list) -> APISpec:
    """Create the APISpec from Marshmallow schemas and registered Flask view functions."""
    spec = APISpec(
        title="Student & Course Enrollment REST API",
        version="1.0.0",
        openapi_version="3.0.3",
        plugins=[FlaskPlugin(), MarshmallowPlugin()],
        info={
            "description": (
                "RESTful Flask service backed by SQLite (parameterized '?' queries) "
                "and validated with Marshmallow schemas. Resource URLs use singular nouns."
            ),
        },
        servers=[{"url": "/", "description": "Current host"}],
        tags=[
            {"name": "Meta", "description": "Service info and health check"},
            {"name": "Student", "description": "Student management (/api/student)"},
            {"name": "Course", "description": "Course management (/api/course)"},
            {"name": "Enrollment", "description": "Student course enrollment (/api/enrollment)"},
        ],
    )

    spec.components.schema("Student", schema=StudentSchema)
    spec.components.schema("StudentPatch", schema=StudentPatchSchema)
    spec.components.schema("Course", schema=CourseSchema)
    spec.components.schema("CoursePatch", schema=CoursePatchSchema)
    spec.components.schema("Enrollment", schema=EnrollmentSchema)
    spec.components.schema("EnrollmentPatch", schema=EnrollmentPatchSchema)
    spec.components.schema("Error", schema=ErrorSchema)
    spec.components.schema("Health", schema=HealthSchema)
    spec.components.schema("ApiInfo", schema=ApiInfoSchema)

    with app.test_request_context():
        for view_fn in views:
            spec.path(view=view_fn)

    return spec


def register_swagger(app: Flask, views: list) -> None:
    """Serve /openapi.json, /openapi.yaml, and Swagger UI at /docs."""
    spec = build_openapi_spec(app, views)
    spec_dict = spec.to_dict()
    spec_yaml = spec.to_yaml()

    @app.get("/openapi.json")
    def openapi_json():
        return jsonify(spec_dict), 200

    @app.get("/openapi.yaml")
    def openapi_yaml():
        return Response(spec_yaml, status=200, mimetype="application/yaml")

    swagger_bp = get_swaggerui_blueprint(
        "/docs",
        "/openapi.json",
        config={
            "app_name": "Student & Course Enrollment REST API",
            "validatorUrl": None,
        },
    )
    app.register_blueprint(swagger_bp, url_prefix="/docs")

# Student & Course Enrollment REST API (Flask + SQLite + Marshmallow + Swagger UI)

A RESTful web service built with Flask 3, `sqlite3` using **parameterized `?` SQL**, **Marshmallow 4** request/query validation, auto-generated **OpenAPI 3.0.3** (`apispec`) with **Swagger UI**, singular resource URLs, and Docker deployment support, bound to `0.0.0.0:5000`.

## Endpoints (Singular Resource URLs)

| Resource | Verb | Path | Description | Status Codes |
|---|---|---|---|---|
| **Meta** | `GET` | `/` | Service metadata & endpoint index | `200` |
| | `GET` | `/api/health` | Health & SQLite connectivity check | `200` |
| **Docs** | `GET` | `/docs` | Interactive Swagger UI | `200` |
| | `GET` | `/openapi.json` | Auto-generated OpenAPI 3.0.3 JSON | `200` |
| | `GET` | `/openapi.yaml` | Auto-generated OpenAPI 3.0.3 YAML | `200` |
| **Student** | `GET` | `/api/student` | List students (`?major=`, `?email=`) | `200`, `400` |
| | `POST` | `/api/student` | Create student | `201` (+ `Location`), `400`, `409`, `415` |
| | `GET` | `/api/student/<id>` | Get one student | `200`, `404` |
| | `PUT` | `/api/student/<id>` | Full replace student | `200`, `400`, `404`, `409`, `415` |
| | `PATCH` | `/api/student/<id>` | Partial update student | `200`, `400`, `404`, `409`, `415` |
| | `DELETE` | `/api/student/<id>` | Delete student (blocked if enrolled) | `204`, `404`, `409` |
| **Course** | `GET` | `/api/course` | List courses (`?code=`, `?available=true\|false`) | `200`, `400` |
| | `POST` | `/api/course` | Create course | `201` (+ `Location`), `400`, `409`, `415` |
| | `GET` | `/api/course/<id>` | Get one course (includes `enrolled_count`) | `200`, `404` |
| | `PUT` | `/api/course/<id>` | Full replace course | `200`, `400`, `404`, `409`, `415` |
| | `PATCH` | `/api/course/<id>` | Partial update course | `200`, `400`, `404`, `409`, `415` |
| | `DELETE` | `/api/course/<id>` | Delete course (blocked if enrolled) | `204`, `404`, `409` |
| **Enrollment** | `GET` | `/api/enrollment` | List enrollments (`?student_id=`, `?course_id=`, `?status=`) | `200`, `400` |
| | `POST` | `/api/enrollment` | Enroll student in course | `201` (+ `Location`), `400`, `404`, `409`, `415` |
| | `GET` | `/api/enrollment/<id>` | Get one enrollment | `200`, `404` |
| | `PUT` | `/api/enrollment/<id>` | Full replace enrollment | `200`, `400`, `404`, `409`, `415` |
| | `PATCH` | `/api/enrollment/<id>` | Partial update enrollment (`status`, `grade`) | `200`, `400`, `404`, `409`, `415` |
| | `DELETE` | `/api/enrollment/<id>` | Delete enrollment | `204`, `404` |

## Run Locally (Conda `rmi` environment)

```powershell
conda activate rmi
cd "D:\uFr Materials\Erasmus\APL_Code\rest-enrollment"
pip install -r requirements.txt
python app.py
```

Open Swagger UI in your browser: **http://127.0.0.1:5000/docs**

Environment variables:
- `HOST` (default `0.0.0.0`)
- `PORT` (default `5000`)
- `DATABASE_PATH` (default `./enrollment.db` locally, `/data/enrollment.db` in Docker)

## Run with Docker

```powershell
cd "D:\uFr Materials\Erasmus\APL_Code\rest-enrollment"
docker build -t enrollment-api .

# Run detached on port 5000 (ephemeral DB)
docker run -d --name enrollment-api --rm -p 5000:5000 enrollment-api

# Or persist SQLite data in a named Docker volume
docker run -d --name enrollment-api --rm -p 5000:5000 -v enrollment_data:/data enrollment-api
```

Stop the container:
```powershell
docker stop enrollment-api
```

## Run the Curl Tests

See [CURL_TESTS.md](CURL_TESTS.md) for individual `curl` / `curl.exe` examples, or run the full automated suites while the server (local or Docker) is running:

```powershell
# PowerShell
.\test_api.ps1
```

```bash
# Git Bash / Linux / macOS
bash test_api.sh
```

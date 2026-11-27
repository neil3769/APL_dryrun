# Curl Test Documentation — Student & Course Enrollment REST API

Base URL: `http://127.0.0.1:5000` (service listens on `0.0.0.0:5000`).  
Swagger UI: `http://127.0.0.1:5000/docs`  
OpenAPI Spec: `http://127.0.0.1:5000/openapi.json` and `http://127.0.0.1:5000/openapi.yaml`

> **Windows PowerShell Note:** In PowerShell, `curl` is an alias for `Invoke-WebRequest`. Always invoke **`curl.exe`**, and pipe JSON containing spaces via stdin (`-d "@-"`) so PowerShell does not mangle quotes:
> ```powershell
> '{"student_number":"STU-1001","name":"Alice Rossi","email":"alice@university.edu","major":"Computer Science"}' | curl.exe -i -X POST -H "Content-Type: application/json" -d "@-" http://127.0.0.1:5000/api/student
> ```

---

## 1. HTTP Status Code Reference

| Status Code | Meaning | When Returned |
|---|---|---|
| `200 OK` | Request succeeded | `GET`, `PUT`, `PATCH` |
| `201 Created` | Resource created | `POST` to `/api/student`, `/api/course`, `/api/enrollment` (includes `Location` header) |
| `204 No Content` | Resource deleted | `DELETE` with empty response body |
| `400 Bad Request` | Invalid input | Malformed JSON, non-object JSON, Marshmallow validation error, invalid query parameter |
| `404 Not Found` | Resource missing | Unknown route, unknown ID, or unknown `student_id`/`course_id` in enrollment |
| `405 Method Not Allowed` | Verb not supported | E.g., `DELETE /api/health` (includes `Allow` header) |
| `409 Conflict` | Constraint / rule conflict | Duplicate `student_number`/`email`/`code`/enrollment, full course capacity, capacity reduced below active count, deleting student/course with enrollments |
| `415 Unsupported Media Type` | Missing JSON header | `POST`/`PUT`/`PATCH` without `Content-Type: application/json` |

---

## 2. Meta & Documentation Checks

### Health Check (`GET /api/health`) — `200 OK`
```bash
curl -i http://127.0.0.1:5000/api/health
```
PowerShell:
```powershell
curl.exe -i http://127.0.0.1:5000/api/health
```
Expected response:
```json
{
  "database": "sqlite",
  "status": "ok"
}
```

### OpenAPI Spec & Swagger UI (`GET /openapi.json`, `GET /docs/`) — `200 OK`
```bash
curl -i http://127.0.0.1:5000/openapi.json
curl -i http://127.0.0.1:5000/docs/
```

---

## 3. Student Endpoints (`/api/student`)

### Create Student (`POST /api/student`) — `201 Created`
```bash
curl -i -X POST http://127.0.0.1:5000/api/student \
  -H "Content-Type: application/json" \
  -d '{"student_number":"STU-1001","name":"Alice Rossi","email":"alice@university.edu","major":"Computer Science"}'
```
PowerShell:
```powershell
'{"student_number":"STU-1001","name":"Alice Rossi","email":"alice@university.edu","major":"Computer Science"}' |
  curl.exe -i -X POST -H "Content-Type: application/json" -d "@-" http://127.0.0.1:5000/api/student
```
Expected header & body (`201 Created`):
```http
Location: /api/student/1
```
```json
{
  "id": 1,
  "student_number": "STU-1001",
  "name": "Alice Rossi",
  "email": "alice@university.edu",
  "major": "Computer Science",
  "created_at": "2026-11-27T19:40:00+00:00"
}
```

### Duplicate Student (`POST /api/student`) — `409 Conflict`
```bash
curl -i -X POST http://127.0.0.1:5000/api/student \
  -H "Content-Type: application/json" \
  -d '{"student_number":"STU-9999","name":"Duplicate","email":"alice@university.edu","major":"CS"}'
```

### Marshmallow Validation Error (`POST /api/student`) — `400 Bad Request`
```bash
curl -i -X POST http://127.0.0.1:5000/api/student \
  -H "Content-Type: application/json" \
  -d '{"student_number":"S","name":"   ","email":"bad-email"}'
```
Expected body (`400 Bad Request`):
```json
{
  "error": "ValidationError",
  "message": "Invalid request data.",
  "details": {
    "email": ["Not a valid email address."],
    "major": ["Missing data for required field."],
    "name": ["Must be between 1 and 120 characters."],
    "student_number": ["Must be between 2 and 32 characters."]
  }
}
```

### Missing Content-Type (`POST /api/student`) — `415 Unsupported Media Type`
```bash
curl -i -X POST http://127.0.0.1:5000/api/student \
  -H "Content-Type: text/plain" \
  -d '{"student_number":"STU-1002","name":"Bob","email":"bob@university.edu","major":"Math"}'
```

### List / Filter / Get Student (`GET /api/student`, `GET /api/student/<id>`) — `200 OK` / `404 Not Found`
```bash
curl -i http://127.0.0.1:5000/api/student
curl -i "http://127.0.0.1:5000/api/student?major=computer"
curl -i http://127.0.0.1:5000/api/student/1
curl -i http://127.0.0.1:5000/api/student/99999
```

### Full Replace (`PUT /api/student/1`) — `200 OK`
```bash
curl -i -X PUT http://127.0.0.1:5000/api/student/1 \
  -H "Content-Type: application/json" \
  -d '{"student_number":"STU-1001","name":"Alice Rossi-Verdi","email":"alice@university.edu","major":"Distributed Systems"}'
```

### Partial Update (`PATCH /api/student/1`) — `200 OK`
```bash
curl -i -X PATCH http://127.0.0.1:5000/api/student/1 \
  -H "Content-Type: application/json" \
  -d '{"major":"Artificial Intelligence"}'
```

---

## 4. Course Endpoints (`/api/course`)

### Create Course (`POST /api/course`) — `201 Created`
```bash
curl -i -X POST http://127.0.0.1:5000/api/course \
  -H "Content-Type: application/json" \
  -d '{"code":"CS101","title":"Distributed Systems","credits":6,"capacity":1}'
```
PowerShell:
```powershell
'{"code":"CS101","title":"Distributed Systems","credits":6,"capacity":1}' |
  curl.exe -i -X POST -H "Content-Type: application/json" -d "@-" http://127.0.0.1:5000/api/course
```

### List / Filter Courses (`GET /api/course`) — `200 OK` / `400 Bad Request`
```bash
curl -i http://127.0.0.1:5000/api/course
curl -i "http://127.0.0.1:5000/api/course?code=cs&available=true"
curl -i "http://127.0.0.1:5000/api/course?available=invalid"
```

### Update Course (`PUT` / `PATCH /api/course/1`) — `200 OK` / `409 Conflict`
```bash
curl -i -X PATCH http://127.0.0.1:5000/api/course/1 \
  -H "Content-Type: application/json" \
  -d '{"capacity":20}'

curl -i -X PUT http://127.0.0.1:5000/api/course/1 \
  -H "Content-Type: application/json" \
  -d '{"code":"CS101","title":"Distributed Systems & Middleware","credits":6,"capacity":20}'
```

---

## 5. Enrollment Endpoints (`/api/enrollment`)

### Enroll Student in Course (`POST /api/enrollment`) — `201 Created` / `404` / `409`
```bash
# 201 Created
curl -i -X POST http://127.0.0.1:5000/api/enrollment \
  -H "Content-Type: application/json" \
  -d '{"student_id":1,"course_id":1}'

# 409 Conflict (duplicate enrollment or full course)
curl -i -X POST http://127.0.0.1:5000/api/enrollment \
  -H "Content-Type: application/json" \
  -d '{"student_id":1,"course_id":1}'

# 404 Not Found (missing student or course)
curl -i -X POST http://127.0.0.1:5000/api/enrollment \
  -H "Content-Type: application/json" \
  -d '{"student_id":99999,"course_id":1}'
```

### List & Filter Enrollments (`GET /api/enrollment`) — `200 OK`
```bash
curl -i "http://127.0.0.1:5000/api/enrollment?student_id=1&status=enrolled"
```

### Complete & Grade via `PATCH /api/enrollment/1` — `200 OK` / `400 Bad Request`
```bash
# 200 OK
curl -i -X PATCH http://127.0.0.1:5000/api/enrollment/1 \
  -H "Content-Type: application/json" \
  -d '{"status":"completed","grade":"A"}'

# 400 Bad Request (cannot assign grade unless status is 'completed')
curl -i -X PATCH http://127.0.0.1:5000/api/enrollment/1 \
  -H "Content-Type: application/json" \
  -d '{"status":"dropped"}'
```

### Full Replace via `PUT /api/enrollment/1` — `200 OK`
```bash
curl -i -X PUT http://127.0.0.1:5000/api/enrollment/1 \
  -H "Content-Type: application/json" \
  -d '{"student_id":1,"course_id":1,"status":"dropped","grade":null}'
```

### Foreign Key Restriction on Delete — `409 Conflict` then `204 No Content`
```bash
# 409 Conflict while enrollment 1 still references student 1
curl -i -X DELETE http://127.0.0.1:5000/api/student/1

# 204 No Content: delete enrollment first
curl -i -X DELETE http://127.0.0.1:5000/api/enrollment/1

# 204 No Content: now student 1 and course 1 can be deleted
curl -i -X DELETE http://127.0.0.1:5000/api/student/1
curl -i -X DELETE http://127.0.0.1:5000/api/course/1
```

---

## 6. Automated Test Runners

- **Git Bash / Linux / macOS:**
  ```bash
  bash test_api.sh
  ```
- **Windows PowerShell:**
  ```powershell
  .\test_api.ps1
  ```

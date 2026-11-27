#!/usr/bin/env bash
# End-to-end curl test suite for the Student & Course Enrollment REST API.
# Usage: ./test_api.sh [BASE_URL]

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:5000}"
PASSED=0
FAILED=0

PY_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import json' >/dev/null 2>&1; then
    PY_BIN="$candidate"
    break
  fi
done
if [[ -z "$PY_BIN" ]]; then
  echo "Error: a working python3 or python interpreter is required to parse JSON responses." >&2
  exit 1
fi

LAST_HEADERS=""
LAST_BODY=""

call_api() {
  local label="$1"
  local method="$2"
  local path="$3"
  local expected_status="$4"
  local body="${5:-}"
  local content_type="${6:-application/json}"
  local require_location="${7:-false}"

  local hdr_file body_file status location
  hdr_file="$(mktemp)"
  body_file="$(mktemp)"

  local curl_args=(-sS -D "$hdr_file" -o "$body_file" -w "%{http_code}" -X "$method")
  if [[ -n "$body" ]]; then
    if [[ "$content_type" != "none" ]]; then
      curl_args+=(-H "Content-Type: $content_type")
    fi
    curl_args+=(--data-raw "$body")
  fi

  status="$(curl "${curl_args[@]}" "${BASE_URL}${path}")"
  LAST_HEADERS="$(cat "$hdr_file")"
  LAST_BODY="$(cat "$body_file")"
  rm -f "$hdr_file" "$body_file"

  location="$(printf '%s\n' "$LAST_HEADERS" | grep -i '^Location:' | awk '{print $2}' | tr -d '\r' || true)"

  local ok=true
  if [[ "$status" -ne "$expected_status" ]]; then
    ok=false
  fi
  if [[ "$require_location" == "true" && -z "$location" ]]; then
    ok=false
  fi

  if [[ "$ok" == "true" ]]; then
    PASSED=$((PASSED + 1))
    if [[ -n "$location" ]]; then
      echo "[PASS] $label -> $status (Location: $location)"
    else
      echo "[PASS] $label -> $status"
    fi
  else
    FAILED=$((FAILED + 1))
    echo "[FAIL] $label -> got $status (expected $expected_status)"
    echo "       Body: $LAST_BODY"
  fi
}

assert_json_expr() {
  local label="$1"
  local expr="$2"
  if printf '%s' "$LAST_BODY" | "$PY_BIN" -c "import json, sys; data = json.load(sys.stdin); assert ($expr), f'Assertion failed on {data!r}'"; then
    PASSED=$((PASSED + 1))
    echo "[PASS] $label"
  else
    FAILED=$((FAILED + 1))
    echo "[FAIL] $label -> assertion failed"
    echo "       Body: $LAST_BODY"
  fi
}

assert_body_contains() {
  local label="$1"
  local needle="$2"
  if printf '%s' "$LAST_BODY" | grep -q "$needle"; then
    PASSED=$((PASSED + 1))
    echo "[PASS] $label"
  else
    FAILED=$((FAILED + 1))
    echo "[FAIL] $label -> expected '$needle' in body"
  fi
}

extract_id() {
  printf '%s' "$LAST_BODY" | "$PY_BIN" -c 'import json, sys; print(json.load(sys.stdin)["id"])'
}

echo "=== Testing Student & Course Enrollment REST API at $BASE_URL ==="

# 1. Meta, Health, OpenAPI & Swagger UI
call_api "GET / (API overview)" "GET" "/" 200
assert_json_expr "GET / returns docs='/docs' and singular endpoints" \
  "data['docs'] == '/docs' and data['endpoints'] == ['/api/student', '/api/course', '/api/enrollment']"

call_api "GET /api/health" "GET" "/api/health" 200
assert_json_expr "Health status is ok" "data == {'status': 'ok', 'database': 'sqlite'}"

call_api "GET /openapi.json" "GET" "/openapi.json" 200
assert_json_expr "OpenAPI spec uses 3.0.3 and singular paths" \
  "data['openapi'] == '3.0.3' and '/api/student' in data['paths'] and '/api/course' in data['paths'] and '/api/enrollment' in data['paths'] and 'Student' in data['components']['schemas']"

call_api "GET /openapi.yaml" "GET" "/openapi.yaml" 200
assert_body_contains "OpenAPI YAML contains openapi: 3.0.3" "openapi: 3.0.3"

call_api "GET /docs/ (Swagger UI)" "GET" "/docs/" 200
assert_body_contains "Swagger UI page renders SwaggerUIBundle" "SwaggerUIBundle"

# 2. HTTP protocol & error envelopes (404, 405, 415)
call_api "DELETE /api/health -> 405" "DELETE" "/api/health" 405
assert_json_expr "405 returns JSON error" "data['error'] == 'MethodNotAllowed'"

call_api "GET /api/unknown -> 404" "GET" "/api/unknown" 404
assert_json_expr "404 returns JSON error" "data['error'] == 'NotFound'"

call_api "POST /api/student without JSON Content-Type -> 415" "POST" "/api/student" 415 '{"student_number":"STU-0","name":"Test","email":"t@u.edu","major":"CS"}' "text/plain"
assert_json_expr "415 returns UnsupportedMediaType JSON" "data['error'] == 'UnsupportedMediaType'"

# 3. Student CRUD & Validation
call_api "GET /api/student (initial list)" "GET" "/api/student" 200
assert_json_expr "GET /api/student returns list" "isinstance(data, list)"

call_api "POST /api/student (Alice)" "POST" "/api/student" 201 \
  '{"student_number":"stu-1001","name":"  Alice Rossi  ","email":"ALICE@UNIVERSITY.EDU","major":"Computer Science"}' \
  "application/json" "true"
assert_json_expr "Student normalized fields and timestamps" \
  "data['student_number'] == 'STU-1001' and data['name'] == 'Alice Rossi' and data['email'] == 'alice@university.edu'"
STUDENT1_ID="$(extract_id)"

call_api "POST /api/student (Bob)" "POST" "/api/student" 201 \
  '{"student_number":"STU-1002","name":"Bob Bianchi","email":"bob@university.edu","major":"Mathematics"}' \
  "application/json" "true"
STUDENT2_ID="$(extract_id)"

call_api "POST /api/student (duplicate email -> 409)" "POST" "/api/student" 409 \
  '{"student_number":"STU-9999","name":"Dup","email":"alice@university.edu","major":"CS"}'

call_api "POST /api/student (duplicate student_number -> 409)" "POST" "/api/student" 409 \
  '{"student_number":"STU-1001","name":"Dup","email":"dup@university.edu","major":"CS"}'

call_api "POST /api/student (bad email + missing major -> 400)" "POST" "/api/student" 400 \
  '{"student_number":"STU-1003","name":"Bad","email":"not-an-email"}'
assert_json_expr "400 ValidationError includes details" \
  "data['error'] == 'ValidationError' and 'email' in data['details'] and 'major' in data['details']"

call_api "POST /api/student (malformed JSON -> 400)" "POST" "/api/student" 400 '{bad json'

call_api "GET /api/student/$STUDENT1_ID" "GET" "/api/student/$STUDENT1_ID" 200
call_api "GET /api/student/99999 -> 404" "GET" "/api/student/99999" 404
call_api "GET /api/student?major=computer" "GET" "/api/student?major=computer" 200
assert_json_expr "Filter by major includes Alice" "any(s['id'] == $STUDENT1_ID for s in data)"

call_api "PUT /api/student/$STUDENT2_ID (full replace)" "PUT" "/api/student/$STUDENT2_ID" 200 \
  '{"student_number":"STU-1002","name":"Roberto Bianchi","email":"bob@university.edu","major":"Applied Math"}'
assert_json_expr "PUT updated Bob's name" "data['name'] == 'Roberto Bianchi'"

call_api "PUT /api/student/$STUDENT2_ID (missing field -> 400)" "PUT" "/api/student/$STUDENT2_ID" 400 \
  '{"name":"Incomplete"}'

call_api "PATCH /api/student/$STUDENT2_ID (partial major)" "PATCH" "/api/student/$STUDENT2_ID" 200 \
  '{"major":"Data Science"}'
assert_json_expr "PATCH updated major while keeping name" "data['major'] == 'Data Science' and data['name'] == 'Roberto Bianchi'"

call_api "PATCH /api/student/$STUDENT2_ID (empty {} -> 400)" "PATCH" "/api/student/$STUDENT2_ID" 400 '{}'
call_api "PATCH /api/student/$STUDENT2_ID (duplicate email -> 409)" "PATCH" "/api/student/$STUDENT2_ID" 409 \
  '{"email":"alice@university.edu"}'

# 4. Course CRUD & Validation
call_api "POST /api/course (CS101 capacity=1)" "POST" "/api/course" 201 \
  '{"code":"cs101","title":"Distributed Systems","credits":6,"capacity":1}' \
  "application/json" "true"
assert_json_expr "Course normalized code and enrolled_count=0" \
  "data['code'] == 'CS101' and data['enrolled_count'] == 0"
COURSE1_ID="$(extract_id)"

call_api "POST /api/course (MATH201 capacity=2)" "POST" "/api/course" 201 \
  '{"code":"MATH201","title":"Linear Algebra","credits":6,"capacity":2}' \
  "application/json" "true"
COURSE2_ID="$(extract_id)"

call_api "POST /api/course (duplicate code -> 409)" "POST" "/api/course" 409 \
  '{"code":"CS101","title":"Dup","credits":3,"capacity":10}'

call_api "POST /api/course (non-int credits bool -> 400)" "POST" "/api/course" 400 \
  '{"code":"CS999","title":"Bad Credits","credits":true,"capacity":10}'

call_api "GET /api/course?available=invalid -> 400" "GET" "/api/course?available=invalid" 400
call_api "GET /api/course/$COURSE1_ID" "GET" "/api/course/$COURSE1_ID" 200
call_api "GET /api/course/99999 -> 404" "GET" "/api/course/99999" 404

# 5. Enrollment CRUD, Foreign Keys, Capacity & Grade Rules
call_api "POST /api/enrollment (Alice -> CS101)" "POST" "/api/enrollment" 201 \
  "{\"student_id\":$STUDENT1_ID,\"course_id\":$COURSE1_ID}" \
  "application/json" "true"
assert_json_expr "Enrollment defaults to status='enrolled', grade=None" \
  "data['status'] == 'enrolled' and data['grade'] is None"
ENROLL1_ID="$(extract_id)"

call_api "GET /api/course/$COURSE1_ID (enrolled_count=1)" "GET" "/api/course/$COURSE1_ID" 200
assert_json_expr "Course CS101 enrolled_count is 1" "data['enrolled_count'] == 1"

call_api "GET /api/course?available=false" "GET" "/api/course?available=false" 200
assert_json_expr "Full courses filter includes CS101" "any(c['id'] == $COURSE1_ID for c in data)"

call_api "POST /api/enrollment (duplicate Alice -> CS101 -> 409)" "POST" "/api/enrollment" 409 \
  "{\"student_id\":$STUDENT1_ID,\"course_id\":$COURSE1_ID}"

call_api "POST /api/enrollment (Bob -> full CS101 -> 409)" "POST" "/api/enrollment" 409 \
  "{\"student_id\":$STUDENT2_ID,\"course_id\":$COURSE1_ID}"

call_api "POST /api/enrollment (unknown student -> 404)" "POST" "/api/enrollment" 404 \
  "{\"student_id\":99999,\"course_id\":$COURSE2_ID}"

call_api "POST /api/enrollment (unknown course -> 404)" "POST" "/api/enrollment" 404 \
  "{\"student_id\":$STUDENT1_ID,\"course_id\":99999}"

call_api "POST /api/enrollment (grade while enrolled -> 400)" "POST" "/api/enrollment" 400 \
  "{\"student_id\":$STUDENT2_ID,\"course_id\":$COURSE2_ID,\"status\":\"enrolled\",\"grade\":\"A\"}"

call_api "POST /api/enrollment (Alice -> MATH201)" "POST" "/api/enrollment" 201 \
  "{\"student_id\":$STUDENT1_ID,\"course_id\":$COURSE2_ID}" \
  "application/json" "true"
ENROLL2_ID="$(extract_id)"

call_api "POST /api/enrollment (Bob -> MATH201)" "POST" "/api/enrollment" 201 \
  "{\"student_id\":$STUDENT2_ID,\"course_id\":$COURSE2_ID}" \
  "application/json" "true"
ENROLL3_ID="$(extract_id)"

call_api "PATCH /api/course/$COURSE2_ID (capacity < enrolled_count -> 409)" "PATCH" "/api/course/$COURSE2_ID" 409 \
  '{"capacity":1}'

call_api "PATCH /api/course/$COURSE2_ID (increase capacity to 25 -> 200)" "PATCH" "/api/course/$COURSE2_ID" 200 \
  '{"capacity":25}'

call_api "PUT /api/course/$COURSE2_ID (full replace -> 200)" "PUT" "/api/course/$COURSE2_ID" 200 \
  '{"code":"MATH201","title":"Linear Algebra II","credits":6,"capacity":25}'

call_api "DELETE /api/student/$STUDENT1_ID (has enrollments -> 409)" "DELETE" "/api/student/$STUDENT1_ID" 409
call_api "DELETE /api/course/$COURSE1_ID (has enrollments -> 409)" "DELETE" "/api/course/$COURSE1_ID" 409

call_api "PATCH /api/enrollment/$ENROLL1_ID (complete with grade A -> 200)" "PATCH" "/api/enrollment/$ENROLL1_ID" 200 \
  '{"status":"completed","grade":"A"}'
assert_json_expr "Enrollment completed with grade A" \
  "data['status'] == 'completed' and data['grade'] == 'A'"

call_api "PATCH /api/enrollment/$ENROLL1_ID (drop while grade remains -> 400)" "PATCH" "/api/enrollment/$ENROLL1_ID" 400 \
  '{"status":"dropped"}'

call_api "PUT /api/enrollment/$ENROLL1_ID (replace as dropped, grade null -> 200)" "PUT" "/api/enrollment/$ENROLL1_ID" 200 \
  "{\"student_id\":$STUDENT1_ID,\"course_id\":$COURSE1_ID,\"status\":\"dropped\",\"grade\":null}"
assert_json_expr "PUT cleared grade and set status dropped" \
  "data['status'] == 'dropped' and data['grade'] is None"

call_api "GET /api/enrollment?student_id=$STUDENT1_ID&status=dropped" "GET" "/api/enrollment?student_id=$STUDENT1_ID&status=dropped" 200
assert_json_expr "Filtered enrollment list returns ENROLL1_ID" "any(e['id'] == $ENROLL1_ID for e in data)"

call_api "GET /api/enrollment?student_id=not-an-int -> 400" "GET" "/api/enrollment?student_id=not-an-int" 400
call_api "GET /api/enrollment/$ENROLL1_ID" "GET" "/api/enrollment/$ENROLL1_ID" 200
call_api "GET /api/enrollment/99999 -> 404" "GET" "/api/enrollment/99999" 404

# 6. Delete cleanup (204 -> 404)
call_api "DELETE /api/enrollment/$ENROLL1_ID -> 204" "DELETE" "/api/enrollment/$ENROLL1_ID" 204
call_api "DELETE /api/enrollment/$ENROLL1_ID again -> 404" "DELETE" "/api/enrollment/$ENROLL1_ID" 404
call_api "DELETE /api/enrollment/$ENROLL2_ID -> 204" "DELETE" "/api/enrollment/$ENROLL2_ID" 204
call_api "DELETE /api/enrollment/$ENROLL3_ID -> 204" "DELETE" "/api/enrollment/$ENROLL3_ID" 204

call_api "DELETE /api/student/$STUDENT1_ID -> 204" "DELETE" "/api/student/$STUDENT1_ID" 204
call_api "DELETE /api/student/$STUDENT2_ID -> 204" "DELETE" "/api/student/$STUDENT2_ID" 204
call_api "GET /api/student/$STUDENT1_ID after delete -> 404" "GET" "/api/student/$STUDENT1_ID" 404

call_api "DELETE /api/course/$COURSE1_ID -> 204" "DELETE" "/api/course/$COURSE1_ID" 204
call_api "DELETE /api/course/$COURSE2_ID -> 204" "DELETE" "/api/course/$COURSE2_ID" 204
call_api "GET /api/course/$COURSE1_ID after delete -> 404" "GET" "/api/course/$COURSE1_ID" 404

echo ""
echo "=== Summary: $PASSED passed, $FAILED failed ==="
if [[ "$FAILED" -ne 0 ]]; then
  exit 1
fi

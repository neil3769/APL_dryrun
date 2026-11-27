<#
.SYNOPSIS
  End-to-end curl.exe test suite for the Student & Course Enrollment REST API.
.EXAMPLE
  .\test_api.ps1
  .\test_api.ps1 -BaseUrl "http://127.0.0.1:5000"
#>
param(
    [string]$BaseUrl = "http://127.0.0.1:5000"
)

$ErrorActionPreference = "Stop"
$script:Passed = 0
$script:Failed = 0

function Invoke-Api {
    param(
        [string]$Label,
        [string]$Method,
        [string]$Path,
        [int]$ExpectedStatus,
        [string]$Body = $null,
        [string]$ContentType = "application/json",
        [switch]$RequireLocation
    )

    $hdrFile = [System.IO.Path]::GetTempFileName()
    $bodyFile = [System.IO.Path]::GetTempFileName()
    $reqFile = $null
    try {
        $argsList = @("-sS", "-D", $hdrFile, "-o", $bodyFile, "-w", "%{http_code}", "-X", $Method)
        if (-not [string]::IsNullOrEmpty($Body)) {
            $reqFile = [System.IO.Path]::GetTempFileName()
            [System.IO.File]::WriteAllText($reqFile, $Body, (New-Object System.Text.UTF8Encoding($false)))
            if ($ContentType -ne "none") {
                $argsList += @("-H", "Content-Type: $ContentType")
            }
            $argsList += @("--data-binary", "@$reqFile")
        }
        $argsList += "$BaseUrl$Path"

        $status = [int](& curl.exe @argsList)
        $headers = Get-Content -Raw $hdrFile
        $respBody = if ((Get-Item $bodyFile).Length -gt 0) { Get-Content -Raw $bodyFile } else { "" }

        $location = $null
        if ($headers -match "(?im)^Location:\s*(\S+)") {
            $location = $Matches[1].Trim()
        }

        $ok = ($status -eq $ExpectedStatus)
        if ($RequireLocation -and [string]::IsNullOrWhiteSpace($location)) {
            $ok = $false
        }

        if ($ok) {
            $script:Passed++
            $locNote = if ($location) { " | Location: $location" } else { "" }
            Write-Host "[PASS] $Label -> $status$locNote" -ForegroundColor Green
        } else {
            $script:Failed++
            Write-Host "[FAIL] $Label -> got $status (expected $ExpectedStatus)" -ForegroundColor Red
            Write-Host "       Body: $respBody" -ForegroundColor Yellow
        }

        $parsed = $null
        if ($respBody -and ($respBody.TrimStart().StartsWith("{") -or $respBody.TrimStart().StartsWith("["))) {
            $parsed = $respBody | ConvertFrom-Json
        }

        return [PSCustomObject]@{
            Status   = $status
            Location = $location
            Body     = $respBody
            Json     = $parsed
        }
    } finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $hdrFile, $bodyFile
        if ($reqFile) { Remove-Item -Force -ErrorAction SilentlyContinue $reqFile }
    }
}

function Assert-Check {
    param([string]$Label, [bool]$Condition, [string]$Detail = "")
    if ($Condition) {
        $script:Passed++
        Write-Host "[PASS] $Label" -ForegroundColor Green
    } else {
        $script:Failed++
        Write-Host "[FAIL] $Label $Detail" -ForegroundColor Red
    }
}

Write-Host "=== Testing Student & Course Enrollment REST API at $BaseUrl ===" -ForegroundColor Cyan

# 1. Meta, Health, OpenAPI & Swagger UI
$root = Invoke-Api "GET / (API overview)" "GET" "/" 200
Assert-Check "GET / returns docs='/docs'" ($root.Json.docs -eq "/docs")

$health = Invoke-Api "GET /api/health" "GET" "/api/health" 200
Assert-Check "Health status is ok" ($health.Json.status -eq "ok" -and $health.Json.database -eq "sqlite")

$spec = Invoke-Api "GET /openapi.json" "GET" "/openapi.json" 200
Assert-Check "OpenAPI 3.0.3 singular paths present" (
    $spec.Json.openapi -eq "3.0.3" -and
    $null -ne $spec.Json.paths."/api/student" -and
    $null -ne $spec.Json.paths."/api/course" -and
    $null -ne $spec.Json.paths."/api/enrollment"
)

$yamlResp = Invoke-Api "GET /openapi.yaml" "GET" "/openapi.yaml" 200
Assert-Check "OpenAPI YAML includes openapi: 3.0.3" ($yamlResp.Body -match "openapi:\s*3\.0\.3")

$docs = Invoke-Api "GET /docs/ (Swagger UI)" "GET" "/docs/" 200
Assert-Check "Swagger UI contains SwaggerUIBundle" ($docs.Body -match "SwaggerUIBundle")

# 2. HTTP protocol errors (404, 405, 415)
Invoke-Api "DELETE /api/health -> 405" "DELETE" "/api/health" 405 | Out-Null
Invoke-Api "GET /api/unknown -> 404" "GET" "/api/unknown" 404 | Out-Null
Invoke-Api "POST /api/student without application/json -> 415" "POST" "/api/student" 415 `
    '{"student_number":"STU-0","name":"Test","email":"t@u.edu","major":"CS"}' "text/plain" | Out-Null

# 3. Student CRUD & Validation
Invoke-Api "GET /api/student" "GET" "/api/student" 200 | Out-Null

$s1 = Invoke-Api "POST /api/student (Alice)" "POST" "/api/student" 201 `
    '{"student_number":"stu-1001","name":"  Alice Rossi  ","email":"ALICE@UNIVERSITY.EDU","major":"Computer Science"}' `
    -RequireLocation
$student1Id = $s1.Json.id
Assert-Check "Student normalized fields" (
    $s1.Json.student_number -eq "STU-1001" -and
    $s1.Json.name -eq "Alice Rossi" -and
    $s1.Json.email -eq "alice@university.edu"
)

$s2 = Invoke-Api "POST /api/student (Bob)" "POST" "/api/student" 201 `
    '{"student_number":"STU-1002","name":"Bob Bianchi","email":"bob@university.edu","major":"Mathematics"}' `
    -RequireLocation
$student2Id = $s2.Json.id

Invoke-Api "POST /api/student (duplicate email -> 409)" "POST" "/api/student" 409 `
    '{"student_number":"STU-9999","name":"Dup","email":"alice@university.edu","major":"CS"}' | Out-Null
Invoke-Api "POST /api/student (duplicate student_number -> 409)" "POST" "/api/student" 409 `
    '{"student_number":"STU-1001","name":"Dup","email":"dup@university.edu","major":"CS"}' | Out-Null
Invoke-Api "POST /api/student (validation error -> 400)" "POST" "/api/student" 400 `
    '{"student_number":"STU-1003","name":"Bad","email":"not-an-email"}' | Out-Null
Invoke-Api "POST /api/student (malformed JSON -> 400)" "POST" "/api/student" 400 '{bad json' | Out-Null

Invoke-Api "GET /api/student/$student1Id" "GET" "/api/student/$student1Id" 200 | Out-Null
Invoke-Api "GET /api/student/99999 -> 404" "GET" "/api/student/99999" 404 | Out-Null
Invoke-Api "GET /api/student?major=computer" "GET" "/api/student?major=computer" 200 | Out-Null

Invoke-Api "PUT /api/student/$student2Id" "PUT" "/api/student/$student2Id" 200 `
    '{"student_number":"STU-1002","name":"Roberto Bianchi","email":"bob@university.edu","major":"Applied Math"}' | Out-Null
Invoke-Api "PUT /api/student/$student2Id (incomplete -> 400)" "PUT" "/api/student/$student2Id" 400 `
    '{"name":"Incomplete"}' | Out-Null

$s2Patch = Invoke-Api "PATCH /api/student/$student2Id" "PATCH" "/api/student/$student2Id" 200 `
    '{"major":"Data Science"}'
Assert-Check "PATCH updated major while preserving name" ($s2Patch.Json.major -eq "Data Science" -and $s2Patch.Json.name -eq "Roberto Bianchi")
Invoke-Api "PATCH /api/student/$student2Id (empty {} -> 400)" "PATCH" "/api/student/$student2Id" 400 '{}' | Out-Null
Invoke-Api "PATCH /api/student/$student2Id (duplicate email -> 409)" "PATCH" "/api/student/$student2Id" 409 `
    '{"email":"alice@university.edu"}' | Out-Null

# 4. Course CRUD & Validation
$c1 = Invoke-Api "POST /api/course (CS101 capacity=1)" "POST" "/api/course" 201 `
    '{"code":"cs101","title":"Distributed Systems","credits":6,"capacity":1}' -RequireLocation
$course1Id = $c1.Json.id
Assert-Check "Course normalized code" ($c1.Json.code -eq "CS101" -and $c1.Json.enrolled_count -eq 0)

$c2 = Invoke-Api "POST /api/course (MATH201 capacity=2)" "POST" "/api/course" 201 `
    '{"code":"MATH201","title":"Linear Algebra","credits":6,"capacity":2}' -RequireLocation
$course2Id = $c2.Json.id

Invoke-Api "POST /api/course (duplicate code -> 409)" "POST" "/api/course" 409 `
    '{"code":"CS101","title":"Dup","credits":3,"capacity":10}' | Out-Null
Invoke-Api "POST /api/course (bool credits -> 400)" "POST" "/api/course" 400 `
    '{"code":"CS999","title":"Bad Credits","credits":true,"capacity":10}' | Out-Null
Invoke-Api "GET /api/course?available=invalid -> 400" "GET" "/api/course?available=invalid" 400 | Out-Null
Invoke-Api "GET /api/course/$course1Id" "GET" "/api/course/$course1Id" 200 | Out-Null
Invoke-Api "GET /api/course/99999 -> 404" "GET" "/api/course/99999" 404 | Out-Null

# 5. Enrollment CRUD, Foreign Keys, Capacity & Grade Rules
$e1 = Invoke-Api "POST /api/enrollment (Alice -> CS101)" "POST" "/api/enrollment" 201 `
    "{`"student_id`":$student1Id,`"course_id`":$course1Id}" -RequireLocation
$enroll1Id = $e1.Json.id

$c1Check = Invoke-Api "GET /api/course/$course1Id (enrolled_count=1)" "GET" "/api/course/$course1Id" 200
Assert-Check "CS101 enrolled_count is 1" ($c1Check.Json.enrolled_count -eq 1)
Invoke-Api "GET /api/course?available=false" "GET" "/api/course?available=false" 200 | Out-Null

Invoke-Api "POST /api/enrollment (duplicate -> 409)" "POST" "/api/enrollment" 409 `
    "{`"student_id`":$student1Id,`"course_id`":$course1Id}" | Out-Null
Invoke-Api "POST /api/enrollment (full course -> 409)" "POST" "/api/enrollment" 409 `
    "{`"student_id`":$student2Id,`"course_id`":$course1Id}" | Out-Null
Invoke-Api "POST /api/enrollment (missing student -> 404)" "POST" "/api/enrollment" 404 `
    "{`"student_id`":99999,`"course_id`":$course2Id}" | Out-Null
Invoke-Api "POST /api/enrollment (missing course -> 404)" "POST" "/api/enrollment" 404 `
    "{`"student_id`":$student1Id,`"course_id`":99999}" | Out-Null
Invoke-Api "POST /api/enrollment (grade while enrolled -> 400)" "POST" "/api/enrollment" 400 `
    "{`"student_id`":$student2Id,`"course_id`":$course2Id,`"status`":`"enrolled`",`"grade`":`"A`"}" | Out-Null

$e2 = Invoke-Api "POST /api/enrollment (Alice -> MATH201)" "POST" "/api/enrollment" 201 `
    "{`"student_id`":$student1Id,`"course_id`":$course2Id}" -RequireLocation
$enroll2Id = $e2.Json.id
$e3 = Invoke-Api "POST /api/enrollment (Bob -> MATH201)" "POST" "/api/enrollment" 201 `
    "{`"student_id`":$student2Id,`"course_id`":$course2Id}" -RequireLocation
$enroll3Id = $e3.Json.id

Invoke-Api "PATCH /api/course/$course2Id (capacity < enrolled_count -> 409)" "PATCH" "/api/course/$course2Id" 409 '{"capacity":1}' | Out-Null
Invoke-Api "PATCH /api/course/$course2Id (capacity=25 -> 200)" "PATCH" "/api/course/$course2Id" 200 '{"capacity":25}' | Out-Null
Invoke-Api "PUT /api/course/$course2Id" "PUT" "/api/course/$course2Id" 200 `
    '{"code":"MATH201","title":"Linear Algebra II","credits":6,"capacity":25}' | Out-Null

Invoke-Api "DELETE /api/student/$student1Id (with enrollment -> 409)" "DELETE" "/api/student/$student1Id" 409 | Out-Null
Invoke-Api "DELETE /api/course/$course1Id (with enrollment -> 409)" "DELETE" "/api/course/$course1Id" 409 | Out-Null

Invoke-Api "PATCH /api/enrollment/$enroll1Id (completed + grade A)" "PATCH" "/api/enrollment/$enroll1Id" 200 `
    '{"status":"completed","grade":"A"}' | Out-Null
Invoke-Api "PATCH /api/enrollment/$enroll1Id (drop with grade still set -> 400)" "PATCH" "/api/enrollment/$enroll1Id" 400 `
    '{"status":"dropped"}' | Out-Null
Invoke-Api "PUT /api/enrollment/$enroll1Id (dropped, grade null)" "PUT" "/api/enrollment/$enroll1Id" 200 `
    "{`"student_id`":$student1Id,`"course_id`":$course1Id,`"status`":`"dropped`",`"grade`":null}" | Out-Null

Invoke-Api "GET /api/enrollment?student_id=$student1Id&status=dropped" "GET" "/api/enrollment?student_id=$student1Id&status=dropped" 200 | Out-Null
Invoke-Api "GET /api/enrollment?student_id=bad -> 400" "GET" "/api/enrollment?student_id=bad" 400 | Out-Null
Invoke-Api "GET /api/enrollment/$enroll1Id" "GET" "/api/enrollment/$enroll1Id" 200 | Out-Null
Invoke-Api "GET /api/enrollment/99999 -> 404" "GET" "/api/enrollment/99999" 404 | Out-Null

# 6. Cleanup (204 -> 404)
Invoke-Api "DELETE /api/enrollment/$enroll1Id -> 204" "DELETE" "/api/enrollment/$enroll1Id" 204 | Out-Null
Invoke-Api "DELETE /api/enrollment/$enroll1Id again -> 404" "DELETE" "/api/enrollment/$enroll1Id" 404 | Out-Null
Invoke-Api "DELETE /api/enrollment/$enroll2Id -> 204" "DELETE" "/api/enrollment/$enroll2Id" 204 | Out-Null
Invoke-Api "DELETE /api/enrollment/$enroll3Id -> 204" "DELETE" "/api/enrollment/$enroll3Id" 204 | Out-Null

Invoke-Api "DELETE /api/student/$student1Id -> 204" "DELETE" "/api/student/$student1Id" 204 | Out-Null
Invoke-Api "DELETE /api/student/$student2Id -> 204" "DELETE" "/api/student/$student2Id" 204 | Out-Null
Invoke-Api "GET /api/student/$student1Id after delete -> 404" "GET" "/api/student/$student1Id" 404 | Out-Null

Invoke-Api "DELETE /api/course/$course1Id -> 204" "DELETE" "/api/course/$course1Id" 204 | Out-Null
Invoke-Api "DELETE /api/course/$course2Id -> 204" "DELETE" "/api/course/$course2Id" 204 | Out-Null
Invoke-Api "GET /api/course/$course1Id after delete -> 404" "GET" "/api/course/$course1Id" 404 | Out-Null

Write-Host ""
Write-Host "=== Summary: $script:Passed passed, $script:Failed failed ===" -ForegroundColor Cyan
if ($script:Failed -ne 0) {
    exit 1
}

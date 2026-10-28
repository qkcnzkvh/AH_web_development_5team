# 환자 관리 및 진료기록 API 통합 설계 명세서

## 1. 개요

### 1.1 목적

의료진이 등록한 환자 정보와 진료기록(흉부 X-Ray 이미지 포함)을 등록·조회·수정·삭제하는 API를 설계한다. 공통 규칙은 User API 통합 설계 명세서(`docs/4일차_USER_API_설계.md`)를 따른다.

### 1.2 담당 분배

| 담당자 | 요구사항 |
|---|---|
| A | 환자 정보 등록 `REQ-PTNT-001`, 수정 `REQ-PTNT-004`, 삭제 `REQ-PTNT-005` |
| B | 환자 목록 조회 `REQ-PTNT-002`, 환자 정보 상세 조회 `REQ-PTNT-003` |
| C | 진료기록 등록 `REQ-MDR-001`, 진료기록 목록 조회 `REQ-MDR-002` |
| D | 진료기록 상세 조회 `REQ-MDR-003`, API 성능 `NFR-PTNT-001`, `NFR-MDR-001` |

### 1.3 관련 요구사항

- `REQ-PTNT-001` 환자 정보 등록 / `REQ-PTNT-002` 환자 목록 조회 / `REQ-PTNT-003` 환자 정보 상세 조회
- `REQ-PTNT-004` 환자 정보 수정 / `REQ-PTNT-005` 환자 정보 삭제
- `REQ-MDR-001` 진료기록 등록 / `REQ-MDR-002` 진료기록 목록 조회 / `REQ-MDR-003` 진료기록 상세 조회
- `NFR-PTNT-001`, `NFR-MDR-001` API 성능 (3초 이내 응답)

## 2. 공통 규칙

| 항목 | 규칙 |
|---|---|
| Base URL | `/api/v1` |
| 라우터 Prefix | 라우터 파일에는 `/patients`, `/medical-records` 등만 작성하고, `/api/v1`은 `main.py`에서 라우터 등록 시 공통 적용 |
| 데이터 형식 | `application/json` (진료기록 등록은 `multipart/form-data`) |
| 인증 방식 | `Authorization: Bearer <access_token>` (User API에서 발급한 Access Token) |
| 인증·인가 | 공통 `app/core/security.py`의 `get_current_user`, `require_staff`, `require_medical_staff` 사용 (JWT 검증 로직을 별도로 구현하지 않음) |
| 인가 | `PENDING`은 마이페이지 외 접근 불가 → 환자·진료기록 API는 `STAFF`, `ADMIN`만 허용 (`require_staff`) |
| 등록 권한 | 환자 등록과 진료기록 등록은 `STAFF`, `ADMIN` + `department = MEDICAL`만 허용 (`require_medical_staff`) |
| 필드명 규칙 | 요청·응답 필드는 snake_case |
| 전화번호 저장 및 응답 | 공통 함수 `normalize_phone()`(`app/core/validators.py`)으로 정규화하여 숫자만 저장·응답 (User API와 동일) |
| 날짜·시간 | DB는 UTC로 저장한다. 응답의 `created_at`, `updated_at`은 UTC 기준 ISO 8601 형식(예: `2026-10-27T03:03:00Z`)으로 반환하며, `Z` 부착은 응답 스키마의 공통 datetime 직렬화로 처리하여 모든 파트가 같이 사용한다. `created_at`은 등록 시각, `updated_at`은 수정 시각으로 갱신된다(`TimestampMixin`의 `onupdate=func.now()`, 마이그레이션 불필요). |
| 응답 시간 | 모든 Patient·MedicalRecord API 3초 이내 응답 목표 |

각 엔드포인트는 별도 표기가 없다면 Base URL을 제외한 상대 경로로 작성한다. 예를 들어 `/patients`의 실제 경로는 `/api/v1/patients`이다.

공통 모듈(`security.py`)의 의존성 함수는 다음과 같이 사용한다.

| 의존성 | 허용 대상 | 사용할 API |
|---|---|---|
| `require_staff` | `STAFF`, `ADMIN` (`PENDING`은 403) | 환자 목록·상세·수정·삭제, 진료기록 목록·상세 |
| `require_medical_staff` | `STAFF`, `ADMIN` 중 `department = MEDICAL` | 환자 등록, 진료기록 등록 |

### 2.1 Enum 값

**성별 (`gender`)**

| 값 | 의미 |
|---|---|
| `M` | 남성 |
| `F` | 여성 |

- 조회 필터와 환자 등록에서는 프론트엔드가 보내는 `male`, `female`도 허용하여 `M`, `F`로 변환한다.
- 응답의 `gender`는 항상 `M`, `F`이다. 프론트엔드의 성별 표시 비교 코드(`=== 'male'`)는 `=== 'M'`으로 수정한다.

**권한 검사에 사용하는 회원 정보**

| 구분 | 값 | 사용처 |
|---|---|---|
| 회원 권한 (`role`) | `PENDING`, `STAFF`, `ADMIN` | 환자·진료기록 API 접근 가능 여부 (`STAFF`, `ADMIN`만 허용) |
| 부서 (`department`) | `MEDICAL`, `DEV`, `RESEARCH` | 환자 등록·진료기록 등록 가능 여부 (`MEDICAL`만 허용) |
`role`과 `department`는 서로 다른 정보이므로 각각 검사한다. `STAFF`라고 해서 `MEDICAL` 부서인 것은 아니다.

`department`는 마이페이지(User API `REQ-USER-007`)에서 변경할 수 있지만, `STAFF`가 부서를 변경하면 `role`이 `PENDING`으로 전환되어 관리자 재승인 전까지 환자·진료기록 API에 접근할 수 없다. 따라서 `STAFF`가 스스로 `MEDICAL`로 부서를 바꿔 환자·진료기록을 등록하는 것은 불가능하다. (`ADMIN`은 부서 변경 시에도 권한이 유지된다.)


### 2.2 공통 에러 응답

일반 오류는 다음 형식을 사용한다.

```json
{
  "detail": "에러 메시지"
}
```

입력값 검증 실패는 FastAPI/Pydantic의 `422 Unprocessable Entity` 응답 형식을 따른다.

| 상태 코드 | 의미 |
|---|---|
| `400 Bad Request` | 잘못된 요청 (수정할 항목이 없음 등) |
| `401 Unauthorized` | 인증 실패, 토큰 누락·오류·만료 또는 사용자 확인 실패 (탈퇴한 회원의 토큰 포함) |
| `403 Forbidden` | 권한 부족 (`PENDING` 회원, 환자·진료기록 등록 시 `MEDICAL` 부서가 아님) 또는 비활성 계정. `PENDING` 회원의 응답은 `{"detail": "접근 권한이 없습니다."}` |
| `404 Not Found` | 해당 환자 또는 진료기록을 찾을 수 없음 |
| `422 Unprocessable Entity` | 요청 본문 또는 파라미터 검증 실패 |

### 2.3 환자 데이터 정의

아래 자료형 및 NULL 허용 여부는 `patients` 테이블의 Alembic 마이그레이션을 기준으로 한다. (User 테이블의 nullable 규칙과 다르다.)

| API 필드명 | 자료형 | DB 컬럼 | NULL 허용 (DB) | 설명 |
|---|---|---|---|---|
| `id` | integer | `id` | 아니요 | 환자 고유 ID |
| `name` | string | `name` (`String(30)`) | 아니요 | 이름 |
| `age` | integer | `age` (`SmallInteger`) | 아니요 | 나이 |
| `gender` | enum | `gender` | 예 | 성별 (`M`, `F`) |
| `phone_number` | string | `phone` (`String(11)`) | 아니요 | 연락처 (숫자만) |
| `created_at` | datetime | `created_at` | 아니요 | 생성 일시 (UTC) |
| `updated_at` | datetime | `updated_at` | 예 | 수정 일시 (UTC) |

- DB 컬럼은 `phone`이지만, API 필드는 User API 및 프론트엔드(`static/apis.js`)에 맞춰 `phone_number`를 사용한다. 마이그레이션 없이 스키마에서 변환한다.
- `gender`는 DB에서 NULL을 허용하지만, 환자 등록 시에는 필수 입력으로 받는다.
- `updated_at`은 DB에서 NULL을 허용하지만 `server_default=current_timestamp(0)`이 설정되어 있어, 등록 직후에도 `created_at`과 같은 값이 저장된다. 따라서 등록 직후 응답의 `updated_at`은 `null`이 아니라 `created_at`과 같은 값이다. 공통 `TimestampMixin` 수정으로 `created_at`은 등록 시각, `updated_at`은 수정 시각이 정상 저장된다.

### 2.4 환자 응답 객체 (`PatientResponse`)

환자 등록·수정·목록 항목·상세 조회 응답에 모두 같은 모델을 사용한다.

```json
{
  "id": 1,
  "name": "김환자",
  "age": 45,
  "gender": "M",
  "phone_number": "01012345678",
  "created_at": "2026-10-27T03:03:00Z",
  "updated_at": "2026-10-27T03:03:00Z"
}
```

### 2.5 페이지네이션 규칙

목록 조회 API(환자 목록, 진료기록 목록)는 User API의 회원 목록 조회와 응답 구조 및 기본값이 같다. 검증 범위는 User API에 별도 규정이 없어 이 문서에서 제안한다.

| 파라미터 | 타입 | 기본값 | 검증 |
|---|---|---:|---|
| `page` | integer | `1` | 1 이상 (5일차 제안) |
| `size` | integer | `10` | 1~100 (5일차 제안) |

응답 구조는 다음과 같다.

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "size": 10
}
```

| 필드 | 설명 |
|---|---|
| `items` | 현재 페이지의 목록 |
| `total` | 조회 조건에 맞는 전체 개수 |
| `page` | 현재 페이지 번호 |
| `size` | 페이지당 조회 수 |

> `page`, `size`의 검증 범위는 4일차 명세서에 없으므로 팀 합의 후 확정하고, 회원 목록에도 같은 범위를 적용할지 함께 정한다. (13장 참조)

## 3. API 목록

| 순서 | 요구사항 ID | 기능 | Method | Endpoint | 권한 | 담당 |
|---:|---|---|---|---|---|---|
| 1 | `REQ-PTNT-001` | 환자 정보 등록 | `POST` | `/patients` | `STAFF`, `ADMIN` + `department = MEDICAL` | A |
| 2 | `REQ-PTNT-002` | 환자 목록 조회 | `GET` | `/patients` | `STAFF`, `ADMIN` | B |
| 3 | `REQ-PTNT-003` | 환자 정보 상세 조회 | `GET` | `/patients/{patient_id}` | `STAFF`, `ADMIN` | B |
| 4 | `REQ-PTNT-004` | 환자 정보 수정 | `PATCH` | `/patients/{patient_id}` | `STAFF`, `ADMIN` | A |
| 5 | `REQ-PTNT-005` | 환자 정보 삭제 | `DELETE` | `/patients/{patient_id}` | `STAFF`, `ADMIN` | A |
| 6 | `REQ-MDR-001` | 진료기록 등록 | `POST` | `/medical-records` | `STAFF`, `ADMIN` + `department = MEDICAL` | C |
| 7 | `REQ-MDR-002` | 진료기록 목록 조회 | `GET` | `/patients/{patient_id}/medical-records` | `STAFF`, `ADMIN` | C |
| 8 | `REQ-MDR-003` | 진료기록 상세 조회 | `GET` | `/medical-records/{record_id}` | `STAFF`, `ADMIN` | D |

- 엔드포인트는 `static/apis.js` 프론트 템플릿의 호출 경로를 기준으로 한다.
- 권한 열은 `STAFF`, `ADMIN`은 `require_staff`, `+ MEDICAL`은 `require_medical_staff`에 대응한다.
- 권한 검사는 서버에서 수행한다. 클라이언트 화면에서 버튼을 숨기는 것만으로 권한 검사를 대체하지 않는다.
- `PENDING` 회원은 환자·진료기록 API에 접근할 수 없으며 `403 Forbidden`을 반환한다.

---

## 4. 환자 정보 등록 — `REQ-PTNT-001` (담당자 A)

사내 의료인이 환자 정보를 시스템에 등록한다.

- **Method:** `POST`
- **Endpoint:** `/patients`
- **실제 경로:** `/api/v1/patients`
- **권한:** `STAFF`, `ADMIN` 중 `department = MEDICAL`인 회원 (`require_medical_staff`)

### 4.1 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `name` | string | 예 | 이름 |
| `age` | integer | 예 | 나이 |
| `gender` | enum | 예 | 성별 (`M`, `F`) |
| `phone_number` | string | 예 | 연락처 (휴대폰 번호) |

```json
{
  "name": "김환자",
  "age": 45,
  "gender": "M",
  "phone_number": "010-1234-5678"
}
```

### 4.2 처리 및 검증

- `name`: 앞뒤 공백을 제거한 뒤 1~30자
- `age`: 0~150
- `gender`: `M`, `F` (`male`, `female`도 허용하여 `M`, `F`로 변환)
- `phone_number`: 휴대폰 번호 형식(`01X` + 7~8자리)을 검증하고 공통 함수 `normalize_phone()`으로 숫자만 남겨 저장한다. (`010-1234-5678` → `01012345678`)
- 전화번호는 중복을 허용한다. (보호자 번호 공유 등, DB에도 UNIQUE 제약 없음)

### 4.3 성공 응답

**`201 Created`**

등록된 환자 정보를 `PatientResponse` 형식으로 반환한다. 등록 직후에는 `updated_at`이 `created_at`과 같은 값이다.

```json
{
  "id": 1,
  "name": "김환자",
  "age": 45,
  "gender": "M",
  "phone_number": "01012345678",
  "created_at": "2026-10-27T03:03:00Z",
  "updated_at": "2026-10-27T03:03:00Z"
}
```

### 4.4 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `401 Unauthorized` | 토큰 누락·만료·유효하지 않음 |
| `403 Forbidden` | `PENDING` 회원 또는 `MEDICAL` 부서가 아닌 회원 |
| `422 Unprocessable Entity` | 필수 필드 누락, 나이 범위·성별·전화번호 형식 오류 |

---

## 5. 환자 목록 조회 — `REQ-PTNT-002` (담당자 B)

- **Method:** `GET`
- **Endpoint:** `/patients`
- **실제 경로:** `/api/v1/patients`
- **권한:** `STAFF`, `ADMIN`
- **구현 파일:** `app/apis/patient_read.py`

### 5.1 요청

**Headers**

| Key | Value | 설명 |
|---|---|---|
| `Authorization` | `Bearer <access_token>` | 로그인 시 발급받은 Access Token |

**쿼리 파라미터** (모두 선택, Pydantic Query Parameter Model `PatientListQuery`)

| 파라미터 | 타입 | 필수 | 검증 | 설명 |
|---|---|---|---|---|
| `name` | string | N | 최대 30자, 앞뒤 공백 제거 | 이름 부분 일치 검색 (`%`, `_`는 일반 문자로 처리) |
| `gender` | enum | N | `M`, `F` (`male`, `female` 허용, 빈 값은 전체) | 성별 필터 |
| `min_age` | integer | N | 0~150 | 최소 나이 (이상) |
| `max_age` | integer | N | 0~150, `min_age` 이상 | 최대 나이 (이하) |
| `page` | integer | N | 1 이상, 기본 `1` | 페이지 번호 |
| `size` | integer | N | 1~100, 기본 `10` | 페이지당 조회 수 |

요청 예시: `GET /api/v1/patients?name=홍&gender=F&min_age=20&max_age=60&page=1&size=10`

### 5.2 처리

- 조건이 주어진 항목만 `AND`로 조합하여 조회한다.
- 최근 등록한 환자가 먼저 오도록 `id` 내림차순 정렬한다.
- 정의되지 않은 쿼리 파라미터는 User API 회원 목록과 동일하게 FastAPI 기본 동작에 따라 무시한다.

### 5.3 성공 응답 — `200 OK`

결과가 없으면 `items`는 빈 배열 `[]`, `total`은 `0`이다.

```json
{
  "items": [
    {
      "id": 3,
      "name": "홍길순",
      "age": 61,
      "gender": "F",
      "phone_number": "01011112222",
      "created_at": "2026-10-27T03:03:00Z",
      "updated_at": "2026-10-27T03:03:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10
}
```

- 응답은 `{items, total, page, size}` 객체이므로, 프론트엔드 `renderPatients`는 `data.items`를 목록으로 사용하도록 수정한다. (`const patients = data.items;`)

### 5.4 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `401 Unauthorized` | 토큰 누락·오류·만료 |
| `403 Forbidden` | `PENDING` 권한 또는 비활성 계정 |
| `422 Unprocessable Entity` | 잘못된 성별 값, 나이 범위 오류(음수, 150 초과, `min_age > max_age`), `page`·`size` 범위 오류 |

---

## 6. 환자 정보 상세 조회 — `REQ-PTNT-003` (담당자 B)

- **Method:** `GET`
- **Endpoint:** `/patients/{patient_id}`
- **실제 경로:** `/api/v1/patients/{patient_id}`
- **권한:** `STAFF`, `ADMIN`
- **구현 파일:** `app/apis/patient_read.py`

### 6.1 요청

**Headers**: `Authorization: Bearer <access_token>`

**경로 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `patient_id` | integer (1 이상) | Y | 환자 고유 ID |

요청 본문 없음

### 6.2 성공 응답 — `200 OK`

`PatientResponse` 형식으로 반환한다.

```json
{
  "id": 1,
  "name": "홍길동",
  "age": 34,
  "gender": "M",
  "phone_number": "01011112222",
  "created_at": "2026-10-27T03:03:00Z",
  "updated_at": "2026-10-27T03:03:00Z"
}
```

- 프론트엔드의 성별 표시는 응답이 `M`/`F`이므로 `=== 'M'`으로 비교한다. (목록, 상세 두 곳)

### 6.3 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `401 Unauthorized` | 토큰 누락·오류·만료 |
| `403 Forbidden` | `PENDING` 권한 또는 비활성 계정 |
| `404 Not Found` | `{"detail": "환자를 찾을 수 없습니다."}` |
| `422 Unprocessable Entity` | `patient_id`가 1 미만이거나 숫자가 아님 |

---

## 7. 환자 정보 수정 — `REQ-PTNT-004` (담당자 A)

환자의 이름과 연락처를 부분 수정한다. 보낸 필드만 수정되고, 보내지 않은 필드는 기존 값을 유지한다.

- **Method:** `PATCH`
- **Endpoint:** `/patients/{patient_id}`
- **실제 경로 예시:** `/api/v1/patients/1`
- **권한:** `STAFF`, `ADMIN`

### 7.1 경로 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `patient_id` | integer | 예 | 수정할 환자의 고유 ID |

### 7.2 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `name` | string | 아니요 | 이름 (앞뒤 공백 제거 후 1~30자) |
| `phone_number` | string | 아니요 | 연락처 (휴대폰 번호 형식, 하이픈 유무 무관, `normalize_phone()`으로 정규화) |

```json
{
  "name": "김수정",
  "phone_number": "010-9876-5432"
}
```

- 최소 하나 이상의 허용 필드를 전달해야 한다.
- 허용 필드는 `name`, `phone_number`다.
- 나이, 성별 등 허용되지 않은 필드는 요청에 포함되어도 무시한다.

### 7.3 성공 응답

**`200 OK`**

수정이 반영된 환자 정보를 `PatientResponse` 형식으로 반환한다. `updated_at`이 갱신된다.

```json
{
  "id": 1,
  "name": "김수정",
  "age": 45,
  "gender": "M",
  "phone_number": "01098765432",
  "created_at": "2026-10-27T03:03:00Z",
  "updated_at": "2026-10-27T04:30:00Z"
}
```

### 7.4 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `400 Bad Request` | 수정할 허용 필드가 없음 (`"수정할 항목이 없습니다."`) |
| `401 Unauthorized` | 토큰 누락·만료·유효하지 않음 |
| `403 Forbidden` | `PENDING` 회원 |
| `404 Not Found` | `{"detail": "환자를 찾을 수 없습니다."}` |
| `422 Unprocessable Entity` | 이름 길이 또는 전화번호 형식 검증 실패 |

---

## 8. 환자 정보 삭제 — `REQ-PTNT-005` (담당자 A)

환자 정보와 해당 환자의 진료기록, X-Ray 이미지, AI 분석 결과를 영구 삭제(Hard Delete)한다.

- **Method:** `DELETE`
- **Endpoint:** `/patients/{patient_id}`
- **실제 경로 예시:** `/api/v1/patients/1`
- **권한:** `STAFF`, `ADMIN`

### 8.1 경로 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `patient_id` | integer | 예 | 삭제할 환자의 고유 ID |

### 8.2 처리 내용

1. 환자를 조회한다. 없으면 `404 Not Found`를 반환한다.
2. 해당 환자의 진료기록에 연결된 X-Ray 이미지 경로(`xray_images.image_url`)를 조회한다.
3. `patients` 행을 삭제한다. Alembic FK 설정 `ON DELETE CASCADE`에 따라 다음 데이터가 DB에서 함께 삭제된다.
   - `medical_records` → `xray_images`, `ai_analysis_results`
4. DB 삭제를 커밋한 뒤, 2에서 조회한 `image_url`(`/media/xray/{파일명}`)을 서버 경로 `media/xray/{파일명}`으로 바꿔 이미지 파일을 삭제한다.
   - DB의 CASCADE 삭제는 실제 이미지 파일을 삭제하지 않으므로 별도로 처리한다.
   - 파일이 이미 없으면 무시하고, 파일 삭제 실패는 로그만 남긴다. (DB 삭제는 이미 완료되었으므로 응답은 성공으로 처리)

- 이미지 저장·삭제 함수는 진료기록 등록(담당자 C)이 공통 함수로 작성하고, 환자 삭제(담당자 A)가 이를 가져다 사용한다. 저장 정책은 9.2를 따른다.
- "관련 데이터가 모두 삭제됩니다" 확인 팝업은 프론트엔드에서 처리하며, 서버는 확인 여부를 별도로 받지 않는다.

### 8.3 성공 응답

**`204 No Content`**

응답 본문은 반환하지 않는다.

### 8.4 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `401 Unauthorized` | 토큰 누락·만료·유효하지 않음 |
| `403 Forbidden` | `PENDING` 회원 |
| `404 Not Found` | `{"detail": "환자를 찾을 수 없습니다."}` (이미 삭제된 환자 포함) |

---

## 9. 진료기록 등록 — `REQ-MDR-001` (담당자 C)

- **Method:** `POST`
- **Endpoint:** `/medical-records`
- **실제 경로:** `/api/v1/medical-records`
- **권한:** `STAFF`, `ADMIN` 중 `department = MEDICAL`인 회원 (`require_medical_staff`)
- **구현 파일:** `app/apis/medical_record.py` (파일명은 기존 프로젝트 구조와 확인 후 확정)

### 9.1 요청

`Content-Type: multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `patient_id` | integer | Y | 진료 대상 환자 ID |
| `chart_number` | string | Y | 차트 번호 |
| `symptoms` | string | Y | 증상 및 진료 내용 |
| `xray_image` | file | Y | 흉부 X-Ray 이미지 파일 |

`xray_image`는 업로드 파일 필드명 제안이며, 프론트엔드 템플릿의 실제 필드명과 일치시킨다.

### 9.2 처리

1. Access Token을 검증하고 사용자의 권한(`role`, `department`)을 확인한다.
2. `patient_id`에 해당하는 환자가 존재하는지 확인한다.
3. 요청 데이터와 이미지 파일을 검증한다.
4. 진료기록을 `medical_records` 테이블에 저장한다.
5. X-Ray 이미지 정보를 `xray_images` 테이블에 연결하여 저장하며, `uploader_id`에 현재 로그인 회원의 id를 기록한다. (회원 탈퇴 시 `ON DELETE SET NULL`로 `NULL` 처리됨)
6. 이미지 파일은 서버에 저장하고, DB에는 아래 경로 정책에 따른 경로를 저장한다.

- `xray_images.shooting_datetime`은 `NOT NULL`이지만 요청 필드에 없으므로, 별도 입력 없이 업로드 시각(서버 현재 UTC 시각)으로 저장한다.

**이미지 저장 경로 정책**

| 항목 | 값 |
|---|---|
| 저장 위치 | `media/xray/{uuid4}.{확장자}` |
| DB `image_url` | `/media/xray/{uuid4}.{확장자}` (예: `/media/xray/{uuid4}.png`) |
| 응답 `xray_image_url` | DB 값 그대로 |

- `main.py`에 이미 마운트된 `/media`를 사용한다.
- 저장 함수와 삭제 함수는 C가 공통으로 작성한다.

`MedicalRecord`와 `XrayImage`는 별도 모델이므로, 진료기록과 이미지 간의 관계를 실제 DB 모델에 맞게 설정한다.

### 9.3 성공 응답 — `201 Created`

```json
{
  "id": 1,
  "patient_id": 3,
  "chart_number": "CH-20261027-001",
  "symptoms": "기침과 발열",
  "created_at": "2026-10-27T03:03:00Z",
  "updated_at": "2026-10-27T03:03:00Z"
}
```

- 위 값은 응답 형식 예시이며, 실제 응답 필드는 DB 모델 및 공통 응답 스키마와 맞춘다.
- `created_at`, `updated_at`은 UTC ISO 8601 형식으로 반환한다.
- `updated_at`이 DB에서 NULL을 허용하더라도 서버 기본값이 설정되어 있으면 등록 직후에는 `created_at`과 같은 값이 반환된다. 실제 모델에서 기본값이 없어 NULL로 저장되는 경우에만 `null`을 반환한다.
- 이미지 미리보기는 프론트엔드 기능이며, 서버는 이미지 파일 저장과 조회 가능한 경로 제공을 담당한다.

### 9.4 오류 응답

| 상태 코드 | 상황 |
|---|---|
| `401 Unauthorized` | 토큰 누락·오류·만료 |
| `403 Forbidden` | `PENDING` 회원, `MEDICAL` 부서가 아닌 회원 또는 비활성 계정 |
| `404 Not Found` | `{"detail": "환자를 찾을 수 없습니다."}` (존재하지 않는 `patient_id`) |
| `422 Unprocessable Entity` | 필수 필드 누락, 잘못된 데이터 형식 등 |

---

## 10. 환자별 진료기록 목록 조회 — `REQ-MDR-002` (담당자 C)

- **Method:** `GET`
- **Endpoint:** `/patients/{patient_id}/medical-records`
- **실제 경로:** `/api/v1/patients/{patient_id}/medical-records`
- **권한:** `STAFF`, `ADMIN`
- **구현 파일:** `app/apis/medical_record.py` (파일명은 기존 프로젝트 구조와 확인 후 확정)

### 10.1 요청

**Headers**: `Authorization: Bearer <access_token>`

**경로 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `patient_id` | integer | Y | 진료기록을 조회할 환자 ID, 1 이상 |

**쿼리 파라미터**

| 파라미터 | 타입 | 기본값 | 검증 |
|---|---|---:|---|
| `page` | integer | `1` | 1 이상 |
| `size` | integer | `10` | 1~100 |

### 10.2 처리

1. Access Token을 검증하고 사용자의 권한을 확인한다.
2. 해당 환자가 존재하는지 확인한다.
3. `patient_id`에 연결된 진료기록을 조회한다.
4. 최근 등록한 기록이 먼저 오도록 `id` 내림차순으로 정렬한다.
5. `page`, `size`가 적용된 결과를 반환한다.
6. 증상 내용이 100자를 초과하면 목록 응답에서는 앞 100자 뒤에 `…`을 붙여 반환한다. 100자 이하이면 원문 그대로 반환한다.

### 10.3 성공 응답 — `200 OK`

```json
{
  "items": [
    {
      "id": 1,
      "patient_id": 3,
      "chart_number": "CH-20261027-001",
      "symptoms": "기침과 발열",
      "created_at": "2026-10-27T03:03:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10
}
```

- 조회 결과가 없으면 `items`는 `[]`, `total`은 `0`이다.
- `symptoms`는 목록 화면 표시용으로 100자를 초과하면 앞 100자 + `…`으로 반환한다. 프론트엔드는 `symptoms`를 그대로 출력한다.
- 응답은 `{items, total, page, size}` 객체이므로, 프론트엔드 `renderPatientDetail`은 `(await apis.getPatientMedicalRecords(patientId)).items`를 사용하도록 수정한다.
- 상세 정보 및 이미지 URL은 진료기록 상세 조회 API(`REQ-MDR-003`)에서 제공한다.
- `updated_at` 등 목록에 필요한 추가 필드는 프론트엔드 요구사항과 팀 공통 응답 모델에 맞춰 확정한다.
- User 개인정보는 별도 요구사항이 없는 한 목록 응답에 추가하지 않는다.

### 10.4 오류 응답

| 상태 코드 | 상황 |
|---|---|
| `401 Unauthorized` | 토큰 누락·오류·만료 |
| `403 Forbidden` | 권한 부족 또는 비활성 계정 |
| `404 Not Found` | `{"detail": "환자를 찾을 수 없습니다."}` |
| `422 Unprocessable Entity` | 잘못된 `patient_id`, `page`, `size` 등 |

---

## 11. 진료기록 상세 조회 — `REQ-MDR-003` (담당자 D)

특정 진료기록의 상세 정보(차트 번호, 증상 전문, X-Ray 이미지 접근 URL 등)를 조회한다.

- **Method:** `GET`
- **Endpoint:** `/medical-records/{record_id}`
- **실제 경로:** `/api/v1/medical-records/{record_id}`
- **권한:** `STAFF`, `ADMIN`
- **구현 파일:** `app/apis/medical_record.py`
- 라우터에는 `/medical-records/{record_id}`만 작성하고, `/api/v1` prefix는 `main.py`의 라우터 등록에서 공통 적용한다.
- 인증·토큰 검증은 `app/core/security.py`의 `get_current_user`를 재사용한다.
- 조회 권한은 `role`(`STAFF`, `ADMIN`) 기준이다. `department = MEDICAL` 제한은 환자·진료기록 등록에만 적용하고 조회에는 적용하지 않는다.

### 11.1 요청

**Headers**: `Authorization: Bearer <access_token>`

**경로 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `record_id` | integer (1 이상) | Y | 진료기록 고유 ID (예: `101`) |

요청 본문 없음

Access Token 유효기간은 30분이다. (User API 공통)

### 11.2 성공 응답 — `200 OK`

```json
{
  "id": 101,
  "patient_id": 1,
  "patient_name": "홍길동",
  "chart_number": "CHART-2026-001",
  "symptoms": "환자가 3일 전부터 시작된 심한 기침과 흉부 통증을 호소함. 엑스레이 촬영 결과 우하엽 소음영 관찰됨.",
  "xray_image_url": "/media/xray/<파일명>",
  "created_at": "2026-10-27T02:00:00Z",
  "updated_at": "2026-10-27T02:00:00Z"
}
```

- `symptoms`는 목록과 달리 전문을 반환한다.
- DB는 UTC로 저장하며, 응답 시 `Z`를 붙여 ISO 8601 형식으로 반환한다. (공통 datetime 직렬화 사용, 2장 참조)
- DB 클라이언트(DBeaver 등)에서는 한국 시각보다 9시간 느리게 보이는 것이 정상이다.
- `xray_image_url`은 9.2의 이미지 저장 경로 정책에 따라 DB에 저장된 `image_url`(`/media/xray/{파일명}`)을 그대로 반환한다. 프론트엔드는 이 값을 `<img src>`에 그대로 사용한다.
- X-Ray 이미지가 없는 진료기록의 `xray_image_url` 값은 13장 미확정 사항을 참조한다.

### 11.3 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `401 Unauthorized` | 토큰 누락·오류·만료 |
| `403 Forbidden` | `PENDING` 회원 또는 비활성 계정 |
| `404 Not Found` | `{"detail": "진료기록을 찾을 수 없습니다."}` |
| `422 Unprocessable Entity` | `record_id`가 1 미만이거나 숫자가 아님 |
| `500 Internal Server Error` | 서버 내부 오류 |

---

## 12. 비기능 요구사항 — `NFR-PTNT-001`, `NFR-MDR-001` (담당자 D)

### 12.1 성능

- 모든 Patient·MedicalRecord API는 요청부터 응답까지 **3초 이내** 처리를 목표로 한다.
- 등록·수정·삭제·상세 조회는 PK 기준으로 조회하여 불필요한 DB 조회를 방지한다.
- 환자 삭제 시 이미지 경로 조회는 한 번의 쿼리로 처리한다.
- 목록 조회에는 페이지네이션(`page`, `size`)을 적용한다.
- `patient_id`, `chart_number` 등 자주 조회되는 필드의 DB 인덱스는 실제 DB 모델과 조회 조건을 확인한 뒤 적용 여부를 검토한다.

### 12.2 응답 시간 측정

- FastAPI 미들웨어(`@app.middleware("http")`)로 모든 요청의 처리 시간을 측정하고, 3초를 초과하면 경고 로그를 남긴다.
- 로그 레벨 및 알림(Slack 등) 연동 여부는 13장 미확정 사항에서 확정한다.

### 12.3 이미지 파일 전달

- 이미지는 `main.py`에 마운트된 `/media`(`media/xray/`)를 통해 서빙한다.
- 이미지 서빙 시 정적 파일 캐싱(`Cache-Control`) 적용 여부를 검토한다.
- 서버는 이미지 파일 저장과 조회 가능한 경로 제공을 담당하고, 미리보기는 프론트엔드에서 처리한다.

### 12.4 NULL 처리

- NULL 허용 여부는 User 테이블이 아니라 실제 `patients`, `medical_records`, `xray_images` 모델 및 Alembic 마이그레이션을 기준으로 판단한다.
- nullable 필드가 응답에 포함되는 경우, 값이 없다면 `null`을 반환한다. 단, `updated_at`처럼 서버 기본값이 설정된 컬럼은 등록 직후 `created_at`과 같은 값이 저장되므로 `null`이 아니다.
- DB에서 NULL이 허용되지 않는 필드는 임의로 `null`을 허용하지 않는다.

---

## 13. 미확정 사항

팀 합의 후 확정하고, 확정되면 해당 본문에 반영한 뒤 이 장에서 삭제한다.

| 번호 | 항목 | 관련 위치 | 비고 |
|---:|---|---|---|
| 1 | `page`, `size` 검증 범위(`page` 1 이상, `size` 1~100) | 2.5, 10.1 | 4일차 회원 목록(`/users`)에는 검증 범위가 없다. 회원 목록에도 같은 범위를 적용할지 함께 결정한다. |
| 2 | 이미지가 없는 진료기록의 `xray_image_url` 값 | 11.2 | 등록 시 이미지가 필수이므로 `null`이 될 일은 없다고 정리할 수 있다. |
| 3 | 3초 초과 시 알림(Slack 등) 연동 여부와 로그 레벨 | 12.2 | |
| 4 | 성별 `male`, `female` 허용 문구 유지 여부 | 2.1, 4.2, 5.1 | 4일차 회원가입은 `M`, `F`만 받는다. 프론트엔드가 `M`/`F`를 보내도록 통일하면 삭제할 수 있다. |
| 5 | 진료기록 목록 경로(`/patients/{patient_id}/medical-records`)를 둘 라우터 | 3장, 10장 | 진료기록 라우터 prefix를 `/medical-records`로 두면 이 경로가 들어가지 못한다. 환자 라우터에 두거나 prefix 없는 별도 라우터로 분리하는 방안을 C와 A·B가 합의한다. |
| 6 | `medical_records`의 `updated_at` 기본값 | 9.3, 11.2 | `server_default` 확인은 `patients`만 했다. C·D가 `medical_records` 마이그레이션을 확인하고, 기본값이 없으면 두 예시의 `updated_at`을 `null`로 되돌린다. |
| 7 | 비활성 계정(`is_active = false`)의 `403` 처리 | 2.2 | `require_staff`가 비활성 계정을 막는지 실제 코드로 확인한 뒤 2.2 문구를 유지할지 정한다. |

## 14. 구현 시 확인 사항

1. 라우터 파일에는 `/patients`, `/medical-records`만 작성하고, `main.py`에서 `API_PREFIX`(`/api/v1`)를 적용해 등록했는지, `/api/v1/api/v1` 같은 prefix 중복이 없는지 확인한다.
2. 인증·인가는 공통 `app/core/security.py`의 의존성(`get_current_user`, `require_staff`, `require_medical_staff`)을 사용하고 JWT 검증 로직을 중복 구현하지 않았는지 확인한다.
3. 환자 등록과 진료기록 등록에서 `role`(`STAFF`, `ADMIN`)과 `department`(`MEDICAL`)를 각각 검사하는지 확인한다.
4. API 필드 `phone_number`가 DB 컬럼 `phone`으로 저장되고, 모든 응답에서 `phone_number`로 반환되는지 확인한다. 정규화에는 공통 `normalize_phone()`을 사용한다.
5. 환자 등록·수정·목록·상세 응답이 모두 같은 `PatientResponse`를 사용하는지 확인한다.
6. 목록 조회 응답이 `items`, `total`, `page`, `size` 구조이며 기본 `size`가 `10`인지 확인하고, 프론트엔드가 `.items`를 사용하는지 확인한다. (`renderPatients`, `renderPatientDetail`)
7. 응답의 날짜·시간이 UTC ISO 8601 형식(`Z` 포함)이고 공통 datetime 직렬화를 사용하는지 확인한다.
8. `updated_at`이 등록 직후 `created_at`과 같은 값으로 응답되는지 확인한다. (공통 Timestamp 설정 확인)
9. 에러 응답이 `{"detail": "..."}` 형식이고, 404 메시지가 이 문서의 문구와 일치하는지 확인한다.
10. 진료기록 등록 시 `xray_images.uploader_id`에 현재 로그인 회원 id가 저장되고, `shooting_datetime`이 서버 현재 UTC 시각으로 저장되는지 확인한다.
11. 이미지가 `media/xray/{uuid4}.{확장자}`에 저장되고 DB `image_url`이 `/media/xray/...` 형식인지 확인한다.
12. 환자 삭제 시 관련 진료기록, X-Ray 이미지, AI 분석 결과가 DB에서 함께 삭제되고, 이미지 파일도 삭제되는지 확인한다.
13. `PENDING` 회원이 모든 환자·진료기록 API에서 `403`을 받는지 확인한다.
14. 프론트엔드 성별 표시 비교가 `=== 'M'`으로 수정되었는지 확인한다. (환자 목록, 상세)
15. Swagger UI에서 정상 요청과 오류 응답을 테스트한다.
16. API 응답 시간이 3초 이내인지 확인한다.
17. `xray_image_url`(`/media/xray/...`)이 `main.py`의 `/media` 마운트 설정과 일치하고 브라우저에서 이미지가 표시되는지 확인한다.
18. 공통 PR 머지 후 `uv run python -c "import app.main"`이 오류 없이 실행되고, `.env`에 `JWT_SECRET_KEY`가 설정되어 있는지 확인한다.
19. `STAFF` 회원이 부서를 변경하면 `PENDING`으로 전환되어 환자·진료기록 API가 `403`을 반환하는지 확인한다.  

## 15. 변경 이력

| 버전 | 내용 |
|---|---|
| v1.0 | A·B·C·D 파트 통합, 4일차 User API 공통 규칙(필드명, 페이지네이션, 에러 포맷, 날짜 형식, 인증 모듈)에 맞춰 정리 |
| v1.1 | D파트 수정본 반영(진료기록 상세 조회 500 상태 코드, 인증·권한 보강, 이미지 URL 미확정 항목 추가), 안건을 담당자 알파벳 순으로 재정렬 |
| v1.2 | 검토 결과 반영(4일차 우선): `require_medical_staff` 추가 및 진료기록 등록 `MEDICAL` 제한 확정, `updated_at` 예시와 NULL 설명 수정, 이미지 저장 경로 `/media/xray/...` 확정 및 `xray_image_url` 수정, `shooting_datetime` 서버 UTC 시각 저장, 증상 100자 초과 시 `…` 표기, DB UTC 저장 설명으로 KST 변환 문구 교체, 페이지네이션 검증 범위를 5일차 제안으로 명시, `normalize_phone()` 명시, 프론트엔드 `.items`·성별 비교 수정 사항 추가, 미확정 사항 장(13장) 신설, 공통 PR 반영(`TimestampMixin` 수정, `security.py`·`validators.py` 도입, `require_staff`·`require_medical_staff` 기준으로 인가 문구 정리, `require_roles` 제거) |
| v1.3 | 프론트엔드를 명세서 기준으로 정리(API 경로·형식, Enum 값 통일), `STAFF` 부서 변경 시 `PENDING` 전환 정책 확정에 따라 13장 4번 삭제 및 2.1절 보완 |
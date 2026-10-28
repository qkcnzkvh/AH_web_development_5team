# User API 통합 설계 명세서

## 1. 개요

### 1.1 목적

회원가입, 로그인, 로그아웃, 토큰 갱신, 회원 목록 조회, 회원 권한 변경, 마이페이지 및 개인정보 관리 기능을 제공하는 API를 설계한다.

### 1.2 관련 요구사항

- `REQ-USER-001`: 회원가입
- `REQ-USER-002`: 로그인
- `REQ-USER-003`: 로그아웃
- `REQ-USER-004`: 회원 목록 조회
- `REQ-USER-005`: 회원 권한 변경
- `REQ-USER-006`: 마이페이지 조회
- `REQ-USER-007`: 회원 정보 수정
- `REQ-USER-008`: 비밀번호 변경
- `REQ-USER-009`: 회원 탈퇴
- `NFR-USER-001`: 인증 및 인가
- `NFR-USER-002`: 비밀번호 입력 보안
- `NFR-USER-003`: API 성능

## 2. 공통 규칙

| 항목 | 규칙 |
|---|---|
| Base URL | `/api/v1` |
| 인증 API Prefix | `/api/v1/auth` |
| 데이터 형식 | `application/json` |
| 인증 방식 | 인증이 필요한 API는 `Authorization: Bearer <access_token>` 사용 |
| JWT Payload | `user_id`를 최소 식별자로 포함하고, 필요한 표준 클레임 사용 |
| Access Token 유효기간 | 30분 |
| Refresh Token 유효기간 | 7일 |
| Refresh Token 전달 | `HttpOnly` 쿠키 |
| 비밀번호 해시 | 공통 `security.py` 모듈의 Argon2 사용 |
| 전화번호 저장 및 응답 | 숫자만 사용 |
| 응답 시간 | 모든 User API 3초 이내 응답 목표 |

각 엔드포인트는 별도 표기가 없다면 Base URL을 제외한 상대 경로로 작성한다. 예를 들어 `/users`의 실제 경로는 `/api/v1/users`이다.

### 2.1 Enum 값

**부서 (`department`)**

| 값 | 의미 |
|---|---|
| `RESEARCH` | 연구 |
| `MEDICAL` | 의료 |
| `DEV` | 개발 |

**성별 (`gender`)**

| 값 | 의미 |
|---|---|
| `M` | 남성 |
| `F` | 여성 |

**회원 권한 (`role`)**

| 값 | 의미 |
|---|---|
| `PENDING` | 대기자 |
| `STAFF` | 스태프 |
| `ADMIN` | 관리자 |

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
| `400 Bad Request` | 잘못된 요청 또는 비밀번호 변경 실패 |
| `401 Unauthorized` | 인증 실패, 토큰 누락·오류·만료 또는 사용자 확인 실패 |
| `403 Forbidden` | 권한 부족 또는 비활성 계정 |
| `404 Not Found` | 해당 회원을 찾을 수 없음 |
| `409 Conflict` | 이메일 또는 휴대폰 번호 중복 등 리소스 충돌 |
| `422 Unprocessable Entity` | 요청 본문 또는 파라미터 검증 실패 |

회원 탈퇴 후 기존 Access Token 사용 시 사용자 존재 여부를 확인한다. 존재하지 않는 사용자에 대한 응답은 공통 인증 정책에 따라 `401` 또는 `404` 중 하나로 통일한다.

### 2.3 회원 데이터 정의

아래 자료형 및 NULL 허용 여부는 Alembic 마이그레이션을 기준으로 한다.

| 필드명 | 자료형 | NULL 허용 | 설명 |
|---|---|---|---|
| `id` | integer | 아니요 | 회원 고유 ID |
| `email` | string | 예 | 이메일 |
| `hashed_password` | string | 예 | 비밀번호 해시 |
| `name` | string | 예 | 이름 |
| `department` | enum | 아니요 | 부서 |
| `gender` | enum | 아니요 | 성별 |
| `phone_number` | string | 예 | 휴대폰 번호 |
| `role` | enum | 아니요 | 회원 권한 |
| `is_active` | boolean | 아니요 | 계정 활성화 여부 |
| `created_at` | datetime | 아니요 | 생성 일시 |
| `updated_at` | datetime | 예 | 수정 일시 |

`hashed_password`는 내부 인증 처리에만 사용하며 API 응답에 포함하지 않는다. `email`, `name`, `phone_number`는 DB 스키마상 `null`일 수 있으므로 응답 스키마에도 반영한다.

## 3. API 목록

| 순서 | 요구사항 ID | 기능 | Method | Endpoint |
|---:|---|---|---|---|
| 1 | `REQ-USER-001` | 회원가입 | `POST` | `/auth/signup` |
| 2 | `REQ-USER-002` | 로그인 | `POST` | `/auth/login` |
| 3 | `NFR-USER-001` | Access Token 갱신 | `POST` | `/auth/refresh` |
| 4 | `REQ-USER-003` | 로그아웃 | `POST` | `/auth/logout` |
| 5 | `REQ-USER-004` | 회원 목록 조회 | `GET` | `/users` |
| 6 | `REQ-USER-005` | 회원 권한 변경 | `PATCH` | `/users/{user_id}/role` |
| 7 | `REQ-USER-006` | 마이페이지 조회 | `GET` | `/users/me` |
| 8 | `REQ-USER-007` | 회원 정보 수정 | `PATCH` | `/users/me` |
| 9 | `REQ-USER-008` | 비밀번호 변경 | `PATCH` | `/users/me/password` |
| 10 | `REQ-USER-009` | 회원 탈퇴 | `DELETE` | `/users/me` |

---

## 4. 회원가입 — `REQ-USER-001`

- **Method:** `POST`
- **Endpoint:** `/auth/signup`
- **실제 경로:** `/api/v1/auth/signup`
- **권한:** 비로그인 사용자

### 4.1 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `email` | string | 예 | 이메일 |
| `password` | string | 예 | 비밀번호 |
| `name` | string | 예 | 이름 |
| `department` | enum | 예 | `RESEARCH`, `MEDICAL`, `DEV` |
| `gender` | enum | 예 | `M`, `F` |
| `phone_number` | string | 예 | 휴대폰 번호 |

```json
{
  "email": "user@example.com",
  "password": "Password123!",
  "name": "홍길동",
  "department": "MEDICAL",
  "gender": "M",
  "phone_number": "01012345678"
}
```

### 4.2 처리 및 검증

- 비밀번호는 평문으로 저장하지 않고 Argon2로 해시하여 `hashed_password`에 저장한다.
- 비밀번호는 8~20자이며, 대문자·소문자·특수문자를 각각 최소 1개 포함해야 한다.
- 숫자는 포함할 수 있지만 필수 조건은 아니다.
- 전화번호는 `normalize_phone()`을 사용하여 숫자만 남기도록 정규화한다.
- 이메일과 휴대폰 번호의 중복 여부를 확인한다.
- 회원가입 시 기본 권한은 `PENDING`으로 설정한다.
- 비밀번호 및 해시값은 응답에 포함하지 않는다.

### 4.3 성공 응답

**`201 Created`**

성공 응답에는 생성된 회원의 공개 정보를 반환한다. `hashed_password`는 반환하지 않는다.

```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "홍길동",
  "department": "MEDICAL",
  "gender": "M",
  "phone_number": "01012345678",
  "role": "PENDING"
}
```

### 4.4 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `409 Conflict` | 이메일 또는 휴대폰 번호 중복 |
| `422 Unprocessable Entity` | 필수 필드 누락 또는 입력값 검증 실패 |

---

## 5. 로그인 — `REQ-USER-002`

- **Method:** `POST`
- **Endpoint:** `/auth/login`
- **실제 경로:** `/api/v1/auth/login`
- **권한:** 비로그인 사용자

### 5.1 요청 본문

로그인은 JSON 형식을 사용한다.

```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

### 5.2 성공 응답

**`200 OK`**

```json
{
  "access_token": "<JWT_ACCESS_TOKEN>",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "홍길동",
    "department": "MEDICAL",
    "gender": "M",
    "phone_number": "01012345678",
    "role": "PENDING"
  }
}
```

- `access_token`: Access Token
- `token_type`: 토큰 유형
- `expires_in`: Access Token의 남은 유효시간(초). 기본 유효기간은 1800초다.
- `user`: 로그인한 회원의 공개 정보
- Refresh Token은 JSON 응답에 포함하지 않고 `HttpOnly` 쿠키로 전달한다.

### 5.3 계정 및 비밀번호 검증

- 이메일과 비밀번호가 일치하지 않으면 `401 Unauthorized`를 반환한다.
- `is_active = false`인 계정은 로그인을 거부하고 `403 Forbidden`을 반환한다.
- 비밀번호는 저장된 Argon2 해시를 통해 검증한다.

---

## 6. 인증 및 Access Token 갱신 — `NFR-USER-001`

### 6.1 토큰 정책

| 항목 | 정책 |
|---|---|
| Access Token | 30분 |
| Refresh Token | 7일 |
| Access Token 전달 | `Authorization: Bearer` 헤더 |
| Refresh Token 전달 | `HttpOnly` 쿠키 |
| JWT Payload | `user_id` 및 필요한 표준 클레임 |

### 6.2 쿠키 보안

Refresh Token 쿠키는 다음 정책을 사용한다.

- 쿠키 이름: `refresh_token`
- `HttpOnly`: JavaScript에서 직접 읽을 수 없도록 설정
- `SameSite=Lax`
- `Path=/api/v1/auth`
- HTTPS 환경에서는 `Secure` 설정

로그인, 토큰 갱신, 로그아웃에서 쿠키 이름과 경로 등 주요 속성을 일관되게 적용한다.

### 6.3 Access Token 갱신

- **Method:** `POST`
- **Endpoint:** `/auth/refresh`
- **실제 경로:** `/api/v1/auth/refresh`

Refresh Token은 쿠키를 통해 전달한다.

**성공 응답 — `200 OK`**

```json
{
  "access_token": "<NEW_JWT_ACCESS_TOKEN>",
  "token_type": "bearer",
  "expires_in": 1800
}
```

Refresh Token이 유효하면 새로운 Access Token을 발급한다. Refresh Token이 누락되었거나 만료 또는 유효하지 않으면 `401 Unauthorized`를 반환한다.

Refresh Token 회전 여부와 서버 측 토큰 저장·폐기 방식은 실제 인증 구현에 맞춰 적용한다.

---

## 7. 로그아웃 — `REQ-USER-003`

- **Method:** `POST`
- **Endpoint:** `/auth/logout`
- **실제 경로:** `/api/v1/auth/logout`
- **Access Token 인증:** 불필요

### 7.1 처리 방식

1. Refresh Token 쿠키를 즉시 만료시킨다.
2. 쿠키 삭제 응답에 기존 쿠키와 동일한 이름 및 경로를 사용한다.
3. 서버에서 Refresh Token을 별도로 저장하거나 관리한다면 해당 토큰의 폐기 처리도 수행한다.

쿠키 만료 예시:

```http
Set-Cookie: refresh_token=; Max-Age=0; Path=/api/v1/auth; HttpOnly; SameSite=Lax
```

HTTPS 환경에서는 `Secure` 옵션도 일치시킨다.

### 7.2 성공 응답

**`204 No Content`**

응답 본문은 반환하지 않는다.

> 쿠키를 삭제하는 것만으로 서버에 이미 전달된 Refresh Token 자체가 무효화되는 것은 아니다. 서버 측 폐기가 필요한 경우 별도의 토큰 관리 정책을 적용한다.

---

## 8. 회원 목록 조회 — `REQ-USER-004`

- **Method:** `GET`
- **Endpoint:** `/users`
- **실제 경로:** `/api/v1/users`
- **권한:** `ADMIN`

### 8.1 요청 파라미터

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `search` | string | 아니요 | 없음 | 이메일 또는 이름 검색 |
| `department` | string | 아니요 | 없음 | 부서 필터 |
| `page` | integer | 아니요 | `1` | 페이지 번호 |
| `size` | integer | 아니요 | `10` | 페이지당 조회 수 |

### 8.2 요청 예시

```http
GET /api/v1/users?search=홍길동&department=MEDICAL&page=1&size=10
Authorization: Bearer <access_token>
```

### 8.3 성공 응답

**`200 OK`**

```json
{
  "items": [
    {
      "id": 1,
      "email": "user@example.com",
      "name": "홍길동",
      "department": "MEDICAL",
      "gender": "M",
      "phone_number": "01012345678",
      "is_active": true,
      "role": "STAFF"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10
}
```

| 필드 | 설명 |
|---|---|
| `items` | 현재 페이지의 회원 목록 |
| `total` | 검색 조건에 맞는 전체 회원 수 |
| `page` | 현재 페이지 번호 |
| `size` | 페이지당 조회 수 |

회원 객체의 `email`, `name`, `phone_number`는 `null`일 수 있다. 비밀번호 및 해시값은 응답에 포함하지 않는다.

### 8.4 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `401 Unauthorized` | 인증 실패 |
| `403 Forbidden` | 관리자 권한 없음 |
| `422 Unprocessable Entity` | 잘못된 요청 파라미터 |

---

## 9. 회원 권한 변경 — `REQ-USER-005`

- **Method:** `PATCH`
- **Endpoint:** `/users/{user_id}/role`
- **실제 경로 예시:** `/api/v1/users/1/role`
- **권한:** `ADMIN`

### 9.1 요청 본문

```json
{
  "role": "STAFF"
}
```

허용 값은 `PENDING`, `STAFF`, `ADMIN`이다.

### 9.2 성공 응답

**`200 OK`**

```json
{
  "id": 1,
  "role": "STAFF",
  "message": "회원 권한이 변경되었습니다."
}
```

### 9.3 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `401 Unauthorized` | 인증 실패 |
| `403 Forbidden` | 관리자 권한 없음 |
| `404 Not Found` | 해당 회원을 찾을 수 없음 |
| `422 Unprocessable Entity` | 허용되지 않는 권한 값 |

---

## 10. 마이페이지 조회 — `REQ-USER-006`

- **Method:** `GET`
- **Endpoint:** `/users/me`
- **실제 경로:** `/api/v1/users/me`
- **권한:** 로그인 사용자 (모든 권한)

### 10.1 요청

```http
GET /api/v1/users/me
Authorization: Bearer <access_token>
```

### 10.2 성공 응답

**`200 OK`**

```json
{
  "name": "홍길동",
  "email": "user@example.com",
  "department": "MEDICAL",
  "gender": "M",
  "phone_number": "01012345678",
  "role": "STAFF"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | string 또는 null | 이름 |
| `email` | string 또는 null | 이메일 |
| `department` | enum | 부서 |
| `gender` | enum | 성별 |
| `phone_number` | string 또는 null | 휴대폰 번호 |
| `role` | enum | 회원 권한 |

### 10.3 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `401 Unauthorized` | 토큰 누락·만료·유효하지 않음 또는 회원이 존재하지 않음 |
| `404 Not Found` | 해당 회원을 찾을 수 없음 (공통 인증 정책과 통일) |

---

## 11. 회원 정보 수정 — `REQ-USER-007`

- **Method:** `PATCH`
- **Endpoint:** `/users/me`
- **실제 경로:** `/api/v1/users/me`
- **권한:** 로그인 사용자 (모든 권한)

### 11.1 요청 본문

```json
{
  "department": "RESEARCH",
  "phone_number": "01098765432"
}
```

| 필드 | 타입 | 필수 | 검증 규칙 |
|---|---|---|---|
| `department` | enum | 아니요 | `MEDICAL`, `DEV`, `RESEARCH` 중 하나 |
| `phone_number` | string | 아니요 | 전화번호 형식, 중복 불가 |

- 최소 하나 이상의 허용 필드를 전달해야 한다.
- 허용 필드는 `department`, `phone_number`다.
- 허용되지 않은 추가 필드는 무시한다.
- 보내지 않은 필드는 기존 값을 유지한다.
- `STAFF` 회원이 `department`를 현재 값과 다른 값으로 변경하면 `role`이 `PENDING`으로 전환되며, 관리자(`ADMIN`)가 다시 승인(권한 변경)하기 전까지 `PENDING` 권한으로 제한된다.
- 다음 경우에는 `role`을 유지한다.
  - `ADMIN` 회원의 부서 변경
  - 현재와 같은 부서로 저장하는 경우
  - `phone_number`만 수정하는 경우

### 11.2 성공 응답

- 부서 변경으로 `role`이 `PENDING`으로 전환된 경우, 응답의 `role`은 `PENDING`으로 반환된다.  

**`200 OK`**

수정된 마이페이지 정보를 반환한다.

```json
{
  "name": "홍길동",
  "email": "user@example.com",
  "department": "RESEARCH",
  "gender": "M",
  "phone_number": "01098765432",
  "role": "STAFF"
}
```

### 11.3 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `400 Bad Request` | 수정할 허용 필드가 없음 |
| `401 Unauthorized` | 인증 실패 |
| `404 Not Found` | 해당 회원을 찾을 수 없음 |
| `409 Conflict` | 휴대폰 번호 중복 |
| `422 Unprocessable Entity` | 허용 필드의 값 또는 형식 검증 실패 |

---

## 12. 비밀번호 변경 — `REQ-USER-008`

- **Method:** `PATCH`
- **Endpoint:** `/users/me/password`
- **실제 경로:** `/api/v1/users/me/password`
- **권한:** 로그인 사용자 (모든 권한)

### 12.1 요청 본문

```json
{
  "current_password": "OldPassword1!",
  "new_password": "NewPassword1!"
}
```

| 필드 | 타입 | 필수 | 검증 규칙 |
|---|---|---|---|
| `current_password` | string | 예 | 기존 비밀번호 |
| `new_password` | string | 예 | 새 비밀번호 규칙 적용, 기존 비밀번호와 달라야 함 |

### 12.2 처리 순서

1. Access Token을 검증하고 사용자를 조회한다.
2. `current_password`를 DB의 `hashed_password`와 비교한다.
3. 기존 비밀번호가 일치하면 새 비밀번호를 Argon2로 해시한다.
4. 새 해시를 `hashed_password`에 저장한다.

새 비밀번호는 다음 규칙을 만족해야 한다.

- 8~20자
- 대문자 최소 1개
- 소문자 최소 1개
- 특수문자 최소 1개

### 12.3 성공 응답

**`204 No Content`**

응답 본문은 반환하지 않는다.

### 12.4 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `400 Bad Request` | 기존 비밀번호 불일치 또는 새 비밀번호가 기존 비밀번호와 동일 |
| `401 Unauthorized` | 인증 실패 |
| `404 Not Found` | 해당 회원을 찾을 수 없음 |
| `422 Unprocessable Entity` | 필수 값 누락 또는 새 비밀번호 규칙 위반 |

---

## 13. 회원 탈퇴 — `REQ-USER-009`

- **Method:** `DELETE`
- **Endpoint:** `/users/me`
- **실제 경로:** `/api/v1/users/me`
- **권한:** 로그인 사용자 (모든 권한)

### 13.1 처리 내용

1. 본인 계정을 DB에서 실제 삭제한다(Hard Delete).
2. Refresh Token 쿠키를 즉시 만료시킨다.
3. `xray_images.uploader_id`는 Alembic 외래 키의 `ON DELETE SET NULL` 설정에 따라 `NULL`이 된다.
4. `get_current_user`에서 DB 사용자 존재 여부를 확인하여 탈퇴한 회원의 기존 Access Token 사용을 차단한다.

### 13.2 성공 응답

**`204 No Content`**

응답 본문은 반환하지 않는다.

### 13.3 오류 응답

| 상태 코드 | 설명 |
|---|---|
| `401 Unauthorized` | 인증 실패 또는 탈퇴한 회원의 토큰 |
| `404 Not Found` | 해당 회원을 찾을 수 없음 |

탈퇴 후 사용자 존재 여부 확인 결과에 따른 상태 코드는 공통 인증 정책과 일치시킨다.

---

## 14. 비밀번호 입력 보안 — `NFR-USER-002`

- 모든 비밀번호 입력창은 기본적으로 `<input type="password">`를 사용한다.
- 비밀번호 보기 아이콘을 선택하면 `password`와 `text` 사이에서 입력 타입을 전환한다.
- 전환 시 아이콘과 `aria-label`을 함께 변경한다.
- 적용 범위는 회원가입, 로그인, 기존 비밀번호 및 새 비밀번호 입력창이다.

---

## 15. 성능 요구사항 — `NFR-USER-003`

- 모든 User API는 요청부터 응답까지 3초 이내 처리를 목표로 한다.
- 회원 목록 조회에는 페이지네이션을 적용한다.
- 검색 조건에 따라 DB 인덱스 적용을 검토한다.
- 불필요한 DB 조회와 반복 조회를 방지한다.
- 테스트 환경에서 응답 시간을 측정해 요구사항 충족 여부를 확인한다.

---

## 16. 구현 시 확인 사항

1. 인증 라우터가 `/api/v1/auth` 경로를 사용하는지 확인한다.
2. 로그인 요청이 JSON의 `email`, `password`를 사용하는지 확인한다.
3. 로그인 응답에 `access_token`, `token_type`, `expires_in`, `user`가 포함되는지 확인한다.
4. 로그아웃에서 Access Token 인증 없이 Refresh Token 쿠키를 만료시키는지 확인한다.
5. 비밀번호 규칙과 Argon2 해시 구현이 공통 `security.py`와 일치하는지 확인한다.
6. Refresh Token 쿠키 경로가 `/api/v1/auth`로 통일됐는지 확인한다.
7. 쿠키 삭제 시 쿠키 이름과 경로가 기존 설정과 일치하는지 확인한다.
8. 전화번호가 DB 저장 및 API 응답에서 숫자만 사용하는지 확인한다.
9. 비활성 계정 로그인 시 `403 Forbidden`을 반환하는지 확인한다.
10. 회원 목록 응답이 `items`, `total`, `page`, `size` 구조이며 기본 `size`가 `10`인지 확인한다.
11. 허용되지 않은 회원 정보 수정 필드가 무시되는지 확인한다.
12. 회원 탈퇴 후 `get_current_user`가 DB 사용자 존재 여부를 확인해 접근을 차단하는지 확인한다.
13. 서버에서 Refresh Token을 별도로 관리한다면 로그아웃 시 서버 측 폐기도 수행하는지 확인한다.
14. Swagger UI 또는 API 테스트로 정상 요청과 오류 응답을 검증한다.
15. API 응답 시간이 3초 이내인지 확인한다.
16. `STAFF` 회원이 부서를 변경하면 `PENDING`으로 전환되고, `ADMIN`이나 동일 부서 저장·전화번호만 수정하는 경우에는 `role`이 유지되는지 확인한다.

## 17. 변경 이력

| 버전 | 내용 |
|---|---|
| v1.0 | User API 통합 및 팀 합의 사항 반영 |
| v1.1 | 부서 변경 시 `STAFF`는 `PENDING`으로 전환(관리자 재승인 필요), 프론트엔드 호출 경로·형식을 명세서 기준으로 정리 |

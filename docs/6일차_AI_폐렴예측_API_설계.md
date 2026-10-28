# AI 폐렴 예측 API 통합 설계 명세서

## 1. 개요

### 1.1 목적

진료기록에 등록된 흉부 X-Ray 이미지를 AI 모델에 입력하여 폐렴 여부를 예측하고, 예측 결과를 저장·조회하는 API를 설계한다. 공통 규칙은 User API 통합 설계 명세서(`docs/4일차_USER_API_설계.md`)와 환자 관리 및 진료기록 API 통합 설계 명세서(`docs/5일차_환자관리_API_설계.md`, v1.3 기준)를 따른다.

### 1.2 관련 요구사항

- `REQ-PRED-001`: AI 모델 활용 폐렴 예측
- `REQ-PRED-002`: AI 모델 활용 폐렴 예측 결과 조회
- `NFR-PRED-001`: AI 모델 평가 기준
- `NFR-PRED-002`: API 성능 (3초 이내 응답)

## 2. 공통 규칙

| 항목 | 규칙 |
|---|---|
| Base URL | `/api/v1` |
| 라우터 Prefix | 라우터 파일에는 `/medical-records`만 작성하고, `/api/v1`은 `main.py`에서 라우터 등록 시 공통 적용 |
| 데이터 형식 | `application/json` (요청 본문 없음) |
| 인증 방식 | `Authorization: Bearer <access_token>` |
| 인가 | 공통 `app/core/security.py`의 `require_staff` 사용 (`STAFF`, `ADMIN`만 허용, `PENDING`은 403) |
| 부서 제한 | **없음.** 의료진·개발팀·연구진 모두 사용할 수 있다. (`require_medical_staff`를 사용하지 않는다) |
| 부서 변경 시 | 5일차 v1.3 정책에 따라 `STAFF`가 마이페이지에서 부서를 변경하면 `role`이 `PENDING`으로 전환되어, 관리자가 재승인하기 전까지 이 API를 포함한 환자·진료기록 API가 `403`이다. `ADMIN`은 부서를 변경해도 권한이 유지된다. |
| 필드명 규칙 | 요청·응답 필드는 snake_case |
| 날짜·시간 | 5일차 공통 규칙과 같다. DB는 UTC로 저장하고, 응답은 UTC ISO 8601(`Z` 포함)로 반환한다. (예: `2026-10-28T03:03:00Z`) |
| 입력 이미지 | 진료기록 등록(`REQ-MDR-001`) 시 업로드한 X-Ray 이미지를 사용한다. 별도 이미지 업로드는 받지 않는다. |
| 응답 시간 | 모든 AI 예측 API 3초 이내 응답 (`NFR-PRED-002`) |

각 엔드포인트는 별도 표기가 없다면 Base URL을 제외한 상대 경로로 작성한다. 예를 들어 `/medical-records/{record_id}/predict`의 실제 경로는 `/api/v1/medical-records/{record_id}/predict`이다.

### 2.1 공통 에러 응답

일반 오류는 4·5일차와 같은 형식을 사용한다.

```json
{
  "detail": "에러 메시지"
}
```

| 상태 코드 | 의미 |
|---|---|
| `401 Unauthorized` | 토큰 누락·오류·만료 또는 사용자 확인 실패 |
| `403 Forbidden` | `PENDING` 회원(부서를 변경하여 `PENDING`으로 전환된 `STAFF` 포함) 또는 비활성 계정 (`{"detail": "접근 권한이 없습니다."}`) |
| `404 Not Found` | 진료기록 또는 X-Ray 이미지를 찾을 수 없음 |
| `422 Unprocessable Entity` | 경로 파라미터 검증 실패 (`record_id`가 1 미만 등) |
| `500 Internal Server Error` | 이미지 파일 읽기 실패, 추론 실패 등 서버 내부 오류 |
| `503 Service Unavailable` | AI 모델이 로드되지 않아 예측을 수행할 수 없음 |

### 2.2 AI 분석 결과 데이터 정의

아래 자료형 및 NULL 허용 여부는 `ai_analysis_results` 테이블의 Alembic 마이그레이션(`c75d234c47b0`)을 기준으로 하되, 변경이 필요한 항목은 비고에 적는다.

| API 필드명 | 자료형 | DB 컬럼 | NULL 허용 (DB) | 설명 |
|---|---|---|---|---|
| `id` | integer | `id` | 아니요 | 예측 결과 고유 ID |
| `record_id` | integer | `record_id` | 아니요 | 진료기록 ID (FK, `ON DELETE CASCADE`) |
| `is_pneumonia` | boolean | `is_pneumonia` | 아니요 | 폐렴 여부 (`true`: 폐렴, `false`: 정상) |
| `confidence` | number | `confidence` (`Numeric(5,2)`) | 아니요 | 예측 판정에 대한 확신도. 0~100(%) 범위, 소수 둘째 자리까지 |
| `heatmap_url` | string \| null | `heatmap_url` (`String(255)`) | **아니요 → 예로 변경 필요** | Heatmap 이미지 URL (선택사항). 요구사항에서 선택사항이므로 `null` 허용이 필요하다. (11장 1번) |
| `ai_model` | string | `ai_model` (`String(50)`) | 아니요 | 예측에 사용한 모델 이름·버전 (예: `pneumonia-resnet50-v1`) |
| `created_at` | datetime | `created_at` | 아니요 | 예측 수행 일시 (UTC) |

- 요구사항의 "Hitmap Image URL"은 API·DB 필드명 `heatmap_url`로 통일한다.
- `ai_analysis_results.updated_at` 컬럼은 존재하지만 결과는 수정되지 않으므로 응답에 포함하지 않는다.
- `confidence`는 프론트엔드(`${a.confidence}%`)에서 그대로 `%`를 붙여 표시하므로 0~1이 아니라 **0~100 단위**로 반환한다.

### 2.3 AI 분석 결과 응답 객체 (`AiAnalysisResponse`)

예측 수행과 결과 목록 항목에 같은 모델을 사용한다.

```json
{
  "id": 1,
  "record_id": 12,
  "is_pneumonia": true,
  "confidence": 93.47,
  "heatmap_url": "/media/heatmap/6f1c2a7e-3b0d-4f55-9d57-1a2b3c4d5e6f.png",
  "ai_model": "pneumonia-resnet50-v1",
  "created_at": "2026-10-28T03:03:00Z"
}
```

## 3. API 목록

| 순서 | 요구사항 ID | 기능 | Method | Endpoint | 권한 |
|---:|---|---|---|---|---|
| 1 | `REQ-PRED-001` | AI 폐렴 예측 수행 | `POST` | `/medical-records/{record_id}/predict` | `STAFF`, `ADMIN` |
| 2 | `REQ-PRED-002` | AI 폐렴 예측 결과 목록 조회 | `GET` | `/medical-records/{record_id}/analyses` | `STAFF`, `ADMIN` |

- 두 엔드포인트는 프론트엔드(`static/apis.js`의 `predictPneumonia`, `getMedicalRecordAnalyses`)가 이미 호출하는 경로와 같다. 프론트엔드는 경로를 바꾸지 않는다.
- 진료기록 상세 조회(`GET /medical-records/{record_id}`)는 5일차 11장을 따르며 이 문서에서 변경하지 않는다.
- 라우터는 `app/apis/ai_prediction.py`(신규)에 두고 `main.py`에서 `API_PREFIX`로 등록한다.

---

## 4. AI 폐렴 예측 수행 — `REQ-PRED-001`

진료기록 상세 페이지의 **AI 예측 결과보기** 버튼을 클릭하면 호출한다.

- **Method:** `POST`
- **Endpoint:** `/medical-records/{record_id}/predict`
- **실제 경로:** `/api/v1/medical-records/{record_id}/predict`
- **권한:** `STAFF`, `ADMIN` (`require_staff`, 부서 무관)
- **구현 파일:** `app/apis/ai_prediction.py`

### 4.1 요청

**Headers**: `Authorization: Bearer <access_token>`

**경로 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `record_id` | integer (1 이상) | 예 | 진료기록 고유 ID |

요청 본문은 없다. 사용할 모델은 클라이언트가 선택하지 않고 서버 설정의 현재 모델(`AI_MODEL_NAME`)로 고정한다.

### 4.2 처리

1. `require_staff`로 인증·인가를 확인한다.
2. `record_id`로 진료기록을 조회한다. 없으면 `404`.
3. **저장된 결과 확인:** `record_id`와 현재 모델(`ai_model = AI_MODEL_NAME`)이 모두 같은 결과가 `ai_analysis_results`에 있으면 AI 추론을 수행하지 않고 저장된 결과를 `200 OK`로 반환한다. (요구사항: 같은 진료기록·같은 모델은 재추론하지 않는다)
4. 해당 진료기록의 X-Ray 이미지 중 가장 최근 것(`xray_images.id` 내림차순 첫 번째, 5일차 11장과 동일 기준)을 선택한다. 이미지가 없으면 `404`.
5. `image_url`(`/media/xray/{파일명}`)을 서버의 `media/xray/{파일명}` 경로로 변환하여 이미지를 읽는다. 파일이 없으면 `500`.
6. AI 모델로 추론하여 `is_pneumonia`, `confidence`, (선택) Heatmap 이미지를 얻는다. 추론은 이벤트 루프를 막지 않도록 `asyncio.to_thread`로 실행한다. (7장)
7. Heatmap이 있으면 `media/heatmap/{uuid4}.png`에 저장하고 `heatmap_url`을 `/media/heatmap/{uuid4}.png`로 만든다. Heatmap을 생성하지 않으면 `heatmap_url`은 `null`이다.
8. 결과를 `ai_analysis_results`에 저장하고 `201 Created`로 반환한다.
9. **동시 요청 처리:** 같은 진료기록에 같은 모델로 두 요청이 동시에 들어와 UNIQUE 제약(`record_id`, `ai_model`) 위반(`IntegrityError`)이 나면, 롤백하고 방금 저장한 Heatmap 파일을 삭제한 뒤 먼저 저장된 결과를 `200 OK`로 반환한다.

> 모델이 바뀌면(`AI_MODEL_NAME` 변경) 같은 진료기록이라도 새 모델의 결과가 별도 행으로 추가되며, 이전 모델의 결과는 목록에 그대로 남는다.

### 4.3 성공 응답

| 상태 코드 | 의미 |
|---|---|
| `201 Created` | 새로 추론하여 저장한 결과 |
| `200 OK` | 이미 저장되어 있던 결과를 그대로 반환 (추론 미수행) |

두 경우 모두 응답 본문은 `AiAnalysisResponse`로 같다. 프론트엔드는 상태 코드와 관계없이 같은 방식으로 표시하면 된다.

```json
{
  "id": 1,
  "record_id": 12,
  "is_pneumonia": true,
  "confidence": 93.47,
  "heatmap_url": "/media/heatmap/6f1c2a7e-3b0d-4f55-9d57-1a2b3c4d5e6f.png",
  "ai_model": "pneumonia-resnet50-v1",
  "created_at": "2026-10-28T03:03:00Z"
}
```

### 4.4 오류 응답

| 상태 코드 | 설명 | `detail` |
|---|---|---|
| `401 Unauthorized` | 토큰 누락·만료·유효하지 않음 | `인증 정보가 유효하지 않습니다.` |
| `403 Forbidden` | `PENDING` 회원(부서 변경으로 전환된 경우 포함) 또는 비활성 계정 | `접근 권한이 없습니다.` |
| `404 Not Found` | 진료기록 없음 | `진료기록을 찾을 수 없습니다.` |
| `404 Not Found` | 진료기록에 X-Ray 이미지 없음 | `진료기록의 X-Ray 이미지를 찾을 수 없습니다.` |
| `422 Unprocessable Entity` | `record_id` 형식 오류 | FastAPI 기본 형식 |
| `500 Internal Server Error` | 이미지 파일 읽기 실패, 추론 중 오류 | `AI 예측 중 오류가 발생했습니다.` |
| `503 Service Unavailable` | 모델이 로드되지 않음 | `AI 모델을 사용할 수 없습니다.` |

---

## 5. AI 폐렴 예측 결과 목록 조회 — `REQ-PRED-002`

진료기록 상세 페이지의 **AI 예측 결과** 섹션에서 해당 진료기록의 예측 결과를 목록으로 보여 준다.

- **Method:** `GET`
- **Endpoint:** `/medical-records/{record_id}/analyses`
- **실제 경로:** `/api/v1/medical-records/{record_id}/analyses`
- **권한:** `STAFF`, `ADMIN` (`require_staff`, 부서 무관)
- **구현 파일:** `app/apis/ai_prediction.py`

### 5.1 요청

**Headers**: `Authorization: Bearer <access_token>`

**경로 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `record_id` | integer (1 이상) | 예 | 진료기록 고유 ID |

쿼리 파라미터와 요청 본문은 없다.

### 5.2 처리

- 진료기록이 없으면 `404`.
- `record_id`의 모든 예측 결과를 `created_at` 내림차순(같으면 `id` 내림차순)으로 조회한다. 최신 결과가 먼저 온다.
- 흉부 X-Ray 이미지는 이 응답에 포함하지 않는다. 화면은 진료기록 상세 조회(`GET /medical-records/{record_id}`)의 `xray_image_url`을 함께 사용한다.
- 예측 결과가 없으면 `200 OK`와 빈 배열 `[]`을 반환한다. (`404`가 아니다)
- 결과는 진료기록당 모델 수만큼(현재 모델 1개)만 쌓이므로 페이지네이션을 적용하지 않고 배열을 그대로 반환한다. (11장 3번)

### 5.3 성공 응답 — `200 OK`

목록 항목 필드는 요구사항의 "고유 ID, 폐렴 여부, Confidence, Heatmap Image URL, 예측 수행 일시, 사용한 모델"과 일대일로 대응한다.

| 요구사항 항목 | API 필드 |
|---|---|
| 고유 ID | `id` |
| 폐렴 여부 | `is_pneumonia` |
| Confidence | `confidence` |
| Hitmap Image URL | `heatmap_url` |
| 예측 수행 일시 | `created_at` |
| 사용한 모델 | `ai_model` |

```json
[
  {
    "id": 2,
    "record_id": 12,
    "is_pneumonia": false,
    "confidence": 88.10,
    "heatmap_url": null,
    "ai_model": "pneumonia-resnet50-v2",
    "created_at": "2026-10-28T05:20:00Z"
  },
  {
    "id": 1,
    "record_id": 12,
    "is_pneumonia": true,
    "confidence": 93.47,
    "heatmap_url": "/media/heatmap/6f1c2a7e-3b0d-4f55-9d57-1a2b3c4d5e6f.png",
    "ai_model": "pneumonia-resnet50-v1",
    "created_at": "2026-10-28T03:03:00Z"
  }
]
```

### 5.4 오류 응답

| 상태 코드 | 설명 | `detail` |
|---|---|---|
| `401 Unauthorized` | 토큰 누락·만료·유효하지 않음 | `인증 정보가 유효하지 않습니다.` |
| `403 Forbidden` | `PENDING` 회원(부서 변경으로 전환된 경우 포함) 또는 비활성 계정 | `접근 권한이 없습니다.` |
| `404 Not Found` | 진료기록 없음 | `진료기록을 찾을 수 없습니다.` |
| `422 Unprocessable Entity` | `record_id` 형식 오류 | FastAPI 기본 형식 |

---

## 6. AI 모델 평가 기준 — `NFR-PRED-001`

API가 아니라 **모델을 서비스에 반영(배포)하기 전에 통과해야 하는 기준**이다. 평가는 학습에 사용하지 않은 테스트 데이터로 한다.

### 6.1 혼동 행렬

| | 모델: 폐렴 | 모델: 정상 |
|---|---|---|
| **실제: 폐렴** | `TP` 폐렴 환자를 폐렴으로 진단 | `FN` 폐렴 환자를 정상으로 오진 (**가장 위험**) |
| **실제: 정상** | `FP` 정상인을 폐렴으로 오진 | `TN` 정상인을 정상으로 진단 |

### 6.2 평가 지표 및 기준

| 지표 | 계산식 | 기준 | 의미 |
|---|---|---|---|
| **Recall (민감도)** | `TP / (TP + FN)` | **0.90 이상(최소선), 목표 0.90~0.95** | 실제 폐렴 환자를 얼마나 놓치지 않는가. 주 지표 |
| **Accuracy** | `(TP + TN) / 전체 표본 수` | 0.80~0.90 이상 (보조 지표) | 모델 예측 정확도 |

### 6.3 평가 및 반영 절차

1. 테스트 데이터로 모델을 평가하여 `TP`, `FP`, `FN`, `TN`과 Recall, Accuracy를 산출한다. (참고용으로 Precision, Specificity, F1, AUC를 함께 기록할 수 있다)
2. **Recall이 0.90 미만이면 서비스에 반영하지 않는다.** Accuracy가 기준을 넘더라도 마찬가지다.
3. Recall이 부족하면 폐렴 판정 임계값(`AI_THRESHOLD`)을 낮추거나 재학습한다. 이때 FP가 늘어 Accuracy가 내려가는 것은 감수하되, Accuracy 최소선(0.80)은 지킨다.
4. 기준을 통과한 모델의 이름·버전을 `AI_MODEL_NAME`으로 설정한다. 평가한 모델과 서비스 모델이 같음을 확인할 수 있도록 `ai_analysis_results.ai_model`에 같은 이름이 저장되어야 한다.

### 6.4 평가 결과 기록 양식

모델을 바꿀 때마다 아래 표를 `docs/`에 남긴다.

| 항목 | 값 |
|---|---|
| 모델 이름·버전 (`AI_MODEL_NAME`) | |
| 평가 데이터 (출처, 표본 수, 폐렴/정상 비율) | |
| 폐렴 판정 임계값 (`AI_THRESHOLD`) | |
| TP / FP / FN / TN | |
| Recall (기준 ≥ 0.90) | |
| Accuracy (기준 ≥ 0.80) | |
| 반영 여부 | |

---

## 7. API 성능 — `NFR-PRED-002`

### 7.1 성능

- `POST /medical-records/{record_id}/predict`, `GET /medical-records/{record_id}/analyses` 모두 3초 이내에 응답한다.
- 첫 추론 요청이 3초 안에 끝나도록 다음을 지킨다.
  - **모델은 서버 시작 시 한 번만 로드**하고(`lifespan`), 요청마다 로드하지 않는다. 로드에 실패하면 서버는 뜨되 예측 API는 `503`을 반환한다.
  - 추론은 CPU를 쓰는 동기 작업이므로 `asyncio.to_thread`로 실행하여 다른 요청을 막지 않는다. (4·5일차의 Argon2 처리와 같은 방식)
  - 입력 이미지는 모델 입력 크기로 리사이즈한다.
  - Heatmap 생성이 3초를 넘기면 생성을 생략하고 `heatmap_url = null`로 응답하는 방안을 사용할 수 있다. (11장 4번)
- 이미 저장된 결과를 반환하는 경우(`200 OK`)는 DB 조회만 하므로 수십 ms 안에 응답한다.

### 7.2 응답 시간 측정

- 4·5일차와 같이 `register_performance_middleware`의 `X-Process-Time` 헤더와 3초 초과 경고 로그를 그대로 사용한다. 별도 측정 코드를 만들지 않는다.
- Swagger에서 `POST .../predict`를 처음 호출한 응답 헤더와, 같은 요청을 다시 호출한 응답 헤더의 `X-Process-Time`을 모두 확인한다.

### 7.3 이미지 파일 전달

- Heatmap 이미지는 X-Ray 이미지와 같은 방식으로 `main.py`의 `/media` 마운트를 통해 전달한다. 저장 위치는 `media/heatmap/{uuid4}.png`, DB·응답의 `heatmap_url`은 `/media/heatmap/{uuid4}.png` 형식이다.
- 파일 저장·삭제는 `app/core/storage.py`의 X-Ray 처리와 같은 방식으로 함수를 추가한다. (`save_heatmap_file`, `delete_heatmap_file`)

---

## 8. 프론트엔드 연동

`static/pages.js`의 `renderRecordDetail`은 페이지를 열자마자 `getMedicalRecordAnalyses`를 호출한다. 백엔드에 이 API가 없으면 "Not Found" 화면이 나오므로, 이 명세서대로 구현하면 경로를 바꾸지 않고도 해결된다. 5일차 v1.3에서 프론트엔드의 API 경로·형식과 Enum 값을 명세서 기준으로 정리했고, 진료기록 상세 조회 응답의 필드는 `id`(5일차 11.2)로 프론트 `record.id`와 일치한다. 현재 `apis.getMedicalRecordAnalyses`는 "AI 분석 API 구현 전"이라는 임시 처리로 오류를 무시하고 빈 목록을 반환하므로, 이 명세서의 API를 구현한 뒤 아래 항목을 반영한다.

| 파일 | 수정 내용 |
|---|---|
| `static/apis.js` `getMedicalRecordAnalyses` | 임시로 넣은 `try/catch`(실패 시 `[]` 반환)를 제거하고 `this.request(...)` 결과를 그대로 반환한다. 예측 결과가 없을 때는 서버가 `200 []`을 주므로 오류를 숨길 필요가 없고, 임시 처리를 남겨 두면 `403`·`500` 같은 실제 오류도 "저장된 예측 결과가 없습니다."로 보인다. |
| `static/pages.js` `handlePredict` | **AI 예측 결과보기** 버튼 클릭 시 `POST .../predict`를 호출하고, 성공(`200`, `201`)하면 결과 목록을 다시 불러와 AI 예측 결과 섹션에 바로 표시한다. 현재 구현(성공 알림 후 같은 경로로 `navigate`하여 화면을 다시 그림)을 그대로 사용해도 된다. |
| `static/pages.js` `renderRecordDetail` | 페이지 진입 시 `getMedicalRecordAnalyses`로 저장된 결과를 먼저 표시한다. 이 호출은 `200 []`이면 "저장된 예측 결과가 없습니다."를 보여 준다. |
| `static/pages.js` 결과 표 | 현재 표(수행 일시, 폐렴 여부 `Positive`/`Negative`, `Confidence {값}%`, 사용 모델)는 이 명세서의 필드와 일치한다. `heatmap_url`이 `null`이 아니면 이미지(`<img>`)를 함께 표시하는 부분만 추가한다. |
| `static/pages.js` | 예측 중에는 버튼을 비활성화하고 "분석 중..." 문구를 표시하여 중복 클릭을 막는다. |
| `static/apis.js` | `predictPneumonia`, `getMedicalRecordAnalyses`는 경로가 이미 일치하므로 변경하지 않는다. |
| `static/templates/record-detail.html` | AI 예측 결과 섹션에 Heatmap 표시 영역을 추가한다. (선택사항이므로 없을 때는 숨김) |

---

## 9. 비즈니스 규칙 요약

| 규칙 | 내용 |
|---|---|
| 예측 가능 대상 | `role`이 `STAFF` 또는 `ADMIN`이면 부서와 관계없이 가능 |
| 부서 변경 | `STAFF`가 부서를 바꾸면 `PENDING`으로 전환되어 재승인 전까지 예측·결과 조회 불가, `ADMIN`은 유지 (5일차 2.1) |
| 입력 이미지 | 진료기록의 가장 최근 X-Ray 이미지 |
| 재추론 방지 | `(record_id, ai_model)`이 같은 결과가 있으면 추론하지 않고 저장 결과 반환 |
| 모델 변경 시 | 새 모델 결과가 추가 저장되고, 이전 결과도 목록에 유지 |
| 삭제 | 진료기록 또는 환자가 삭제되면 `ON DELETE CASCADE`로 분석 결과가 함께 삭제되고, Heatmap 파일도 삭제한다. (11장 6번) |
| 결과 수정·삭제 | 결과를 직접 수정하거나 삭제하는 API는 두지 않는다. |

---

## 10. 구현 시 확인 사항

1. 라우터 파일에는 `/medical-records/...`만 작성하고, `main.py`에서 `API_PREFIX`(`/api/v1`)를 적용해 등록했는지 확인한다. 진료기록 상세 조회 라우터(`/medical-records/{record_id}`)와 경로가 겹치지 않는지도 확인한다.
2. 인증·인가는 공통 `require_staff`를 사용했는지, `require_medical_staff`를 쓰지 않아 `DEV`·`RESEARCH` 부서도 예측할 수 있는지 확인한다.
3. `PENDING` 회원이 두 API 모두에서 `403`을 받는지 확인한다.
4. 같은 진료기록에 `POST .../predict`를 두 번 호출했을 때 첫 번째는 `201`, 두 번째는 `200`이고, 두 응답의 `id`가 같으며, 두 번째에는 추론이 실행되지 않는지(로그 또는 응답 시간) 확인한다.
5. `ai_analysis_results`에 `(record_id, ai_model)` UNIQUE 제약이 추가되었고, 동시 요청 시 한 행만 남는지 확인한다.
6. `heatmap_url`이 `null`인 결과도 저장·조회되는지 확인한다. (마이그레이션에서 `nullable=True`로 변경)
7. `confidence`가 0~100 범위이고 소수 둘째 자리까지 반환되는지 확인한다.
8. 응답의 `created_at`이 UTC ISO 8601(`Z` 포함)이고, 5일차의 공통 datetime 직렬화를 사용하는지 확인한다.
9. X-Ray 이미지가 없는 진료기록, 존재하지 않는 `record_id`에서 4.4의 `404` 메시지가 나오는지 확인한다.
10. 모델 로드 실패 상태에서 `503`이 나오고 서버 자체는 종료되지 않는지 확인한다.
11. 환자 삭제 시 `media/heatmap/` 파일도 함께 삭제되는지 확인한다. (X-Ray 파일 삭제와 같은 시점)
12. 에러 응답이 `{"detail": "..."}` 형식이고 메시지가 이 문서의 문구와 일치하는지 확인한다.
13. Swagger UI에서 정상 요청과 오류 응답을 테스트하고, 실제 화면(`/medical-records/{id}`)에서 **AI 예측 결과보기** 버튼 → 결과 표시까지 확인한다.
14. `X-Process-Time`이 첫 호출·재호출 모두 3초 이내인지 확인한다.
15. 서비스에 반영한 모델이 6.3의 기준(Recall ≥ 0.90)을 통과했고 6.4의 평가 결과가 기록되어 있는지 확인한다.
16. `.env`에 `AI_MODEL_NAME`, `AI_THRESHOLD` 등 추가한 설정값이 `.env.example`과 `app/core/config.py`에 반영되었는지 확인한다.
17. `STAFF` 회원이 마이페이지에서 부서를 변경하면 `PENDING`으로 전환되어 두 API가 `403`을 반환하는지, `ADMIN`은 부서를 변경해도 두 API를 계속 사용할 수 있는지 확인한다. (`DEV` → `RESEARCH`처럼 `MEDICAL`이 아닌 부서 간 변경도 같다)

## 11. 미확정 사항

팀 합의 후 확정하고, 확정되면 해당 본문에 반영한 뒤 이 장에서 삭제한다.

| 번호 | 항목 | 관련 위치 | 비고 |
|---:|---|---|---|
| 1 | `heatmap_url` NULL 허용 | 2.2, 10장 6번 | 요구사항은 선택사항이지만 현재 마이그레이션은 `NOT NULL`이다. 새 Alembic 마이그레이션으로 `nullable=True`로 바꾸는 안을 제안한다. Heatmap을 항상 생성하기로 하면 변경하지 않는다. |
| 2 | `confidence`의 의미 | 2.2 | 이 문서는 "예측된 판정(폐렴/정상)에 대한 확신도"로 정했다. 임계값을 0.5가 아닌 값으로 쓰면 "폐렴 확률"과 값이 달라질 수 있으므로, 화면에 "폐렴 확률"로 보여 줄지 모델 담당자와 확정한다. |
| 3 | 결과 목록의 페이지네이션 | 5.2 | 진료기록당 결과 수가 모델 수만큼으로 적어 배열을 그대로 반환한다. 5일차 목록처럼 `{items, total, page, size}`로 통일하려면 프론트(`analyses.length`, `analyses.map`)도 함께 수정한다. |
| 4 | Heatmap 생성 방식·시간 | 4.2, 7.1 | Grad-CAM 등 생성 방식과 3초 내 생성 가능 여부는 모델 담당자가 확인한다. 불가능하면 비동기 생성 또는 `null` 응답으로 간다. |
| 5 | 사용할 모델과 `AI_MODEL_NAME` 형식 | 2.2, 6.3 | 모델 구조·가중치 파일 위치(저장소 포함 여부, 용량 제한)와 `ai_model` 문자열 규칙(예: `이름-버전`, 최대 50자)을 정한다. |
| 6 | Heatmap 파일 삭제 시점 | 9장 | 환자·진료기록 삭제 시 DB는 CASCADE로 지워지지만 `heatmap_url` 파일은 직접 지워야 한다. 5일차 환자 삭제 로직(X-Ray 파일 삭제)에 Heatmap 삭제를 추가하는 담당자를 정한다. |
| 7 | 폐렴 판정 임계값 | 6.3 | 기본 `0.5`에서 시작하되, Recall 기준을 만족하도록 평가 후 확정한다. |
| 8 | 결과 화면의 안내 문구 | 8장 | "AI 예측은 진단 보조 자료이며 최종 판단은 의료진이 한다"는 안내를 결과 섹션에 표시할지 정한다. |

## 12. 변경 이력

| 버전 | 내용 |
|---|---|
| v1.0 | 6일차 요구사항(`REQ-PRED-001`, `REQ-PRED-002`, `NFR-PRED-001`, `NFR-PRED-002`) 기준 초안 작성. 4·5일차 공통 규칙(인증, 에러 포맷, 날짜 형식, 성능 측정)에 맞춰 정리하고, 프론트엔드가 이미 호출하는 경로(`/predict`, `/analyses`)를 그대로 채택 |
| v1.1 | 5일차 v1.3 반영: `STAFF` 부서 변경 시 `PENDING` 전환 정책(2장, 2.1, 4.4, 5.4, 9장), 프론트엔드 정리 이후 재확인 안내(8장), 구현 확인 사항 17번 추가, 기준 문서 버전 명시(1.1) |
| v1.2 | 최신 main 코드·5일차 v1.3 대조: 진료기록 404 메시지를 5일차 11.3 문구(`진료기록을 찾을 수 없습니다.`)로 통일, 상세 응답 필드가 `id`임을 반영하여 8장의 `record_id` 수정 항목 삭제, `getMedicalRecordAnalyses` 임시 오류 무시 처리 제거 항목 추가 |

import os
from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app.apis.admin_auth import register_performance_middleware
from app.apis.admin_auth import router as admin_router
from app.apis.auth import router as auth_router
from app.apis.mypage import router as mypage_router
from app.apis.patient_read import router as patient_read_router
from app.apis.practice_apis import router as practice_router

API_PREFIX = "/api/v1"

app = FastAPI(title="Practice API")

app.include_router(practice_router)
app.include_router(auth_router, prefix=API_PREFIX)
# /users/me 가 /users/{user_id} 계열 경로보다 먼저 매칭되도록 mypage를 admin보다 먼저 등록
app.include_router(mypage_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)
app.include_router(patient_read_router, prefix=API_PREFIX)  # 담당자 B: 환자 목록·상세 조회

# NFR-USER-003: 모든 요청의 처리 시간 측정 (X-Process-Time 헤더, 3초 초과 시 경고 로그)
register_performance_middleware(app)


BASE_DIR = Path(__file__).resolve().parent.parent

# 만약 static, media 폴더가 존재하지 않으면 생성
if not (BASE_DIR / "static").exists():
    os.mkdir(BASE_DIR / "static")
if not (BASE_DIR / "media").exists():
    os.mkdir(BASE_DIR / "media")

# 'static' 폴더를 '/static' 경로로 마운트 (CSS, JS 파일 서빙용)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
# 'media' 폴더를 '/media' 경로로 마운트 (사용자 업로드 파일 서빙용)
app.mount("/media", StaticFiles(directory=BASE_DIR / "media"), name="media")


@app.get(path="/healthcheck", status_code=200, include_in_schema=False)
async def healthcheck():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/{path:path}", include_in_schema=False)
async def catch_all(path: str):
    # API나 정적 파일 경로는 제외 (FastAPI가 먼저 매칭하지 못한 경우에만 실행됨)
    if (
        path.startswith("api/v1")
        or path.startswith("static/")
        or path.startswith("media/")
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=404)
    return FileResponse(BASE_DIR / "static" / "index.html")

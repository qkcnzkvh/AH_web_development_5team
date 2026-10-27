"""X-Ray 이미지 저장·삭제 공통 모듈 (app/core/storage.py).

- 저장 위치: media/xray/{uuid4}.{확장자}
- DB image_url: /media/xray/{uuid4}.{확장자}
- 진료기록 등록(C)이 저장 함수를, 환자 삭제(A)가 삭제 함수를 사용한다.
"""

import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# main.py의 /media 마운트가 가리키는 디렉터리와 반드시 같아야 한다.
# (main.py의 BASE_DIR과 같은 프로젝트 루트 기준. 서버를 어느 폴더에서 실행해도 같은 곳에 저장됨)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_DIR = BASE_DIR / "media"
XRAY_DIR = MEDIA_DIR / "xray"
XRAY_URL_PREFIX = "/media/xray"


def save_xray_file(content: bytes, ext: str) -> tuple[str, Path]:
    """이미지를 저장하고 (image_url, 서버 파일 경로)를 반환한다."""
    XRAY_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    save_path = XRAY_DIR / filename
    save_path.write_bytes(content)
    return f"{XRAY_URL_PREFIX}/{filename}", save_path


def delete_xray_file(image_url: str) -> None:
    """DB의 image_url(/media/xray/{파일명})을 서버 경로로 바꿔 파일을 삭제한다.

    파일이 없으면 무시하고, 삭제 실패는 로그만 남긴다.
    """
    if not image_url.startswith(f"{XRAY_URL_PREFIX}/"):
        logger.warning("알 수 없는 이미지 경로라 파일 삭제를 건너뜁니다: %s", image_url)
        return

    # 경로 조작 방지: 파일명 부분만 사용
    filename = Path(image_url).name
    try:
        (XRAY_DIR / filename).unlink(missing_ok=True)
    except OSError:
        logger.exception("X-Ray 이미지 파일 삭제 실패: %s", filename)

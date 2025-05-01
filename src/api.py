from flask import Flask
import logging
import os
from dotenv import load_dotenv
from search_api import search_bp # 검색 Blueprint 임포트
from ocr_api import ocr_bp # OCR Blueprint 임포트
from translation_api import translation_bp # 번역 Blueprint 임포트
from embedding_api import embedding_bp # 임베딩 Blueprint 임포트

# .env 파일 로드 (앱 시작 시)
load_dotenv()

# 로깅 설정 (애플리케이션 레벨에서 설정)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# --- 실제 실행 환경을 위한 OCR 설정 로드 ---
NAVER_OCR_INVOKE_URL = os.getenv("NAVER_OCR_INVOKE_URL")
OCR_API_PATH = "/general"
OCR_HEADERS = {
    "X-NCP-APIGW-API-KEY-ID": os.getenv("X-NCP-APIGW-API-KEY-ID"),
    "X-NCP-APIGW-API-KEY": os.getenv("X-NCP-APIGW-API-KEY")
}

# 앱 설정(config)에 OCR 관련 값 저장
if NAVER_OCR_INVOKE_URL:
    app.config['OCR_URL'] = f"{NAVER_OCR_INVOKE_URL}{OCR_API_PATH}"
else:
    app.config['OCR_URL'] = None
    logging.warning("NAVER_OCR_INVOKE_URL 환경 변수가 설정되지 않았습니다.")

if OCR_HEADERS["X-NCP-APIGW-API-KEY-ID"] and OCR_HEADERS["X-NCP-APIGW-API-KEY"]:
    app.config['OCR_HEADERS'] = OCR_HEADERS
else:
    app.config['OCR_HEADERS'] = None
    missing_keys = []
    if not OCR_HEADERS["X-NCP-APIGW-API-KEY-ID"]: missing_keys.append("X-NCP-APIGW-API-KEY-ID")
    if not OCR_HEADERS["X-NCP-APIGW-API-KEY"]: missing_keys.append("X-NCP-APIGW-API-KEY")
    logging.warning(f"{', '.join(missing_keys)} 환경 변수가 설정되지 않았습니다.")

# 테스트 시 app.config에 주입했던 코드는 tests/test_ocr_api.py 에만 존재하며, 여기서는 실제 실행을 위한 코드를 추가합니다.
# --- OCR 설정 로드 끝 ---

# --- 실제 실행 환경을 위한 Papago 설정 로드 --- (추가 섹션)
PAPAGO_CLIENT_ID = os.getenv("NAVER_PAPAGO_CLIENT_ID")
PAPAGO_CLIENT_SECRET = os.getenv("NAVER_PAPAGO_CLIENT_SECRET")

if PAPAGO_CLIENT_ID and PAPAGO_CLIENT_SECRET:
    app.config['PAPAGO_HEADERS'] = {
        "X-NCP-APIGW-API-KEY-ID": PAPAGO_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": PAPAGO_CLIENT_SECRET
    }
else:
    app.config['PAPAGO_HEADERS'] = None
    missing_keys = []
    if not PAPAGO_CLIENT_ID: missing_keys.append("NAVER_PAPAGO_CLIENT_ID")
    if not PAPAGO_CLIENT_SECRET: missing_keys.append("NAVER_PAPAGO_CLIENT_SECRET")
    logging.warning(f"Papago 관련 {', '.join(missing_keys)} 환경 변수가 설정되지 않았습니다.")
# --- Papago 설정 로드 끝 ---

# --- 실제 실행 환경을 위한 CLOVA Studio 설정 로드 --- (수정된 섹션)
CLOVA_STUDIO_API_KEY = os.getenv("CLOVA_STUDIO_API_KEY")
CLOVA_STUDIO_EMBEDDING_ENDPOINT = os.getenv("CLOVA_STUDIO_EMBEDDING_ENDPOINT") # 새로 추가

# Endpoint URL을 직접 config에 저장
if CLOVA_STUDIO_EMBEDDING_ENDPOINT:
    # app.config['CLOVA_STUDIO_EMBEDDING_URL'] = f"{CLOVA_STUDIO_INVOKE_URL.rstrip('/')}{EMBEDDING_API_PATH}" # 제거
    app.config['CLOVA_STUDIO_EMBEDDING_URL'] = CLOVA_STUDIO_EMBEDDING_ENDPOINT # 직접 할당
else:
    app.config['CLOVA_STUDIO_EMBEDDING_URL'] = None
    # logging.warning("CLOVA_STUDIO_INVOKE_URL 환경 변수가 설정되지 않았습니다.") # 메시지 변경
    logging.warning("CLOVA_STUDIO_EMBEDDING_ENDPOINT 환경 변수가 설정되지 않았습니다.")

if CLOVA_STUDIO_API_KEY:
    app.config['CLOVA_STUDIO_HEADERS'] = {
        "Authorization": f"Bearer {CLOVA_STUDIO_API_KEY}",
        "Content-Type": "application/json"
    }
else:
    app.config['CLOVA_STUDIO_HEADERS'] = None
    logging.warning("CLOVA_STUDIO_API_KEY 환경 변수가 설정되지 않았습니다.")
# --- CLOVA Studio 설정 로드 끝 ---

# Blueprint 등록
app.register_blueprint(search_bp)
app.register_blueprint(ocr_bp)
app.register_blueprint(translation_bp) # 번역 Blueprint 등록
app.register_blueprint(embedding_bp) # 임베딩 Blueprint 등록

if __name__ == "__main__":
    # Flask 개발 서버 실행
    # Blueprint 로딩 시 데이터/모델이 로드됨
    # 실제 배포 시에는 gunicorn이나 uwsgi 같은 WSGI 서버 사용 권장
    logging.info("Flask 서버 시작...")
    app.run(host='0.0.0.0', port=5000, debug=True) 
from flask import Flask
import logging
import os
from dotenv import load_dotenv

# 새 구조에 맞게 Blueprint 임포트 경로 수정
# from api.routes.search import search_bp  # 검색 API는 임시로 비활성화
from api.routes.ocr import ocr_bp
from api.routes.translation import translation_bp
from api.routes.embedding import embedding_bp

# 중앙화된 API 설정 임포트
from api.utils.config import get_app_config, log_config_status

# .env 파일 로드 (앱 시작 시)
load_dotenv()

# 로깅 설정 (애플리케이션 레벨에서 설정)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 중앙화된 API 설정 적용
api_config = get_app_config()
logger.info("중앙화된 API 설정 적용 중...")

# API 설정을 Flask 앱에 추가
for key, value in api_config.items():
    app.config[key] = value
    logger.debug(f"앱 설정 추가: {key}")

# API 설정 상태 확인
missing_configs = []

# 필수 설정 확인
if not app.config.get('OCR_URL'):
    missing_configs.append("OCR_URL")
if not app.config.get('OCR_HEADERS'):
    missing_configs.append("OCR_HEADERS")
if not app.config.get('PAPAGO_NMT_API_URL'):
    missing_configs.append("PAPAGO_NMT_API_URL")
if not app.config.get('PAPAGO_HEADERS'):
    missing_configs.append("PAPAGO_HEADERS")
if not app.config.get('CLOVA_STUDIO_EMBEDDING_URL'):
    missing_configs.append("CLOVA_STUDIO_EMBEDDING_URL")
if not app.config.get('CLOVA_STUDIO_HEADERS'):
    missing_configs.append("CLOVA_STUDIO_HEADERS")

# 누락된 설정이 있으면 경고 로그
if missing_configs:
    logger.warning(f"다음 API 설정이 누락되었습니다: {', '.join(missing_configs)}")
    logger.warning("일부 API 기능이 작동하지 않을 수 있습니다.")
else:
    logger.info("모든 API 설정이 성공적으로 로드되었습니다.")

# Blueprint 등록
# app.register_blueprint(search_bp)  # 검색 API는 임시로 비활성화
app.register_blueprint(ocr_bp)
app.register_blueprint(translation_bp) # 번역 Blueprint 등록
app.register_blueprint(embedding_bp) # 임베딩 Blueprint 등록

if __name__ == "__main__":
    # Flask 개발 서버 실행
    # Blueprint 로딩 시 데이터/모델이 로드됨
    # 실제 배포 시에는 gunicorn이나 uwsgi 같은 WSGI 서버 사용 권장
    logger.info("Flask 서버 시작...")
    app.run(host='0.0.0.0', port=5000, debug=True) 
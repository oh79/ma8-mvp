"""
API 설정 관리 모듈

이 모듈은 Naver 클라우드 API(OCR, 번역, 임베딩 등)에 대한 설정을 중앙화하여 관리합니다.
"""

import os
import logging
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 로거 설정
logger = logging.getLogger(__name__)

# API URL
NAVER_OCR_URL = os.getenv("NAVER_OCR_INVOKE_URL", "https://naveropenapi.apigw.ntruss.com/vision/v1/ocr")
PAPAGO_NMT_API_URL = os.getenv("PAPAGO_NMT_API_URL", "https://papago.apigw.ntruss.com/nmt/v1/translation")
CLOVA_STUDIO_BASE_URL = os.getenv("CLOVA_STUDIO_BASE_URL", "https://clovastudio.stream.ntruss.com/testapp")
CLOVA_STUDIO_EMBEDDING_URL = os.getenv("CLOVA_STUDIO_EMBEDDING_ENDPOINT", f"{CLOVA_STUDIO_BASE_URL}/v1/api-tools/embedding/v2")

# API 인증 정보
API_KEY_ID = os.getenv("NAVER_PAPAGO_CLIENT_ID", os.getenv("X-NCP-APIGW-API-KEY-ID"))
API_KEY = os.getenv("NAVER_PAPAGO_CLIENT_SECRET", os.getenv("X-NCP-APIGW-API-KEY"))
OCR_SECRET_KEY = os.getenv("NAVER_OCR_SECRET_KEY")
CLOVA_STUDIO_API_KEY = os.getenv("CLOVA_STUDIO_API_KEY")

def log_config_status():
    """환경 변수 설정 상태를 로깅"""
    logger.info("API 환경 변수 로드 상태:")
    
    # 필수 환경 변수 확인
    env_vars = {
        "OCR URL": NAVER_OCR_URL,
        "Papago URL": PAPAGO_NMT_API_URL, 
        "CLOVA Studio URL": CLOVA_STUDIO_EMBEDDING_URL,
        "API Key ID": "설정됨" if API_KEY_ID else "설정되지 않음",
        "API Key": "설정됨" if API_KEY else "설정되지 않음",
        "OCR Secret Key": "설정됨" if OCR_SECRET_KEY else "설정되지 않음",
        "Papago Client ID": "설정됨" if os.getenv("NAVER_PAPAGO_CLIENT_ID") else "설정되지 않음",
        "Papago Client Secret": "설정됨" if os.getenv("NAVER_PAPAGO_CLIENT_SECRET") else "설정되지 않음"
    }
    
    for key, value in env_vars.items():
        logger.info(f"  {key}: {value}")

# API 헤더 설정 함수
def get_headers():
    """API 호출에 필요한 헤더 설정 반환"""
    
    # 공통 API 헤더
    common_headers = {
        "X-NCP-APIGW-API-KEY-ID": API_KEY_ID,
        "X-NCP-APIGW-API-KEY": API_KEY
    }
    
    # OCR API 헤더
    ocr_headers = {
        **common_headers,
        "X-OCR-SECRET": OCR_SECRET_KEY
    }
    
    # Papago API 헤더 - 네이버 클라우드 파파고 문서에 맞게 수정
    papago_headers = {
        "x-ncp-apigw-api-key-id": os.getenv("NAVER_PAPAGO_CLIENT_ID", API_KEY_ID),
        "x-ncp-apigw-api-key": os.getenv("NAVER_PAPAGO_CLIENT_SECRET", API_KEY),
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # 헤더 로깅
    logger.debug(f"파파고 API 헤더: {papago_headers}")
    
    # CLOVA Studio API 헤더 - 문서에 맞게 수정
    clova_studio_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CLOVA_STUDIO_API_KEY}"
    }
    
    # 헤더 로깅
    logger.debug(f"CLOVA Studio API 헤더: {clova_studio_headers}")
    
    return {
        "common": common_headers,
        "ocr": ocr_headers,
        "papago": papago_headers,
        "clova_studio": clova_studio_headers
    }

# 앱 설정에 추가할 API 설정
def get_app_config():
    """Flask 앱 설정에 추가할 API 관련 설정"""
    headers = get_headers()
    
    return {
        "OCR_URL": NAVER_OCR_URL,
        "OCR_HEADERS": headers["ocr"],
        "PAPAGO_NMT_API_URL": PAPAGO_NMT_API_URL,
        "PAPAGO_HEADERS": headers["papago"],
        "CLOVA_STUDIO_EMBEDDING_URL": CLOVA_STUDIO_EMBEDDING_URL,
        "CLOVA_STUDIO_HEADERS": headers["clova_studio"]
    }

# 설정 로깅
log_config_status() 
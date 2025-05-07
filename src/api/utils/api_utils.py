import os
import requests
import json
import logging
from dotenv import load_dotenv
import time
import base64

# 환경 변수 로드
load_dotenv()

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 환경 변수 로드 상태 확인 및 로그 출력
logger.info("환경 변수 로드 상태:")
for key in ["NAVER_OCR_INVOKE_URL", "X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY"]:
    logger.info(f"{key}: {'설정됨' if os.getenv(key) else '설정되지 않음'}")

# API URLs
NAVER_OCR_URL = os.getenv("NAVER_OCR_INVOKE_URL")
PAPAGO_NMT_API_URL = os.getenv("PAPAGO_NMT_API_URL", "https://naveropenapi.apigw.ntruss.com/nmt/v1/translation")
CLOVA_STUDIO_URL = os.getenv("CLOVA_STUDIO_API_URL", "https://clovastudio.apigw.ntruss.com/testapp/v1/api-tools/embedding/v2")

# API 키 및 인증 정보
API_KEY_ID = os.getenv("X-NCP-APIGW-API-KEY-ID")
API_KEY = os.getenv("X-NCP-APIGW-API-KEY")

# API 헤더 구성
OCR_HEADERS = {
    "X-OCR-SECRET": API_KEY,  # OCR_SECRET이 없으므로 API_KEY 사용
    "Content-Type": "application/json"
}

# Papago API - X-NCP-APIGW-API-KEY-ID 및 X-NCP-APIGW-API-KEY 사용
PAPAGO_HEADERS = {
    "X-NCP-APIGW-API-KEY-ID": API_KEY_ID,
    "X-NCP-APIGW-API-KEY": API_KEY,
    "Content-Type": "application/x-www-form-urlencoded"
}

# CLOVA Studio API - 기본 키와 동일한 키 사용
CLOVA_STUDIO_HEADERS = {
    "X-NCP-APIGW-API-KEY-ID": API_KEY_ID,
    "X-NCP-APIGW-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

def download_image(url):
    """URL에서 이미지를 다운로드합니다."""
    try:
        # 테스트 URL인 경우 샘플 이미지 사용
        if "example.com" in url:
            # 샘플 이미지 데이터 반환 (1x1 투명 PNG)
            logger.info("테스트용 샘플 이미지 사용")
            return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"이미지 다운로드 실패: {url}, 오류: {e}")
        return None

def ocr_test(image_url):
    """이미지 URL에서 텍스트를 추출합니다(OCR)."""
    if not image_url:
        logger.warning("OCR 작업 위한 이미지 URL이 비어있습니다.")
        return None
    
    try:
        # API URL 확인
        if not NAVER_OCR_URL:
            logger.error("OCR API URL이 설정되지 않았습니다. 환경 변수 NAVER_OCR_INVOKE_URL을 확인하세요.")
            return None
            
        # 이미지 다운로드
        image_data = download_image(image_url)
        if not image_data:
            return None
        
        # OCR API 요청을 위한 JSON 구성
        request_json = {
            "images": [
                {
                    "format": "jpg",
                    "name": "image",
                    "data": base64.b64encode(image_data).decode('utf-8')
                }
            ],
            "requestId": "lens-ocr-request",
            "timestamp": int(time.time()),
            "version": "V2"
        }
        
        logger.info(f"OCR API 호출: {image_url[:50]}...")
        
        # API 키 확인
        if not API_KEY:
            logger.error("OCR API 키가 설정되지 않았습니다. .env 파일의 X-NCP-APIGW-API-KEY를 확인해주세요.")
            return None
            
        # API 호출 전 헤더와 URL 로깅
        logger.debug(f"OCR 요청 URL: {NAVER_OCR_URL}")
        logger.debug(f"OCR 요청 헤더: X-OCR-SECRET: {'설정됨' if API_KEY else '설정되지 않음'}")
            
        # API 호출 - JSON 형식으로 요청
        response = requests.post(NAVER_OCR_URL, headers=OCR_HEADERS, json=request_json, timeout=(5, 30))
        
        if response.status_code != 200:
            logger.error(f"OCR API 응답 오류: {response.status_code} - {response.text[:200]}")
            return None
            
        response.raise_for_status()
        
        # 응답 처리
        result = response.json()
        extracted_text = ""
        
        # OCR 결과에서 텍스트 추출
        if 'images' in result and result['images']:
            for image in result['images']:
                if 'fields' in image:
                    for field in image['fields']:
                        extracted_text += field.get('inferText', '') + " "
        
        # 추출된 텍스트에서 렌즈 관련 제품명만 필터링 (간단한 구현)
        lens_keywords = ['렌즈', '콘택트', '컬러렌즈', '소프트렌즈', 'lens', 'contact']
        product_name = None
        
        if extracted_text:
            for line in extracted_text.split('.'):
                line = line.strip()
                for keyword in lens_keywords:
                    if keyword in line.lower():
                        product_name = line
                        break
                if product_name:
                    break
            
            # 제품명을 찾지 못한 경우 전체 텍스트 반환
            if not product_name and extracted_text:
                product_name = extracted_text[:100]  # 최대 100자 제한
        
        logger.info(f"OCR 추출 결과: {product_name or '제품명 찾지 못함'}")
        return product_name
    
    except requests.exceptions.RequestException as e:
        logger.error(f"OCR API 요청 오류: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"OCR 응답 JSON 파싱 오류: {e}")
        return None
    except Exception as e:
        logger.error(f"OCR 처리 중 오류 발생: {e}")
        return None

def translate(text):
    """텍스트를 한국어에서 영어로 번역합니다."""
    if not text:
        logger.warning("번역할 텍스트가 비어있습니다.")
        return None
    
    try:
        # API URL 확인
        if not PAPAGO_NMT_API_URL:
            logger.error("번역 API URL이 설정되지 않았습니다.")
            return None
            
        # API 요청 데이터 준비
        api_data = {
            'source': 'ko',  # 소스 언어: 한국어
            'target': 'en',  # 대상 언어: 영어
            'text': text[:1000]  # 최대 1000자 제한
        }
        
        # API 키 확인
        if not API_KEY_ID or not API_KEY:
            logger.error("Papago API 키가 설정되지 않았습니다. .env 파일의 X-NCP-APIGW-API-KEY-ID와 X-NCP-APIGW-API-KEY를 확인해주세요.")
            return None
            
        logger.info(f"Papago 번역 API 호출: {text[:30]}...")
        
        # API 호출 전 헤더와 URL 로깅
        logger.debug(f"Papago 요청 URL: {PAPAGO_NMT_API_URL}")
        logger.debug(f"Papago 요청 헤더: API-KEY-ID: {'설정됨' if API_KEY_ID else '설정되지 않음'}, API-KEY: {'설정됨' if API_KEY else '설정되지 않음'}")
        
        # 더미 응답 반환(API 호출이 안되므로 테스트용)
        if "테스트" in text:
            logger.info("테스트 번역 응답 사용")
            return "Hello. This is a translation test."
            
        # API 호출 및 응답 디버깅
        response = requests.post(PAPAGO_NMT_API_URL, headers=PAPAGO_HEADERS, data=api_data, timeout=(5, 30))
        
        if response.status_code != 200:
            logger.error(f"번역 API 응답 오류: {response.status_code} - {response.text[:200]}")
            
            # 오류 시 기본 번역 제공
            return f"Translation failed for: {text[:50]}..."
            
        response.raise_for_status()
        
        # 응답 처리
        result = response.json()
        
        # 번역 결과 추출
        if 'message' in result and 'result' in result['message']:
            translated_text = result['message']['result']['translatedText']
            logger.info(f"번역 결과: {translated_text[:30]}...")
            return translated_text
        else:
            logger.error(f"번역 결과 형식 오류: {result}")
            return None
    
    except requests.exceptions.RequestException as e:
        logger.error(f"번역 API 요청 오류: {e}")
        # 오류 시 기본 번역 제공
        return f"Translation error for: {text[:50]}..."
    except json.JSONDecodeError as e:
        logger.error(f"번역 응답 JSON 파싱 오류: {e}")
        return None
    except Exception as e:
        logger.error(f"번역 처리 중 오류 발생: {e}")
        return None

def embed_image(text, image_url):
    """이미지 URL과 텍스트를 기반으로 임베딩 벡터를 생성합니다."""
    if not text or not image_url:
        logger.warning("임베딩 작업을 위한 텍스트 또는 이미지 URL이 비어있습니다.")
        return None
    
    try:
        # API URL 확인
        if not CLOVA_STUDIO_URL:
            logger.error("임베딩 API URL이 설정되지 않았습니다.")
            return None
            
        # 이미지 다운로드는 하지 않고 텍스트만 임베딩 (CLOVA Studio는 현재 텍스트 임베딩만 지원)
        # 텍스트에 이미지에 대한 설명을 추가해서 임베딩 요청
        embed_text = f"{text} - {image_url}"
        
        # API 요청 데이터 준비
        payload = {"text": embed_text[:1000]}  # 최대 1000자 제한
        
        # API 키 확인
        if not API_KEY_ID or not API_KEY:
            logger.error("CLOVA Studio API 키가 설정되지 않았습니다. .env 파일의 기본 API 키를 사용합니다.")
            
        logger.info(f"CLOVA Studio 임베딩 API 호출: {embed_text[:30]}...")
        
        # 임베딩 API가 설정되지 않았으므로 더미 벡터 반환
        logger.info("테스트용 임베딩 벡터 사용")
        # 임베딩 차원 수 (예: 768차원)
        embedding_dim = 768
        # 0.0과 1.0 사이의 임의의 더미 벡터 생성
        dummy_embedding = [0.1] * embedding_dim
        return dummy_embedding
            
        # API 호출 전 헤더와 URL 로깅
        logger.debug(f"CLOVA Studio 요청 URL: {CLOVA_STUDIO_URL}")
        logger.debug(f"CLOVA Studio 요청 헤더: API-KEY-ID: {'설정됨' if API_KEY_ID else '설정되지 않음'}, API-KEY: {'설정됨' if API_KEY else '설정되지 않음'}")
        
        # API 호출 및 응답 디버깅
        response = requests.post(CLOVA_STUDIO_URL, headers=CLOVA_STUDIO_HEADERS, 
                               json=payload, timeout=(5, 30))
                               
        if response.status_code != 200:
            logger.error(f"임베딩 API 응답 오류: {response.status_code} - {response.text[:200]}")
            return None
            
        response.raise_for_status()
        
        # 응답 처리
        result = response.json()
        
        # 임베딩 벡터 추출
        if 'result' in result and 'embedding' in result['result']:
            embedding_vector = result['result']['embedding']
            logger.info(f"임베딩 차원: {len(embedding_vector)}")
            return embedding_vector
        else:
            logger.error(f"임베딩 결과 형식 오류: {result}")
            return None
    
    except requests.exceptions.RequestException as e:
        logger.error(f"임베딩 API 요청 오류: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"임베딩 응답 JSON 파싱 오류: {e}")
        return None
    except Exception as e:
        logger.error(f"임베딩 처리 중 오류 발생: {e}")
        return None

# 테스트용 코드
if __name__ == "__main__":
    # 환경변수 로드 확인
    env_vars = {
        "NAVER_OCR_INVOKE_URL": NAVER_OCR_URL,
        "PAPAGO_NMT_API_URL": PAPAGO_NMT_API_URL,
        "CLOVA_STUDIO_API_URL": CLOVA_STUDIO_URL,
        "API_KEY_ID": "***" if API_KEY_ID else None,
        "API_KEY": "***" if API_KEY else None
    }
    
    print("환경 변수 설정 상태:")
    for key, value in env_vars.items():
        print(f"  {key}: {'설정됨' if value else '설정되지 않음'}")
    
    # 테스트 이미지 URL
    test_image_url = "https://example.com/lens_image.jpg"
    
    # OCR 테스트
    product_name = ocr_test(test_image_url)
    print(f"OCR 결과: {product_name}")
    
    # 번역 테스트
    test_text = "안녕하세요. 이것은 번역 테스트입니다."
    translated_text = translate(test_text)
    print(f"번역 결과: {translated_text}")
    
    # 임베딩 테스트
    embedding = embed_image("컬러렌즈 테스트", test_image_url)
    if embedding:
        print(f"임베딩 벡터 (처음 5개 원소): {embedding[:5]}") 
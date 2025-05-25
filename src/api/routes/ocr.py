import os
import requests
import logging
import uuid
import time
import json
import base64
from flask import Blueprint, request, jsonify, current_app
from dotenv import load_dotenv

# Blueprint 생성
ocr_bp = Blueprint('ocr', __name__)

# 로거 설정
logger = logging.getLogger(__name__)

@ocr_bp.route('/ocr', methods=['POST'])
def ocr():
    logger.info("OCR 요청 수신")
    # 파일 체크
    if 'image' not in request.files:
        logger.warning("OCR 요청에 이미지 파일이 없습니다.")
        return jsonify({"error": "No image file uploaded"}), 400

    image_file = request.files['image']
    image_name = image_file.filename
    # mimetype에서 확장자 추출 (예: 'image/jpeg' -> 'jpeg')
    image_format = image_file.mimetype.split('/')[-1] if image_file.mimetype else 'jpg' 
    # API에서 허용하는 포맷으로 변환 (필요시)
    if image_format.lower() == 'jpeg':
        image_format = 'jpg'

    logger.info(f"OCR 요청 파일: {image_name} ({image_file.mimetype}, format: {image_format})")

    # 요청 컨텍스트 내에서 앱 설정 가져오기
    ocr_url = current_app.config.get('OCR_URL')
    ocr_headers = current_app.config.get('OCR_HEADERS')

    if not ocr_url or not ocr_headers:
        logger.error("OCR 설정(URL 또는 Headers)이 앱 설정에 없어 API를 호출할 수 없습니다.")
        return jsonify({"error": "OCR 서비스 설정 오류 (설정 누락)"}), 500

    # CLOVA OCR API 요청 message 구성
    message = {
        "version": "V2",  # API 문서 권장값
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [{
            "format": image_format,
            "name": image_name  # 또는 고정된 이름 사용 가능 (예: "image")
            # "data": "base64_encoded_image_string" # 이미지 데이터를 직접 넣을 경우
            # "url": "image_url" # 이미지 URL을 사용할 경우
        }]
        # "lang": "ko", # 필요시 언어 설정 추가
        # "enableTableDetection": True, # 필요시 테이블 인식 기능 활성화
    }

    # files 딕셔너리: API 문서에 따라 'file' 키 사용
    files = {
        'file': (image_file.filename, image_file.stream, image_file.mimetype)
    }
    # data 딕셔너리: message JSON 객체 전달 (문자열로 변환)
    payload = {
        'message': json.dumps(message) # message 객체를 JSON 문자열로 변환
    }

    try:
        logger.info(f"CLOVA OCR API 호출 중... URL: {ocr_url}")
        logger.debug(f"Request Headers: {ocr_headers}")
        logger.debug(f"Request Payload (message): {payload}")
        
        # multipart/form-data 요청 시 data에는 message JSON 문자열, files에는 이미지 파일 전달
        response = requests.post(ocr_url, headers=ocr_headers, data=payload, files=files)
        response.raise_for_status() # 오류 발생 시 예외 발생

        logger.info(f"CLOVA OCR API 응답 코드: {response.status_code}")
        return jsonify(response.json())

    except requests.exceptions.HTTPError as e:
        logger.error(f"CLOVA OCR API HTTP 오류: {e.response.status_code} - {e.response.text}", exc_info=True)
        error_details = {"message": str(e), "status_code": e.response.status_code}
        try:
            error_details["api_message"] = e.response.json()
        except ValueError:
            error_details["api_message"] = e.response.text
        return jsonify({"error": "OCR API HTTP error", "details": error_details}), e.response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"CLOVA OCR API 요청 실패: {e}", exc_info=True)
        error_details = {"message": str(e)}
        if hasattr(e, 'response') and e.response is not None:
            error_details["status_code"] = e.response.status_code
            try:
                error_details["api_message"] = e.response.json()
            except ValueError:
                error_details["api_message"] = e.response.text
        return jsonify({"error": "OCR API request failed", "details": error_details}), getattr(e.response, 'status_code', 500)
    except Exception as e:
        logger.error(f"OCR 처리 중 예상치 못한 오류 발생: {e}", exc_info=True)
        return jsonify({"error": "OCR 처리 중 내부 오류 발생", "details": str(e)}), 500 

@ocr_bp.route('/ocr/base64', methods=['POST'])
def ocr_base64():
    """
    Base64 인코딩 이미지를 사용한 OCR API 엔드포인트
    
    요청 형식:
    {
        "image": "base64로 인코딩된 이미지 문자열",
        "format": "jpg" (선택, 기본값: jpg)
    }
    """
    logger.info("Base64 OCR 요청 수신")
    
    # 요청 데이터 확인
    data = request.get_json()
    if not data or 'image' not in data:
        logger.warning("OCR 요청에 이미지 데이터가 없습니다.")
        return jsonify({"error": "No image data provided"}), 400
    
    # Base64 이미지 데이터와 형식 추출
    image_data = data.get('image')
    image_format = data.get('format', 'jpg').lower()
    
    # 요청 컨텍스트 내에서 앱 설정 가져오기
    ocr_url = current_app.config.get('OCR_URL')
    ocr_headers = current_app.config.get('OCR_HEADERS')

    if not ocr_url or not ocr_headers:
        logger.error("OCR 설정(URL 또는 Headers)이 앱 설정에 없어 API를 호출할 수 없습니다.")
        return jsonify({"error": "OCR 서비스 설정 오류 (설정 누락)"}), 500
    
    # Content-Type 헤더 추가
    headers = ocr_headers.copy()
    headers["Content-Type"] = "application/json; charset=UTF-8"
    
    # CLOVA OCR API 요청 구성 (Base64 방식)
    payload = {
        "version": "V1",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [{
            "format": image_format,
            "name": "image_data",
            "data": image_data
        }]
    }
    
    try:
        logger.info(f"CLOVA OCR API 호출 중 (Base64 방식)... URL: {ocr_url}")
        logger.debug(f"Request Headers: {headers}")
        
        # Base64 방식은 JSON 형태로 직접 전송
        response = requests.post(ocr_url, headers=headers, data=json.dumps(payload).encode("utf-8"))
        response.raise_for_status()  # 오류 발생 시 예외 발생
        
        logger.info(f"CLOVA OCR API 응답 코드: {response.status_code}")
        return jsonify(response.json())
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"CLOVA OCR API HTTP 오류: {e.response.status_code} - {e.response.text}", exc_info=True)
        error_details = {"message": str(e), "status_code": e.response.status_code}
        try:
            error_details["api_message"] = e.response.json()
        except ValueError:
            error_details["api_message"] = e.response.text
        return jsonify({"error": "OCR API HTTP error", "details": error_details}), e.response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"CLOVA OCR API 요청 실패: {e}", exc_info=True)
        error_details = {"message": str(e)}
        if hasattr(e, 'response') and e.response is not None:
            error_details["status_code"] = e.response.status_code
            try:
                error_details["api_message"] = e.response.json()
            except ValueError:
                error_details["api_message"] = e.response.text
        return jsonify({"error": "OCR API request failed", "details": error_details}), getattr(e.response, 'status_code', 500)
    except Exception as e:
        logger.error(f"OCR 처리 중 예상치 못한 오류 발생: {e}", exc_info=True)
        return jsonify({"error": "OCR 처리 중 내부 오류 발생", "details": str(e)}), 500 
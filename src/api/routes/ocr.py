import os
import requests
import logging
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
    files = {'image': (image_file.filename, image_file.stream, image_file.mimetype)}
    logger.info(f"OCR 요청 파일: {image_file.filename} ({image_file.mimetype})")

    # 요청 컨텍스트 내에서 앱 설정 가져오기
    ocr_url = current_app.config.get('OCR_URL')
    ocr_headers = current_app.config.get('OCR_HEADERS')

    # OCR API 호출
    try:
        if not ocr_url or not ocr_headers:
            logger.error("OCR 설정(URL 또는 Headers)이 앱 설정에 없어 API를 호출할 수 없습니다.")
            return jsonify({"error": "OCR 서비스 설정 오류 (설정 누락)"}), 500

        logger.info("CLOVA OCR API 호출 중...")
        # 설정에서 가져온 URL과 헤더 사용
        response = requests.post(ocr_url, headers=ocr_headers, files=files)
        response.raise_for_status()

        logger.info(f"CLOVA OCR API 응답 코드: {response.status_code}")
        return jsonify(response.json())

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
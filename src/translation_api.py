import os
import requests
import logging
from flask import Blueprint, request, jsonify, current_app

# Blueprint 생성
translation_bp = Blueprint('translation', __name__)

# 로거 설정
logger = logging.getLogger(__name__)

# Papago NMT API URL
PAPAGO_NMT_API_URL = "https://papago.apigw.ntruss.com/nmt/v1/translation"

@translation_bp.route('/translate', methods=['POST'])
def translate_text():
    logger.info("Papago 번역 요청 수신")

    # 요청 본문에서 파라미터 추출 (JSON 형식 가정)
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Request body is empty or not JSON")
        text_to_translate = data.get('text')
        source_lang = data.get('source')
        target_lang = data.get('target')

        if not all([text_to_translate, source_lang, target_lang]):
            missing_params = [p for p in ['text', 'source', 'target'] if not data.get(p)]
            raise ValueError(f"Missing required parameters: {', '.join(missing_params)}")

    except Exception as e:
        logger.error(f"잘못된 번역 요청 파라미터: {e}")
        return jsonify({"error": "Invalid request parameters", "details": str(e)}), 400

    # 앱 설정에서 Papago API 헤더 가져오기
    papago_headers = current_app.config.get('PAPAGO_HEADERS')
    if not papago_headers:
        logger.error("Papago API 설정(Headers)이 앱 설정에 없어 API를 호출할 수 없습니다.")
        return jsonify({"error": "Papago API service configuration error"}), 500

    # Papago API 호출 데이터 준비 (x-www-form-urlencoded)
    api_data = {
        'source': source_lang,
        'target': target_lang,
        'text': text_to_translate
    }

    try:
        logger.info(f"Papago NMT API 호출: {source_lang} -> {target_lang}")
        # 타임아웃 추가 (예: 연결 5초, 읽기 10초)
        response = requests.post(PAPAGO_NMT_API_URL, headers=papago_headers, data=api_data, timeout=(5, 10))
        response.raise_for_status() # 4xx, 5xx 에러 발생 시 예외 처리

        logger.info(f"Papago NMT API 응답 코드: {response.status_code}")
        translation_result = response.json()

        # Papago API 자체 에러 처리 (응답 코드는 200이지만, 내용에 에러 메시지가 있을 수 있음)
        if 'errorCode' in translation_result:
             logger.error(f"Papago API 오류: {translation_result.get('errorCode')} - {translation_result.get('errorMessage')}")
             return jsonify({
                 "error": "Papago API returned an error",
                 "details": translation_result
             }), 400 # Papago 내부 오류는 클라이언트 오류(400)로 처리

        return jsonify(translation_result)

    except requests.exceptions.RequestException as e:
        # 네트워크 오류 또는 4xx/5xx 응답 코드
        logger.error(f"Papago NMT API 호출 실패: {e}", exc_info=True)
        error_details = {"message": str(e)}
        status_code = 500 # 기본 내부 서버 오류
        if hasattr(e, 'response') and e.response is not None:
            status_code = e.response.status_code
            try:
                # Papago 오류 응답이 JSON 형태일 수 있음
                error_details["api_message"] = e.response.json()
            except ValueError:
                error_details["api_message"] = e.response.text
        # 4xx 오류는 클라이언트 측 문제일 가능성이 높으므로 해당 코드 유지
        return jsonify({"error": "Papago API request failed", "details": error_details}), status_code
    except Exception as e:
        logger.error(f"번역 처리 중 예상치 못한 오류 발생: {e}", exc_info=True)
        return jsonify({"error": "Translation processing error", "details": str(e)}), 500 
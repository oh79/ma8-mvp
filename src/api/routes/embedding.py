import os
import requests
import logging
from flask import Blueprint, request, jsonify, current_app

# Blueprint 생성
embedding_bp = Blueprint('embedding', __name__)

# 로거 설정
logger = logging.getLogger(__name__)

# Embedding v2 API 경로
EMBEDDING_API_PATH = "/v1/api-tools/embedding/v2"

@embedding_bp.route('/embedding', methods=['POST'])
def get_embedding():
    logger.info("CLOVA Studio Embedding 요청 수신")

    # 요청 본문에서 파라미터 추출
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Request body is empty or not JSON")
        text_to_embed = data.get('text')
        if not text_to_embed:
            raise ValueError("Missing required parameter: text")
        # 토큰 길이 제한은 API 서버에서 처리하므로 여기서는 검증 생략 (필요시 추가)

    except Exception as e:
        logger.error(f"잘못된 임베딩 요청 파라미터: {e}")
        return jsonify({"error": "Invalid request parameters", "details": str(e)}), 400

    # 앱 설정에서 CLOVA Studio API URL 및 헤더 가져오기
    embedding_url = current_app.config.get('CLOVA_STUDIO_EMBEDDING_URL')
    clova_headers = current_app.config.get('CLOVA_STUDIO_HEADERS')

    if not embedding_url or not clova_headers:
        logger.error("CLOVA Studio API 설정(URL 또는 Headers)이 앱 설정에 없어 API를 호출할 수 없습니다.")
        return jsonify({"error": "CLOVA Studio API service configuration error"}), 500

    # API 요청 데이터 준비 (JSON)
    api_payload = {
        "text": text_to_embed
    }

    try:
        logger.info("CLOVA Studio Embedding v2 API 호출 중...")
        response = requests.post(embedding_url, headers=clova_headers, json=api_payload, timeout=(5, 30)) # 타임아웃 설정 (읽기 30초)
        response.raise_for_status() # 4xx, 5xx 에러 발생 시 예외 처리

        logger.info(f"CLOVA Studio Embedding API 응답 코드: {response.status_code}")
        result_data = response.json()

        # API 응답 상태 확인 (성공 시 status.code 가 "20000")
        if result_data.get('status', {}).get('code') == "20000":
            embedding_vector = result_data.get('result', {}).get('embedding')
            input_tokens = result_data.get('result', {}).get('inputTokens')
            if embedding_vector is not None:
                # 성공 응답 구성 (필요에 따라 inputTokens 포함)
                return jsonify({
                    "embedding": embedding_vector,
                    "inputTokens": input_tokens
                })
            else:
                 logger.error(f"CLOVA Studio API 성공 응답(20000)에 embedding 결과 누락: {result_data}")
                 return jsonify({"error": "CLOVA Studio API returned success but missing embedding data"}), 500
        else:
            # API 응답 상태가 성공(20000)이 아닌 경우
            logger.error(f"CLOVA Studio API 오류 응답: {result_data}")
            return jsonify({
                "error": "CLOVA Studio API returned an error",
                "details": result_data
            }), 400 # API 내부 오류는 클라이언트 문제로 간주 (400)

    except requests.exceptions.Timeout:
        logger.error("CLOVA Studio Embedding API 호출 시간 초과")
        return jsonify({"error": "CLOVA Studio API request timed out"}), 504 # Gateway Timeout
    except requests.exceptions.RequestException as e:
        logger.error(f"CLOVA Studio Embedding API 호출 실패: {e}", exc_info=True)
        error_details = {"message": str(e)}
        status_code = 500
        if hasattr(e, 'response') and e.response is not None:
            status_code = e.response.status_code
            try:
                error_details["api_message"] = e.response.json()
            except ValueError:
                error_details["api_message"] = e.response.text
        return jsonify({"error": "CLOVA Studio API request failed", "details": error_details}), status_code
    except Exception as e:
        logger.error(f"임베딩 처리 중 예상치 못한 오류 발생: {e}", exc_info=True)
        return jsonify({"error": "Embedding processing error", "details": str(e)}), 500 
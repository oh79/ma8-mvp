"""
Naver CLOVA OCR API 테스트 스크립트

이 스크립트는 Naver Cloud CLOVA OCR API를 호출하여 이미지에서 텍스트를 추출합니다.
환경 변수에서 API 키를 로드하거나 직접 입력하여 사용할 수 있습니다.
"""

import requests
import time
import uuid
import json
import base64
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ===== 사용자 설정 =====
# 환경 변수에서 로드하거나 직접 입력

# ======================

def ocr_image(image_path: str) -> dict:
    """이미지를 Base64로 인코딩해 OCR 요청을 보낸 뒤 JSON 응답을 반환"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")
        
    with open(image_path, "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "version": "V1",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [{
            "format": os.path.splitext(image_path)[1][1:],  # 확장자(jpg, png ...)
            "name": "demo",
            "data": img_base64
        }]
    }

    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-OCR-SECRET": SECRET_KEY
    }

    print(f"API 호출: {API_URL}")
    resp = requests.post(API_URL, headers=headers, data=json.dumps(payload).encode("utf-8"))
    
    # 응답 코드 출력
    print(f"응답 상태 코드: {resp.status_code}")
    
    try:
        resp.raise_for_status()  # 2xx 이외일 때 예외 발생
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"HTTP 오류: {e}")
        print(f"응답 내용: {resp.text}")
        raise

def print_ocr_results(result):
    """OCR 결과를 깔끔하게 출력하는 함수"""
    if "images" not in result:
        print("결과에 'images' 필드가 없습니다.")
        return
        
    # 인식된 모든 텍스트 출력
    print("\n=== 인식된 텍스트 ===")
    for img_idx, image in enumerate(result["images"]):
        print(f"\n[이미지 {img_idx + 1}]")
        
        if "fields" not in image:
            print("텍스트 필드가 없습니다.")
            continue
            
        for field_idx, field in enumerate(image["fields"]):
            confidence = field.get("confidence", 0)
            text = field.get("inferText", "")
            print(f"{field_idx + 1:3d}. [{confidence:.2f}] {text}")

if __name__ == "__main__":
    # 환경 변수 확인
    if API_URL == "YOUR_INVOKE_URL_HERE":
        print("경고: NAVER_OCR_INVOKE_URL 환경 변수가 설정되지 않았습니다.")
    if SECRET_KEY == "YOUR_SECRET_KEY_HERE":
        print("경고: NAVER_OCR_SECRET_KEY 환경 변수가 설정되지 않았습니다.")
    
    # 이미지 파일 존재 확인
    if not os.path.exists(IMAGE_PATH):
        print(f"경고: 샘플 이미지를 찾을 수 없습니다: {IMAGE_PATH}")
        # 대체 이미지 경로 찾기 시도
        for root, dirs, files in os.walk(os.path.dirname(os.path.dirname(__file__))):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    IMAGE_PATH = os.path.join(root, file)
                    print(f"대체 이미지를 사용합니다: {IMAGE_PATH}")
                    break
            if os.path.exists(IMAGE_PATH):
                break
    
    try:
        print(f"이미지 경로: {IMAGE_PATH}")
        result = ocr_image(IMAGE_PATH)
        print("\n=== 전체 JSON 결과 ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 결과 요약 출력
        print_ocr_results(result)
        
    except Exception as e:
        print(f"오류 발생: {e}") 
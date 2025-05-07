"""
Naver CLOVA OCR API를 통합 테스트하는 스크립트

이 스크립트는 Flask 애플리케이션의 OCR API 엔드포인트를 호출하여 
이미지에서 텍스트를 추출합니다.

두 가지 방식을 모두 테스트합니다:
1. Multipart/form-data 방식 (/ocr 엔드포인트)
2. Base64 인코딩 방식 (/ocr/base64 엔드포인트)
"""

import requests
import base64
import os
import json
import sys
from pathlib import Path

# 스크립트 디렉토리 기준으로 상대 경로 설정
script_dir = Path(__file__).parent
root_dir = script_dir.parent

# 샘플 이미지 경로 (samples/ocr 폴더 내 모든 이미지 파일)
samples_dir = root_dir / "samples" / "ocr"

def find_image_files(directory):
    """지정된 디렉토리에서 이미지 파일 찾기"""
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
    image_files = []
    
    # 디렉토리가 존재하는지 확인
    if not directory.exists():
        print(f"경고: 샘플 디렉토리를 찾을 수 없습니다: {directory}")
        return []
    
    # 모든 하위 폴더 포함해서 이미지 파일 검색
    for path in directory.glob('**/*'):
        if path.is_file() and path.suffix.lower() in image_extensions:
            image_files.append(path)
    
    return image_files

def test_ocr_multipart(image_path, api_url="http://localhost:5000/ocr"):
    """Multipart/form-data 방식으로 OCR API 테스트"""
    print(f"\n=== Multipart 방식 테스트: {image_path} ===")
    
    with open(image_path, 'rb') as f:
        files = {'image': (image_path.name, f, f'image/{image_path.suffix[1:]}')}
        
        try:
            print(f"API 호출: {api_url}")
            response = requests.post(api_url, files=files)
            print(f"응답 상태 코드: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print_ocr_results(result)
                return True
            else:
                print(f"오류 응답: {response.text}")
                return False
        except Exception as e:
            print(f"요청 중 오류 발생: {e}")
            return False

def test_ocr_base64(image_path, api_url="http://localhost:5000/ocr/base64"):
    """Base64 인코딩 방식으로 OCR API 테스트"""
    print(f"\n=== Base64 방식 테스트: {image_path} ===")
    
    with open(image_path, 'rb') as f:
        # 이미지를 Base64로 인코딩
        img_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        # 요청 데이터 구성
        payload = {
            "image": img_base64,
            "format": image_path.suffix[1:].lower()  # .jpg -> jpg
        }
        
        try:
            print(f"API 호출: {api_url}")
            response = requests.post(api_url, json=payload, headers={'Content-Type': 'application/json'})
            print(f"응답 상태 코드: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print_ocr_results(result)
                return True
            else:
                print(f"오류 응답: {response.text}")
                return False
        except Exception as e:
            print(f"요청 중 오류 발생: {e}")
            return False

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

def main():
    # API 서버 URL 설정 (기본값: localhost:5000)
    host = "localhost"
    port = 5000
    
    # 커맨드 라인 인자가 있으면 호스트와 포트 설정
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    base_url = f"http://{host}:{port}"
    
    # 이미지 파일 목록 가져오기
    image_files = find_image_files(samples_dir)
    
    if not image_files:
        print("테스트할 이미지 파일을 찾을 수 없습니다!")
        print(f"이미지 파일을 {samples_dir} 폴더에 추가하세요.")
        return
    
    print(f"발견한 이미지 파일: {len(image_files)}개")
    for idx, img_path in enumerate(image_files):
        print(f"{idx + 1}. {img_path.relative_to(root_dir)}")
    
    # 테스트 모드 선택
    print("\n테스트 모드를 선택하세요:")
    print("1. Multipart/form-data 방식 (/ocr)")
    print("2. Base64 인코딩 방식 (/ocr/base64)")
    print("3. 두 가지 방식 모두 테스트")
    
    while True:
        try:
            mode = int(input("\n모드 선택 (1-3): ").strip())
            if 1 <= mode <= 3:
                break
            print("1-3 사이의 숫자를 입력하세요.")
        except ValueError:
            print("숫자를 입력하세요.")
    
    # 테스트할 이미지 선택
    print("\n테스트할 이미지를 선택하세요:")
    print("0. 모든 이미지 테스트")
    
    while True:
        try:
            img_idx = int(input(f"\n이미지 선택 (0-{len(image_files)}): ").strip())
            if 0 <= img_idx <= len(image_files):
                break
            print(f"0-{len(image_files)} 사이의 숫자를 입력하세요.")
        except ValueError:
            print("숫자를 입력하세요.")
    
    # 테스트 실행
    if img_idx == 0:
        # 모든 이미지 테스트
        test_images = image_files
    else:
        # 선택한 이미지만 테스트
        test_images = [image_files[img_idx - 1]]
    
    # 선택한 모드에 따라 테스트 실행
    for img_path in test_images:
        if mode == 1 or mode == 3:
            test_ocr_multipart(img_path, f"{base_url}/ocr")
        if mode == 2 or mode == 3:
            test_ocr_base64(img_path, f"{base_url}/ocr/base64")

if __name__ == "__main__":
    main() 
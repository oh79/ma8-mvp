import pytest
from flask import Flask
from src.ocr_api import ocr_bp # 테스트하려는 Blueprint 임포트
import io

@pytest.fixture
def app():
    """테스트용 Flask 앱 생성"""
    app = Flask(__name__)
    app.config['TESTING'] = True

    # 테스트용 앱 설정 추가
    app.config['OCR_URL'] = 'https://fake.invoke.url/general' # 가짜 URL
    app.config['OCR_HEADERS'] = {
        "X-NCP-APIGW-API-KEY-ID": "fake_key_id",
        "X-NCP-APIGW-API-KEY": "fake_key_secret"
    }

    app.register_blueprint(ocr_bp)

    return app # yield 대신 return 사용 (환경 변수 정리 불필요)

@pytest.fixture
def client(app):
    """Flask 테스트 클라이언트 생성"""
    return app.test_client()

def test_ocr_endpoint_success(client, mocker):
    """OCR 엔드포인트 성공 케이스 테스트"""
    # requests.post 모킹 (실제 API 호출 방지)
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "mocked_ocr_text"}

    # 테스트용 이미지 데이터
    image_data = (io.BytesIO(b"fake_image_content"), 'test.jpg')

    # mocker.patch의 대상 확인 (ocr_api 모듈 내부의 requests)
    mocker.patch('src.ocr_api.requests.post', return_value=mock_response)

    # 테스트 클라이언트로 POST 요청 보내기
    response = client.post('/ocr', content_type='multipart/form-data', data={'image': image_data})

    # 응답 검증
    assert response.status_code == 200
    assert response.json == {"result": "mocked_ocr_text"}
    # mocker.patch 내부에서 requests를 찾지 못하는 문제 해결 위해 임포트 위치 변경 고려 또는 전역 임포트 사용
    # 아래 assert는 mocker 사용 방식에 따라 다를 수 있음
    # requests.post.assert_called_once() # 필요시 mocker 설정 확인

def test_ocr_endpoint_no_image(client):
    """이미지 파일 없이 요청 시 400 오류 테스트"""
    response = client.post('/ocr')
    assert response.status_code == 400
    assert 'No image file uploaded' in response.json['error']

# ... 기타 오류 케이스 테스트 추가 ...

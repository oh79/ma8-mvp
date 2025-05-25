import pytest
from flask import Flask
from src.api.routes.ocr import ocr_bp # 테스트하려는 Blueprint 임포트
import io
import os # 추가
from dotenv import load_dotenv # 추가
import warnings # 추가: 환경 변수 누락 시 경고용
import requests # <--- 이 줄 추가

# --- 테스트용 실제 이미지 파일 경로 ---
# 사용자는 이 경로를 실제 테스트할 이미지 파일의 위치로 수정해야 합니다.
# 예: TEST_REAL_IMAGE_PATH = "sample_data/ocr_test_image.jpg"
# 이미지가 tests 폴더 기준으로 있다면 "test_image.jpg" 등으로 설정 가능
TEST_REAL_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "test_image_for_api.jpg") # 기본값: tests 폴더 내 test_image_for_api.jpg
# 이 경로에 실제 이미지 파일을 준비해주세요. 없다면 테스트는 실패합니다.

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

@pytest.fixture(scope="session")
def loaded_env():
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    print(f"DEBUG: Attempting to load .env file from: {dotenv_path}")
    if os.path.exists(dotenv_path):
        loaded = load_dotenv(dotenv_path=dotenv_path, override=True)
        print(f"DEBUG: .env file loaded: {loaded}")
        # 로드 후 실제 환경 변수 값 확인
        print(f"DEBUG: (loaded_env) X-NCP-APIGW-API-KEY-ID: {os.getenv('X-NCP-APIGW-API-KEY-ID')}")
        print(f"DEBUG: (loaded_env) X-NCP-APIGW-API-KEY: {os.getenv('X-NCP-APIGW-API-KEY')}")
        print(f"DEBUG: (loaded_env) NAVER_OCR_INVOKE_URL: {os.getenv('NAVER_OCR_INVOKE_URL')}")
        return True
    else:
        # .env 파일이 없는 경우 경고 (통합 테스트 시 필요)
        warnings.warn(UserWarning(f".env 파일을 찾을 수 없습니다: {dotenv_path}. 통합 테스트는 실제 환경 변수가 필요합니다."))
        return False

@pytest.fixture
def real_api_app(loaded_env): # loaded_env fixture를 사용하여 .env 로드 보장 시도
    """(통합 테스트용) 실제 API 설정을 사용하는 Flask 앱 생성"""
    app = Flask(__name__)
    app.config['TESTING'] = True

    # .env 파일에서 실제 환경 변수 로드 (src/app.py 로직과 일치하게 수정)
    ocr_url_from_env = os.getenv("NAVER_OCR_INVOKE_URL")
    ocr_secret_key_from_env = os.getenv("OCR_SECRET_KEY") # OCR_SECRET_KEY 읽기

    print(f"DEBUG: (real_api_app) NAVER_OCR_INVOKE_URL: {ocr_url_from_env}")
    # print(f"DEBUG: (real_api_app) X-NCP-APIGW-API-KEY-ID: {os.getenv('X-NCP-APIGW-API-KEY-ID')}") # 더 이상 헤더에 직접 사용 안 함
    print(f"DEBUG: (real_api_app) OCR_SECRET_KEY: {ocr_secret_key_from_env}") # 변경된 키 로깅

    if ocr_url_from_env:
        app.config['OCR_URL'] = ocr_url_from_env
    else:
        app.config['OCR_URL'] = None

    # 헤더 설정 수정: X-OCR-SECRET 사용
    if ocr_secret_key_from_env:
        app.config['OCR_HEADERS'] = {
            "X-OCR-SECRET": ocr_secret_key_from_env
        }
    else:
        app.config['OCR_HEADERS'] = None

    app.register_blueprint(ocr_bp)
    print(f"DEBUG: (real_api_app) app.config['OCR_URL']: {app.config.get('OCR_URL')}")
    print(f"DEBUG: (real_api_app) app.config['OCR_HEADERS']: {app.config.get('OCR_HEADERS')}")
    return app

@pytest.fixture
def real_api_client(real_api_app):
    """(통합 테스트용) Flask 테스트 클라이언트 생성"""
    return real_api_app.test_client()

def test_ocr_endpoint_success_mocked(client, mocker):
    """OCR 엔드포인트 성공 케이스 테스트 (API 호출 모킹)"""
    # requests.post 모킹 (실제 API 호출 방지)
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "mocked_ocr_text"}

    # 테스트용 이미지 데이터
    image_data = (io.BytesIO(b"fake_image_content"), 'test.jpg')

    # mocker.patch의 대상 확인 (ocr_api 모듈 내부의 requests)
    mocker.patch('src.api.routes.ocr.requests.post', return_value=mock_response)

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

@pytest.mark.integration
def test_ocr_endpoint_real_api_call(real_api_client):
    """OCR 엔드포인트 실제 API 호출 테스트"""
    # 필수 환경 변수 확인 (수정)
    ocr_url = real_api_client.application.config.get('OCR_URL')
    ocr_headers = real_api_client.application.config.get('OCR_HEADERS')

    # 환경 변수 체크 수정: OCR_SECRET_KEY 확인
    if not ocr_url or not ocr_headers or not ocr_headers.get("X-OCR-SECRET"):
        pytest.skip("OCR 통합 테스트를 위한 환경 변수(NAVER_OCR_INVOKE_URL, OCR_SECRET_KEY)가 .env 파일에 설정되지 않았습니다.")

    if not os.path.exists(TEST_REAL_IMAGE_PATH):
        pytest.fail(f"테스트용 실제 이미지 파일을 찾을 수 없습니다: {TEST_REAL_IMAGE_PATH}. 경로를 확인하고 파일을 준비해주세요.")

    try:
        with open(TEST_REAL_IMAGE_PATH, 'rb') as img_file:
            image_data = (img_file, os.path.basename(TEST_REAL_IMAGE_PATH))
            # MIME 타입은 image_file.mimetype으로 설정되므로 명시적 전달 불필요 (Werkzeug MultiDict 처리)
            data = {'image': image_data}
            
            # 실제 API 호출 (모킹 없음)
            response = real_api_client.post('/ocr', content_type='multipart/form-data', data=data)

        assert response.status_code == 200, f"API 호출 실패: {response.status_code} - {response.text}"
        
        response_json = response.json
        assert response_json is not None, "API 응답이 JSON이 아닙니다."
        assert "version" in response_json, "응답 JSON에 'version' 키가 없습니다."
        assert "requestId" in response_json, "응답 JSON에 'requestId' 키가 없습니다."
        assert "images" in response_json, "응답 JSON에 'images' 키가 없습니다."
        assert isinstance(response_json["images"], list), "'images' 필드가 리스트가 아닙니다."
        assert len(response_json["images"]) > 0, "'images' 리스트가 비어있습니다."
        # 첫 번째 이미지 결과에 대한 추가 검증 (필요시)
        first_image_result = response_json["images"][0]
        assert "uid" in first_image_result
        assert "name" in first_image_result
        assert "inferResult" in first_image_result
        # 실제 OCR 텍스트 내용은 이미지에 따라 달라지므로 특정 텍스트를 검증하기는 어려움

    except FileNotFoundError:
        pytest.fail(f"테스트 이미지를 찾을 수 없습니다: {TEST_REAL_IMAGE_PATH}")
    except requests.exceptions.ConnectionError as e:
        pytest.fail(f"API 서버 연결 실패: {e}. Flask 앱 또는 외부 API 서버 상태를 확인하세요.")
    except Exception as e:
        pytest.fail(f"실제 API 호출 중 예외 발생: {e}")

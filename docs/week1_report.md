# Week1 Report: API 환경 설정 및 기본 호출 검증 (Flask 통합 방식)

## 목표 달성 요약

Sprint2 Week1의 주요 목표인 NCP의 핵심 API(CLOVA OCR, Papago Translation, CLOVA Studio Embedding v2) 사용을 위한 환경 설정 및 기본적인 API 호출 가능성 검증을 완료했습니다.

## 진행 내용

1.  **API 환경 설정:**
    *   `.env` 파일을 통해 각 API 사용에 필요한 인증 정보(API Key, Secret/Client ID, Invoke URL/Endpoint)를 안전하게 관리하도록 설정했습니다.
    *   `requirements.txt`에 `python-dotenv`, `requests`, `flask` 등 API 연동 및 웹 서버 구동에 필요한 주요 라이브러리가 포함되어 있음을 확인했습니다.

2.  **Flask 애플리케이션 통합:**
    *   원래 계획된 개별 테스트 스크립트 방식 대신, 각 API 기능을 Flask 애플리케이션 내의 별도 Blueprint(`ocr_api.py`, `translation_api.py`, `embedding_api.py`)로 구현하여 모듈성과 확장성을 높였습니다.
    *   메인 Flask 앱(`api.py`)에서 환경 변수를 읽어 각 Blueprint가 사용할 설정을 `app.config`에 주입하는 방식을 적용했습니다.

3.  **기본 호출 검증:**
    *   **CLOVA OCR:** `/ocr` 엔드포인트를 통해 이미지 파일을 전송하고 API 호출이 성공하는 것을 `pytest` (모킹 사용) 및 `curl`로 확인했습니다.
    *   **Papago Translation:** `/translate` 엔드포인트를 통해 번역할 텍스트, 소스/타겟 언어를 전송하고 API 호출이 성공하여 번역 결과를 반환하는 것을 `curl`로 확인했습니다.
    *   **CLOVA Studio Embedding v2:** `/embedding` 엔드포인트를 통해 텍스트를 전송하고 API 호출이 성공하여 임베딩 벡터를 반환하는 것을 `curl`로 확인했습니다.
    *   테스트 과정에서 발생한 인코딩 문제, 경로 문제, 설정 누락 문제 등을 해결했습니다.

## 원래 계획과의 차이점

*   **구현 방식:** 개별 테스트 스크립트(`clova_test.py` 등) 대신 Flask 앱에 API 기능을 통합하는 방식으로 진행했습니다.
*   **검증 방식:** 원래 계획된 정량적 테스트(OCR 인식률, 번역 성공률, 임베딩 유사도)는 수행하지 않고, 각 API 엔드포인트의 기본적인 호출 성공 여부와 응답 확인에 중점을 두었습니다.
*   **API URL/인증:** 일부 API(Papago, Embedding)의 경우, 계획된 스크립트 예시와 실제 구현에 사용된 API 엔드포인트 URL 또는 인증 방식(헤더)에 차이가 있었습니다. 실제 서비스 가능한 최신 API 명세를 기준으로 구현했습니다.

## 결론

핵심 목표인 API 연동 환경 구축 및 기본 호출 검증은 성공적으로 완료했으며, 실제 서비스 백엔드에 통합하는 방식으로 진행하여 향후 확장성을 확보했습니다. 정량적인 성능 평가는 추후 별도의 테스트나 평가 단계를 통해 진행할 수 있습니다. 
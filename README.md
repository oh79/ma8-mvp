# 📈 인스타 인플루언서 검색 MVP (Sprint 3 - 성능 최적화 버전)

간단한 자연어 쿼리를 통해 인스타그램 인플루언서를 검색하는 MVP 프로젝트입니다. **Week 1에서는 자연어 쿼리에서 팔로워 수 범위를 추출하여 필터링하는 기능과 텍스트 유사도 기반 검색 기능을 구현했습니다. Week 2에서는 렌즈 관련 데이터 수집 및 API 통합 기능이 추가되었습니다. Sprint 3에서는 스크래퍼 성능을 최적화하고 2단계 파이프라인 구조로 리팩터링했습니다.**

## Setup

1.  **저장소 복제:**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```
2.  **가상 환경 생성 및 활성화:**
    ```bash
    python -m venv .venv
    # Windows
    .\.venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```
3.  **필요 라이브러리 설치:**
    ```bash
    pip install -r requirements.txt
    # (konlpy 사용 시 JDK 설치 및 JAVA_HOME 환경 변수 설정 필요)
    ```
4.  **.env 파일 작성:**
    *   프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 입력합니다.
      ```dotenv
      INSTAGRAM_USERNAME=your_instagram_username
      INSTAGRAM_PASSWORD=your_instagram_password
      OCR_API_KEY=your_ocr_api_key
      EMBEDDING_API_KEY=your_embedding_api_key
      ```

## 데이터 준비 (Data Pipeline)

### 1. 인스타그램 데이터 스크래핑 (최적화 버전)

최적화된 스크래퍼는 2단계 파이프라인 구조로 작동합니다:

#### 1) 태그 스캐너 모드
해시태그를 검색하여 사용자명만 수집합니다:
```bash
python run_scraper.py --mode scan --tags lens,colorlens,contactlens --limit 5000
```

#### 2) 디테일 크롤러 모드
수집된 사용자명 목록에서 상세 정보와 게시물을 수집합니다:
```bash
python run_scraper.py --mode crawl --parallel 8
```

#### 그 외 옵션
- **테스트 모드**: `--dry-run` 옵션을 추가하면 소량의 데이터만 처리합니다.
- **특정 사용자**: `--users user1,user2,user3` 형식으로 특정 사용자만 처리할 수 있습니다.
- **병렬 처리**: `--parallel` 옵션으로 병렬 처리 스레드 수를 지정할 수 있습니다.

자세한 옵션은 다음 명령어로 확인할 수 있습니다:
```bash
python run_scraper.py --help
```

#### Docker로 실행
```bash
# 빌드
docker-compose build

# 태그 스캐너 모드 실행
docker-compose run --rm scraper --mode scan --tags lens,colorlens

# 디테일 크롤러 모드 실행
docker-compose run --rm scraper --mode crawl
```

### 2. ETL 및 API 처리
*   스크래핑 결과를 SQLite 데이터베이스에 저장하고 API 호출을 통해 추가 데이터를 생성합니다.
    ```bash
    python src/data/etl.py
    ```
*   ETL 결과 검증:
    ```bash
    python verify_etl.py
    ```

### 3. 임베딩 벡터 생성
*   수집된 인플루언서의 자기소개를 벡터화하여 검색에 사용될 파일을 생성합니다.
    ```bash
    python scripts/embed.py
    ```
*   이 과정은 `influencers.csv` 파일이 변경될 때마다 다시 실행해야 합니다.

## 실행 (Run Application)

1.  **Flask API 서버 실행:**
    *   `.env` 파일에 필요한 모든 API 키 및 설정 (인스타그램 계정, OCR, Papago, CLOVA Studio)이 올바르게 입력되었는지 확인합니다.
    *   터미널에서 다음 명령어를 실행합니다:
      ```bash
      python src/api.py
      ```
    *   서버가 `http://127.0.0.1:5000` 에서 실행됩니다.
2.  **Streamlit UI 실행:**
    *   다른 터미널에서 다음 명령어를 실행합니다:
      ```bash
      streamlit run app.py
      ```
    *   웹 브라우저에서 자동으로 열리는 Streamlit 앱 페이지에서 검색어를 입력하여 사용합니다.

## API 엔드포인트 테스트

Flask API 서버가 실행 중인 상태에서 다음 `curl` 명령을 사용하여 각 API 엔드포인트의 기본 기능을 테스트할 수 있습니다.

*   **검색 API (`/search`):**
    ```bash
    # GET 요청, 쿼리 파라미터로 검색어 전달
    curl "http://localhost:5000/search?q=뷰티+팔로워+1만명" 
    ```

*   **CLOVA OCR API (`/ocr`):**
    ```bash
    # POST 요청, 이미지 파일을 form-data로 전송
    # samples/ocr_test.jpg 부분은 실제 테스트할 이미지 경로로 변경
    curl -X POST http://localhost:5000/ocr -F "image=@samples/ocr_test.jpg"
    ```

*   **Papago 번역 API (`/translate`):**
    ```bash
    # POST 요청, JSON 본문으로 번역할 내용 전달
    # (Windows curl 사용 시 인코딩 문제 해결 위해 파일 사용 권장)
    # 1. src/translate_payload.json 파일 생성 (UTF-8 인코딩)
    #    {"text": "안녕하세요", "source": "ko", "target": "en"}
    # 2. curl 명령어 실행
    curl -X POST http://localhost:5000/translate -H "Content-Type: application/json" -d @src/translate_payload.json
    ```

*   **CLOVA Studio Embedding API (`/embedding`):**
    ```bash
    # POST 요청, JSON 본문으로 임베딩할 텍스트 전달
    # (Windows curl 사용 시 인코딩 문제 해결 위해 파일 사용 권장)
    # 1. src/embedding_payload.json 파일 생성 (UTF-8 인코딩)
    #    {"text": "테스트할 문장을 입력하세요."}
    # 2. curl 명령어 실행
    curl -X POST http://localhost:5000/embedding -H "Content-Type: application/json" -d @src/embedding_payload.json
    ```

## 주요 파일 설명

### 스크래퍼 모듈 (최적화 버전)
*   `run_scraper.py`: 스크래퍼 실행 스크립트 (태그 스캐너/디테일 크롤러 모드 선택)
*   `src/data/tag_scanner.py`: 해시태그 기반 사용자명 수집 모듈
*   `src/data/detail_crawler.py`: 사용자 정보 및 게시물 상세 정보 수집 모듈
*   `src/data/rate_control.py`: 응답시간 기반 동적 딜레이 조정 모듈
*   `src/data/proxy_manager.py`: 프록시 관리 및 자동 전환 모듈
*   `src/data/utils.py`: 공통 유틸리티 함수
*   `src/data/db.py`: 데이터베이스 관리 모듈
*   `config.yaml`: 스크래퍼 설정 파일
*   `Dockerfile`: 도커 이미지 빌드 파일
*   `docker-compose.yml`: 도커 컴포즈 설정 파일

### 그 외 파일
*   `src/data/etl.py`: CSV 데이터를 SQLite DB(`mvp.db`)로 로드하고 API 호출을 통해 데이터를 보강합니다.
*   `src/data/api_utils.py`: 외부 API(OCR, 번역, 임베딩)를 호출하는 함수를 제공합니다.
*   `verify_etl.py`: ETL 처리 결과를 검증하는 스크립트입니다.
*   `scripts/embed.py`: 인플루언서 자기소개 텍스트를 임베딩하여 `vecs.npy`와 `meta.csv`를 생성합니다.
*   `src/nlp_parse.py`: 자연어 쿼리를 분석하여 팔로워 범위 필터 조건을 추출합니다.
*   `src/api.py`: Flask 기반의 검색 API 서버입니다.
*   `app.py`: Streamlit 기반의 웹 UI입니다.
*   `requirements.txt`: 프로젝트 실행에 필요한 Python 라이브러리 목록입니다.
*   `.env`: 인스타그램 계정 정보, API 키 설정을 저장합니다.

## Sprint 3 최적화 완료 기능

*   **2단계 파이프라인 구조:**
    *   **태그 스캐너**: 해시태그 검색으로 사용자명만 빠르게 수집
    *   **디테일 크롤러**: 수집된 사용자명 목록에서 상세 정보 수집
*   **성능 최적화:**
    *   **동적 딜레이 어댑터**: 응답 시간에 따라 딜레이 자동 조정
    *   **프록시 자동 전환**: 실패 시 다른 프록시로 자동 전환
    *   **병렬 처리**: 다중 스레드 지원으로 병렬 데이터 수집
*   **안정성 개선:**
    *   **재시도 메커니즘**: 요청 실패 시 자동 재시도
    *   **체크포인트 관리**: 중간 상태 저장으로 중단 후 재개 가능
    *   **에러 처리**: 상세한 예외 처리 및 로깅
*   **Docker 지원:**
    *   **Dockerfile**: 실행 환경 컨테이너화
    *   **docker-compose.yml**: 스크래퍼와 프록시 서비스 통합

## Sprint 2 완료 기능

*   **렌즈 관련 데이터 수집:**
    *   렌즈 관련 해시태그 기반 인플루언서 및 게시물 수집 
    *   user_pk 기반 게시물 수집 로직 추가
    *   수집된 인플루언서 목록 저장 (lens_influencers.txt)
*   **API 호출 통합:**
    *   OCR API를 통한 이미지 내 제품명 추출
    *   Papago 번역 API를 통한 캡션 번역
    *   CLOVA Studio API를 통한 이미지-텍스트 임베딩 생성
*   **ETL 검증:**
    *   데이터베이스 테이블 검증
    *   결측치 확인 및 데이터 통계 제공

## Sprint 1 완료 기능

*   자연어 쿼리에서 팔로워 수 범위(X만~Y만, X천 이상 등) 추출 (`nlp_parse.py`)
*   추출된 팔로워 수 범위로 검색 대상 필터링 (`api.py`)
*   필터링된 결과 내에서 입력 쿼리와 인플루언서 biography 간 텍스트 유사도 계산 (`api.py`, Sentence Transformer)
*   유사도 순으로 정렬된 결과 반환 (`api.py`)
*   Streamlit UI에서 검색어 입력 및 결과(username, follower_count, category) 확인 (`app.py`)
*   데이터 스크래핑, DB 적재, 임베딩 생성 파이프라인 구축 
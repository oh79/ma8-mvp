flowchart TD
  %% 1. 수집 단계
  subgraph COLLECT[수집]
    A1[Instaloader Scraper] --> A2[Raw Data: posts.csv]
    A1 --> A3[Raw Data: influencers.csv]
  end

  %% 2. 전처리_ETL
  subgraph ETL[전처리_ETL]
    A2 --> B1[OCR: Clova OCR API]
    A2 --> B2[CLIP Embedding]
    B1 --> B3[ocr_text 컬럼]
    B2 --> B4[style_similarity 컬럼]
    A3 --> B5[Brand Collab 집계]
    B3 --> B6[ETL 통합 스크립트]
    B4 --> B6
    B5 --> B6
    B6 --> C1[SQLite (mvp.db)]
  end

  %% 3. 검색엔진
  subgraph SEARCH[검색엔진]
    C1 --> D1[API: Flask /search]
    D1 -->|"프롬프트 q"| E1[NLP 파싱: nlp_parse.py]
    E1 --> D1
    D1 -->|"필터 min_sim·팔로워"| D2[결과 DataFrame]
    D2 --> F1[Ranking 함수 적용]
    F1 --> G1[JSON 결과 반환]
  end

  %% 4. UI
  subgraph UI[UI]
    G1 --> H1[Streamlit 인터페이스]
    H1 -->|"입력: 자연어 + 슬라이더"| D1
    H1 -->|"출력: 테이블/카드"| User[렌즈 마케터]
  end

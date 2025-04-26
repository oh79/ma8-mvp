import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 설정 ---
INPUT_CSV_FILE = 'influencers.csv' # 스크래핑 결과 CSV 파일
OUTPUT_VEC_FILE = 'vecs.npy'      # 생성될 임베딩 벡터 파일
OUTPUT_META_FILE = 'meta.csv'     # 생성될 메타데이터 파일 (벡터 순서와 일치)
MODEL_NAME = 'snunlp/KR-SBERT-V40K-klueNLI-augSTS' # 사용할 Sentence Transformer 모델

# 메타데이터 파일에 포함할 컬럼 목록
META_COLUMNS = ['pk', 'username', 'full_name', 'follower_count', 'biography'] # biography 포함하여 나중에 확인 용이

# --- 메인 로직 ---
def main():
    # 1. CSV 파일 로드
    try:
        logging.info(f"'{INPUT_CSV_FILE}' 파일 로딩 중...")
        df = pd.read_csv(INPUT_CSV_FILE)
        logging.info(f"총 {len(df)}명의 인플루언서 데이터 로드 완료.")
    except FileNotFoundError:
        logging.error(f"오류: '{INPUT_CSV_FILE}' 파일을 찾을 수 없습니다. scraper.py를 먼저 실행하세요.")
        return
    except Exception as e:
        logging.error(f"CSV 파일 로딩 중 오류 발생: {e}")
        return

    # 2. Sentence Transformer 모델 로드
    try:
        logging.info(f"'{MODEL_NAME}' 모델 로딩 중...")
        model = SentenceTransformer(MODEL_NAME)
        logging.info("모델 로딩 완료.")
    except Exception as e:
        logging.error(f"Sentence Transformer 모델 로딩 중 오류 발생: {e}")
        return

    # 3. 임베딩 생성
    # biography 컬럼이 없는 경우 또는 NaN 값이 있는 경우 처리
    if 'biography' not in df.columns:
        logging.error(f"'{INPUT_CSV_FILE}' 파일에 'biography' 컬럼이 없습니다.")
        return
    
    # NaN 값을 빈 문자열로 대체 (모델 입력으로 NaN 불가)
    biographies = df['biography'].fillna('').tolist()
    logging.info(f"총 {len(biographies)}개의 자기소개 텍스트 임베딩 생성 시작...")
    
    try:
        # 모델을 사용하여 텍스트 목록을 임베딩 벡터로 변환
        # show_progress_bar=True 로 진행률 표시 (데이터가 많을 경우 유용)
        embeddings = model.encode(biographies, show_progress_bar=True)
        logging.info(f"임베딩 생성 완료. 생성된 벡터 수: {len(embeddings)}")
    except Exception as e:
        logging.error(f"임베딩 생성 중 오류 발생: {e}", exc_info=True)
        return

    # 4. 임베딩 벡터 파일 저장 (npy)
    try:
        logging.info(f"임베딩 벡터를 '{OUTPUT_VEC_FILE}' 파일로 저장 중...")
        np.save(OUTPUT_VEC_FILE, embeddings)
        logging.info("임베딩 벡터 저장 완료.")
    except Exception as e:
        logging.error(f"임베딩 벡터 저장 중 오류 발생: {e}")
        return

    # 5. 메타데이터 파일 저장 (csv)
    try:
        logging.info(f"메타데이터를 '{OUTPUT_META_FILE}' 파일로 저장 중...")
        # 정의된 컬럼만 선택하여 저장
        meta_df = df[META_COLUMNS]
        meta_df.to_csv(OUTPUT_META_FILE, index=False, encoding='utf-8-sig')
        logging.info(f"메타데이터 저장 완료. ({len(meta_df)} 행, {len(META_COLUMNS)} 컬럼)")
    except KeyError as ke:
        logging.error(f"오류: 메타데이터 저장에 필요한 컬럼('{ke}')이 '{INPUT_CSV_FILE}'에 없습니다.")
    except Exception as e:
        logging.error(f"메타데이터 저장 중 오류 발생: {e}")
        return

    logging.info("임베딩 및 메타데이터 생성 작업 완료.")

if __name__ == "__main__":
    main() 
import pandas as pd
import sqlite3
import logging
import os
import sys
import time
import random
import functools
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.api.utils.api_utils import ocr_test, embed_image, retry_api_call

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API 재시도 관련 상수
MAX_RETRIES = 3
RETRY_DELAY = 3  # 5초에서 3초로 단축
MAX_BACKOFF_TIME = 30  # 60초에서 30초로 단축
MAX_WORKERS = 5  # 병렬 처리 워커 수

# API 호출 함수 (api_utils.py의 함수 직접 사용)
def safe_ocr_test(image_url):
    return ocr_test(image_url)

def safe_embed_image(query, image_url):
    return embed_image(query, image_url)

# 병렬 처리용 함수
def process_ocr(idx, image_url):
    """단일 이미지에 대한 OCR 처리 함수"""
    try:
        logger.info(f"[{idx}] OCR 처리 중: {image_url[:30]}...")
        product_name = safe_ocr_test(image_url)
        return idx, product_name
    except Exception as e:
        logger.error(f"[{idx}] OCR 처리 오류: {e}")
        return idx, None

def process_embedding(idx, image_url):
    """단일 이미지에 대한 임베딩 처리 함수"""
    try:
        logger.info(f"[{idx}] 임베딩 처리 중: {image_url[:30]}...")
        embedding = safe_embed_image('렌즈 사진', image_url)
        return idx, embedding
    except Exception as e:
        logger.error(f"[{idx}] 임베딩 처리 오류: {e}")
        return idx, None

def main():
    """ETL 메인 함수"""
    logger.info("ETL 프로세스 시작...")
    start_time = time.time()
    
    # 데이터 디렉토리 확인 및 생성
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        logger.info(f"'{data_dir}' 디렉토리 생성 완료")
    
    # 1. CSV 파일에서 데이터 로드
    logger.info("CSV 파일에서 데이터 로드 중...")
    try:
        influencers_file = os.path.join(data_dir, "influencers.csv")
        posts_file = os.path.join(data_dir, "posts.csv")
        
        df_influencers = pd.read_csv(influencers_file, encoding='utf-8-sig')
        df_posts = pd.read_csv(posts_file, encoding='utf-8-sig')
        
        logger.info(f"인플루언서 데이터 {len(df_influencers)}건 로드 완료")
        logger.info(f"게시물 데이터 {len(df_posts)}건 로드 완료")
    except Exception as e:
        logger.error(f"CSV 파일 로드 실패: {e}")
        return
    
    # 'translated_caption' 컬럼이 있으면 제거 (스프린트2에서 Papago 제거)
    if 'translated_caption' in df_posts.columns:
        logger.info("Papago 번역 컬럼 제거 중...")
        df_posts = df_posts.drop('translated_caption', axis=1)
        logger.info("번역 컬럼 제거 완료")
    
    # 2. 데이터 변환 및 API 호출
    
    # 1. OCR을 통한 제품명 추출 (병렬 처리)
    if 'product_name' not in df_posts.columns:
        logger.info("제품명 추출 (OCR) 처리 시작...")
        df_posts['product_name'] = None
    
    # 처리해야 할 항목 선별
    ocr_tasks = []
    for idx, row in df_posts.iterrows():
        if pd.isna(df_posts.loc[idx, 'product_name']):  # 이미 값이 있는 경우 스킵
            image_url = row['thumbnail_url']
            if not pd.isna(image_url) and image_url:
                ocr_tasks.append((idx, image_url))
    
    logger.info(f"OCR 처리할 데이터 건수: {len(ocr_tasks)}")
    
    # 병렬 처리 실행
    if ocr_tasks:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # OCR 태스크 제출
            future_to_idx = {executor.submit(process_ocr, idx, url): idx for idx, url in ocr_tasks}
            
            # 결과 수집
            for future in as_completed(future_to_idx):
                idx, product_name = future.result()
                if product_name:
                    df_posts.loc[idx, 'product_name'] = product_name
    
    logger.info("OCR 처리 완료")
    
    # 2. 이미지 임베딩 (병렬 처리)
    if 'semantic_emb' not in df_posts.columns:
        logger.info("이미지 임베딩 처리 시작...")
        df_posts['semantic_emb'] = None
    
    # 처리해야 할 항목 선별
    embedding_tasks = []
    for idx, row in df_posts.iterrows():
        if pd.isna(df_posts.loc[idx, 'semantic_emb']):  # 이미 값이 있는 경우 스킵
            image_url = row['thumbnail_url']
            if not pd.isna(image_url) and image_url:
                embedding_tasks.append((idx, image_url))
    
    logger.info(f"임베딩 처리할 데이터 건수: {len(embedding_tasks)}")
    
    # 병렬 처리 실행
    embedding_success = 0
    if embedding_tasks:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # 임베딩 태스크 제출
            future_to_idx = {executor.submit(process_embedding, idx, url): idx for idx, url in embedding_tasks}
            
            # 결과 수집
            for future in as_completed(future_to_idx):
                try:
                    idx, embedding = future.result()
                    if embedding:
                        df_posts.loc[idx, 'semantic_emb'] = embedding
                        embedding_success += 1
                except Exception as e:
                    logger.error(f"임베딩 결과 처리 오류: {e}")
    
    # 성공률 계산
    if embedding_tasks:
        success_rate = (embedding_success / len(embedding_tasks)) * 100
        logger.info(f"임베딩 처리 완료: 성공 {embedding_success}/{len(embedding_tasks)} ({success_rate:.1f}%)")
    
    # 3. 데이터 정리 및 후처리
    # 결측치가 많은 경우 경고 출력
    null_counts = df_posts.isnull().sum()
    for col, count in null_counts.items():
        if count > 0:
            pct = (count / len(df_posts)) * 100
            logger.warning(f"'{col}' 컬럼에 결측치 {count}개 ({pct:.1f}%) 존재")
    
    # 4. SQLite DB에 저장
    logger.info("SQLite 데이터베이스에 데이터 저장 중...")
    try:
        # 데이터베이스 연결
        db_path = os.path.join(data_dir, "mvp.db")
        con = sqlite3.connect(db_path)
        
        # 테이블 작성
        df_influencers.to_sql('influencers', con, if_exists='replace', index=False)
        df_posts.to_sql('posts', con, if_exists='replace', index=False)
        
        logger.info(f"데이터베이스 저장 완료: {db_path}")
        
        # 데이터베이스 닫기
        con.close()
    except Exception as e:
        logger.error(f"데이터베이스 저장 실패: {e}")
        return
    
    # 백업
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(data_dir, "backup")
        os.makedirs(backup_dir, exist_ok=True)
        
        # CSV 백업
        influencers_backup = os.path.join(backup_dir, f"influencers_{timestamp}.csv")
        posts_backup = os.path.join(backup_dir, f"posts_{timestamp}.csv")
        
        df_influencers.to_csv(influencers_backup, index=False, encoding='utf-8-sig')
        df_posts.to_csv(posts_backup, index=False, encoding='utf-8-sig')
        
        logger.info(f"데이터 백업 완료: {backup_dir}")
    except Exception as e:
        logger.warning(f"데이터 백업 실패: {e}")
    
    # 총 실행 시간 계산
    elapsed_time = time.time() - start_time
    logger.info(f"ETL 프로세스 완료 (총 소요시간: {elapsed_time:.1f}초)")

if __name__ == "__main__":
    main() 
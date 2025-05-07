import pandas as pd
import sqlite3
import logging
import os
import sys
import time
import random
import functools
from datetime import datetime

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.api.utils.api_utils import ocr_test, translate, embed_image, retry_api_call

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API 재시도 관련 상수
MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_BACKOFF_TIME = 60

# API 호출 함수 (api_utils.py의 함수를 직접 사용)
def safe_ocr_test(image_url):
    return ocr_test(image_url)

def safe_translate(text):
    return translate(text)

def safe_embed_image(query, image_url):
    return embed_image(query, image_url)

def main():
    """ETL 메인 함수"""
    logger.info("ETL 프로세스 시작...")
    
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
    
    # 2. 데이터 변환 및 API 호출
    
    # 1. OCR을 통한 제품명 추출
    if 'product_name' not in df_posts.columns:
        logger.info("제품명 추출 (OCR) 처리 시작...")
        df_posts['product_name'] = None
        
    # thumbnail_url 기반으로 OCR 처리 (모든 데이터 처리)
    logger.info(f"OCR 처리할 데이터 건수: {len(df_posts)}")

    for idx, row in df_posts.iterrows():
        if pd.isna(df_posts.loc[idx, 'product_name']):  # 이미 값이 있는 경우 스킵
            image_url = row['thumbnail_url']
            if not pd.isna(image_url) and image_url:
                logger.info(f"[{idx+1}/{len(df_posts)}] OCR 처리 중: {image_url[:30]}...")
                product_name = safe_ocr_test(image_url)
                df_posts.loc[idx, 'product_name'] = product_name
                
    logger.info("OCR 처리 완료")

    # 2. 캡션 번역
    if 'translated_caption' not in df_posts.columns:
        logger.info("캡션 번역 처리 시작...")
        df_posts['translated_caption'] = None
        
    # caption_text 기반으로 번역 처리 (모든 데이터 처리)
    logger.info(f"번역 처리할 데이터 건수: {len(df_posts)}")
    
    for idx, row in df_posts.iterrows():
        if pd.isna(df_posts.loc[idx, 'translated_caption']):  # 이미 값이 있는 경우 스킵
            caption = row['caption_text']
            if not pd.isna(caption) and caption:
                logger.info(f"[{idx+1}/{len(df_posts)}] 번역 처리 중: {caption[:30]}...")
                translated = safe_translate(caption)
                df_posts.loc[idx, 'translated_caption'] = translated
                
    logger.info("번역 처리 완료")

    # 3. 이미지 임베딩
    if 'semantic_emb' not in df_posts.columns:
        logger.info("이미지 임베딩 처리 시작...")
        df_posts['semantic_emb'] = None
        
    # thumbnail_url 기반으로 임베딩 처리 (모든 데이터 처리)
    logger.info(f"임베딩 처리할 데이터 건수: {len(df_posts)}")
    
    embedding_success = 0  # 성공 횟수 추적
    
    for idx, row in df_posts.iterrows():
        if pd.isna(df_posts.loc[idx, 'semantic_emb']):  # 이미 값이 있는 경우 스킵
            image_url = row['thumbnail_url']
            if not pd.isna(image_url) and image_url:
                logger.info(f"[{idx+1}/{len(df_posts)}] 임베딩 처리 중: {image_url[:30]}...")
                try:
                    embedding = safe_embed_image('렌즈 사진', image_url)
                    if embedding:  # None이 아닌 경우만 저장
                        df_posts.loc[idx, 'semantic_emb'] = embedding
                        embedding_success += 1
                        logger.info(f"임베딩 성공 ({embedding_success}/{idx+1})")
                    else:
                        logger.warning(f"임베딩 결과가 없습니다: {idx+1}")
                except Exception as e:
                    logger.error(f"임베딩 저장 오류: {e}")
    
    logger.info(f"임베딩 처리 완료: 성공 {embedding_success}/{len(df_posts)} ({embedding_success/len(df_posts)*100:.1f}%)")
    
    # 4. 데이터 정리 및 후처리
    # 결측치가 많은 경우 경고 출력
    null_counts = df_posts.isnull().sum()
    for col, count in null_counts.items():
        if count > 0:
            pct = (count / len(df_posts)) * 100
            logger.warning(f"'{col}' 컬럼에 결측치 {count}개 ({pct:.1f}%) 존재")
    
    # 3. SQLite DB에 저장
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
    
    logger.info("ETL 프로세스 완료")

if __name__ == "__main__":
    main() 
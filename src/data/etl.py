import pandas as pd
import sqlite3
import logging
import os
from api.utils.api_utils import ocr_test, translate, embed_image

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 데이터 디렉토리 확인 및 생성
data_dir = 'data'
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
    logger.info(f"'{data_dir}' 디렉토리 생성 완료")

# CSV 파일 경로
influencers_csv = 'influencers.csv'
posts_csv = 'posts.csv'

# CSV 파일 읽기
try:
    # 현재 디렉토리 또는 data 디렉토리에서 파일을 찾습니다.
    if os.path.exists(influencers_csv):
        df_inf = pd.read_csv(influencers_csv)
        logger.info(f"CSV 파일 로드 완료: {influencers_csv}")
    elif os.path.exists(os.path.join(data_dir, influencers_csv)):
        df_inf = pd.read_csv(os.path.join(data_dir, influencers_csv))
        logger.info(f"CSV 파일 로드 완료: {os.path.join(data_dir, influencers_csv)}")
    else:
        logger.error(f"오류: {influencers_csv} 파일을 찾을 수 없습니다.")
        exit(1)
        
    if os.path.exists(posts_csv):
        df_posts = pd.read_csv(posts_csv)
        logger.info(f"CSV 파일 로드 완료: {posts_csv}")
    elif os.path.exists(os.path.join(data_dir, posts_csv)):
        df_posts = pd.read_csv(os.path.join(data_dir, posts_csv))
        logger.info(f"CSV 파일 로드 완료: {os.path.join(data_dir, posts_csv)}")
    else:
        logger.error(f"오류: {posts_csv} 파일을 찾을 수 없습니다.")
        exit(1)
        
except Exception as e:
    logger.error(f"CSV 파일 읽기 중 오류 발생: {e}")
    exit(1)

# 인플루언서 정보 처리
logger.info(f"인플루언서 데이터: {len(df_inf)}개 행")

# 게시물 정보 처리 및 API 호출
logger.info(f"게시물 데이터: {len(df_posts)}개 행")

# API 호출을 통한 데이터 보강
logger.info("API 호출을 통한 데이터 보강 시작...")

# 1. OCR을 통한 제품명 추출
if 'product_name' not in df_posts.columns:
    logger.info("제품명 추출 (OCR) 처리 시작...")
    df_posts['product_name'] = None
    
# thumbnail_url 기반으로 OCR 처리 (샘플 10개만)
sample_size = min(50, len(df_posts))
logger.info(f"OCR 처리할 샘플 크기: {sample_size}")

for idx, row in df_posts.head(sample_size).iterrows():
    if pd.isna(df_posts.loc[idx, 'product_name']):  # 이미 값이 있는 경우 스킵
        image_url = row['thumbnail_url']
        if not pd.isna(image_url) and image_url:
            logger.info(f"[{idx+1}/{sample_size}] OCR 처리 중: {image_url[:30]}...")
            product_name = ocr_test(image_url)
            df_posts.loc[idx, 'product_name'] = product_name
            
logger.info("OCR 처리 완료")

# 2. 캡션 번역
if 'translated_caption' not in df_posts.columns:
    logger.info("캡션 번역 처리 시작...")
    df_posts['translated_caption'] = None
    
# caption_text 기반으로 번역 처리 (샘플 10개만)
for idx, row in df_posts.head(sample_size).iterrows():
    if pd.isna(df_posts.loc[idx, 'translated_caption']):  # 이미 값이 있는 경우 스킵
        caption = row['caption_text']
        if not pd.isna(caption) and caption:
            logger.info(f"[{idx+1}/{sample_size}] 번역 처리 중: {caption[:30]}...")
            translated = translate(caption)
            df_posts.loc[idx, 'translated_caption'] = translated
            
logger.info("번역 처리 완료")

# 3. 이미지 임베딩
if 'semantic_emb' not in df_posts.columns:
    logger.info("이미지 임베딩 처리 시작...")
    df_posts['semantic_emb'] = None
    
# 이미지 및 캡션 기반 임베딩 생성 (샘플 10개만)
for idx, row in df_posts.head(sample_size).iterrows():
    if pd.isna(df_posts.loc[idx, 'semantic_emb']):  # 이미 값이 있는 경우 스킵
        image_url = row['thumbnail_url']
        caption = row['caption_text'] if not pd.isna(row['caption_text']) else "렌즈 사진"
        if not pd.isna(image_url) and image_url:
            logger.info(f"[{idx+1}/{sample_size}] 임베딩 처리 중: {image_url[:30]}...")
            embedding = embed_image(caption, image_url)
            if embedding:
                # 임베딩 벡터는 리스트이므로 문자열로 변환하여 저장
                df_posts.loc[idx, 'semantic_emb'] = str(embedding)
            
logger.info("임베딩 처리 완료")

# SQLite 데이터베이스 연결
try:
    # 데이터베이스 파일 경로
    db_path = os.path.join(data_dir, 'mvp.db')
    con = sqlite3.connect(db_path)
    logger.info(f"데이터베이스 연결 성공: {db_path}")

    # 데이터프레임을 SQL 테이블로 저장
    df_inf.to_sql('influencers', con, if_exists='replace', index=False)
    logger.info("'influencers' 테이블 저장 완료.")
    
    # 날짜 형식 처리
    if 'taken_at' in df_posts.columns:
        df_posts['taken_at'] = df_posts['taken_at'].astype(str)
    
    df_posts.to_sql('posts', con, if_exists='replace', index=False)
    logger.info("'posts' 테이블 저장 완료.")

except sqlite3.Error as e:
    logger.error(f"데이터베이스 작업 중 오류 발생: {e}")
except Exception as e:
    logger.error(f"데이터 저장 중 오류 발생: {e}")
finally:
    # 데이터베이스 연결 종료 (오류 발생 여부와 관계없이 실행)
    if 'con' in locals() and con:
        con.close()
        logger.info("데이터베이스 연결 종료.")

logger.info("ETL 스크립트 실행 완료.") 
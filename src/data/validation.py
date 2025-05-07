import sqlite3
import pandas as pd
import os
import logging

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_etl():
    """ETL 결과를 검증하는 함수"""
    # 데이터 디렉토리 확인
    data_dir = 'data'
    db_path = os.path.join(data_dir, 'mvp.db')
    
    if not os.path.exists(db_path):
        logger.error(f"데이터베이스 파일을 찾을 수 없습니다: {db_path}")
        return False
    
    try:
        # 데이터베이스 연결
        logger.info(f"데이터베이스 연결 중: {db_path}")
        con = sqlite3.connect(db_path)
        
        # 인플루언서 테이블 검증
        logger.info("인플루언서 테이블 검증 중...")
        df_inf = pd.read_sql('SELECT * FROM influencers', con)
        logger.info(f"인플루언서 테이블 레코드 수: {len(df_inf)}")
        logger.info(f"인플루언서 테이블 컬럼: {', '.join(df_inf.columns)}")
        logger.info(f"인플루언서 테이블 결측치:\n{df_inf.isnull().sum()}")
        
        # 게시물 테이블 검증
        logger.info("게시물 테이블 검증 중...")
        df_posts = pd.read_sql('SELECT * FROM posts', con)
        logger.info(f"게시물 테이블 레코드 수: {len(df_posts)}")
        logger.info(f"게시물 테이블 컬럼: {', '.join(df_posts.columns)}")
        
        # API 추가 컬럼 검증
        api_columns = ['product_name', 'translated_caption', 'semantic_emb']
        logger.info(f"API 추가 컬럼 검증 중: {', '.join(api_columns)}")
        
        for column in api_columns:
            if column in df_posts.columns:
                non_null_count = df_posts[column].notnull().sum()
                logger.info(f"'{column}' 컬럼 존재함: 비어있지 않은 값 {non_null_count}개")
            else:
                logger.warning(f"'{column}' 컬럼이 존재하지 않습니다.")
        
        # 게시물 테이블 결측치 확인
        logger.info("게시물 테이블 결측치:")
        logger.info(f"{df_posts.isnull().sum()}")
        
        # 샘플 데이터 출력
        logger.info("게시물 테이블 샘플 데이터 (처음 5개 행):")
        sample_columns = ['post_pk', 'user_pk', 'caption_text', 'product_name', 'translated_caption']
        if all(col in df_posts.columns for col in sample_columns):
            logger.info(f"\n{df_posts[sample_columns].head()}")
        else:
            available_columns = [col for col in sample_columns if col in df_posts.columns]
            logger.info(f"\n{df_posts[available_columns].head()}")
            
        # 검증 완료
        logger.info("ETL 결과 검증 완료")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"데이터베이스 작업 중 오류 발생: {e}")
        return False
    except Exception as e:
        logger.error(f"검증 중 오류 발생: {e}")
        return False
    finally:
        # 데이터베이스 연결 종료
        if 'con' in locals() and con:
            con.close()
            logger.info("데이터베이스 연결 종료")

if __name__ == "__main__":
    verify_etl() 
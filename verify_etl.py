"""
ETL 결과 검증 스크립트

이 스크립트는 ETL 처리 후 SQLite DB에 저장된 데이터를 검사하여
필수 컬럼 존재 여부, 결측치 개수, 데이터 품질 등을 확인합니다.

또한 API 구성과 환경 변수 설정을 확인하여 API 호출이 가능한지 검증합니다.
"""

import sqlite3
import pandas as pd
import os
import sys
import json
from datetime import datetime

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
from src.api.utils.config import log_config_status

# 결과 기록을 위한 함수
def log_result(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

# API 환경 확인
def verify_api_settings():
    log_result("\n==== API 환경 설정 검증 ====")
    
    # .env 파일 존재 확인
    if os.path.exists('.env'):
        log_result("✅ .env 파일이 존재합니다.")
    else:
        log_result("❌ .env 파일이 존재하지 않습니다. API 호출에 문제가 발생할 수 있습니다.", "ERROR")
    
    # API 설정 로깅
    from src.api.utils.config import API_KEY_ID, API_KEY, OCR_SECRET_KEY
    
    api_keys = {
        "API_KEY_ID": API_KEY_ID,
        "API_KEY": API_KEY,
        "OCR_SECRET_KEY": OCR_SECRET_KEY
    }
    
    for key, value in api_keys.items():
        if value:
            log_result(f"✅ {key}: 설정됨")
        else:
            log_result(f"❌ {key}: 설정되지 않음", "WARNING")
    
    # API URL 확인
    from src.api.utils.config import NAVER_OCR_URL, PAPAGO_NMT_API_URL, CLOVA_STUDIO_EMBEDDING_URL
    
    api_urls = {
        "OCR API URL": NAVER_OCR_URL,
        "Papago API URL": PAPAGO_NMT_API_URL,
        "CLOVA Studio Embedding URL": CLOVA_STUDIO_EMBEDDING_URL
    }
    
    for name, url in api_urls.items():
        if url:
            log_result(f"✅ {name}: {url}")
        else:
            log_result(f"❌ {name}: 설정되지 않음", "WARNING")
    
    return all(api_keys.values()) and all(api_urls.values())

# 컬럼 검증 함수
def validate_columns(df, required_columns, table_name):
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        log_result(f"오류: {table_name} 테이블에 필수 컬럼이 누락되었습니다: {', '.join(missing_columns)}", "ERROR")
        return False
    else:
        log_result(f"{table_name} 테이블 필수 컬럼 검증 성공: {', '.join(required_columns)}")
        return True

# 결측치 분석 함수
def analyze_null_values(df, table_name):
    null_counts = df[df.columns].isnull().sum()
    
    # 결측치가 있는 컬럼만 필터링
    null_columns = null_counts[null_counts > 0]
    
    if len(null_columns) > 0:
        log_result(f"{table_name} 테이블 결측치 분석:", "WARNING")
        for col, count in null_columns.items():
            percentage = (count / len(df)) * 100
            log_result(f"  - {col}: {count}개 ({percentage:.2f}%)", "WARNING")
    else:
        log_result(f"{table_name} 테이블에 결측치가 없습니다!")
    
    return null_counts

# 메인 함수
def main():
    # API 환경 설정 검증
    api_settings_valid = verify_api_settings()
    if not api_settings_valid:
        log_result("⚠️ API 환경 설정에 문제가 있습니다. API 호출 관련 기능이 제대로 작동하지 않을 수 있습니다.", "WARNING")
    
    # 데이터 디렉토리 경로
    data_dir = 'data'
    db_path = os.path.join(data_dir, 'mvp.db')
    
    # 데이터베이스 파일 존재 확인
    if not os.path.exists(db_path):
        log_result(f"오류: 데이터베이스 파일이 존재하지 않습니다: {db_path}", "ERROR")
        sys.exit(1)
    
    # SQLite 연결
    log_result(f"데이터베이스 연결 중: {db_path}")
    con = sqlite3.connect(db_path)
    
    try:
        # 테이블 목록 확인
        tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", con)
        log_result(f"데이터베이스 내 테이블 목록: {', '.join(tables['name'].tolist())}")
        
        # posts 테이블 검증
        log_result("\n==== posts 테이블 검증 ====")
        posts_df = pd.read_sql("SELECT * FROM posts", con)
        
        # 테이블 정보 출력
        log_result(f"총 레코드 수: {len(posts_df)}")
        log_result(f"컬럼 목록: {', '.join(posts_df.columns)}")
        
        # 필수 컬럼 검증
        required_columns = ['product_name', 'translated_caption', 'semantic_emb']
        column_valid = validate_columns(posts_df, required_columns, 'posts')
        
        if not column_valid:
            log_result("필수 컬럼 검증 실패", "ERROR")
        else:
            # 결측치 분석
            log_result("\n--- 결측치 분석 ---")
            null_counts = analyze_null_values(posts_df, 'posts')
            
            # API 처리 컬럼 분석
            log_result("\n--- API 처리 성공률 ---")
            total_records = len(posts_df)
            
            for col in required_columns:
                if col in posts_df.columns:
                    filled_count = total_records - null_counts.get(col, 0)
                    success_rate = (filled_count / total_records) * 100
                    log_result(f"{col}: {filled_count}/{total_records} ({success_rate:.2f}%)")
            
            # 샘플 데이터 출력
            log_result("\n--- 샘플 데이터 (5건) ---")
            sample_data = posts_df.head(5)
            
            # DataFrame 출력을 더 읽기 쉽게 설정
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', 1000)
            pd.set_option('display.max_colwidth', 30)
            
            print(sample_data[['product_name', 'translated_caption', 'caption_text']].to_string())
            
            # 검증 결과 요약
            log_result("\n=== 검증 결과 요약 ===")
            if null_counts.sum() == 0:
                log_result("✅ 모든 데이터가 정상적으로 처리되었습니다!")
            else:
                log_result(f"⚠️ 일부 데이터({null_counts.sum()}개)가 처리되지 않았습니다.", "WARNING")
    
        # influencers 테이블 검증
        log_result("\n==== influencers 테이블 검증 ====")
        influencers_df = pd.read_sql("SELECT * FROM influencers", con)
        log_result(f"총 인플루언서 수: {len(influencers_df)}")
        
        # 결과 파일로 저장
        verification_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(data_dir, f"verification_result_{verification_time}.txt")
        
        log_result(f"\n검증 결과를 파일에 저장: {result_file}")
        
    except Exception as e:
        log_result(f"데이터 검증 중 오류 발생: {e}", "ERROR")
    finally:
        # 연결 종료
        con.close()
        log_result("데이터베이스 연결 종료")

if __name__ == "__main__":
    main() 
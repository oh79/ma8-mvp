import pandas as pd
from instagrapi import Client
from instagrapi.exceptions import UserNotFound, PrivateAccount, LoginRequired, HashtagNotFound, ClientJSONDecodeError
import logging
import time
import os
from dotenv import load_dotenv
import random
import sys
import json
import requests
import functools
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import signal
import atexit
import argparse
import yaml
from pathlib import Path
import duckdb  # 설치 필요: pip install duckdb
from statistics import mean
from typing import List, Dict, Set, Tuple, Any, Optional

# 모듈화된 코드 임포트
from .db import DatabaseManager
from .api import InstagramClient, ProxyManager, fetch_instagram_data, send_notification
from .config import Config
from .utils import (
    setup_logging, register_signal_handlers, start_heartbeat_monitor,
    memory_usage, create_progress_report, save_progress_info, 
    clean_temp_files, parse_cli_args
)

# 전역 변수
influencers_info = {}
all_post_details = []
data_dir = "data"
db_manager = None
config = None

# 설정 파라미터 (나중에 YAML로 분리 가능)
SAVE_INTERVAL = 10
PROXY_SWITCH_THRESHOLD = 3
RATE_LIMIT_COOLDOWN = 60
MAX_PROXY_FAILURES = 5
PROXIES = []  # 프록시 목록 (비어있으면 직접 연결)
NUM_POSTS_TO_FETCH = 10  # 사용자별 게시물 수집 개수
TARGET_USERNAMES = []  # 수집 대상 사용자명 목록
TARGET_HASHTAGS = [
    '렌즈', 
    '콘택트렌즈', 
    '컬러렌즈', 
    '소프트렌즈', 
    'contactlens', 
    'colorlens', 
    'lens', 
    'softlens'
]  # 검색할 해시태그 목록

# User-Agent 목록 (로테이션에 사용)
UA_LIST = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 284.0.0.20.117",
    "Mozilla/5.0 (Android 10; Mobile; rv:123.0) Gecko/123.0 Firefox/123.0",
    "Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; 6T; OnePlus6T; qcom; en_US; 314665256)",
    "Mozilla/5.0 (Linux; Android 13; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
]

# 설정 로드 함수
def load_config(config_path="config.yaml"):
    """YAML 설정 파일에서 설정 로드"""
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}

# 데이터베이스 초기화
def init_database():
    """DuckDB 초기화 및 테이블 생성"""
    db_path = os.path.join(data_dir, "instagram.db")
    conn = duckdb.connect(db_path)
    
    # 인플루언서 테이블 생성
    conn.execute("""
        CREATE TABLE IF NOT EXISTS influencers (
            username VARCHAR PRIMARY KEY,
            pk BIGINT,
            full_name VARCHAR,
            follower_count INT,
            following_count INT,
            media_count INT,
            biography TEXT,
            category VARCHAR,
            external_url VARCHAR,
            is_private BOOLEAN,
            is_verified BOOLEAN
        )
    """)
    
    # 게시물 테이블 생성
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id VARCHAR PRIMARY KEY,
            user_pk BIGINT,
            username VARCHAR,
            caption TEXT,
            like_count INT,
            comment_count INT,
            taken_at TIMESTAMP,
            media_type INT,
            product_type VARCHAR,
            image_url VARCHAR,
            video_url VARCHAR
        )
    """)
    
    return conn

# 데이터베이스에 인플루언서 저장
def save_influencer_to_db(conn, influencer):
    """인플루언서 정보를 데이터베이스에 저장"""
    try:
        conn.execute("""
            INSERT OR REPLACE INTO influencers 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            influencer.get('username', ''),
            influencer.get('pk', 0),
            influencer.get('full_name', ''),
            influencer.get('follower_count', 0),
            influencer.get('following_count', 0),
            influencer.get('media_count', 0),
            influencer.get('biography', ''),
            influencer.get('category', ''),
            influencer.get('external_url', ''),
            influencer.get('is_private', False),
            influencer.get('is_verified', False)
        ))
        return True
    except Exception as e:
        logging.error(f"인플루언서 DB 저장 오류: {str(e)}")
        return False

# 데이터베이스에 게시물 저장
def save_post_to_db(conn, post):
    """게시물 정보를 데이터베이스에 저장"""
    try:
        conn.execute("""
            INSERT OR IGNORE INTO posts 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post.get('id', ''),
            post.get('user_pk', 0),
            post.get('username', ''),
            post.get('caption', ''),
            post.get('like_count', 0),
            post.get('comment_count', 0),
            post.get('taken_at', datetime.now()),
            post.get('media_type', 0),
            post.get('product_type', ''),
            post.get('image_url', ''),
            post.get('video_url', '')
        ))
        return True
    except Exception as e:
        logging.error(f"게시물 DB 저장 오류: {str(e)}")
        return False

# 저장 함수 (CSV + DB 동시 저장)
def save_data_to_csv(influencers, posts, is_temp=False, conn=None):
    """수집된 데이터를 CSV 파일 및 데이터베이스에 저장"""
    # 디렉토리가 없으면 생성
    os.makedirs(data_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    # 파일명 설정 (임시 파일은 접두어 추가)
    prefix = "temp_" if is_temp else ""
    influencers_file = os.path.join(data_dir, f"{prefix}influencers.csv")
    posts_file = os.path.join(data_dir, f"{prefix}posts.csv")
    
    # 인플루언서 정보를 DataFrame으로 변환하여 저장
    if influencers:
        influencers_df = pd.DataFrame(list(influencers.values()))
        influencers_df.to_csv(influencers_file, index=False)
        logging.info(f"인플루언서 데이터 {len(influencers)}건을 {influencers_file}에 저장했습니다.")
        
        # DB에도 저장
        if conn:
            for _, row in influencers_df.iterrows():
                save_influencer_to_db(conn, row.to_dict())
    
    # 게시물 정보를 DataFrame으로 변환하여 저장
    if posts:
        posts_df = pd.DataFrame(posts)
        posts_df.to_csv(posts_file, index=False)
        logging.info(f"게시물 데이터 {len(posts)}건을 {posts_file}에 저장했습니다.")
        
        # DB에도 저장
        if conn:
            for _, row in posts_df.iterrows():
                save_post_to_db(conn, row.to_dict())
    
    # 백업 파일 생성 (3시간마다)
    if not is_temp and (int(timestamp.split("_")[1]) % 300 == 0):
        backup_dir = os.path.join(data_dir, "backup")
        os.makedirs(backup_dir, exist_ok=True)
        
        if influencers:
            backup_influencers = os.path.join(backup_dir, f"influencers_{timestamp}.csv")
            influencers_df.to_csv(backup_influencers, index=False)
            
        if posts:
            backup_posts = os.path.join(backup_dir, f"posts_{timestamp}.csv")
            posts_df.to_csv(backup_posts, index=False)
            
        logging.info(f"백업 파일 생성 완료: {timestamp}")

# 시그널 핸들러 함수
def save_current_data_handler(signum=None, frame=None):
    """시그널을 받으면 현재까지 수집된 데이터를 저장"""
    global influencers_info, all_post_details, data_dir, db_manager
    
    logging.info(f"신호 수신: 현재까지 수집된 데이터 저장 중... ({len(influencers_info)}명 인플루언서, {len(all_post_details)}개 게시물)")
    
    if db_manager:
        db_manager.save_data_to_csv(influencers_info, all_post_details, is_temp=True)
    
    # 진행 상황 저장
    if 'start_time' in globals():
        save_progress_info(
            data_dir,
            TARGET_USERNAMES if 'TARGET_USERNAMES' in globals() else [],
            processed_users if 'processed_users' in globals() else set(),
            len(influencers_info),
            len(all_post_details),
            globals().get('start_time', time.time())
        )
    
    logging.info("중간 데이터 저장 완료")

# 종료 시 데이터 저장 함수 (atexit에 등록)
def save_and_exit():
    """프로그램 종료 시 데이터 저장"""
    global influencers_info, all_post_details, data_dir, db_manager
    
    logging.info("프로그램 종료 - 데이터 저장 중...")
    
    if db_manager:
        db_manager.save_data_to_csv(influencers_info, all_post_details, is_temp=False)
    
    logging.info("종료 시 데이터 저장 완료")
    
    # Slack/Discord 웹훅으로 알림 전송 (선택적)
    webhook_url = os.getenv('WEBHOOK_URL')
    if webhook_url:
        send_notification(
            "스크래핑 작업이 종료되었습니다.", 
            f"인플루언서 {len(influencers_info)}명, 게시물 {len(all_post_details)}개 수집 완료", 
            webhook_url
        )

# 개선된 인스타그램 데이터 수집 함수
def fetch_instagram_data_thread(username: str, proxy_manager: ProxyManager, user_agents: List[str]) -> Tuple[Optional[Dict], List[Dict]]:
    """스레드별 인스타그램 데이터 수집 함수"""
    # 스레드별 클라이언트 생성
    client = InstagramClient(proxy_manager, user_agents)
    
    try:
        # 클라이언트 초기화 및 로그인
        client.create_client()
        if not client.login():
            logging.error(f"[{username}] 인스타그램 로그인 실패")
            return None, []

        # 데이터 수집
        user_details, user_posts = fetch_instagram_data(client, username)
        return user_details, user_posts
    finally:
        # 클라이언트 세션 정리
        client.close()

# 메인 함수
def main():
    """메인 스크래퍼 함수"""
    global influencers_info, all_post_details, data_dir, db_manager, config
    global TARGET_USERNAMES, processed_users, start_time
    
    # 명령행 인수 파싱
    args = parse_cli_args()
    
    # 로깅 설정 - utils 모듈 사용
    log_level = getattr(logging, args.log_level)
    setup_logging(level=log_level)
    
    logging.info("인스타그램 스크래퍼 실행 시작")
    
    # 설정 로드
    config = Config(args.config)
    if not os.path.exists(args.config):
        logging.info(f"설정 파일 {args.config}이 없습니다. 기본값 생성합니다.")
        config.create_default_config()
    
    # 시작 시간 기록
    start_time = time.time()
    
    # 시그널 핸들러 등록
    register_signal_handlers(save_current_data_handler, save_and_exit)
    
    # 하트비트 모니터 시작
    start_heartbeat_monitor(save_current_data_handler)
    
    # 프록시 초기화
    config.load_proxies_from_env()
    proxy_manager = ProxyManager(config.proxies, config.max_proxy_failures)
    
    # 데이터베이스 초기화
    db_manager = DatabaseManager(data_dir)
    
    # 체크포인트 로드 (재수집 모드가 아닐 경우만)
    processed_users = set()
    if not args.rescrape:
        processed_users = db_manager.load_checkpoint()
        logging.info(f"체크포인트 로드: {len(processed_users)}명 이미 처리됨")
    else:
        logging.info("재수집 모드: 이미 처리된 사용자도 다시 수집합니다.")
    
    # 대상 사용자명 로드
    TARGET_USERNAMES = db_manager.load_target_usernames(args.users)
    logging.info(f"타겟 사용자명 로드 완료: {len(TARGET_USERNAMES)}명")
    
    # 임시 데이터 로드 (이전 실행이 중단된 경우)
    temp_influencers, temp_posts = db_manager.load_temp_data()
    if temp_influencers:
        influencers_info.update(temp_influencers)
        logging.info(f"임시 인플루언서 데이터 {len(temp_influencers)}건 로드됨")
    if temp_posts:
        all_post_details.extend(temp_posts)
        logging.info(f"임시 게시물 데이터 {len(temp_posts)}건 로드됨")
    
    # 대상 사용자 처리 
    if TARGET_USERNAMES:
        # 체크포인트에서 이미 처리된 사용자는 제외
        usernames_to_fetch = [u for u in TARGET_USERNAMES if u not in processed_users]
        logging.info(f"체크포인트에서 이미 처리된 사용자 {len(processed_users)}명 제외")
        logging.info(f"새로 수집할 사용자: {len(usernames_to_fetch)}명")
        
        # 최대 사용자 수 제한
        if args.max_users and len(usernames_to_fetch) > args.max_users:
            usernames_to_fetch = usernames_to_fetch[:args.max_users]
            logging.info(f"최대 사용자 수 제한: {args.max_users}명")
        
        # 테스트 모드인 경우 일부만 처리
        if args.dry_run:
            if usernames_to_fetch:
                usernames_to_fetch = usernames_to_fetch[:2]
                logging.info(f"테스트 모드: {len(usernames_to_fetch)}명만 수집합니다.")
            else:
                logging.warning("테스트 모드: 수집할 새 사용자가 없습니다.")
        
        if not usernames_to_fetch:
            logging.warning("모든 사용자가 이미 처리되었습니다. 수집할 새 사용자가 없습니다.")
            return True
            
        logging.info(f"수집 대상 사용자: {len(usernames_to_fetch)}명")
        
        # 사용자 처리 카운터
        processed_users_count = 0
        errors_count = 0
        
        # ThreadPoolExecutor로 병렬 수집
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            # 작업 제출
            future_to_username = {
                executor.submit(
                    fetch_instagram_data_thread, 
                    username, 
                    proxy_manager,
                    config.user_agents
                ): username for username in usernames_to_fetch
            }
            
            # 결과 수집
            for future in as_completed(future_to_username):
                username = future_to_username[future]
                try:
                    user_details, user_posts = future.result()
                    
                    # 성공적으로 가져온 경우에만 추가
                    if user_details:
                        influencers_info[username] = user_details
                        all_post_details.extend(user_posts)
                        
                        # 데이터베이스에 즉시 저장
                        db_manager.save_influencer(user_details)
                        for post in user_posts:
                            db_manager.save_post(post)
                        
                        # 체크포인트 업데이트
                        processed_users.add(username)
                        processed_users_count += 1
                        
                        logging.info(f"'{username}' 정보 수집 완료. 게시물 {len(user_posts)}개 추가. 총 {processed_users_count}/{len(usernames_to_fetch)}명 수집 완료.")
                    else:
                        errors_count += 1
                        logging.warning(f"'{username}' 정보 수집 실패.")
                        
                    # 주기적 저장 및 진행 상황 보고
                    if processed_users_count % config.save_interval == 0:
                        db_manager.save_checkpoint(processed_users)
                        db_manager.save_data_to_csv(influencers_info, all_post_details, is_temp=True)
                        
                        # 진행 상황 보고
                        mem_usage = memory_usage()
                        progress_report = create_progress_report(
                            len(usernames_to_fetch),
                            processed_users_count,
                            errors_count,
                            start_time,
                            mem_usage
                        )
                        
                        logging.info(f"중간 저장 완료 ({processed_users_count}명)\n{progress_report}")
                        
                        # 메모리 관리
                        if mem_usage > 500:  # 500MB 이상인 경우
                            logging.info("메모리 정리 중...")
                            import gc
                            gc.collect()
                except Exception as e:
                    logging.error(f"'{username}' 처리 중 오류: {str(e)}")
                    errors_count += 1
        
        # 해시태그로 부터 사용자 수집 - 생략 (기존 코드와 동일)
        
        # 최종 결과 저장
        db_manager.save_checkpoint(processed_users, force_save=True)
        db_manager.save_data_to_csv(influencers_info, all_post_details, is_temp=False)
        
        # 완료 메시지
        end_time = time.time()
        duration_hours = (end_time - start_time) / 3600
        logging.info(f"수집 완료: 인플루언서 {len(influencers_info)}명, 게시물 {len(all_post_details)}개")
        logging.info(f"총 소요 시간: {duration_hours:.2f}시간")
        
        # 임시 파일 정리
        clean_temp_files(data_dir)
        
    return True

# --- 메인 실행 로직 ---
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        logging.critical(f"프로그램 실행 중 치명적 오류 발생: {e}", exc_info=True) 
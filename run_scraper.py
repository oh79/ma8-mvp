#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
인스타그램 스크래퍼 실행 스크립트
2단계 파이프라인 구조 (태그 스캐너 -> 디테일 크롤러)
"""

import os
import sys
import signal
import logging
import atexit

# 기본 인코딩을 UTF-8로 설정
if sys.platform.startswith('win'):
    # Windows 환경에서 인코딩 설정
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 모듈 검색 경로에 현재 디렉토리 추가
sys.path.insert(0, os.path.abspath('.'))

from src.data.utils import setup_logging, parse_cli_args, load_config
from src.data.tag_scanner import run_tag_scanner
from src.data.detail_crawler import run_detail_crawler
from src.data.proxy_manager import ProxyManager

def main():
    """메인 함수"""
    # 명령행 인수 파싱
    args = parse_cli_args()
    
    # 로그 레벨 설정
    log_level = getattr(logging, args.log_level.upper())
    log_file = setup_logging(level=log_level)
    
    # 설정 파일 로드
    config = load_config(args.config)
    
    # 프록시 관리자 초기화
    proxies = config.get('proxies', [])
    max_proxy_failures = config.get('max_proxy_failures', 5)
    proxy_manager = ProxyManager(proxies=proxies, max_failures=max_proxy_failures) if proxies else None
    
    # 데이터 디렉토리 확인
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    # 모드에 따라 실행
    if args.mode == 'scan':
        # 태그 스캔 모드
        logging.info("태그 스캐너 모드로 실행")
        
        # 태그 목록 준비
        tags = args.tags.split(',') if args.tags else config.get('target_hashtags', [])
        if not tags:
            logging.error("스캔할 태그가 지정되지 않았습니다. --tags 옵션 또는 config.yaml 파일에 지정하세요.")
            sys.exit(1)
        
        # 병렬 처리 스레드 수
        max_workers = args.parallel or config.get('max_workers', 5)
        
        # 태그 스캐너 실행
        run_tag_scanner(
            tags=tags,
            amount=100,  # 태그당 수집할 게시물 수
            data_dir=data_dir,
            proxies=proxies,
            max_workers=max_workers,
            limit=args.limit
        )
        
    else:
        # 디테일 크롤링 모드
        logging.info("디테일 크롤러 모드로 실행")
        
        # 병렬 처리 스레드 수
        max_workers = args.parallel or config.get('max_workers', 5)
        
        # 게시물 수집 개수
        posts_per_user = config.get('num_posts_to_fetch', 10)
        
        # 디테일 크롤러 실행
        run_detail_crawler(
            data_dir=data_dir,
            specific_users=args.users,
            proxies=proxies,
            max_workers=max_workers,
            posts_per_user=posts_per_user,
            max_users=args.max_users,
            dry_run=args.dry_run
        )
    
    logging.info("스크래퍼 실행 완료")

def save_handler(signum=None, frame=None):
    """시그널 핸들러 - 데이터 저장"""
    logging.info(f"신호 수신 (신호 번호: {signum}) - 안전하게 종료합니다...")
    # 여기서는 특별한 처리가 필요 없음. 각 모듈에서 자체적으로 처리됨.

def exit_handler():
    """종료 시 실행할 함수"""
    logging.info("프로그램 종료...")

if __name__ == "__main__":
    try:
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, save_handler)
        signal.signal(signal.SIGTERM, save_handler)
        atexit.register(exit_handler)
        
        # 스크래퍼 실행
        main()
        
    except KeyboardInterrupt:
        logging.info("\n프로그램이 사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        logging.error(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 
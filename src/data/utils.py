import os
import sys
import time
import signal
import atexit
import logging
import threading
import functools
import random
import re
from pathlib import Path
from datetime import datetime
from typing import Set, Dict, List, Any, Optional, Callable, Tuple
from logging.handlers import RotatingFileHandler

def setup_logging(log_dir="logs", level=logging.INFO):
    """로깅 설정"""
    # 로그 디렉토리 생성
    os.makedirs(log_dir, exist_ok=True)
    
    # 로그 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    log_file = os.path.join(log_dir, f"scraper_{timestamp}.log")
    
    # 로깅 설정
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.info(f"로그 파일 생성됨: {log_file}")
    return log_file

def register_signal_handlers(save_handler: Callable, exit_handler: Callable) -> None:
    """시그널 핸들러 등록"""
    # 시그널 핸들러 등록
    signal.signal(signal.SIGTERM, save_handler)
    signal.signal(signal.SIGINT, save_handler)
    
    # Windows에서는 SIGUSR1이 없음
    if hasattr(signal, 'SIGUSR1'):
        signal.signal(signal.SIGUSR1, save_handler)
        
    # 종료 시 핸들러 등록
    atexit.register(exit_handler)
    
    logging.info("시그널 핸들러 등록 완료. Ctrl+C 또는 종료 신호로 안전하게 종료 가능")

def start_heartbeat_monitor(stop_handler: Callable, stop_flag_path="stop.flag", interval=10) -> threading.Thread:
    """중지 플래그 파일을 감시하는 스레드 시작"""
    def monitor_flag():
        while True:
            if Path(stop_flag_path).exists():
                logging.info(f"중지 플래그 파일 {stop_flag_path} 감지됨. 안전하게 종료합니다.")
                stop_handler()
                return
            time.sleep(interval)
    
    monitor_thread = threading.Thread(target=monitor_flag, daemon=True)
    monitor_thread.start()
    logging.info(f"하트비트 모니터 시작됨. '{stop_flag_path}' 파일 생성 시 안전하게 종료됩니다.")
    return monitor_thread

def memory_usage() -> float:
    """현재 프로세스의 메모리 사용량을 MB 단위로 반환"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        return mem_info.rss / 1024 / 1024  # MB 단위
    except ImportError:
        return 0.0

def format_time_elapsed(start_time: float) -> str:
    """경과 시간을 포맷팅"""
    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    
    if hours > 0:
        return f"{hours}시간 {minutes}분 {seconds}초"
    elif minutes > 0:
        return f"{minutes}분 {seconds}초"
    else:
        return f"{seconds}초"

def create_progress_report(
    total: int, 
    completed: int, 
    errors: int, 
    start_time: float,
    memory_mb: Optional[float] = None
) -> str:
    """진행 상황 보고서 생성"""
    progress_pct = (completed / total) * 100 if total > 0 else 0
    elapsed = format_time_elapsed(start_time)
    
    report = [
        f"진행 상황: {completed}/{total} ({progress_pct:.1f}%)",
        f"오류: {errors}건",
        f"실행 시간: {elapsed}"
    ]
    
    if memory_mb:
        report.append(f"메모리 사용량: {memory_mb:.1f} MB")
    
    return "\n".join(report)

def save_progress_info(
    data_dir: str,
    usernames: List[str], 
    processed_usernames: Set[str],
    influencers_count: int,
    posts_count: int,
    start_time: float
) -> None:
    """진행 상황 정보를 JSON 파일로 저장"""
    import json
    
    progress_file = os.path.join(data_dir, "scraping_progress.json")
    
    progress_data = {
        "total_users": len(usernames),
        "processed_users": len(processed_usernames),
        "influencers_count": influencers_count,
        "posts_count": posts_count,
        "start_time": start_time,
        "current_time": time.time(),
        "elapsed_seconds": time.time() - start_time,
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, indent=2)
    except Exception as e:
        logging.error(f"진행 상황 저장 중 오류: {str(e)}")

def clean_temp_files(data_dir: str) -> None:
    """임시 파일 정리"""
    temp_files = [
        os.path.join(data_dir, "temp_influencers.csv"),
        os.path.join(data_dir, "temp_posts.csv")
    ]
    
    for file_path in temp_files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"임시 파일 삭제됨: {file_path}")
        except Exception as e:
            logging.error(f"임시 파일 삭제 중 오류: {str(e)}")

def parse_cli_args():
    """명령행 인수 파싱"""
    import argparse
    
    parser = argparse.ArgumentParser(description='인스타그램 데이터 스크래핑')
    parser.add_argument('--mode', default='crawl', choices=['scan', 'crawl'], 
                        help='스크래퍼 모드 (scan: 태그 스캔, crawl: 세부 정보 크롤링)')
    parser.add_argument('--tags', help='스캔할 해시태그 (쉼표로 구분)')
    parser.add_argument('--limit', type=int, default=5000, help='수집할 최대 사용자 수')
    parser.add_argument('--parallel', type=int, default=5, help='병렬 처리 스레드 수')
    parser.add_argument('--dry-run', action='store_true', help='테스트 모드 (소량만 수집)')
    parser.add_argument('--config', default='config.yaml', help='설정 파일 경로')
    parser.add_argument('--rescrape', action='store_true', help='이미 처리된 사용자도 다시 수집')
    parser.add_argument('--users', help='수집할 특정 사용자 (쉼표로 구분)')
    parser.add_argument('--log-level', default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='로그 레벨')
    parser.add_argument('--max-users', type=int, help='최대 수집 사용자 수')
    
    return parser.parse_args()

def with_retry(max_retries=3, base_delay=5):
    """재시도 로직을 적용하는 데코레이터"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            last_exception = None
            
            # 클라이언트와 딜레이 어댑터 추출
            cl = kwargs.get('cl') if 'cl' in kwargs else args[0] if args else None
            delay_adapter = getattr(cl, 'delay_adapter', None)
            proxy_manager = getattr(cl, 'proxy_manager', None)
            
            # 요청 시작 시간
            start_time = None
            
            while retries <= max_retries:
                try:
                    # 요청 시작 시간 기록
                    start_time = time.time()
                    
                    result = func(*args, **kwargs)
                    
                    # 응답 시간 계산 및 기록
                    if start_time and delay_adapter:
                        rtt_ms = (time.time() - start_time) * 1000
                        delay_adapter.add_rtt(rtt_ms)
                        delay_adapter.report_success()
                        
                        # 딜레이 범위 업데이트
                        if hasattr(cl, 'delay_range'):
                            cl.delay_range = delay_adapter.get_delay_range()
                            
                    # 성공 시 프록시 매니저에 성공 보고
                    if cl and proxy_manager:
                        proxy_manager.report_success()
                        
                    return result
                except Exception as e:
                    # 응답 시간 측정 및 실패 보고
                    if start_time and delay_adapter:
                        delay_adapter.report_failure("429" in str(e))
                    
                    # 실패 로깅
                    logging.warning(f"API 오류 (재시도 {retries+1}/{max_retries}): {str(e)}")
                    last_exception = e
                    
                    # 프록시 매니저에 실패 보고
                    if cl and proxy_manager:
                        proxy = getattr(cl, 'proxy', None)
                        proxy_manager.report_failure(proxy)
                        
                        # 새 프록시 설정
                        new_proxy = proxy_manager.get_proxy()
                        if new_proxy:
                            cl.set_proxy(new_proxy)
                    
                    # 속도 제한으로 의심되는 429 오류 처리 - 더 긴 대기 시간
                    if "429" in str(e):
                        wait_time = 60  # 속도 제한 시 1분 대기
                        logging.warning(f"속도 제한 의심: {wait_time}초 대기 중...")
                        time.sleep(wait_time)
                    else:
                        # 지수 백오프: 기본 대기 시간에 2^retry * 무작위 요소 추가 
                        wait_time = base_delay * (2 ** retries) * (0.5 + random.random())
                        logging.info(f"재시도 대기 중: {wait_time:.2f}초...")
                        time.sleep(wait_time)
                
                retries += 1
            
            # 최대 재시도 횟수를 초과했을 때 마지막 예외 발생
            logging.error(f"최대 재시도 횟수 초과: {func.__name__}")
            raise last_exception
        
        return wrapper
    return decorator

@functools.lru_cache(maxsize=10000)
def parse_category(biography: str) -> str:
    """사용자 프로필에서 카테고리 분석"""
    # 비어있으면 빈 문자열 반환
    if not biography:
        return ""
    
    # 프로필에서 렌즈 관련 텍스트 찾기
    lens_keywords = [
        '렌즈', '콘택트', '컬러렌즈', '소프트렌즈', 
        'lens', 'contact', 'color lens', 'lenses'
    ]
    
    for keyword in lens_keywords:
        if keyword.lower() in biography.lower():
            return "렌즈"
    
    # 기타 가능한 카테고리
    categories = {
        "뷰티": ['뷰티', '화장품', '메이크업', 'beauty', 'makeup', 'cosmetic'],
        "패션": ['패션', '모델', '스타일', 'fashion', 'model', 'style'],
        "의류": ['의류', '쇼핑몰', '옷', 'clothing', 'apparel'],
        "여행": ['여행', '트립', 'travel', 'trip', 'journey'],
        "푸드": ['맛집', '음식', '레스토랑', 'food', 'restaurant'],
        "피트니스": ['피트니스', '운동', '헬스', 'fitness', 'workout', 'gym']
    }
    
    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword.lower() in biography.lower():
                return category
    
    # 이메일 또는 URL이 있으면 비즈니스 계정으로 간주
    if re.search(r'[\w\.-]+@[\w\.-]+', biography) or 'http' in biography:
        return "비즈니스"
    
    return "기타"

def load_config(config_path="config.yaml"):
    """YAML 설정 파일에서 설정 로드"""
    import yaml
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logging.info(f"설정 파일 로드됨: {config_path}")
            return config
        except Exception as e:
            logging.error(f"설정 파일 로드 오류: {str(e)}")
    else:
        logging.warning(f"설정 파일을 찾을 수 없음: {config_path}")
    
    # 기본 설정 반환
    return {
        "save_interval": 10,
        "proxy_switch_threshold": 3,
        "rate_limit_cooldown": 60,
        "max_proxy_failures": 5,
        "num_posts_to_fetch": 10,
        "max_workers": 5,
        "log_level": "INFO",
        "proxies": [],
        "user_agents": [],
        "target_hashtags": [
            "렌즈", "콘택트렌즈", "컬러렌즈", "소프트렌즈", 
            "contactlens", "colorlens", "lens", "softlens"
        ]
    } 
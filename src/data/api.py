import os
import time
import random
import logging
import functools
import requests
from instagrapi import Client
from instagrapi.exceptions import (
    UserNotFound, PrivateAccount, LoginRequired, 
    HashtagNotFound, ClientJSONDecodeError,
    ClientError, ClientLoginRequired, 
    ClientConnectionError, ClientForbiddenError
)
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from statistics import mean

# 응답 시간 기반 동적 딜레이 조정
class DynamicDelayAdapter:
    """응답 시간 기반 동적 딜레이 조정"""
    
    def __init__(self, base_low=1.0, base_high=3.0, window_size=10):
        self.base_low = base_low
        self.base_high = base_high
        self.window_size = window_size
        self.rtt_history = []
        self.failures = 0
    
    def add_rtt(self, rtt_ms):
        """응답 시간 기록"""
        self.rtt_history.append(rtt_ms)
        if len(self.rtt_history) > self.window_size:
            self.rtt_history.pop(0)
    
    def report_failure(self):
        """요청 실패 보고"""
        self.failures += 1
    
    def report_success(self):
        """요청 성공 보고"""
        self.failures = max(0, self.failures - 1)
    
    def get_delay_range(self):
        """현재 응답 시간 히스토리에 기반한 딜레이 범위 계산"""
        if not self.rtt_history:
            return [self.base_low, self.base_high]
        
        avg_rtt = mean(self.rtt_history)
        
        # 응답 시간이 길수록 대기 시간 증가
        # 실패가 많을수록 대기 시간 추가 증가
        factor = 1.0 + (0.2 * self.failures)
        low = max(self.base_low, (avg_rtt * 0.5 * factor) / 1000)
        high = max(self.base_high, (avg_rtt * 1.0 * factor) / 1000)
        
        return [low, high]

# 개선된 프록시 관리자
class ProxyManager:
    """프록시 관리 및 자동 전환"""
    
    def __init__(self, proxies, max_failures=5):
        self.proxies = proxies or [""]  # 빈 문자열은 직접 연결을 의미
        self.current_index = 0
        self.failures = {proxy: 0 for proxy in proxies} if proxies else {"": 0}
        self.consecutive_failures = 0
        self.lock = None  # threading.Lock() - 실제 사용시 설정
        self.last_proxy_switch = time.time()
        self.max_failures = max_failures
    
    def get_proxy(self):
        """다음 사용할 프록시 반환"""
        if not self.proxies or len(self.proxies) == 0:
            return None
                
        # 모든 프록시가 너무 많이 실패했는지 확인 
        if all(failures >= self.max_failures for failures in self.failures.values()):
            # 모든 프록시 재설정
            logging.warning("모든 프록시가 너무 많이 실패했습니다. 실패 카운터 재설정.")
            self.failures = {proxy: 0 for proxy in self.proxies}
        
        # 현재 프록시 너무 많이 실패했는지 확인
        current_proxy = self.proxies[self.current_index]
        if self.failures[current_proxy] >= self.max_failures:
            # 다음 프록시로 전환
            self.switch_proxy("너무 많은 실패")
        
        return self.proxies[self.current_index] if self.proxies[self.current_index] else None
    
    def report_failure(self, proxy):
        """프록시 실패 보고"""
        if proxy in self.failures:
            self.failures[proxy] += 1
        self.consecutive_failures += 1
        
        # 연속 실패가 임계값을 초과하면 프록시 전환
        if self.consecutive_failures >= 3:  # PROXY_SWITCH_THRESHOLD
            self.switch_proxy("연속 실패")
            self.consecutive_failures = 0
    
    def report_success(self):
        """프록시 성공 보고"""
        self.consecutive_failures = 0
        
    def switch_proxy(self, reason=""):
        """다음 프록시로 전환"""
        # 프록시 전환 속도 제한 (10초에 한 번만)
        current_time = time.time()
        if current_time - self.last_proxy_switch < 10:
            return
            
        if not self.proxies or len(self.proxies) <= 1:
            return
            
        old_proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        new_proxy = self.proxies[self.current_index]
        
        logging.info(f"프록시 전환: {old_proxy or '직접 연결'} -> {new_proxy or '직접 연결'} (이유: {reason})")
        self.last_proxy_switch = current_time
        
        # 잠시 대기하여 API 속도 제한 회피
        time.sleep(2)

# 개선된 재시도 데코레이터 (동적 딜레이 어댑터 지원)
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
                    if cl and hasattr(cl, 'proxy_manager'):
                        cl.proxy_manager.report_success()
                        
                    return result
                except (LoginRequired, ClientJSONDecodeError, ClientLoginRequired, 
                        ClientForbiddenError, ClientConnectionError) as e:
                    # 응답 시간 측정 및 실패 보고
                    if start_time and delay_adapter:
                        delay_adapter.report_failure()
                    
                    # 로그인 필요 또는 JSON 디코드 오류는 프록시 문제일 가능성이 높음
                    logging.warning(f"API 오류 (재시도 {retries+1}/{max_retries}): {str(e)}")
                    last_exception = e
                    
                    # 프록시 매니저에 실패 보고
                    if cl and hasattr(cl, 'proxy_manager'):
                        current_proxy = getattr(cl, 'proxy', None)
                        if current_proxy:
                            cl.proxy_manager.report_failure(current_proxy)
                            # 새 프록시 설정
                            new_proxy = cl.proxy_manager.get_proxy()
                            if new_proxy:
                                cl.proxy = new_proxy
                                logging.info(f"새 프록시 설정: {cl.proxy}")
                    
                    # 속도 제한으로 의심되는 401 오류 처리 - 더 긴 대기 시간
                    if "401" in str(e) or "429" in str(e):
                        wait_time = 60  # RATE_LIMIT_COOLDOWN
                        logging.warning(f"속도 제한 의심: {wait_time}초 대기 중...")
                        time.sleep(wait_time)
                    else:
                        # 지수 백오프: 기본 대기 시간에 2^retry * 무작위 요소 추가 
                        wait_time = base_delay * (2 ** retries) * (0.5 + random.random())
                        logging.info(f"재시도 대기 중: {wait_time:.2f}초...")
                        time.sleep(wait_time)
                except Exception as e:
                    # 응답 시간 측정 및 실패 보고
                    if start_time and delay_adapter:
                        delay_adapter.report_failure()
                        
                    # 다른 예외 처리
                    logging.error(f"예상치 못한 오류 (재시도 {retries+1}/{max_retries}): {str(e)}")
                    last_exception = e
                    
                    # 짧은 대기 시간
                    wait_time = base_delay * (1 + random.random())
                    time.sleep(wait_time)
                
                retries += 1
            
            # 최대 재시도 횟수를 초과했을 때 마지막 예외 발생
            logging.error(f"최대 재시도 횟수 초과: {func.__name__}")
            raise last_exception
        
        return wrapper
    return decorator

# 인스타그램 클라이언트 관리 클래스
class InstagramClient:
    """인스타그램 API 클라이언트 관리"""
    
    def __init__(self, proxy_manager=None, user_agents=None):
        self.proxy_manager = proxy_manager
        self.user_agents = user_agents or []
        self.client = None
        self.delay_adapter = DynamicDelayAdapter()
    
    def create_client(self):
        """새 인스타그램 클라이언트 인스턴스 생성"""
        cl = Client()
        
        # 딜레이 범위 설정
        cl.delay_range = self.delay_adapter.get_delay_range()
            
        # 랜덤 User-Agent 설정
        if self.user_agents:
            cl.user_agent = random.choice(self.user_agents)
        
        # 프록시 설정 (있는 경우)
        if self.proxy_manager:
            proxy = self.proxy_manager.get_proxy()
            if proxy:
                cl.set_proxy(proxy)
                
        self.client = cl
        return cl
    
    def login(self):
        """인스타그램에 로그인"""
        if not self.client:
            self.create_client()
            
        cl = self.client
        
        # 환경 변수에서 로그인 정보 가져오기
        from dotenv import load_dotenv
        load_dotenv()  # .env 파일에서 환경 변수 로드
        
        username = os.getenv('INSTAGRAM_USERNAME')
        password = os.getenv('INSTAGRAM_PASSWORD')
        session_path = os.getenv('INSTAGRAM_SESSION_PATH', 'session.json')
        
        if not username or not password:
            logging.error("환경 변수에 인스타그램 로그인 정보가 없습니다.")
            return False
        
        try:
            # 세션 파일이 존재하면 불러오기
            if os.path.exists(session_path):
                try:
                    cl.load_settings(session_path)
                    logging.info("세션 설정 로드 완료")
                    
                    # 세션이 유효한지 확인
                    try:
                        cl.get_timeline_feed()
                        logging.info("기존 세션으로 로그인 성공")
                        return True
                    except (ClientLoginRequired, ClientError) as e:
                        logging.warning(f"세션이 만료되었거나 유효하지 않습니다: {str(e)}")
                    except Exception as e:
                        logging.warning(f"세션 확인 중 오류 발생: {str(e)}")
                except Exception as e:
                    logging.warning(f"세션 로드 실패: {str(e)}")
            
            # 직접 로그인 시도
            logging.info(f"인스타그램 계정 {username}으로 로그인 시도 중...")
            cl.login(username, password)
            
            # 세션 저장
            cl.dump_settings(session_path)
            logging.info("로그인 성공 및 세션 저장 완료")
            return True
        except Exception as e:
            logging.error(f"로그인 실패: {str(e)}")
            return False
    
    @with_retry(max_retries=3)
    def get_user_info(self, username):
        """사용자 정보 가져오기"""
        if not self.client:
            raise ValueError("클라이언트가 초기화되지 않았습니다. login() 먼저 호출하세요.")
            
        try:
            return self.client.user_info_by_username(username)
        except UserNotFound:
            logging.warning(f"사용자를 찾을 수 없음: {username}")
            return None
        except PrivateAccount:
            logging.warning(f"비공개 계정: {username}")
            user = self.client.user_info_by_username(username)
            return user  # 제한된 정보만 반환
        except Exception as e:
            logging.error(f"사용자 정보 가져오기 실패: {str(e)}")
            raise
    
    @with_retry(max_retries=3)
    def get_user_medias(self, user_pk, amount=10):
        """사용자 게시물 가져오기"""
        if not self.client:
            raise ValueError("클라이언트가 초기화되지 않았습니다. login() 먼저 호출하세요.")
            
        try:
            return self.client.user_medias(user_pk, amount)
        except Exception as e:
            logging.error(f"게시물 가져오기 실패: {str(e)}")
            raise
    
    @with_retry(max_retries=3)
    def get_hashtag_medias(self, hashtag, amount=20):
        """해시태그로 게시물 검색"""
        if not self.client:
            raise ValueError("클라이언트가 초기화되지 않았습니다. login() 먼저 호출하세요.")
            
        try:
            return self.client.hashtag_medias_recent(hashtag, amount)
        except HashtagNotFound:
            logging.warning(f"해시태그를 찾을 수 없음: {hashtag}")
            return []
        except Exception as e:
            logging.error(f"해시태그 검색 실패: {str(e)}")
            raise
    
    def close(self):
        """클라이언트 세션 정리"""
        if self.client:
            try:
                self.client.close()
                logging.info("클라이언트 세션 정리 완료")
            except:
                logging.warning("클라이언트 세션 정리 중 오류 발생")

# 인스타그램 데이터 수집 함수
def fetch_instagram_data(client, username):
    """인스타그램 사용자 데이터 수집"""
    try:
        # 사용자 정보 가져오기
        user_info = client.get_user_info(username)
        if not user_info:
            logging.warning(f"[{username}] 사용자 정보를 가져올 수 없습니다.")
            return None, []
            
        user_pk = user_info.pk
        
        # 추가 정보 가공
        user_details = {
            'username': username,
            'pk': user_pk,
            'full_name': user_info.full_name,
            'follower_count': user_info.follower_count,
            'following_count': user_info.following_count,
            'media_count': user_info.media_count,
            'biography': user_info.biography,
            'category': parse_category(user_info.biography),
            'external_url': user_info.external_url,
            'is_private': user_info.is_private,
            'is_verified': user_info.is_verified
        }
        
        # 비공개 계정이면 게시물을 가져오지 않음
        if user_info.is_private:
            logging.warning(f"[{username}] 비공개 계정입니다. 게시물을 가져오지 않습니다.")
            return user_details, []
    except Exception as e:
        logging.error(f"[{username}] 사용자 정보 조회 중 오류: {str(e)}")
        return None, []
        
    # 최근 게시물 가져오기
    user_posts = []
    try:
        medias = client.get_user_medias(user_pk, 10)  # NUM_POSTS_TO_FETCH
        
        for media in medias:
            # 기본 게시물 정보
            post_info = {
                'id': media.id,
                'user_pk': user_pk,
                'username': username,
                'caption': media.caption_text if hasattr(media, 'caption_text') else '',
                'like_count': media.like_count,
                'comment_count': media.comment_count,
                'taken_at': media.taken_at,
                'media_type': media.media_type,
                'product_type': getattr(media, 'product_type', None),
                'image_url': getattr(media, 'thumbnail_url', None),
                'video_url': getattr(media, 'video_url', None)
            }
            user_posts.append(post_info)
            
        logging.info(f"[{username}] {len(user_posts)}개 게시물 수집 완료")
    except Exception as e:
        logging.error(f"[{username}] 게시물 수집 중 오류: {str(e)}")
        # 사용자 정보만 반환
        return user_details, []
        
    return user_details, user_posts

# 바이오그래피에서 카테고리 추출 함수
@functools.lru_cache(maxsize=10000)
def parse_category(biography):
    """바이오그래피에서 카테고리 추출 (캐싱 적용)"""
    if not biography:
        return None
        
    # 카테고리 키워드 매핑
    keywords = {
        '렌즈': 'contacts',
        '콘택트': 'contacts',
        '컬러렌즈': 'contacts',
        '소프트렌즈': 'contacts',
        '뷰티': 'beauty',
        '메이크업': 'makeup',
        '화장품': 'cosmetics',
        '패션': 'fashion',
        '모델': 'model',
        '아이돌': 'idol',
        '가수': 'singer',
        '배우': 'actor',
        '인플루언서': 'influencer',
        '유튜버': 'youtuber',
    }
    
    for keyword, category in keywords.items():
        if keyword in biography:
            return category
            
    return None

# 알림 전송 함수
def send_notification(title, message, webhook_url=None):
    """Slack/Discord 웹훅으로 알림 전송"""
    if not webhook_url:
        webhook_url = os.getenv('WEBHOOK_URL')
        
    if not webhook_url:
        return
        
    try:
        payload = {
            "text": f"*{title}*\n{message}"
        }
        requests.post(webhook_url, json=payload)
        logging.info(f"알림 전송 완료: {title}")
    except Exception as e:
        logging.error(f"알림 전송 실패: {str(e)}") 
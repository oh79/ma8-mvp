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

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.core.nlp import parse_category

# .env 파일에서 환경 변수 로드 (민감 정보 관리)
# 스크립트 시작 시점에 호출하여 필요한 환경 변수를 로드합니다.
load_dotenv()

# 로깅 설정
# INFO 레벨 이상의 로그를 콘솔에 출력합니다.
# TODO: 로그 파일 저장, 로그 로테이션 등 운영 환경에 맞는 로깅 전략 구성
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 설정값 --- 
# .env 파일에서 인스타그램 계정 정보 읽기
# 환경 변수가 설정되지 않은 경우 None이 됩니다.
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')
# TODO: INSTAGRAM_USERNAME 또는 INSTAGRAM_PASSWORD 가 없을 경우 오류 처리 또는 사용자 안내 추가

# --- 스크래핑 대상 설정 ---
# 관련 해시태그 목록 (광고 관련 + 뷰티 관련 + 렌즈 관련)
TARGET_HASHTAGS = [
    '렌즈', 
    '콘택트렌즈', 
    '컬러렌즈', 
    '소프트렌즈', 
    'contactlens', 
    'colorlens', 
    'lens', 
    'softlens'
]
MAX_USERS_TO_COLLECT = 15  # 수집할 최대 사용자 수 (50에서 3으로 변경)
MIN_USERS_TO_COLLECT = 10  # 최소 필요 사용자 수 (10에서 3으로 변경)
HASHTAG_MEDIA_COUNT = 20   # 해시태그당 조회할 게시물 수 
MAX_POSTS_PER_USER = 10    # 사용자당 수집할 최대 게시물 수
NUM_POSTS_TO_FETCH = 10 # 각 사용자별로 가져올 최근 게시물 개수

# 스크래핑 대상 사용자 명 (비워두고 해시태그 기반으로 수집)
TARGET_USERNAMES = []

# --- API 요청 관련 설정 ---
RETRY_DELAY_SECONDS = 30  # 기본 재시도 지연 (지수적으로 증가)
MAX_RETRIES = 5           # 최대 재시도 횟수
MAX_BACKOFF_TIME = 600    # 최대 백오프 시간 (초)

# --- 프록시 설정 (필요시 활성화) ---
# 실제 프록시 사용 시 설정
PROXIES = []
# PROXIES = [
#     "http://user:pass@proxy1:8080",
#     "http://user:pass@proxy2:8080"
# ]

def get_proxy():
    """사용 가능한 프록시 중 하나를 무작위로 선택"""
    if PROXIES:
        return random.choice(PROXIES)
    return None

# 재시도 데코레이터
def with_retry(max_retries=3, base_delay=2):
    """함수 호출 재시도 데코레이터"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        logging.error(f"{func.__name__} 최대 재시도 횟수 도달: {e}")
                        return None
                    
                    wait_time = base_delay * (2 ** (retries - 1)) + random.uniform(0, 1)
                    logging.warning(f"{func.__name__} 호출 실패: {e}. {wait_time:.2f}초 후 재시도 ({retries}/{max_retries})")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator

def handle_two_factor(username):
    """2단계 인증 처리 함수"""
    code = input(f"인스타그램 계정 {username}의 2단계 인증 코드를 입력하세요: ")
    return code

@with_retry(max_retries=5, base_delay=3)
def login_to_instagram(client):
    """강화된 인스타그램 로그인 로직"""
    session_file = "session.json"
    logging.info("인스타그램 로그인 시도...")
    try:
        # 세션 파일이 있으면 로드 시도
        if os.path.exists(session_file):
            logging.info(f"'{session_file}'에서 세션 로드 시도...")
            client.load_settings(session_file)
            logging.info("세션 로드 완료. API 재로그인 시도 (세션 유효성 검사)...")
            # 세션 유효성 검사를 위해 간단한 API 호출
            try:
                client.account_info() 
                logging.info("세션 유효함. 기존 세션 사용.")
                return True
            except Exception as e:
                logging.warning(f"세션 유효성 검사 중 오류 발생: {e}. 새로 로그인 시도.")
    except Exception as e:
        logging.warning(f"세션 로드 실패: {e}. 새로 로그인 시도...")
        
    # 세션 로드 실패 또는 세션 만료/오류 시 새로 로그인
    try:
        username = os.getenv('INSTAGRAM_USERNAME')
        password = os.getenv('INSTAGRAM_PASSWORD')
        
        if not username or not password:
            logging.error("인스타그램 사용자 이름 또는 비밀번호가 .env 파일에 설정되지 않았습니다.")
            return False
            
        # 로그인 전 클라이언트 설정 초기화 (세션 충돌 방지)
        client.set_settings({})
        
        # 로그인 시도
        client.login(
            username,
            password,
            verification_code=handle_two_factor 
        )
        
        # 성공 시 세션 정보 파일로 저장
        client.dump_settings(session_file)
        logging.info(f"로그인 성공 및 세션 저장 완료: {session_file}")
        return True
    except Exception as login_err:
         logging.error(f"로그인 최종 실패: {login_err}")
         return False

@with_retry(max_retries=3, base_delay=2)
def get_user_info(cl, username):
    """사용자 정보 가져오기"""
    logging.info(f"사용자 정보 가져오는 중: {username}")
    user_info = cl.user_info_by_username(username)
    logging.info(f"사용자 PK 확인: {user_info.pk}")
    return user_info

@with_retry(max_retries=3, base_delay=2)
def get_user_medias(cl, user_pk, amount):
    """사용자의 게시물 가져오기"""
    logging.info(f"사용자 PK {user_pk}의 최근 게시물 {amount}개 가져오는 중...")
    try:
        posts = cl.user_medias_gql(user_pk, amount=amount)  # 먼저 GraphQL API 시도
        logging.info(f"GraphQL API로 게시물 {len(posts)}개 가져옴")
        return posts
    except Exception as e:
        logging.warning(f"GraphQL API 실패: {e}. 대체 API 사용...")
        # 실패하면 피드 API로 대체
        time.sleep(random.uniform(1, 3))  # 짧은 지연 후 재시도
        posts = cl.user_medias(user_pk, amount=amount)
        logging.info(f"피드 API로 게시물 {len(posts)}개 가져옴")
        return posts

@with_retry(max_retries=3, base_delay=2)
def get_hashtag_medias(cl, tag, amount):
    """해시태그 관련 게시물 가져오기"""
    logging.info(f"해시태그 '#{tag}' 관련 게시물 가져오는 중...")
    try:
        # 최근 게시물 시도
        medias = cl.hashtag_medias_recent(tag, amount=amount)
        logging.info(f"해시태그 '#{tag}'에서 {len(medias)}개 게시물 찾음")
        return medias
    except Exception as e:
        logging.warning(f"최근 게시물 가져오기 실패: {e}")
        # 일시 대기 후 재시도
        time.sleep(random.uniform(3, 5))
        try:
            # 인기 게시물 시도
            medias = cl.hashtag_medias_top(tag, amount=amount)
            logging.info(f"인기 게시물로 대체: 해시태그 '#{tag}'에서 {len(medias)}개 게시물 찾음")
            return medias
        except Exception as e2:
            logging.error(f"인기 게시물 가져오기도 실패: {e2}")
            # 빈 리스트 반환
            return []

def fetch_instagram_data(cl, username):
    """지정된 사용자의 프로필 정보와 최근 게시물 메타데이터를 가져옵니다."""
    user_info = None
    post_details_list = []

    # 1. 사용자 정보 가져오기
    try:
        user_info = get_user_info(cl, username)
    except UserNotFound:
        logging.warning(f"사용자를 찾을 수 없음: {username}. 스킵합니다.")
        return None, []
    except PrivateAccount:
        logging.warning(f"비공개 계정임: {username}. 프로필 정보만 수집합니다.")
        # 비공개 계정은 프로필 정보만 가져오고 게시물은 없음
        biography_text = user_info.biography.replace('\\n', ' ') if user_info and user_info.biography and isinstance(user_info.biography, str) else ""
        estimated_category = parse_category(biography_text) if user_info else None
        
        influencer_details = {
            'username': user_info.username if user_info else username,
            'pk': user_info.pk if user_info else None,
            'full_name': user_info.full_name if user_info else None,
            'follower_count': user_info.follower_count if user_info else None,
            'following_count': user_info.following_count if user_info else None,
            'media_count': user_info.media_count if user_info else None,
            'biography': biography_text,
            'category': estimated_category,
            'external_url': user_info.external_url if user_info else None,
            'is_private': True,
            'is_verified': user_info.is_verified if user_info else None,
        }
        return influencer_details, []
    except Exception as e:
        logging.error(f"사용자 정보 가져오기 실패: {e}")
        return None, []

    # 사용자 정보를 성공적으로 가져오지 못했으면 종료
    if user_info is None:
        logging.error(f"사용자 정보 '{username}'를 가져오는데 실패했습니다. 스킵합니다.")
        return None, []

    # 2. 최근 게시물 정보 가져오기
    try:
        posts = get_user_medias(cl, user_info.pk, NUM_POSTS_TO_FETCH)
        
        # 게시물 정보 리스트 생성
        for post in posts:
            post_details = {
                'post_pk': post.pk,
                'user_pk': user_info.pk,
                'taken_at': post.taken_at,
                'media_type': post.media_type,
                'like_count': post.like_count,
                'comment_count': post.comment_count,
                'caption_text': post.caption_text.replace('\n', ' ') if post.caption_text and isinstance(post.caption_text, str) else post.caption_text,
                'code': post.code,
                'thumbnail_url': post.thumbnail_url,
                'video_url': post.video_url if post.media_type == 2 else None,
            }
            post_details_list.append(post_details)
    except Exception as e:
        logging.error(f"게시물 정보 가져오기 실패: {e}")
    
    # 게시물 정보를 최종적으로 가져오지 못했더라도 수집된 사용자 정보와 함께 반환
    if not post_details_list:
        logging.warning(f"게시물 정보 '{username}'를 가져오는데 실패했습니다.")

    # 인플루언서 정보 딕셔너리 생성 (사용자 정보 가져오기 성공 시)
    biography_text = user_info.biography.replace('\\n', ' ') if user_info.biography and isinstance(user_info.biography, str) else ""
    # 카테고리 추정 (biography 기반)
    estimated_category = parse_category(biography_text)
    logging.info(f"사용자 '{username}'의 추정 카테고리: {estimated_category}")

    influencer_details = {
        'username': user_info.username,
        'pk': user_info.pk,
        'full_name': user_info.full_name,
        'follower_count': user_info.follower_count,
        'following_count': user_info.following_count,
        'media_count': user_info.media_count,
        'biography': biography_text,
        'category': estimated_category,
        'external_url': user_info.external_url,
        'is_private': user_info.is_private,
        'is_verified': user_info.is_verified,
    }

    return influencer_details, post_details_list

def main():
    """메인 함수 - 인스타그램 데이터 스크래핑 실행"""
    # 클라이언트 인스턴스 초기화
    cl = Client()
    
    # 사람처럼 행동하기 위한 자동 딜레이 설정
    cl.delay_range = [3, 7]  # 모든 API 호출 후 3~7초 무작위 지연 (이전보다 더 긴 시간)
    
    # 프록시 설정 (있는 경우)
    proxy = get_proxy()
    if proxy:
        cl.set_proxy(proxy)
    
    # 로그인
    if not login_to_instagram(cl):
        logging.error("인스타그램 로그인 실패. 프로그램을 종료합니다.")
        return
    
    # 수집된 인플루언서 정보를 저장할 딕셔너리 (username -> details)
    influencers_info = {}
    
    # 게시물 상세 정보 리스트
    all_post_details = []
    
    # TARGET_USERNAMES가 설정되어 있으면 해당 계정 정보 가져오기
    if TARGET_USERNAMES:
        logging.info(f"지정된 사용자 명단({len(TARGET_USERNAMES)}명)에서 데이터 수집 시작...")
        for username in TARGET_USERNAMES:
            try:
                # 사용자 및 게시물 정보 가져오기
                influencer_details, post_details_list = fetch_instagram_data(cl, username)
                
                # 사용자 정보 수집에 성공한 경우에만 추가
                if influencer_details:
                    influencers_info[username] = influencer_details
                    all_post_details.extend(post_details_list)
                    logging.info(f"'{username}' 정보 수집 완료. 게시물 {len(post_details_list)}개 추가.")
                else:
                    logging.warning(f"'{username}' 정보 수집 실패 또는 게시물 없음.")
                
                # 인스타그램 서버 부하 방지를 위한 무작위 지연
                time.sleep(random.uniform(5, 10))
            except Exception as e:
                logging.error(f"'{username}' 처리 중 예외 발생: {e}", exc_info=True)
                # 한 사용자 처리 중 오류가 발생해도 다른 사용자는 계속해서 수집
                continue
    
    # 해시태그 기반으로 수집
    try:
        lens_influencers = set()  # 렌즈 관련 인플루언서 세트 (중복 제거)
        
        # 해시태그 처리 시작
        if not TARGET_USERNAMES or len(influencers_info) < MIN_USERS_TO_COLLECT:
            logging.info(f"해시태그 기반 데이터 수집 시작 (대상 해시태그: {len(TARGET_HASHTAGS)}개)...")
            
            # 각 해시태그에 대해 처리
            for tag in TARGET_HASHTAGS:
                if len(influencers_info) >= MAX_USERS_TO_COLLECT:
                    logging.info(f"최대 사용자 수({MAX_USERS_TO_COLLECT}명)에 도달했습니다. 해시태그 검색을 중단합니다.")
                    break
                    
                logging.info(f"해시태그 '#{tag}' 관련 게시물 수집 시작 (최대 {HASHTAG_MEDIA_COUNT}개)...")
                
                try:
                    # 해시태그로 게시물 검색
                    medias = get_hashtag_medias(cl, tag, HASHTAG_MEDIA_COUNT)
                    
                    if not medias:
                        logging.warning(f"해시태그 '#{tag}'에서 게시물을 찾지 못했습니다. 다음 해시태그로 진행합니다.")
                        continue
                    
                    # 각 게시물의 작성자 정보 수집
                    for media in medias:
                        if len(influencers_info) >= MAX_USERS_TO_COLLECT:
                            logging.info(f"최대 사용자 수({MAX_USERS_TO_COLLECT}명)에 도달했습니다. 검색을 중단합니다.")
                            break
                            
                        try:
                            user_pk = media.user.pk
                            username = media.user.username
                            
                            # 이미 처리한 사용자는 스킵
                            if username in influencers_info:
                                logging.info(f"사용자 '{username}'는 이미 처리됨. 스킵.")
                                continue
                            
                            # 렌즈 인플루언서 목록에 추가
                            lens_influencers.add(username)
                            
                            # 사용자 및 게시물 정보 가져오기
                            influencer_details, post_details_list = fetch_instagram_data(cl, username)
                            
                            # 사용자 정보 수집에 성공한 경우에만 추가
                            if influencer_details:
                                influencers_info[username] = influencer_details
                                all_post_details.extend(post_details_list)
                                logging.info(f"'{username}' 정보 수집 완료. 게시물 {len(post_details_list)}개 추가.")
                            else:
                                logging.warning(f"'{username}' 정보 수집 실패 또는 게시물 없음.")
                                
                            # 인스타그램 서버 부하 방지를 위한 무작위 지연
                            time.sleep(random.uniform(5, 10))
                        except Exception as user_e:
                            logging.error(f"게시물 작성자 '{username}' 처리 중 오류: {user_e}")
                            continue
                
                except Exception as tag_e:
                    logging.error(f"해시태그 '#{tag}' 처리 중 오류 발생: {tag_e}")
                    continue
                
                # 해시태그 간 지연 추가
                time.sleep(random.uniform(8, 15))
        
        # 렌즈 인플루언서 목록을 파일로 저장
        if lens_influencers:
            lens_influencers_file = "data/lens_influencers.txt"
            os.makedirs(os.path.dirname(lens_influencers_file), exist_ok=True)
            with open(lens_influencers_file, "w", encoding="utf-8") as f:
                for username in lens_influencers:
                    f.write(f"{username}\n")
            logging.info(f"렌즈 인플루언서 목록({len(lens_influencers)}명)을 {lens_influencers_file}에 저장했습니다.")
    
    except Exception as e:
        logging.error(f"해시태그 기반 수집 중 예외 발생: {e}", exc_info=True)
    
    # 수집된 데이터 분석 및 로깅
    logging.info(f"수집 완료: 인플루언서 {len(influencers_info)}명, 게시물 {len(all_post_details)}개")
    
    # 최소 필요 데이터 확인
    if len(influencers_info) < MIN_USERS_TO_COLLECT:
        logging.warning(f"수집된 인플루언서 수({len(influencers_info)})가 최소 필요 수({MIN_USERS_TO_COLLECT})보다 적습니다.")
    
    # 수집된 데이터를 CSV 파일로 저장
    logging.info("수집된 데이터를, CSV 파일로 저장합니다...")
    
    # 데이터 디렉토리 확인 및 생성
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        logging.info(f"'{data_dir}' 디렉토리 생성 완료")
    
    # 인플루언서 데이터를 DataFrame으로 변환
    influencers_df = pd.DataFrame(list(influencers_info.values()))
    
    # 게시물 데이터를 DataFrame으로 변환
    posts_df = pd.DataFrame(all_post_details)
    
    # 날짜 필드가 있다면 문자열로 변환 (CSV 저장 시 오류 방지)
    if not posts_df.empty and 'taken_at' in posts_df.columns:
        posts_df['taken_at'] = posts_df['taken_at'].astype(str)
    
    # CSV 파일로 저장
    influencers_file = os.path.join(data_dir, "influencers.csv")
    posts_file = os.path.join(data_dir, "posts.csv")
    
    # 인플루언서 데이터 저장
    if not influencers_df.empty:
        influencers_df.to_csv(influencers_file, index=False, encoding='utf-8-sig')
        logging.info(f"인플루언서 데이터 {len(influencers_df)}건을 {influencers_file}에 저장했습니다.")
    else:
        logging.warning("저장할 인플루언서 데이터가 없습니다.")
    
    # 게시물 데이터 저장
    if not posts_df.empty:
        posts_df.to_csv(posts_file, index=False, encoding='utf-8-sig')
        logging.info(f"게시물 데이터 {len(posts_df)}건을 {posts_file}에 저장했습니다.")
    else:
        logging.warning("저장할 게시물 데이터가 없습니다.")
    
    logging.info("스크래핑 작업이 완료되었습니다.")

# --- 메인 실행 로직 ---
if __name__ == "__main__":
    main() 
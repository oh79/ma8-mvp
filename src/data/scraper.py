import pandas as pd
from instagrapi import Client
from instagrapi.exceptions import UserNotFound, PrivateAccount, LoginRequired, HashtagNotFound, ClientJSONDecodeError
import logging
import time
import os
from dotenv import load_dotenv
import random
from core.nlp import parse_category
import sys
import json
import requests

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
    '광고', 
    # '협찬', 'sponsored', # 광고 지표
    '뷰티스타그램', 
    # 'kbeauty', '화장품추천', '코덕', '메이크업', # 뷰티 카테고리
    '올리브영추천템',
    # '스킨케어루틴', # 좀 더 구체적인 뷰티 관련
    '렌즈', 
    # '콘택트렌즈', '컬러렌즈', '소프트렌즈', # 렌즈 관련 한글 해시태그
    # 'contactlens', 'colorlens', 'lens', 'softlens' # 렌즈 관련 영어 해시태그
]
MAX_USERS_TO_COLLECT = 3  # 수집할 최대 사용자 수 (50에서 3으로 변경)
MIN_USERS_TO_COLLECT = 3  # 최소 필요 사용자 수 (10에서 3으로 변경)
HASHTAG_MEDIA_COUNT = 10   # 해시태그당 조회할 게시물 수 
MAX_POSTS_PER_USER = 10    # 사용자당 수집할 최대 게시물 수
NUM_POSTS_TO_FETCH = 10 # 각 사용자별로 가져올 최근 게시물 개수

# 스크래핑 대상 사용자 명 (비워두고 해시태그 기반으로 수집)
TARGET_USERNAMES = []

# --- API 요청 관련 설정 ---
RETRY_DELAY_SECONDS = 45 # API 요청 실패 시 재시도 전 대기 시간 (초) - 추가 증가
MAX_RETRIES = 10 # API 요청 최대 재시도 횟수 - 추가 증가
USER_FETCH_DELAY_MIN = 30 # 사용자 정보 조회 사이의 최소 대기 시간 (초) - 추가 증가
USER_FETCH_DELAY_MAX = 60 # 사용자 정보 조회 사이의 최대 대기 시간 (초) - 추가 증가
INTRA_USER_DELAY_MIN = 10.0 # 한 사용자의 게시물 조회 등 내부 요청 간 최소 대기 시간 (초) - 추가 증가
INTRA_USER_DELAY_MAX = 20.0 # 한 사용자의 게시물 조회 등 내부 요청 간 최대 대기 시간 (초) - 추가 증가
# TODO: 위 지연 시간들은 인스타그램 API 정책 변경 및 네트워크 상황에 따라 조절 필요
# --- --- 

def handle_two_factor(username):
    """2단계 인증 처리 함수"""
    code = input(f"인스타그램 계정 {username}의 2단계 인증 코드를 입력하세요: ")
    return code

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
            # 세션 유효성 검사를 위해 간단한 API 호출 (예: cl.account_info())
            try:
                client.account_info() 
                logging.info("세션 유효함. 기존 세션 사용.")
                return True
            except LoginRequired:
                logging.warning("세션 만료 또는 유효하지 않음. 새로 로그인 시도.")
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

        # 사람처럼 보이도록 헤더 설정 (선택 사항이지만 도움이 될 수 있음)
        # client.user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1"
        
        # 로그인 시도
        client.login(
            username,
            password,
            # 2단계 인증이 활성화된 경우 호출될 함수
            verification_code=handle_two_factor 
        )
        
        # 성공 시 세션 정보 파일로 저장
        client.dump_settings(session_file)
        logging.info(f"로그인 성공 및 세션 저장 완료: {session_file}")
        return True
    except LoginRequired:
        logging.error("로그인에 2단계 인증 코드가 필요하지만 제공되지 않았거나 잘못되었습니다.")
        logging.error("또는 계정 정보가 잘못되었을 수 있습니다.")
        return False
    except Exception as login_err:
         logging.error(f"로그인 최종 실패: {login_err}")
         # TODO: 실패 원인에 따라 다른 에러 메시지 제공 고려
         return False

def fetch_instagram_data(cl: Client, username: str):
    """지정된 사용자의 프로필 정보와 최근 게시물 메타데이터를 가져옵니다.

    Args:
        cl (Client): Instagrapi 클라이언트 객체.
        username (str): 조회할 인스타그램 사용자 이름.

    Returns:
        tuple: (인플루언서 상세 정보 딕셔너리, 게시물 상세 정보 리스트) 튜플.
               오류 발생 또는 사용자를 찾을 수 없는 경우 (None, []) 또는 (프로필 정보, []) 반환.
    """
    user_info = None
    post_details_list = []

    # 1. 사용자 정보 가져오기 (재시도 포함)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info(f"[시도 {attempt}/{MAX_RETRIES}] 사용자 정보 가져오는 중: {username}")
            user_info = cl.user_info_by_username(username)
            logging.info(f"사용자 PK 확인: {user_info.pk}")
            break # 성공 시 루프 탈출
        except UserNotFound:
            logging.warning(f"사용자를 찾을 수 없음: {username}. 스킵합니다.")
            return None, [] # 사용자를 찾을 수 없으면 즉시 종료
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
            return influencer_details, [] # 비공개 계정은 게시물 없이 프로필 정보만 반환
        except LoginRequired:
            logging.warning(f"[시도 {attempt}/{MAX_RETRIES}] 로그인 필요 오류 발생 (사용자: {username}). {RETRY_DELAY_SECONDS}초 후 재시도...")
            # TODO: 여기서는 relogin 시도보다 메인 루프에서 로그인 상태 점검 및 처리하는 것이 더 나을 수 있음.
            time.sleep(RETRY_DELAY_SECONDS)
        except (requests.exceptions.RequestException, ClientJSONDecodeError, json.JSONDecodeError, KeyError) as e:
            logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 사용자 정보 '{username}' 처리 중 API 오류 발생: {type(e).__name__} - {e}")
            if attempt < MAX_RETRIES:
                logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logging.error(f"사용자 정보 '{username}'를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")
                return None, []
        except Exception as e:
            logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 사용자 정보 '{username}' 처리 중 예상치 못한 오류 발생: {type(e).__name__} - {e}", exc_info=True)
            if attempt < MAX_RETRIES:
                logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logging.error(f"사용자 정보 '{username}'를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")
                return None, []

    # 사용자 정보를 성공적으로 가져오지 못했으면 종료
    if user_info is None:
        logging.error(f"사용자 정보 '{username}'를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")
        return None, []

    # 사용자 내 요청 간 지연 (차단 방지 목적)
    intra_user_delay = random.uniform(INTRA_USER_DELAY_MIN, INTRA_USER_DELAY_MAX)
    logging.debug(f"사용자 내 요청 지연: {intra_user_delay:.2f}초")
    time.sleep(intra_user_delay)

    # 2. 최근 게시물 정보 가져오기 (재시도 포함)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info(f"[시도 {attempt}/{MAX_RETRIES}] {username}의 최근 게시물 {NUM_POSTS_TO_FETCH}개 가져오는 중...")
            posts = cl.user_medias(user_info.pk, amount=NUM_POSTS_TO_FETCH)
            logging.info(f"{username}의 게시물 {len(posts)}개 가져옴")
            
            # --- 게시물 정보 리스트 생성 ---
            for post in posts:
                # TODO: media_type 외에 다양한 필드(e.g., tagged_users, location) 추가 수집 고려
                post_details = {
                    'post_pk': post.pk, # 게시물 고유 ID
                    'user_pk': user_info.pk, # 인플루언서 정보와 연결하기 위한 외래 키 역할
                    'taken_at': post.taken_at, # 게시물 작성 시간 (datetime 객체)
                    'media_type': post.media_type, # 1: 사진, 2: 동영상, 8: 캐러셀(앨범)
                    'like_count': post.like_count,
                    'comment_count': post.comment_count,
                    # caption_text가 존재하고 문자열일 경우에만 replace 적용
                    'caption_text': post.caption_text.replace('\n', ' ') if post.caption_text and isinstance(post.caption_text, str) else post.caption_text,
                    'code': post.code, # 게시물 고유 코드 (URL 생성용: https://www.instagram.com/p/CODE/)
                    'thumbnail_url': post.thumbnail_url, # 썸네일 이미지 URL
                    'video_url': post.video_url if post.media_type == 2 else None, # 동영상인 경우 동영상 URL
                    # TODO: 캐러셀(media_type=8)의 경우 내부 미디어 정보 추가 수집 (resources 리스트 활용)
                }
                post_details_list.append(post_details)
                
            break # 성공 시 루프 탈출
            
        except LoginRequired:
             logging.warning(f"[시도 {attempt}/{MAX_RETRIES}] 로그인 필요 오류 발생 (게시물 - 사용자: {username}). {RETRY_DELAY_SECONDS}초 후 재시도...")
             # TODO: 여기서는 relogin 시도보다 메인 루프에서 로그인 상태 점검 및 처리하는 것이 더 나을 수 있음.
             time.sleep(RETRY_DELAY_SECONDS)
        except (requests.exceptions.RequestException, ClientJSONDecodeError, json.JSONDecodeError, KeyError) as e:
            logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 게시물 정보 '{username}' 처리 중 API 오류 발생: {type(e).__name__} - {e}")
            if attempt < MAX_RETRIES:
                logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logging.error(f"게시물 정보 '{username}'를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")
        except Exception as e:
            logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 게시물 정보 '{username}' 처리 중 예상치 못한 오류 발생: {type(e).__name__} - {e}", exc_info=True)
            if attempt < MAX_RETRIES:
                logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logging.error(f"게시물 정보 '{username}'를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")

    # 게시물 정보를 최종적으로 가져오지 못했더라도 수집된 사용자 정보와 함께 반환
    if not post_details_list:
        logging.warning(f"게시물 정보 '{username}'를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다.")

    # --- 인플루언서 정보 딕셔너리 생성 (사용자 정보 가져오기 성공 시) ---
    # user_info는 이미 위에서 성공적으로 가져왔음을 확인했음
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
        'biography': biography_text, # biography 저장 (줄바꿈 제거됨)
        'category': estimated_category, # 추정된 카테고리 추가
        'external_url': user_info.external_url,
        'is_private': user_info.is_private,
        'is_verified': user_info.is_verified,
    }

    return influencer_details, post_details_list

# 해시태그 검색이 실패했을 경우를 대비한 대안 메서드
def collect_users_from_popular_accounts(client, max_users=30):
    """인기 뷰티/렌즈 계정의 팔로워를 수집하는 대안 방법"""
    # 뷰티/렌즈 관련 인기 계정 목록
    popular_accounts = [
        "lens_naver", 
        "olens_official", 
        "lensnine_official", 
        "anncolor_official", 
        "clalen_official",
        "makeup_ifan",
        "acuvue_korea", # 아큐브 코리아 추가
        "bausch_lomb_korea", # 바슈롬 코리아 추가
        "johnson_and_johnson_vision" # 존슨앤존슨 비전 추가
    ]
    
    collected_users = set()
    
    for username in popular_accounts:
        if len(collected_users) >= max_users:
            break
            
        user_id = None
        # 1. 인기 계정 사용자 정보 가져오기 (재시도 포함)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logging.info(f"[시도 {attempt}/{MAX_RETRIES}] 인기 계정 '{username}' 정보 가져오는 중...")
                user_info = client.user_info_by_username(username)
                user_id = user_info.pk
                logging.debug(f"인기 계정 '{username}' PK 확인: {user_id}")
                break # 성공 시 루프 탈출
            except UserNotFound:
                 logging.warning(f"인기 계정 '{username}'를 찾을 수 없습니다. 스킵합니다.")
                 user_id = None # 찾을 수 없으면 user_id None 설정 후 루프 탈출
                 break # 즉시 루프 탈출
            except LoginRequired:
                 logging.warning(f"[시도 {attempt}/{MAX_RETRIES}] 로그인 필요 오류 발생 (인기 계정 정보: {username}). {RETRY_DELAY_SECONDS}초 후 재시도...")
                 # TODO: 여기서는 relogin 시도보다 메인 루프에서 로그인 상태 점검 및 처리하는 것이 더 나을 수 있음.
                 time.sleep(RETRY_DELAY_SECONDS)
            except (requests.exceptions.RequestException, ClientJSONDecodeError, json.JSONDecodeError, KeyError) as e:
                logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 인기 계정 정보 '{username}' 처리 중 API 오류 발생: {type(e).__name__} - {e}")
                if attempt < MAX_RETRIES:
                    logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                     logging.error(f"인기 계정 정보 '{username}'를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")
                     user_id = None # 실패 시 user_id None 설정
            except Exception as e:
                logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 인기 계정 정보 '{username}' 처리 중 예상치 못한 오류 발생: {type(e).__name__} - {e}", exc_info=True)
                if attempt < MAX_RETRIES:
                    logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    logging.error(f"인기 계정 정보 '{username}'를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")
                    user_id = None # 실패 시 user_id None 설정

        # user_id를 성공적으로 가져왔으면 팔로워 수집 시도 (재시도 포함)
        if user_id:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logging.info(f"[시도 {attempt}/{MAX_RETRIES}] '{username}' 계정 팔로워 가져오는 중...")
                    followers = client.user_followers(user_id, amount=10)
                    logging.info(f"'{username}' 계정에서 팔로워 {len(followers)}명 발견.")
                    
                    # 팔로워 처리
                    for user_pk, follower_info in followers.items():
                        collected_users.add(follower_info.username)
                        if len(collected_users) >= max_users:
                            break # 최대 사용자 수 도달 시 내부 루프 탈출
                    break # 성공 시 루프 탈출
                    
                except LoginRequired:
                     logging.warning(f"[시도 {attempt}/{MAX_RETRIES}] 로그인 필요 오류 발생 (팔로워 - 인기 계정: {username}). {RETRY_DELAY_SECONDS}초 후 재시도...")
                     # TODO: 여기서는 relogin 시도보다 메인 루프에서 로그인 상태 점검 및 처리하는 것이 더 나을 수 있음.
                     time.sleep(RETRY_DELAY_SECONDS)
                except (requests.exceptions.RequestException, ClientJSONDecodeError, json.JSONDecodeError, KeyError) as e:
                    logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 인기 계정 '{username}' 팔로워 처리 중 API 오류 발생: {type(e).__name__} - {e}")
                    if attempt < MAX_RETRIES:
                        logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                        time.sleep(RETRY_DELAY_SECONDS)
                    else:
                        logging.error(f"인기 계정 '{username}' 팔로워를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")
                except Exception as e:
                    logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 인기 계정 '{username}' 팔로워 처리 중 예상치 못한 오류 발생: {type(e).__name__} - {e}", exc_info=True)
                    if attempt < MAX_RETRIES:
                        logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                        time.sleep(RETRY_DELAY_SECONDS)
                    else:
                        logging.error(f"인기 계정 '{username}' 팔로워를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")

        # 최대 사용자 수 도달 시 외부 루프 탈출
        if len(collected_users) >= max_users:
            break
            
        # API 요청 간 지연 (계정 처리 사이)
        delay = random.uniform(INTRA_USER_DELAY_MIN, INTRA_USER_DELAY_MAX) # 변경된 내부 지연 상수 사용
        logging.debug(f"다음 인기 계정 처리 전 {delay:.2f}초 대기...")
        time.sleep(delay)
            
    return collected_users

def direct_accounts_fallback(client):
    """해시태그 검색 실패 시 직접 탐색할 계정 목록"""
    direct_accounts = [
        "olens_official", "clalen_official", "acuvue_korea",
        "bausch_lomb_korea", "johnson_and_johnson_vision"
    ]
    
    collected_users = set()
    logging.info("직접 지정된 계정 목록에서 사용자 수집 시작...")
    
    for username in direct_accounts:
        # 사용자 정보 조회만 시도 (게시물은 메인 루프에서 수집) (재시도 포함)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                 logging.info(f"[시도 {attempt}/{MAX_RETRIES}] 직접 계정 '{username}' 정보 수집 시도 중...")
                 user_info = client.user_info_by_username(username)
                 collected_users.add(user_info.username)
                 logging.info(f"직접 계정 '{username}' 정보 수집 완료.")
                 break # 성공 시 루프 탈출
                 
            except UserNotFound:
                logging.warning(f"직접 계정 '{username}'를 찾을 수 없습니다. 스킵합니다.")
                break # 즉시 루프 탈출
            except LoginRequired:
                 logging.warning(f"[시도 {attempt}/{MAX_RETRIES}] 로그인 필요 오류 발생 (직접 계정: {username}). {RETRY_DELAY_SECONDS}초 후 재시도...")
                 # TODO: 여기서는 relogin 시도보다 메인 루프에서 로그인 상태 점검 및 처리하는 것이 더 나을 수 있음.
                 time.sleep(RETRY_DELAY_SECONDS)
            except (requests.exceptions.RequestException, ClientJSONDecodeError, json.JSONDecodeError, KeyError) as e:
                logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 직접 계정 '{username}' 처리 중 API 오류 발생: {type(e).__name__} - {e}")
                if attempt < MAX_RETRIES:
                    logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    logging.error(f"직접 계정 '{username}' 정보를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")
            except Exception as e:
                logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 직접 계정 '{username}' 처리 중 예상치 못한 오류 발생: {type(e).__name__} - {e}", exc_info=True)
                if attempt < MAX_RETRIES:
                    logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    logging.error(f"직접 계정 '{username}' 정보를 {MAX_RETRIES}번 시도했지만 가져오는데 실패했습니다. 스킵합니다.")

        # API 요청 간 지연 (계정 처리 사이)
        delay = random.uniform(INTRA_USER_DELAY_MIN, INTRA_USER_DELAY_MAX)
        logging.debug(f"다음 직접 계정 처리 전 {delay:.2f}초 대기...")
        time.sleep(delay)
            
    return collected_users

# --- 메인 실행 로직 ---
if __name__ == "__main__":
    # 인스타그램 클라이언트 초기화
    cl = Client()

    # 로그인 시도
    if not login_to_instagram(cl):
        logging.error("인스타그램 로그인 실패. 스크립트를 종료합니다.")
        sys.exit(1)
        
    # 로그인 성공 후 API 호출 전 잠시 대기
    time.sleep(10) # 대기 시간 추가 증가

    # --- 해시태그 기반 사용자 목록 생성 ---
    target_usernames_set = set()
    logging.info(f"지정된 해시태그에서 최대 {MAX_USERS_TO_COLLECT}명의 사용자 수집 시작...")

    for hashtag in TARGET_HASHTAGS:
        if len(target_usernames_set) >= MAX_USERS_TO_COLLECT:
            logging.info(f"목표 사용자 수({MAX_USERS_TO_COLLECT}명) 도달. 해시태그 검색 중단.")
            break
            
        medias = []
        # 해시태그 미디어 조회 (재시도 포함)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logging.info(f"[시도 {attempt}/{MAX_RETRIES}] 해시태그 '#{hashtag}'의 게시물 {HASHTAG_MEDIA_COUNT}개 조회 중...")
                # 먼저 hashtag_medias_recent 메서드 시도
                medias = cl.hashtag_medias_recent(hashtag, amount=HASHTAG_MEDIA_COUNT)
                logging.info(f"'#{hashtag}' 해시태그에서 게시물 {len(medias)}개 발견 (recent).")
                break # 성공 시 루프 탈출
            except HashtagNotFound:
                 logging.warning(f"해시태그 '#{hashtag}'를 찾을 수 없습니다. 스킵합니다.")
                 medias = [] # 찾을 수 없으면 빈 리스트 설정 후 루프 탈출
                 break # 즉시 루프 탈출
            except LoginRequired:
                 logging.warning(f"[시도 {attempt}/{MAX_RETRIES}] 로그인 필요 오류 발생 (해시태그: {hashtag}). {RETRY_DELAY_SECONDS}초 후 재시도...")
                 # TODO: 여기서는 relogin 시도보다 메인 루프에서 로그인 상태 점검 및 처리하는 것이 더 나을 수 있음.
                 time.sleep(RETRY_DELAY_SECONDS)
            except (requests.exceptions.RequestException, ClientJSONDecodeError, json.JSONDecodeError, KeyError) as e:
                logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 해시태그 '#{hashtag}' 처리 중 API 오류 발생: {type(e).__name__} - {e}")
                # 최신 게시물 실패 시 인기 게시물 시도 로직은 제거하고 단순 재시도로 변경 -> 다시 추가, 마지막 시도에서만
                if attempt < MAX_RETRIES:
                    logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                     logging.error(f"해시태그 '#{hashtag}' 처리 최종 실패. 최대 재시도 횟수 초과. 인기 게시물 시도..." ) # 실패 로깅 변경
                     # 최대 재시도 후에도 실패 시 인기 게시물 시도
                     try:
                         medias = cl.hashtag_medias_top(hashtag, amount=HASHTAG_MEDIA_COUNT)
                         logging.info(f"'#{hashtag}' 해시태그에서 게시물 {len(medias)}개 발견 (top) after retries.")
                     except Exception as e2:
                         logging.error(f"해시태그 '#{hashtag}' 인기 게시물 시도도 실패: {type(e2).__name__} - {e2}")
                         medias = [] # 두 메서드 모두 실패 시 빈 리스트
                     break # 인기 게시물 시도 후 루프 탈출 (성공/실패와 무관)
            except Exception as e:
                logging.error(f"[시도 {attempt}/{MAX_RETRIES}] 해시태그 '#{hashtag}' 처리 중 예상치 못한 오류 발생: {type(e).__name__} - {e}", exc_info=True)
                if attempt < MAX_RETRIES:
                     logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
                     time.sleep(RETRY_DELAY_SECONDS)
                else:
                     logging.error(f"해시태그 '#{hashtag}' 처리 최종 실패. 최대 재시도 횟수 초과. 인기 게시물 시도..." ) # 실패 로깅 변경
                     # 최대 재시도 후에도 실패 시 인기 게시물 시도
                     try:
                         medias = cl.hashtag_medias_top(hashtag, amount=HASHTAG_MEDIA_COUNT)
                         logging.info(f"'#{hashtag}' 해시태그에서 게시물 {len(medias)}개 발견 (top) after retries.")
                     except Exception as e2:
                         logging.error(f"해시태그 '#{hashtag}' 인기 게시물 시도도 실패: {type(e2).__name__} - {e2}")
                         medias = [] # 두 메서드 모두 실패 시 빈 리스트
                     break # 인기 게시물 시도 후 루프 탈출 (성공/실패와 무관)

        # medias가 비어있지 않으면 사용자 정보 추출
        if medias:
            for media in medias:
                if media.user:
                    username = media.user.username
                    target_usernames_set.add(username)
                    if len(target_usernames_set) >= MAX_USERS_TO_COLLECT:
                        break # 내부 루프도 중단
                else:
                      # 게시물에서 사용자 정보를 찾을 수 없는 경우 (빈 값 등)
                      logging.debug(f"게시물(ID: {media.pk})에서 사용자 정보를 찾을 수 없습니다.") # 경고 대신 디버그 레벨로 변경

        # API 요청 간 지연 (해시태그 처리 사이)
        hashtag_delay = random.uniform(INTRA_USER_DELAY_MIN, INTRA_USER_DELAY_MAX)
        logging.debug(f"다음 해시태그 처리 전 {hashtag_delay:.2f}초 대기...")
        time.sleep(hashtag_delay)

    target_usernames_list = list(target_usernames_set)
    
    # 해시태그 검색으로 충분한 사용자를 찾지 못한 경우, 인기 계정 검색 또는 직접 계정 검색 실행
    if len(target_usernames_set) < MIN_USERS_TO_COLLECT:
        logging.warning(f"해시태그 검색으로 충분한 사용자를 찾지 못했습니다. 현재 {len(target_usernames_set)}명, 목표 최소 {MIN_USERS_TO_COLLECT}명")
        
        # 인기 계정 팔로워 검색 시도
        logging.info("인기 계정의 팔로워를 통한 추가 사용자 수집 시도...")
        additional_users_from_popular = collect_users_from_popular_accounts(cl, max_users=MAX_USERS_TO_COLLECT - len(target_usernames_set))
        target_usernames_set.update(additional_users_from_popular)
        logging.info(f"인기 계정 팔로워 검색으로 추가 {len(additional_users_from_popular)}명의 사용자를 찾았습니다.")
        
        # 인기 계정 검색 후에도 부족하면 직접 계정 목록 시도
        if len(target_usernames_set) < MIN_USERS_TO_COLLECT:
             logging.warning(f"인기 계정 팔로워 검색으로도 부족합니다. 현재 {len(target_usernames_set)}명.")
             logging.info("직접 지정된 계정 목록을 통한 추가 사용자 수집 시도...")
             additional_users_from_direct = direct_accounts_fallback(cl)
             target_usernames_set.update(additional_users_from_direct)
             logging.info(f"직접 계정 검색으로 추가 {len(additional_users_from_direct)}명의 사용자를 찾았습니다.")

    # 수집된 사용자가 없는 경우 스크립트 종료
    if len(target_usernames_set) == 0:
        logging.warning("수집된 사용자가 없어 스크립트를 종료합니다.")
        sys.exit(0)
    
    # 수집된 고유 사용자 목록 확정
    target_usernames_list = list(target_usernames_set)
    
    # 파일에 사용자 저장
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    user_list_file = os.path.join(data_dir, 'lens_influencers_test.txt')
    with open(user_list_file, 'w', encoding='utf-8') as f:
        for username in target_usernames_list:
            f.write(f"{username}\n")
    
    logging.info(f"총 {len(target_usernames_list)}명의 고유 사용자를 {user_list_file}에 저장했습니다.")
    logging.info(f"총 {len(target_usernames_list)}명의 고유 사용자 수집 완료.")

    # --- 데이터 수집 ---
    all_influencer_data = []
    all_post_data = []

    logging.info(f"총 {len(target_usernames_list)}명의 사용자 데이터 수집 시작...")
    # 타겟 사용자 목록을 순회하며 데이터 수집 함수 호출
    for i, username in enumerate(target_usernames_list, 1):
        logging.info(f"[{i}/{len(target_usernames_list)}] 사용자 처리 시작: {username}")
        influencer_data, post_data_list = fetch_instagram_data(cl, username)

        # 반환된 데이터 리스트에 추가
        if influencer_data:
            all_influencer_data.append(influencer_data)
        if post_data_list:
            all_post_data.extend(post_data_list)

        # 다음 사용자 처리 전 무작위 지연 시간 추가 (API 차단 방지)
        if i < len(target_usernames_list): # 마지막 사용자가 아니면 대기
            user_delay = random.uniform(USER_FETCH_DELAY_MIN, USER_FETCH_DELAY_MAX)
            logging.info(f"다음 사용자 처리 전 {user_delay:.2f}초 대기...")
            time.sleep(user_delay)

    logging.info("데이터 수집 완료. CSV 파일로 저장 중...")

    # --- 데이터 저장 ---
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    influencer_file_path = os.path.join(data_dir, 'influencers.csv')
    posts_file_path = os.path.join(data_dir, 'posts.csv')
    num_influencers_saved = 0
    num_posts_saved = 0

    if all_influencer_data:
        influencer_df = pd.DataFrame(all_influencer_data)
        influencer_df.to_csv(influencer_file_path, index=False, encoding='utf-8-sig')
        num_influencers_saved = len(influencer_df)
        logging.info(f"인플루언서 데이터 {num_influencers_saved}건 저장 완료: {influencer_file_path}")
    else:
        logging.warning("저장할 인플루언서 데이터가 없습니다.")

    if all_post_data:
        posts_df = pd.DataFrame(all_post_data)
        if 'taken_at' in posts_df.columns:
             posts_df['taken_at'] = posts_df['taken_at'].astype(str)
        posts_df.to_csv(posts_file_path, index=False, encoding='utf-8-sig')
        num_posts_saved = len(posts_df)
        logging.info(f"게시물 데이터 {num_posts_saved}건 저장 완료: {posts_file_path}")
    else:
        logging.warning("저장할 게시물 데이터가 없습니다.")

    logging.info("스크립트 실행 완료.")

    # --- 실행 결과 요약 파일에 기록 ---
    try:
        log_file = "logs/scraping_log.md"
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        # 로그 파일에 추가할 내용 생성
        log_entry = f"""\

**시도:**
*   날짜/시간: {time.strftime("%Y-%m-%d %H:%M")} 
*   `MAX_USERS_TO_COLLECT`: {MAX_USERS_TO_COLLECT}
*   `HASHTAG_MEDIA_COUNT`: {HASHTAG_MEDIA_COUNT}
*   지연 시간: MIN/MAX = {USER_FETCH_DELAY_MIN}/{USER_FETCH_DELAY_MAX} (사용자), {INTRA_USER_DELAY_MIN}/{INTRA_USER_DELAY_MAX} (내부/해시태그)
*   결과: 성공 (사용자 {num_influencers_saved}명, 게시물 {num_posts_saved}개 수집)
*   비고: 

---
"""
        # scraping_log.md 파일에 추가 모드(append)로 기록 (utf-8 인코딩 명시)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        logging.info(f"스크래핑 실행 요약이 {log_file} 파일에 추가되었습니다.")
    except Exception as log_err:
        logging.error(f"스크래핑 로그 파일 기록 중 오류 발생: {log_err}") 
import pandas as pd
from instagrapi import Client
from instagrapi.exceptions import UserNotFound, PrivateAccount
import logging
import time
import os
from dotenv import load_dotenv
import random

# .env 파일 로드 (파일 최상단 또는 설정 읽기 직전에)
load_dotenv()

# 로깅 설정 (오류 추적용)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 설정 ---
# .env 파일에서 환경 변수 읽기
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')
TARGET_USERNAMES = [ # 실제 타겟 사용자 이름으로 변경하세요 (약 20개)
    "instagram", "natgeo", "nasa", "apple", "google",
    "microsoft", "github", "python.official", "djangoproject", "flaskpallets",
    "reactjs", "vuejs", "angular", "nodejs", "docker",
    "kubernetes", "tensorflow", "pytorch", "openai", "deepmind"
]
NUM_POSTS_TO_FETCH = 10 # 가져올 최근 게시물 수
RETRY_DELAY_SECONDS = 5 # 재시도 전 대기 시간 (초)
MAX_RETRIES = 3 # 최대 재시도 횟수
USER_FETCH_DELAY_MIN = 3 # 추가: 사용자 처리 간 최소 대기 시간 (초)
USER_FETCH_DELAY_MAX = 7 # 추가: 사용자 처리 간 최대 대기 시간 (초)
INTRA_USER_DELAY_MIN = 0.5 # 추가: 사용자 내 요청 간 최소 대기 시간 (초)
INTRA_USER_DELAY_MAX = 1.5 # 추가: 사용자 내 요청 간 최대 대기 시간 (초)
# --- ---

def fetch_instagram_data(cl, username):
    """지정된 사용자의 프로필 정보와 최근 게시물 메타데이터를 가져옵니다."""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            logging.info(f"사용자 정보 가져오는 중: {username}")
            user_info = cl.user_info_by_username(username)
            user_pk = user_info.pk
            logging.info(f"사용자 PK 확인: {user_pk}")

            # 사용자 내 요청 간 지연 추가
            intra_user_delay = random.uniform(INTRA_USER_DELAY_MIN, INTRA_USER_DELAY_MAX)
            logging.debug(f"사용자 내 요청 지연: {intra_user_delay:.2f}초")
            time.sleep(intra_user_delay)

            logging.info(f"{username}의 최근 게시물 {NUM_POSTS_TO_FETCH}개 가져오는 중...")
            posts = cl.user_medias(user_pk, amount=NUM_POSTS_TO_FETCH)
            logging.info(f"{username}의 게시물 {len(posts)}개 가져옴")

            influencer_details = {
                'username': user_info.username,
                'pk': user_info.pk,
                'full_name': user_info.full_name,
                'follower_count': user_info.follower_count,
                'following_count': user_info.following_count,
                'media_count': user_info.media_count,
                'biography': user_info.biography,
                'external_url': user_info.external_url,
                'is_private': user_info.is_private,
                'is_verified': user_info.is_verified,
            }

            post_details_list = []
            for post in posts:
                post_details = {
                    'post_pk': post.pk,
                    'user_pk': user_pk, # 인플루언서 정보와 연결하기 위함
                    'taken_at': post.taken_at,
                    'media_type': post.media_type, # 1: 사진, 2: 동영상, 8: 앨범
                    'like_count': post.like_count,
                    'comment_count': post.comment_count,
                    'caption_text': post.caption_text,
                    'code': post.code, # 게시물 URL 생성용 (https://www.instagram.com/p/CODE/)
                    'thumbnail_url': post.thumbnail_url,
                    'video_url': post.video_url if post.media_type == 2 else None,
                }
                post_details_list.append(post_details)

            return influencer_details, post_details_list

        except UserNotFound:
            logging.warning(f"사용자를 찾을 수 없음: {username}")
            return None, []
        except PrivateAccount:
            logging.warning(f"비공개 계정: {username}. 게시물을 가져올 수 없습니다.")
            # 비공개 계정이라도 프로필 정보는 일부 반환될 수 있음
            influencer_details = {
                'username': username,
                'pk': None, # 비공개 계정은 PK를 못 얻을 수 있음
                'full_name': None,
                'follower_count': None,
                'following_count': None,
                'media_count': None,
                'biography': None,
                'external_url': None,
                'is_private': True,
                'is_verified': None,
            }
            # user_info_by_username 에서 PrivateAccount 예외가 발생하면 user_info 객체 없음
            # 필요하다면 cl.user_info() 를 pk 대신 username 으로 호출 시도 가능 (하지만 권장되지 않음)
            return influencer_details, []
        except Exception as e:
            retries += 1
            logging.error(f"{username} 처리 중 오류 발생: {e}. {retries}/{MAX_RETRIES} 재시도...")
            if retries >= MAX_RETRIES:
                logging.error(f"{username} 처리 실패. 최대 재시도 횟수 초과.")
                return None, []
            time.sleep(RETRY_DELAY_SECONDS)
    return None, [] # 최대 재시도 후에도 실패

if __name__ == "__main__":
    cl = Client()

    # 세션 파일 경로 설정
    session_file = "session.json"

    logging.info("인스타그램 로그인 시도...")
    try:
        if os.path.exists(session_file):
            cl.load_settings(session_file)
            logging.info(f"{session_file}에서 세션 로드됨. API 재로그인 시도...")
            # 세션이 유효한지 확인하기 위해 간단한 API 호출 시도 (예: 자기 프로필 정보 가져오기)
            cl.get_timeline_feed()
            logging.info("세션 유효함. 로그인 건너뜀.")
        else:
            logging.info(f"{session_file} 없음. 사용자 이름/비밀번호로 로그인 시도...")
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            cl.dump_settings(session_file)
            logging.info(f"로그인 성공 및 세션 저장 완료: {session_file}")

    except Exception as e:
        # 세션 로드 실패 또는 로그인 실패 시, 다시 로그인 시도
        logging.warning(f"세션 로드/확인 실패 또는 초기 로그인 필요: {e}")
        try:
            logging.info("사용자 이름/비밀번호로 재로그인 시도...")
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            cl.dump_settings(session_file)
            logging.info(f"로그인 성공 및 세션 저장 완료: {session_file}")
        except Exception as login_err:
             logging.error(f"로그인 실패: {login_err}")
             exit() # 로그인 최종 실패 시 종료

    all_influencer_data = []
    all_post_data = []

    logging.info(f"총 {len(TARGET_USERNAMES)}명의 사용자 데이터 수집 시작...")
    for username in TARGET_USERNAMES:
        influencer_data, post_data_list = fetch_instagram_data(cl, username)
        if influencer_data:
            all_influencer_data.append(influencer_data)
        if post_data_list:
            all_post_data.extend(post_data_list)
        # API 요청 간 무작위 지연 시간 추가 (차단 방지)
        user_delay = random.uniform(USER_FETCH_DELAY_MIN, USER_FETCH_DELAY_MAX)
        logging.info(f"다음 사용자 처리 전 {user_delay:.2f}초 대기...")
        time.sleep(user_delay)

    logging.info("데이터 수집 완료. CSV 파일로 저장 중...")

    # 인플루언서 데이터 저장
    if all_influencer_data:
        influencer_df = pd.DataFrame(all_influencer_data)
        influencer_df.to_csv('influencers.csv', index=False, encoding='utf-8-sig')
        logging.info(f"인플루언서 데이터 {len(influencer_df)}건 저장 완료: influencers.csv")
    else:
        logging.warning("저장할 인플루언서 데이터가 없습니다.")

    # 게시물 데이터 저장
    if all_post_data:
        posts_df = pd.DataFrame(all_post_data)
        # datetime 객체를 문자열로 변환 (CSV 저장용)
        if 'taken_at' in posts_df.columns:
             posts_df['taken_at'] = posts_df['taken_at'].astype(str)
        posts_df.to_csv('posts.csv', index=False, encoding='utf-8-sig')
        logging.info(f"게시물 데이터 {len(posts_df)}건 저장 완료: posts.csv")
    else:
        logging.warning("저장할 게시물 데이터가 없습니다.")

    logging.info("스크립트 실행 완료.") 
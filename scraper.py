import pandas as pd
from instagrapi import Client
from instagrapi.exceptions import UserNotFound, PrivateAccount, LoginRequired, HashtagNotFound
import logging
import time
import os
from dotenv import load_dotenv
import random

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
# 관련 해시태그 목록 (광고 관련 + 뷰티 관련)
TARGET_HASHTAGS = [
    '광고', '협찬', 'sponsored', # 광고 지표
    '뷰티스타그램', 'kbeauty', '화장품추천', '코덕', '메이크업', # 뷰티 카테고리
    '올리브영추천템', '스킨케어루틴' # 좀 더 구체적인 뷰티 관련
]
MAX_USERS_TO_COLLECT = 10 # 수집할 최대 사용자 수 (강도 낮춤)
HASHTAG_MEDIA_COUNT = 10 # 각 해시태그당 조회할 인기 게시물 수 (강도 낮춤)
NUM_POSTS_TO_FETCH = 10 # 각 사용자별로 가져올 최근 게시물 개수

# --- API 요청 관련 설정 ---
RETRY_DELAY_SECONDS = 10 # API 요청 실패 시 재시도 전 대기 시간 (초)
MAX_RETRIES = 3 # API 요청 최대 재시도 횟수
USER_FETCH_DELAY_MIN = 6 # 사용자 정보 조회 사이의 최소 대기 시간 (초)
USER_FETCH_DELAY_MAX = 14 # 사용자 정보 조회 사이의 최대 대기 시간 (초)
INTRA_USER_DELAY_MIN = 1.0 # 한 사용자의 게시물 조회 등 내부 요청 간 최소 대기 시간 (초)
INTRA_USER_DELAY_MAX = 3.0 # 한 사용자의 게시물 조회 등 내부 요청 간 최대 대기 시간 (초)
# TODO: 위 지연 시간들은 인스타그램 API 정책 변경 및 네트워크 상황에 따라 조절 필요
# --- --- 

def fetch_instagram_data(cl: Client, username: str):
    """지정된 사용자의 프로필 정보와 최근 게시물 메타데이터를 가져옵니다.

    Args:
        cl (Client): Instagrapi 클라이언트 객체.
        username (str): 조회할 인스타그램 사용자 이름.

    Returns:
        tuple: (인플루언서 상세 정보 딕셔너리, 게시물 상세 정보 리스트) 튜플.
               오류 발생 또는 사용자를 찾을 수 없는 경우 (None, []) 또는 (프로필 정보, []) 반환.
    """
    retries = 0
    while retries < MAX_RETRIES:
        try:
            logging.info(f"사용자 정보 가져오는 중: {username}")
            # 사용자 이름으로 사용자 정보 조회 (API 요청 발생)
            user_info = cl.user_info_by_username(username)
            user_pk = user_info.pk # 사용자의 고유 ID (PK)
            logging.info(f"사용자 PK 확인: {user_pk}")

            # 사용자 내 요청 간 지연 (차단 방지 목적)
            intra_user_delay = random.uniform(INTRA_USER_DELAY_MIN, INTRA_USER_DELAY_MAX)
            logging.debug(f"사용자 내 요청 지연: {intra_user_delay:.2f}초")
            time.sleep(intra_user_delay)

            logging.info(f"{username}의 최근 게시물 {NUM_POSTS_TO_FETCH}개 가져오는 중...")
            # 사용자 PK를 사용하여 최근 게시물 정보 조회 (API 요청 발생)
            # amount: 가져올 게시물 개수 지정
            posts = cl.user_medias(user_pk, amount=NUM_POSTS_TO_FETCH)
            logging.info(f"{username}의 게시물 {len(posts)}개 가져옴")

            # --- 인플루언서 정보 딕셔너리 생성 ---
            influencer_details = {
                'username': user_info.username,
                'pk': user_info.pk,
                'full_name': user_info.full_name,
                'follower_count': user_info.follower_count,
                'following_count': user_info.following_count,
                'media_count': user_info.media_count,
                # biography 필드가 존재하고 문자열일 경우에만 replace 적용
                'biography': user_info.biography.replace('\n', ' ') if user_info.biography and isinstance(user_info.biography, str) else user_info.biography,
                'external_url': user_info.external_url,
                'is_private': user_info.is_private,
                'is_verified': user_info.is_verified,
            }

            # --- 게시물 정보 리스트 생성 ---
            post_details_list = []
            for post in posts:
                # TODO: media_type 외에 다양한 필드(e.g., tagged_users, location) 추가 수집 고려
                post_details = {
                    'post_pk': post.pk, # 게시물 고유 ID
                    'user_pk': user_pk, # 인플루언서 정보와 연결하기 위한 외래 키 역할
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

            return influencer_details, post_details_list

        # --- 예외 처리 --- 
        except UserNotFound:
            # 사용자를 찾을 수 없는 경우 경고 로그 남기고 None 반환
            logging.warning(f"사용자를 찾을 수 없음: {username}")
            return None, []
        except PrivateAccount:
            # 비공개 계정인 경우 경고 로그 남김
            # 비공개 계정은 게시물 조회가 불가능하지만, 제한적인 프로필 정보는 반환될 수 있음.
            logging.warning(f"비공개 계정: {username}. 게시물을 가져올 수 없습니다.")
            # TODO: 비공개 계정 처리 정책 결정 필요 (예: 프로필 정보만이라도 저장할지 등)
            # user_info_by_username 에서 PrivateAccount 발생 시 user_info 객체가 없을 수 있음에 유의
            # 현재 로직은 PrivateAccount 발생 전 user_info 가 성공적으로 반환되었다고 가정함.
            # 더 안전하게 하려면, 예외 발생 시 user_info 객체 존재 여부 확인 필요.
            try:
                # user_info 객체가 있으면 해당 정보 사용, 없으면 기본값 사용
                profile_username = user_info.username if 'user_info' in locals() and user_info else username
                profile_pk = user_info.pk if 'user_info' in locals() and user_info else None
                profile_full_name = user_info.full_name if 'user_info' in locals() and user_info else None
                # ... 기타 필드도 유사하게 처리 ...
            except NameError:
                # user_info 자체가 정의되지 않은 극단적 케이스 (이론상 발생 어려움)
                profile_username = username
                profile_pk = None
                profile_full_name = None
                # ...

            influencer_details = {
                'username': profile_username,
                'pk': profile_pk, # 비공개 계정은 PK를 얻지 못할 수 있음
                'full_name': profile_full_name,
                'follower_count': None, # 비공개 계정 정보 제한적
                'following_count': None,
                'media_count': None,
                'biography': None,
                'external_url': None,
                'is_private': True,
                'is_verified': None,
            }
            return influencer_details, [] # 비공개 계정 프로필 정보와 빈 게시물 리스트 반환
        except Exception as e:
            # 기타 예외 발생 시 (네트워크 오류, API 제한 등)
            retries += 1
            logging.error(f"{username} 처리 중 오류 발생 (시도 {retries}/{MAX_RETRIES}): {e}", exc_info=False) # 상세 오류 로깅 (Traceback은 필요시 True로 변경)

            # --- LoginRequired 특별 처리 ---
            if isinstance(e, LoginRequired):
                # 첫 번째 재시도 시에만 relogin 시도 (과도한 relogin 방지)
                if retries == 1:
                    try:
                        logging.warning(f"LoginRequired 감지됨. 재로그인 시도 (사용자: {username})...")
                        cl.relogin()
                        logging.info(f"재로그인 성공. API 요청 재시도 (사용자: {username}).")
                        # 재로그인 성공 시, 재시도 횟수를 증가시키지 않고 바로 다음 시도하도록 retries 조정
                        retries -= 1 # 방금 증가시킨 retries 원복
                        continue # while 루프의 다음 반복으로 가서 API 호출 재시도
                    except Exception as relogin_err:
                        logging.error(f"재로그인 실패: {relogin_err}. 해당 사용자 처리 중단.", exc_info=True)
                        return None, [] # 재로그인 실패 시 더 이상 재시도 무의미

            # --- 일반 재시도 로직 ---
            if retries >= MAX_RETRIES:
                logging.error(f"{username} 처리 실패. 최대 재시도 횟수 초과.")
                # TODO: 실패한 사용자 목록을 별도로 관리하여 나중에 재시도하는 로직 추가 고려
                return None, [] # 최대 재시도 후에도 실패 시 None 반환

            logging.info(f"{RETRY_DELAY_SECONDS}초 후 재시도...")
            time.sleep(RETRY_DELAY_SECONDS) # 재시도 전 대기

    # 최대 재시도 후에도 실패한 경우 (루프 종료)
    logging.error(f"{username} 처리 최종 실패.")
    return None, []

# --- 메인 실행 로직 --- 
if __name__ == "__main__":
    # 인스타그램 클라이언트 초기화
    cl = Client()

    # 세션 파일 경로 설정 (로그인 정보 저장용)
    session_file = "session.json"
    # TODO: 세션 파일 경로를 설정 파일이나 환경 변수로 관리하는 것 고려

    logging.info("인스타그램 로그인 시도...")
    try:
        # 세션 파일이 존재하면 로드 시도
        if os.path.exists(session_file):
            logging.info(f"'{session_file}'에서 세션 로드 시도...")
            cl.load_settings(session_file)
            logging.info("세션 로드 완료. API 재로그인 시도 (세션 유효성 검사)...")
            # 세션 유효성 검사를 위해 간단한 API 호출 (예: 타임라인 피드 가져오기)
            # TODO: 더 가벼운 API 호출(예: cl.account_info())로 유효성 검사 변경 고려
            cl.get_timeline_feed()
            logging.info("세션 유효함. 기존 세션 사용.")
        else:
            # 세션 파일이 없으면 사용자 이름/비밀번호로 새로 로그인
            logging.info(f"'{session_file}' 없음. 사용자 이름/비밀번호로 로그인 시도...")
            if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
                 logging.error("인스타그램 사용자 이름 또는 비밀번호가 .env 파일에 설정되지 않았습니다.")
                 exit()
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            cl.dump_settings(session_file) # 성공 시 세션 정보 파일로 저장
            logging.info(f"로그인 성공 및 세션 저장 완료: {session_file}")

    except Exception as e:
        # 세션 로드/유효성 검사 실패 또는 초기 로그인 필요 시
        logging.warning(f"세션 로드/확인 실패 또는 초기 로그인 필요: {e}. 사용자 이름/비밀번호로 재로그인 시도...")
        try:
            if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
                 logging.error("인스타그램 사용자 이름 또는 비밀번호가 .env 파일에 설정되지 않았습니다.")
                 exit()
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            cl.dump_settings(session_file) # 성공 시 세션 정보 파일로 저장
            logging.info(f"로그인 성공 및 세션 저장 완료: {session_file}")
        except Exception as login_err:
             # 재로그인도 실패하면 에러 로그 남기고 종료
             logging.error(f"로그인 최종 실패: {login_err}")
             exit()

    # --- 해시태그 기반 사용자 목록 생성 --- #
    target_usernames_set = set()
    logging.info(f"지정된 해시태그에서 최대 {MAX_USERS_TO_COLLECT}명의 사용자 수집 시작...")

    for hashtag in TARGET_HASHTAGS:
        if len(target_usernames_set) >= MAX_USERS_TO_COLLECT:
            logging.info(f"목표 사용자 수({MAX_USERS_TO_COLLECT}명) 도달. 해시태그 검색 중단.")
            break
        try:
            logging.info(f"해시태그 '#{hashtag}'의 인기 게시물 {HASHTAG_MEDIA_COUNT}개 조회 중...")
            # 해시태그의 인기 게시물 가져오기
            medias = cl.hashtag_medias_top(hashtag, amount=HASHTAG_MEDIA_COUNT)
            logging.info(f"'#{hashtag}' 해시태그에서 게시물 {len(medias)}개 발견.")

            for media in medias:
                if media.user and media.user.username:
                    target_usernames_set.add(media.user.username)
                    if len(target_usernames_set) >= MAX_USERS_TO_COLLECT:
                        break # 내부 루프도 중단
                else:
                     logging.warning(f"게시물(ID: {media.pk})에서 사용자 정보를 찾을 수 없습니다.")

            # API 요청 간 지연 (해시태그 처리 사이)
            hashtag_delay = random.uniform(INTRA_USER_DELAY_MIN, INTRA_USER_DELAY_MAX) # 짧은 딜레이 사용
            logging.debug(f"다음 해시태그 처리 전 {hashtag_delay:.2f}초 대기...")
            time.sleep(hashtag_delay)

        except HashtagNotFound:
             logging.warning(f"해시태그 '#{hashtag}'를 찾을 수 없습니다. 건너<0xEB><0x9B><0x8D>니다.")
        except Exception as e:
            logging.error(f"해시태그 '#{hashtag}' 처리 중 오류 발생: {e}", exc_info=True)
            # 오류 발생 시 다음 해시태그로 넘어감

    target_usernames_list = list(target_usernames_set)
    logging.info(f"총 {len(target_usernames_list)}명의 고유 사용자 수집 완료.")

    # 수집된 사용자가 없으면 종료
    if not target_usernames_list:
        logging.warning("수집된 사용자가 없어 스크립트를 종료합니다.")
        exit()

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
    influencer_file_path = 'influencers.csv'
    posts_file_path = 'posts.csv'
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

    # --- 실행 결과 요약 파일에 기록 --- #
    try:
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
        with open('scraping_log.md', 'a', encoding='utf-8') as f:
            f.write(log_entry)
        logging.info(f"스크래핑 실행 요약이 scraping_log.md 파일에 추가되었습니다.")
    except Exception as log_err:
        logging.error(f"스크래핑 로그 파일 기록 중 오류 발생: {log_err}")

    # --- 터미널 출력 부분 제거 ---
    # print("\n" + "-" * 20)
    # print("스크래핑 실행 요약 (로그 기록용):")
    # print("*   날짜/시간:", time.strftime("%Y-%m-%d %H:%M")) # 현재 시간
    # print(f"*   `MAX_USERS_TO_COLLECT`: {MAX_USERS_TO_COLLECT}")
    # print(f"*   `HASHTAG_MEDIA_COUNT`: {HASHTAG_MEDIA_COUNT}")
    # print(f"*   지연 시간: MIN/MAX = {USER_FETCH_DELAY_MIN}/{USER_FETCH_DELAY_MAX} (사용자), {INTRA_USER_DELAY_MIN}/{INTRA_USER_DELAY_MAX} (내부/해시태그)")
    # print(f"*   결과: 성공 (사용자 {num_influencers_saved}명, 게시물 {num_posts_saved}개 수집)") # 실제 저장된 건수 기준
    # print("*   비고: (오류 발생 여부 등 수동으로 기록 필요)")
    # print("-" * 20 + "\n") 
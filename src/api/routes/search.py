import numpy as np
import pandas as pd
import sqlite3
from sentence_transformers import SentenceTransformer
import logging
import math
from flask import Blueprint, request, jsonify

# 코어 모듈 import 경로 수정
from core.nlp import parse

# Blueprint 생성
search_bp = Blueprint('search', __name__)

# 로깅 설정 가져오기 (또는 Blueprint별 로거 설정)
# 메인 앱의 로거를 사용하거나, 필요시 여기서 로거 재설정 가능
# 여기서는 메인 로거가 이미 설정되었다고 가정
logger = logging.getLogger(__name__) # Blueprint 로거

# 데이터 및 모델 로드 (Blueprint 로딩 시 한 번만)
# TODO: 앱 컨텍스트나 더 정교한 상태 관리 고려 (현재는 모듈 로딩 시 실행)
try:
    logger.info("데이터베이스 연결 중 (search_api)...")
    con = sqlite3.connect('data/mvp.db', check_same_thread=False)

    logger.info("인플루언서 데이터 로딩 중 (influencers 테이블) (search_api)...")
    infl_df_all = pd.read_sql("SELECT * FROM influencers", con)
    logger.info(f"{len(infl_df_all)}명의 인플루언서 데이터 로드 완료 (search_api).")

    logger.info("게시물 데이터 로딩 중 (posts 테이블) (search_api)...")
    posts_df = pd.read_sql("SELECT * FROM posts", con)
    logger.info(f"{len(posts_df)}개의 게시물 데이터 로드 완료 (search_api).")

    # 코사인 유사도 계산을 위한 임베딩 벡터 로드
    logger.info("임베딩 벡터 추출 중 (posts 테이블) (search_api)...")
    posts_with_emb = posts_df.dropna(subset=['semantic_emb']).copy()
    
    # 임베딩 벡터 추출 방식 수정 - 1차원 문자열에서 다차원 배열로 변환
    semantic_embs = []
    for emb_str in posts_with_emb['semantic_emb']:
        if isinstance(emb_str, str) and emb_str.strip():
            try:
                # 대괄호 제거 후 공백으로 분리하여 배열로 변환
                # 문자열이 1D 배열처럼 저장되어 있을 경우
                if '[' in emb_str and ']' in emb_str:
                    emb_str = emb_str.strip('[]')
                    emb_array = np.fromstring(emb_str, sep=' ')
                # 문자열이 다른 형식으로 저장되어 있을 경우 (예: CSV 형식)
                else:
                    emb_array = np.fromstring(emb_str, sep=',')
                
                semantic_embs.append(emb_array)
            except Exception as e:
                logger.warning(f"임베딩 벡터 파싱 오류: {e} - 원본 문자열: {emb_str[:30]}...")
    
    if semantic_embs:
        semantic_embs = np.array(semantic_embs)
        logger.info(f"{len(semantic_embs)}개의 유효한 임베딩 벡터 추출 완료 (차원: {semantic_embs.shape[1]}) (search_api).")
    else:
        logger.warning("유효한 임베딩 벡터가 없습니다. semantic_emb 열을 확인하세요.")
        semantic_embs = np.array([])
    
    logger.info("Sentence Transformer 모델 로딩 중 (search_api)...")
    model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')
    logger.info("모델 로딩 완료 (search_api).")
except Exception as e:
    logger.error(f"데이터/모델 로딩 중 치명적 오류 발생 (search_api): {e}", exc_info=True)
    # 앱 실행을 중단시키는 대신, 오류 상태를 기록하고 API 요청 시 처리하도록 변경 고려
    # 여기서는 일단 로딩 실패 시 프로그램 종료 유도 (기존 방식 유지)
    exit()


# 코사인 유사도 계산 함수
def cosine_similarity(query_vector, embedding_vectors):
    """쿼리 벡터와 임베딩 벡터 배열 간의 코사인 유사도 계산"""
    if len(embedding_vectors) == 0:
        return np.array([])
    
    # 벡터 차원 확인 로깅
    logger.info(f"쿼리 벡터 차원: {query_vector.shape}, 임베딩 벡터 차원: {embedding_vectors.shape}")
    
    # 차원 불일치 확인 및 처리
    if query_vector.shape[0] != embedding_vectors.shape[1]:
        logger.warning(f"차원 불일치 발생: 쿼리({query_vector.shape[0]}) vs 임베딩({embedding_vectors.shape[1]})")
        # 차원 불일치 시 유사도를 0으로 설정하는 대신 변환 로직 추가 가능
        # 현재는 간단하게 0 반환
        return np.zeros(len(embedding_vectors))
    
    # 정규화
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0:
        return np.zeros(len(embedding_vectors))
    
    query_vector = query_vector / query_norm
    
    # 각 벡터 정규화
    norms = np.linalg.norm(embedding_vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1  # 0으로 나누기 방지
    normalized_vectors = embedding_vectors / norms
    
    # 코사인 유사도 계산
    return np.dot(normalized_vectors, query_vector)


# 랭킹 점수 계산 함수
def calculate_ranking_score(semantic_sim, follower_count):
    """시맨틱 유사도와 팔로워 수를 결합한 랭킹 점수 계산
    score = 0.6*semantic_sim + 0.4*log10(follower_count)
    """
    if follower_count <= 0:
        log_followers = 0
    else:
        # 백만 팔로워를 1.0으로 표준화
        log_followers = math.log10(follower_count) / 6.0
        # 1.0 이상으로 넘어가지 않도록 클리핑
        log_followers = min(log_followers, 1.0)
    
    # 가중치 적용 (시맨틱 유사도 60%, 팔로워 수 40%)
    return 0.6 * semantic_sim + 0.4 * log_followers


@search_bp.route("/search", methods=['GET'])
def search():
    """확장된 검색 API 엔드포인트
    쿼리 파라미터:
    - q: 검색 키워드 (required)
    - min_sim: 최소 시맨틱 유사도 (float, default: 0.0)
    - min_follow: 최소 팔로워 수 (int, default: 0)
    - gender: 성별 필터 (str, 'male'/'female'/'all', default: 'all')
    - age_group: 연령대 필터 (str, '10s'/'20s'/'30s'/etc, default: None)
    - limit: 최대 반환 결과 수 (int, default: 20)
    """
    # 필수 검색어 파라미터
    q = request.args.get("q", "")
    
    # 선택적 필터 파라미터
    try:
        min_sim = float(request.args.get("min_sim", 0.0))
    except ValueError:
        min_sim = 0.0
        logger.warning("min_sim 파라미터가 유효한 숫자가 아닙니다. 기본값 0.0을 사용합니다.")
    
    try:
        min_follow = int(request.args.get("min_follow", 0))
    except ValueError:
        min_follow = 0
        logger.warning("min_follow 파라미터가 유효한 숫자가 아닙니다. 기본값 0을 사용합니다.")
    
    gender = request.args.get("gender", "all").lower()
    age_group = request.args.get("age_group", None)
    
    try:
        limit = int(request.args.get("limit", 20))
        limit = max(1, min(limit, 100))  # 1~100 범위로 제한
    except ValueError:
        limit = 20
        logger.warning("limit 파라미터가 유효한 숫자가 아닙니다. 기본값 20을 사용합니다.")

    if not q:
        logger.info("검색어가 비어 있어 빈 결과를 반환합니다.")
        return jsonify([])

    logger.info(f"검색 요청: q='{q}', min_sim={min_sim}, min_follow={min_follow}, gender={gender}, age_group={age_group}, limit={limit}")

    try:
        # 1. 검색어 임베딩
        logger.info("검색어 임베딩 생성 중...")
        query_embedding = model.encode(q)
        logger.info(f"쿼리 임베딩 차원: {query_embedding.shape}")
        
        # 2. 첫 번째 필터: 임베딩 기반 시맨틱 유사도 계산
        if len(semantic_embs) > 0:
            try:
                similarities = cosine_similarity(query_embedding, semantic_embs)
                # min_sim 이상인 게시물만 선택
                semantic_match_indices = np.where(similarities >= min_sim)[0]
                semantic_match_posts = posts_with_emb.iloc[semantic_match_indices].copy()
                semantic_match_posts['similarity'] = similarities[semantic_match_indices]
                logger.info(f"시맨틱 유사도 {min_sim} 이상인 게시물 {len(semantic_match_posts)}개 발견")
            except Exception as sim_error:
                logger.error(f"유사도 계산 중 오류 발생: {sim_error}")
                # 오류 발생 시 시맨틱 검색을 건너뛰고 키워드 검색으로 대체
                semantic_match_posts = pd.DataFrame()
        else:
            semantic_match_posts = pd.DataFrame()
            logger.warning("유효한 임베딩 벡터가 없어 시맨틱 검색을 건너뜁니다.")
        
        # 3. 텍스트 키워드 검색 (OCR 및 캡션)
        keyword_condition = (
            posts_df['caption_text'].str.contains(q, case=False, na=False) | 
            posts_df['product_name'].str.contains(q, case=False, na=False)
        )
        keyword_match_posts = posts_df[keyword_condition].copy()
        keyword_match_posts['similarity'] = 0.5  # 텍스트 매치에 기본 유사도 할당
        logger.info(f"키워드 '{q}'가 포함된 게시물 {len(keyword_match_posts)}개 발견")
        
        # 4. 두 결과 병합 (중복 제거)
        if not semantic_match_posts.empty:
            # 두 DataFrames 병합 (중복 제거)
            merged_posts = pd.concat([semantic_match_posts, keyword_match_posts])
            merged_posts = merged_posts.drop_duplicates(subset=['post_pk'])
        else:
            merged_posts = keyword_match_posts
        
        if merged_posts.empty:
            logger.info("검색 조건에 맞는 게시물이 없습니다.")
            return jsonify([])
        
        logger.info(f"중복 제거 후 총 {len(merged_posts)}개 게시물 발견")
        
        # 5. 인플루언서 정보 병합
        # 인플루언서 필터링 (min_follow, gender, age_group)
        influencer_filter = (infl_df_all['follower_count'] >= min_follow)
        
        # 성별 필터 (선택 사항)
        if gender != "all" and 'gender' in infl_df_all.columns:
            influencer_filter &= (infl_df_all['gender'] == gender)
        
        # 연령대 필터 (선택 사항)
        if age_group and 'age_group' in infl_df_all.columns:
            influencer_filter &= (infl_df_all['age_group'] == age_group)
        
        filtered_influencers = infl_df_all[influencer_filter]
        logger.info(f"필터링 조건을 만족하는 인플루언서 {len(filtered_influencers)}명 발견")
        
        # 필터링된 인플루언서의 게시물만 선택
        result_posts = merged_posts[merged_posts['user_pk'].isin(filtered_influencers['pk'])]
        logger.info(f"최종 결과에 포함될 게시물 {len(result_posts)}개")
        
        if result_posts.empty:
            logger.info("필터링 후 결과가 없습니다.")
            return jsonify([])
        
        # 인플루언서 정보 조인
        result_with_user = pd.merge(
            result_posts,
            filtered_influencers,
            left_on='user_pk',
            right_on='pk',
            how='inner'
        )
        
        # 6. 랭킹 점수 계산 및 정렬
        result_with_user['score'] = result_with_user.apply(
            lambda row: calculate_ranking_score(row['similarity'], row['follower_count']), 
            axis=1
        )
        
        # 점수 내림차순 정렬
        sorted_results = result_with_user.sort_values('score', ascending=False)
        
        # 최대 결과 수 제한
        final_results = sorted_results.head(limit).to_dict(orient="records")
        logger.info(f"최종 {len(final_results)}개 결과 반환")
        
        return jsonify(final_results)

    except Exception as e:
        logger.error(f"검색 처리 중 오류 발생: {e}", exc_info=True)
        return jsonify({"error": "검색 중 오류가 발생했습니다.", "details": str(e)}), 500 
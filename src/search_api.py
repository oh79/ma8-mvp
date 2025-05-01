import numpy as np
import pandas as pd
import sqlite3
from sentence_transformers import SentenceTransformer
import logging
import math
from flask import Blueprint, request, jsonify
from nlp_parse import parse # 같은 src 디렉토리에 있으므로 직접 import

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

    logger.info("임베딩 벡터 로딩 중 (vecs.npy) (search_api)...")
    vecs_all = np.load('data/vecs.npy')
    logger.info(f"{len(vecs_all)}개의 임베딩 벡터 로드 완료 (search_api).")

    if len(infl_df_all) != len(vecs_all):
        logger.error(f"인플루언서 데이터({len(infl_df_all)})와 임베딩 벡터({len(vecs_all)}) 개수가 일치하지 않습니다! (search_api)")
        raise ValueError("Data and vector counts do not match.")

    logger.info("Sentence Transformer 모델 로딩 중 (search_api)...")
    model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')
    logger.info("모델 로딩 완료 (search_api).")
except Exception as e:
    logger.error(f"데이터/모델 로딩 중 치명적 오류 발생 (search_api): {e}", exc_info=True)
    # 앱 실행을 중단시키는 대신, 오류 상태를 기록하고 API 요청 시 처리하도록 변경 고려
    # 여기서는 일단 로딩 실패 시 프로그램 종료 유도 (기존 방식 유지)
    exit()


@search_bp.route("/search", methods=['GET'])
def search():
    q = request.args.get("q", "")
    try:
        k = int(request.args.get("k", 5))
    except ValueError:
        k = 5
        logger.warning(f"쿼리 파라미터 'k'가 숫자가 아니거나 없습니다. 기본값 5를 사용합니다.")

    if not q:
        logger.info("검색어가 비어 있어 빈 결과를 반환합니다.")
        return jsonify([])

    logger.info(f"검색 요청: q='{q}', k={k}")

    try:
        # 1. 쿼리 파싱하여 필터 추출
        filters = parse(q)
        logger.info(f"파싱된 필터: {filters}")
        follower_min = filters.get("follower_min", 0)
        follower_max = filters.get("follower_max", math.inf)

        # 2. 미리 로드된 데이터프레임 필터링
        condition = (infl_df_all['follower_count'] >= follower_min) & (infl_df_all['follower_count'] <= follower_max)
        filtered_infl_df = infl_df_all[condition].copy()
        logger.info(f"팔로워 필터링 후 {len(filtered_infl_df)}명의 인플루언서 발견.")

        if filtered_infl_df.empty:
            logger.info("필터링 조건에 맞는 인플루언서가 없습니다.")
            return jsonify([])

        # 3. 필터링된 데이터에 대한 임베딩 벡터 선택
        filtered_indices = filtered_infl_df.index.tolist()
        try:
            filtered_vecs = vecs_all[filtered_indices]
        except IndexError as ie:
             logger.error(f"임베딩 벡터 선택 중 인덱스 오류: {ie}. 데이터와 벡터 싱크 문제일 수 있음.", exc_info=True)
             return jsonify({"error": "임베딩 벡터 처리 중 오류.", "details": str(ie)}), 500

        # 4. 쿼리 임베딩 및 유사도 계산
        logger.info("검색어 임베딩 생성 중...")
        qv = model.encode([q])
        logger.info("유사도 계산 중 (필터링된 데이터 대상)...")
        sims = (filtered_vecs @ qv.T).flatten()

        num_results = min(k, len(sims))
        if len(sims) == 0:
             logger.info("유사도 계산 결과가 비어 있습니다.")
             return jsonify([])
        top_indices_in_filtered = sims.argsort()[-num_results:][::-1]

        logger.info(f"상위 {num_results}개 인덱스 (필터링 내): {top_indices_in_filtered}")
        logger.info(f"유사도 점수: {sims[top_indices_in_filtered]}")

        # 5. 최종 결과 구성
        results = filtered_infl_df.iloc[top_indices_in_filtered].to_dict(orient="records")

        return jsonify(results)

    except Exception as e:
        logger.error(f"검색 처리 중 오류 발생: {e}", exc_info=True)
        return jsonify({"error": "검색 중 오류가 발생했습니다.", "details": str(e)}), 500 
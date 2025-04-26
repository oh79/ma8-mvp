from flask import Flask, request, jsonify
import numpy as np
import pandas as pd
import sqlite3
from sentence_transformers import SentenceTransformer
import logging # 로깅 모듈 추가
from nlp_parse import parse # nlp_parse 모듈에서 parse 함수 임포트
import math # math.inf 사용 위해 추가

# 로깅 설정 (파일 핸들러 추가 고려)
# TODO: 운영 환경에서는 파일 로깅 또는 외부 로깅 시스템 연동 고려
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 데이터 및 모델 로드 (애플리케이션 시작 시 한 번만)
try:
    logging.info("데이터베이스 연결 중...")
    # check_same_thread=False 는 Flask의 기본 개발 서버에서 여러 요청을 처리할 때 필요할 수 있습니다.
    # 실제 운영 환경에서는 더 견고한 DB 연결 관리 방식이 필요할 수 있습니다.
    con = sqlite3.connect('mvp.db', check_same_thread=False)

    logging.info("인플루언서 데이터 로딩 중 (influencers 테이블)...")
    # DB에서 influencers 테이블 전체 로드 (pk 컬럼 존재 가정)
    # read_sql_query 대신 read_sql 사용 가능
    infl_df_all = pd.read_sql("SELECT * FROM influencers", con)
    logging.info(f"{len(infl_df_all)}명의 인플루언서 데이터 로드 완료.")

    logging.info("임베딩 벡터 로딩 중 (vecs.npy)...")
    vecs_all = np.load('vecs.npy')
    logging.info(f"{len(vecs_all)}개의 임베딩 벡터 로드 완료.")

    # 데이터와 벡터 개수 일치 확인
    if len(infl_df_all) != len(vecs_all):
        logging.error(f"인플루언서 데이터({len(infl_df_all)})와 임베딩 벡터({len(vecs_all)}) 개수가 일치하지 않습니다!")
        raise ValueError("Data and vector counts do not match.")

    logging.info("Sentence Transformer 모델 로딩 중...")
    model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')
    logging.info("모델 로딩 완료.")
    # meta.csv 와 vecs.npy 는 요청 처리 시 필요할 때 로드하도록 변경 (메모리 효율)
except Exception as e:
    logging.error(f"모델 로딩 또는 DB 연결 중 치명적 오류 발생: {e}")
    exit()

app = Flask(__name__)

@app.route("/search", methods=['GET'])
def search():
    q = request.args.get("q", "")
    try:
        k = int(request.args.get("k", 5))
    except ValueError:
        k = 5
        logging.warning(f"쿼리 파라미터 'k'가 숫자가 아니거나 없습니다. 기본값 5를 사용합니다.")

    if not q:
        logging.info("검색어가 비어 있어 빈 결과를 반환합니다.")
        return jsonify([])

    logging.info(f"검색 요청: q='{q}', k={k}")

    try:
        # 1. 쿼리 파싱하여 필터 추출
        filters = parse(q)
        logging.info(f"파싱된 필터: {filters}")
        follower_min = filters.get("follower_min", 0)
        follower_max = filters.get("follower_max", math.inf) # 기본 최대값 무한대
        # 카테고리 필터링 조건 추가 (카테고리 필터가 존재할 경우) - Week 2 TODO
        # TODO (Week 2): category 컬럼 필터링 로직 구현. DB에 category 컬럼이 있고,
        #                파싱된 category_filter 값이 있을 때 아래 조건 활성화 필요.
        # category_filter = filters.get("category") # 카테고리 필터값 가져오기
        # if category_filter:
        #     condition &= (infl_df_all['category'] == category_filter)
        #     logging.info(f"카테고리 '{category_filter}' 필터링 적용.")

        # 2. 미리 로드된 데이터프레임 필터링
        # 팔로워 수 필터링 조건 기본 생성
        condition = (infl_df_all['follower_count'] >= follower_min) & (infl_df_all['follower_count'] <= follower_max)

        # 최종 조건으로 데이터프레임 필터링
        filtered_infl_df = infl_df_all[condition].copy() # 필터링 결과 복사본 사용
        # 로그 메시지 원복 (팔로워 필터링만 언급)
        logging.info(f"팔로워 필터링 후 {len(filtered_infl_df)}명의 인플루언서 발견.")

        if filtered_infl_df.empty:
            logging.info("필터링 조건에 맞는 인플루언서가 없습니다.")
            return jsonify([])

        # 3. 필터링된 데이터에 대한 임베딩 벡터 선택
        # filtered_infl_df의 원본 인덱스(infl_df_all 기준)를 사용하여 벡터 선택
        filtered_indices = filtered_infl_df.index.tolist()
        try:
            filtered_vecs = vecs_all[filtered_indices]
        except IndexError as ie:
             logging.error(f"임베딩 벡터 선택 중 인덱스 오류: {ie}. 데이터와 벡터 싱크 문제일 수 있음.", exc_info=True)
             return jsonify({"error": "임베딩 벡터 처리 중 오류.", "details": str(ie)}), 500

        # 4. 쿼리 임베딩 및 유사도 계산
        logging.info("검색어 임베딩 생성 중...")
        qv = model.encode([q])
        logging.info("유사도 계산 중 (필터링된 데이터 대상)...")
        # 벡터 정규화 후 내적 계산 (코사인 유사도)
        # filtered_vecs_norm = filtered_vecs / np.linalg.norm(filtered_vecs, axis=1, keepdims=True)
        # qv_norm = qv / np.linalg.norm(qv)
        # sims = (filtered_vecs_norm @ qv_norm.T).flatten()
        # SentenceTransformer 모델은 보통 정규화된 벡터를 반환하므로 내적만 수행
        sims = (filtered_vecs @ qv.T).flatten()

        # 상위 k개 인덱스 찾기 (filtered_vecs 기준)
        num_results = min(k, len(sims))
        if len(sims) == 0:
             logging.info("유사도 계산 결과가 비어 있습니다.")
             return jsonify([])
        # argsort 결과는 filtered_vecs/filtered_infl_df 내에서의 인덱스 (0부터 시작)
        top_indices_in_filtered = sims.argsort()[-num_results:][::-1]

        logging.info(f"상위 {num_results}개 인덱스 (필터링 내): {top_indices_in_filtered}")
        logging.info(f"유사도 점수: {sims[top_indices_in_filtered]}")

        # 5. 최종 결과 구성 (filtered_infl_df 사용)
        # iloc를 사용하여 filtered_infl_df 내에서 상위 k개 인덱스에 해당하는 행 선택
        results = filtered_infl_df.iloc[top_indices_in_filtered].to_dict(orient="records")

        return jsonify(results)

    except Exception as e:
        logging.error(f"검색 처리 중 오류 발생: {e}", exc_info=True)
        return jsonify({"error": "검색 중 오류가 발생했습니다.", "details": str(e)}), 500

if __name__ == "__main__":
    # Flask 개발 서버 실행 (디버그 모드 활성화)
    # 실제 배포 시에는 gunicorn이나 uwsgi 같은 WSGI 서버 사용 권장
    app.run(host='0.0.0.0', port=5000, debug=True) 
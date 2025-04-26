from flask import Flask, request, jsonify
import numpy as np
import pandas as pd
import sqlite3
from sentence_transformers import SentenceTransformer

# 데이터 및 모델 로드 (애플리케이션 시작 시 한 번만)
try:
    print("데이터베이스 연결 중...")
    # check_same_thread=False 는 Flask의 기본 개발 서버에서 여러 요청을 처리할 때 필요할 수 있습니다.
    # 실제 운영 환경에서는 더 견고한 DB 연결 관리 방식이 필요할 수 있습니다.
    con = sqlite3.connect('mvp.db', check_same_thread=False)
    print("메타데이터 로딩 중 (meta.csv)...")
    meta = pd.read_csv('meta.csv')
    print("임베딩 벡터 로딩 중 (vecs.npy)...")
    vecs = np.load('vecs.npy')
    print("Sentence Transformer 모델 로딩 중...")
    # 모델 로딩은 시간이 걸릴 수 있습니다.
    model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')
    print("데이터 및 모델 로딩 완료.")
except FileNotFoundError as e:
    print(f"오류: 필요한 파일({e.filename})을 찾을 수 없습니다. 4단계가 올바르게 완료되었는지 확인하세요.")
    exit()
except Exception as e:
    print(f"데이터 또는 모델 로딩 중 오류 발생: {e}")
    exit()

app = Flask(__name__)

@app.route("/search", methods=['GET']) # HTTP GET 메서드만 허용
def search():
    # 쿼리 파라미터 받기 (q: 검색어, k: 반환할 개수)
    q = request.args.get("q", "") # 검색어가 없으면 빈 문자열
    try:
        k = int(request.args.get("k", 5)) # k가 없거나 숫자가 아니면 기본값 5 사용
    except ValueError:
        k = 5 # 숫자로 변환 실패 시 기본값 5 사용

    if not q:
        # 검색어가 없으면 빈 리스트 반환
        return jsonify([])

    print(f"검색 요청: q='{q}', k={k}")

    try:
        # 검색어 임베딩 생성
        print("검색어 임베딩 생성 중...")
        qv = model.encode([q])
        print("유사도 계산 중...")
        # 코사인 유사도 계산 (벡터 내적)
        # vecs와 qv가 정규화되어 있다고 가정 (SentenceTransformer 모델은 일반적으로 정규화된 벡터 출력)
        sims = (vecs @ qv.T).flatten() # (N,) 형태의 유사도 점수 배열

        # 가장 유사한 k개 인덱스 찾기
        # argsort는 오름차순 정렬 인덱스를 반환하므로, [-k:]로 뒤에서 k개를 가져오고 [::-1]로 내림차순 뒤집기
        top_indices = sims.argsort()[-k:][::-1]
        print(f"상위 {k}개 인덱스: {top_indices}")
        print(f"유사도 점수: {sims[top_indices]}")

        # 결과 데이터 구성 (meta 데이터프레임에서 해당 인덱스 선택)
        results = meta.iloc[top_indices].to_dict(orient="records")

        # JSON 형태로 결과 반환
        return jsonify(results)

    except Exception as e:
        print(f"검색 처리 중 오류 발생: {e}")
        # 서버 오류 시 500 에러와 메시지 반환
        return jsonify({"error": "검색 중 오류가 발생했습니다.", "details": str(e)}), 500

if __name__ == "__main__":
    # Flask 개발 서버 실행 (디버그 모드 활성화)
    # 실제 배포 시에는 gunicorn이나 uwsgi 같은 WSGI 서버 사용 권장
    app.run(host='0.0.0.0', port=5000, debug=True) 
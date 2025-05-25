import streamlit as st, requests, pandas as pd

# --- 스트림릿 앱 설정 ---
st.title("📈 인스타 인플루언서 검색 MVP v0.2") # 앱 제목 설정

# 사이드바 필터 UI
st.sidebar.header("검색 필터")
query = st.sidebar.text_input("검색 키워드", "렌즈")
min_sim = st.sidebar.slider("유사도 임계값", min_value=0.0, max_value=1.0, value=0.25, step=0.05)
min_follow = st.sidebar.number_input("팔로워 최소", min_value=0, max_value=1_000_000, value=30000, step=5000)

# 추가 필터 (옵션 - 데이터에 해당 컬럼이 있을 경우 활성화)
# gender = st.sidebar.radio("성별", ["all", "male", "female"], index=0)
# age_group = st.sidebar.selectbox("연령대", [None, "10s", "20s", "30s", "40s+"])

# 검색 버튼 - 사이드바에 배치
search_btn = st.sidebar.button("검색", use_container_width=True)

# 메인 영역에 검색 파라미터 표시
st.write(f"검색 파라미터: 키워드='{query}', 유사도≥{min_sim}, 팔로워≥{min_follow:,}")

# API 서버 주소 설정
api_url = "http://localhost:5000/search"

# --- 검색 버튼 로직 ---
if search_btn: # '검색' 버튼이 클릭되면 아래 로직 실행
    try:
        # API 서버 주소를 로컬호스트로 가정
        # TODO: API 서버 주소를 환경 변수 또는 설정 파일에서 읽어오도록 변경 (하드코딩 지양)
        api_url = "http://localhost:5000/search"
        # API 서버에 GET 요청 보내기 (파라미터로 검색어 전달)
        res = requests.get(api_url, params={"q": query})
        res.raise_for_status() # 요청 실패 시 (4xx, 5xx 상태 코드) 오류 발생
        data = res.json() # 응답 본문을 JSON 객체로 파싱

        # --- 결과 처리 및 표시 ---
        if data: # API로부터 결과 데이터가 있을 경우
            df = pd.DataFrame(data) # JSON 데이터를 Pandas DataFrame으로 변환
            # 컬럼 순서 및 이름 조정 (필요 시)
            # TODO: 컬럼 존재 여부를 더 안전하게 확인하고, 필수 컬럼이 없을 경우 사용자에게 알림 표시 개선

            # 표시할 컬럼 목록 정의 (category 추가)
            display_columns = []
            if 'username' in df.columns:
                display_columns.append('username')
            if 'follower_count' in df.columns:
                display_columns.append('follower_count')
            if 'category' in df.columns:
                display_columns.append('category')

            if display_columns: # 표시할 컬럼이 있다면
                 st.dataframe(df[display_columns]) # 정의된 컬럼만 표 형태로 표시
            else: # 표시할 주요 컬럼(username, follower_count, category)이 하나도 없다면
                 st.warning("결과에 주요 컬럼이 없어 전체 데이터를 표시합니다.")
                 st.dataframe(df) # 원본 DataFrame 그대로 표시

            # --- 상세 보기 기능 ---
            # 결과 데이터가 있고 'username' 컬럼이 있을 때만 상세 보기 드롭다운 표시
            usernames = df['username'].tolist() if 'username' in df.columns else []
            if usernames:
                sel = st.selectbox("상세 보기", usernames) # 드롭다운 메뉴로 사용자 선택
                if sel:
                     # 선택된 username으로 데이터 필터링
                     # TODO: 선택된 username에 해당하는 데이터가 여러 개일 경우 처리 방안 고려 (현재는 첫 번째 데이터만 사용)
                     # TODO: iloc[0] 사용은 데이터가 없을 경우 IndexError 발생 가능성 있음. 필터링 후 데이터 존재 여부 확인 필요.
                     selected_data = df[df.username == sel].iloc[0]
                     # 선택된 사용자의 상세 정보 표시
                     st.write(f"사용자: {selected_data['username']}")
                     st.write(f"팔로워: {int(selected_data['follower_count'])}") # 팔로워 수를 정수로 변환하여 표시
                     # TODO: 여기에 광고 비율 파이차트 등 추가적인 상세 정보 시각화 기능 구현
            else:
                st.info("상세 정보를 표시할 사용자가 없습니다.") # 'username' 컬럼이 없거나 데이터가 비어있는 경우

        else: # API로부터 결과 데이터가 없을 경우
            st.info("검색 결과가 없습니다.") # 사용자에게 결과 없음을 알림

    # --- 예외 처리 ---
    except requests.exceptions.ConnectionError:
        st.error(f"API 서버({api_url})에 연결할 수 없습니다. Flask API 서버(api.py)가 실행 중인지 확인하세요.")
    except requests.exceptions.RequestException as e:
        st.error(f"API 요청 중 오류가 발생했습니다: {e}")
    except Exception as e:
        # 그 외 예상치 못한 오류 발생 시 메시지 표시
        # TODO: 구체적인 오류 타입에 따른 분기 처리 및 로깅 강화
        st.error(f"데이터 처리 중 오류가 발생했습니다: {e}") 
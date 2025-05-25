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
        # 로딩 상태 표시
        with st.spinner("검색 중..."):
            # API 서버에 GET 요청 보내기 (모든 파라미터 전달)
            params = {
                "q": query,
                "min_sim": min_sim,
                "min_follow": min_follow,
                "limit": 20
                # "gender": gender if gender != "all" else None,
                # "age_group": age_group
            }
            
            # 디버깅용 파라미터 로깅
            st.sidebar.caption(f"API 요청: {api_url}?q={query}&min_sim={min_sim}&min_follow={min_follow}")
            
            # API 호출
            res = requests.get(api_url, params=params)
            res.raise_for_status() # 요청 실패 시 (4xx, 5xx 상태 코드) 오류 발생
            data = res.json() # 응답 본문을 JSON 객체로 파싱

        # --- 결과 처리 및 표시 ---
        if data: # API로부터 결과 데이터가 있을 경우
            df = pd.DataFrame(data) # JSON 데이터를 Pandas DataFrame으로 변환
            
            # 컬럼 재구성 및 순서 지정
            display_columns = []
            
            # 기본 컬럼
            if 'username' in df.columns:
                display_columns.append('username')
            if 'follower_count' in df.columns:
                display_columns.append('follower_count')
            if 'product_name' in df.columns:
                display_columns.append('product_name')
            if 'score' in df.columns:
                display_columns.append('score')
                
            # 추가 정보 컬럼
            if 'category' in df.columns:
                display_columns.append('category')
            
            # 결과 수 표시
            st.subheader(f"검색 결과: {len(df)}개")

            if display_columns:
                # 표시할 데이터프레임 준비
                display_df = df[display_columns].copy()
                
                # 숫자형 컬럼 포맷팅
                if 'follower_count' in display_df.columns:
                    display_df['follower_count'] = display_df['follower_count'].astype(int).apply(lambda x: f"{x:,}")
                if 'score' in display_df.columns:
                    display_df['score'] = display_df['score'].round(3)
                
                # 결과 테이블 표시
                st.dataframe(
                    display_df,
                    column_config={
                        "username": "사용자명",
                        "follower_count": "팔로워",
                        "product_name": "제품명",
                        "score": "스코어",
                        "category": "카테고리",
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.warning("표시할 주요 컬럼이 없어 전체 데이터를 표시합니다.")
                st.dataframe(df, hide_index=True)

            # --- 썸네일 갤러리 ---
            if 'thumbnail_url' in df.columns:
                st.subheader("썸네일 갤러리")
                thumbnail_cols = st.columns(4)  # 4열 그리드로 표시
                
                for i, (_, row) in enumerate(df.iterrows()):
                    if i < 8:  # 최대 8개 이미지만 표시
                        with thumbnail_cols[i % 4]:
                            if pd.notna(row['thumbnail_url']):
                                try:
                                    st.image(
                                        row['thumbnail_url'], 
                                        caption=f"{row['username']}" + (f" | {row['score']:.2f}" if 'score' in row else ""),
                                        use_column_width=True
                                    )
                                except Exception:
                                    st.error("이미지 로드 실패")
            
            # --- 상세 보기 기능 ---
            st.subheader("상세 정보")
            # 결과 데이터가 있고 'username' 컬럼이 있을 때만 상세 보기 드롭다운 표시
            usernames = df['username'].tolist() if 'username' in df.columns else []
            if usernames:
                sel = st.selectbox("인플루언서 선택", usernames) # 드롭다운 메뉴로 사용자 선택
                if sel:
                     # 선택된 username으로 데이터 필터링
                     selected_data = df[df.username == sel].iloc[0]
                     
                     # 2열 레이아웃
                     col1, col2 = st.columns(2)
                     
                     with col1:
                         st.write(f"**사용자**: {selected_data['username']}")
                         st.write(f"**팔로워**: {int(selected_data['follower_count']):,}")
                         if 'score' in selected_data:
                             st.write(f"**검색 스코어**: {selected_data['score']:.3f}")
                         if 'biography' in selected_data:
                             st.text_area("소개", selected_data['biography'], height=100, disabled=True)
                     
                     with col2:
                         # 썸네일 표시
                         if 'thumbnail_url' in selected_data and pd.notna(selected_data['thumbnail_url']):
                             try:
                                 st.image(selected_data['thumbnail_url'], width=200)
                             except Exception:
                                 st.error("이미지 로드 실패")
                         
                         # 제품명
                         if 'product_name' in selected_data and pd.notna(selected_data['product_name']):
                             st.write(f"**제품명**: {selected_data['product_name']}")
            else:
                st.info("상세 정보를 표시할 사용자가 없습니다.")

        else: # API로부터 결과 데이터가 없을 경우
            st.info("검색 결과가 없습니다.")

    # --- 예외 처리 ---
    except requests.exceptions.ConnectionError:
        # API 서버 연결 실패 시 오류 메시지 표시
        st.error(f"API 서버({api_url})에 연결할 수 없습니다. Flask API 서버(api.py)가 실행 중인지 확인하세요.")
    except requests.exceptions.RequestException as e:
        # 기타 API 요청 관련 오류 발생 시 메시지 표시
        st.error(f"API 요청 중 오류가 발생했습니다: {e}")
    except Exception as e:
        # 그 외 예상치 못한 오류 발생 시 메시지 표시
        st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")
        st.exception(e)  # 개발 중에는 전체 오류 스택 표시 (프로덕션에서는 제거) 
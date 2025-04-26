import streamlit as st, requests, pandas as pd

st.title("📈 인스타 인플루언서 검색 MVP")
query = st.text_input("검색어 예) 선크림 1만 팔로워 뷰티")
if st.button("검색"):
    try:
        # API 서버 주소를 로컬호스트로 가정
        api_url = "http://localhost:5000/search"
        res = requests.get(api_url, params={"q": query})
        res.raise_for_status() # 요청 실패 시 오류 발생
        data = res.json()
        
        if data: # 결과가 있을 경우 DataFrame 생성 및 표시
            df = pd.DataFrame(data)
            # 컬럼 순서 및 이름 조정 (필요 시)
            if 'username' in df.columns and 'follower_count' in df.columns:
                 st.dataframe(df[['username', 'follower_count']]) # 원하는 컬럼만 표시
            else:
                 st.dataframe(df) # 원본 그대로 표시
                 
            # 상세 보기 기능 (결과가 있을 때만)
            usernames = df['username'].tolist() if 'username' in df.columns else []
            if usernames:
                sel = st.selectbox("상세 보기", usernames)
                if sel:
                     # 선택된 username으로 데이터 필터링
                     selected_data = df[df.username == sel].iloc[0] 
                     st.write(f"사용자: {selected_data['username']}")
                     st.write(f"팔로워: {int(selected_data['follower_count'])}")
                     # 여기에 광고비율 파이차트 등 더 추가 가능
            else:
                st.info("상세 정보를 표시할 사용자가 없습니다.")
                
        else: # 결과가 없을 경우 메시지 표시
            st.info("검색 결과가 없습니다.")
            
    except requests.exceptions.ConnectionError:
        st.error(f"API 서버({api_url})에 연결할 수 없습니다. Flask API 서버(api.py)가 실행 중인지 확인하세요.")
    except requests.exceptions.RequestException as e:
        st.error(f"API 요청 중 오류가 발생했습니다: {e}")
    except Exception as e:
        st.error(f"데이터 처리 중 오류가 발생했습니다: {e}") 
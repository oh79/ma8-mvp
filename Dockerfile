# Python 3.10 slim 버전을 베이스 이미지로 사용
FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# 현재 디렉토리의 모든 파일을 컨테이너의 /app 디렉토리로 복사
# (.dockerignore 파일이 있다면 해당 파일에 명시된 것은 제외됨)
COPY . .

# requirements.txt 에 명시된 라이브러리 설치
RUN pip install --no-cache-dir -r requirements.txt

# 컨테이너 외부로 노출할 포트 지정 (Streamlit 기본 포트)
EXPOSE 8501

# 컨테이너 시작 시 실행될 명령
# Flask API 서버를 백그라운드로 실행하고(&), Streamlit 앱을 포그라운드로 실행
# 참고: 이 방식은 간단하지만 프로세스 관리에 한계가 있을 수 있음
CMD python api.py & streamlit run app.py --server.port 8501 --server.address 0.0.0.0 
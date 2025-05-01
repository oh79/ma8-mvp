# Python 3.10 slim 버전을 베이스 이미지로 사용
FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 파일 및 디렉토리만 복사
COPY requirements.txt .
# requirements.txt 에 명시된 라이브러리 설치 (먼저 실행하여 레이어 캐싱 활용)
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 및 앱 파일 복사
COPY src/ ./src/
COPY app.py .

# 데이터 파일 복사 (빌드 시점에 필요한 경우, 또는 볼륨 마운트 사용)
# COPY data/ ./data/

# 컨테이너 외부로 노출할 포트 지정 (Streamlit: 8501, Flask API: 5000)
EXPOSE 8501
EXPOSE 5000

# 컨테이너 시작 시 실행될 명령
# Flask API 서버(src/api.py)를 백그라운드로 실행하고(&), Streamlit 앱(app.py)을 포그라운드로 실행
# 참고: 이 방식은 간단하지만 프로세스 관리에 한계가 있을 수 있음 (예: supervisord 사용 고려)
CMD python src/api.py & streamlit run app.py --server.port 8501 --server.address 0.0.0.0 
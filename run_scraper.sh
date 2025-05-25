#!/bin/bash

# 인스타그램 스크래퍼 실행 쉘 스크립트
# 사용법: ./run_scraper.sh [scan|crawl]

# 기본 모드 설정
MODE=${1:-crawl}

# 로그 디렉토리 생성
mkdir -p logs

# 현재 시간 기록
TIMESTAMP=$(date +"%Y%m%d_%H%M")
LOG_FILE="logs/scraper_${TIMESTAMP}.log"

# 실행 모드에 따라 명령 설정
case "$MODE" in
  scan)
    echo "태그 스캐너 모드로 실행합니다..."
    COMMAND="python run_scraper.py --mode scan --tags lens,colorlens,contactlens,소프트렌즈,컬러렌즈 --limit 10000"
    ;;
  crawl)
    echo "디테일 크롤러 모드로 실행합니다..."
    COMMAND="python run_scraper.py --mode crawl --parallel 8"
    ;;
  *)
    echo "알 수 없는 모드: $MODE"
    echo "사용법: ./run_scraper.sh [scan|crawl]"
    exit 1
    ;;
esac

# 명령 실행 (로그 파일에 저장)
echo "명령: $COMMAND"
echo "로그 파일: $LOG_FILE"
echo "시작 시간: $(date)"
echo "Ctrl+C를 눌러 안전하게 종료할 수 있습니다."
echo "-------------------------------------------"

# 명령 실행 (stdout과 stderr 모두 로그 파일로 리다이렉션)
$COMMAND > >(tee -a "$LOG_FILE") 2>&1

# 종료 상태 확인
EXIT_STATUS=$?
if [ $EXIT_STATUS -eq 0 ]; then
  echo "-------------------------------------------"
  echo "실행 완료: 성공"
  echo "종료 시간: $(date)"
else
  echo "-------------------------------------------"
  echo "실행 종료: 오류 발생 (코드: $EXIT_STATUS)"
  echo "종료 시간: $(date)"
fi

exit $EXIT_STATUS

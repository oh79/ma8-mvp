import pandas as pd
import sqlite3

# CSV 파일 읽기
try:
    df_inf = pd.read_csv('data/influencers.csv')
    df_posts = pd.read_csv('data/posts.csv')
    print("CSV 파일 로드 완료: influencers.csv, posts.csv")
except FileNotFoundError as e:
    print(f"오류: 필요한 CSV 파일({e.filename})을 찾을 수 없습니다. scraper.py가 정상적으로 실행되었는지 확인하세요.")
    exit()
except Exception as e:
    print(f"CSV 파일 읽기 중 오류 발생: {e}")
    exit()

# SQLite 데이터베이스 연결
try:
    # mvp.db 파일이 없으면 새로 생성됩니다.
    con = sqlite3.connect('data/mvp.db')
    print("데이터베이스 연결 성공: mvp.db")

    # 데이터프레임을 SQL 테이블로 저장
    # if_exists='replace': 테이블이 이미 존재하면 삭제하고 새로 만듭니다.
    # index=False: 데이터프레임 인덱스를 DB 테이블에 별도 컬럼으로 저장하지 않습니다.
    df_inf.to_sql('influencers', con, if_exists='replace', index=False)
    print("'influencers' 테이블 저장 완료.")
    df_posts.to_sql('posts', con, if_exists='replace', index=False)
    print("'posts' 테이블 저장 완료.")

except sqlite3.Error as e:
    print(f"데이터베이스 작업 중 오류 발생: {e}")
except Exception as e:
    print(f"데이터 저장 중 오류 발생: {e}")
finally:
    # 데이터베이스 연결 종료 (오류 발생 여부와 관계없이 실행)
    if 'con' in locals() and con:
        con.close()
        print("데이터베이스 연결 종료.")

print("ETL 스크립트 실행 완료.") 
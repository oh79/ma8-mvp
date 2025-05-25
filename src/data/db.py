import os
import logging
import duckdb
import pandas as pd
from datetime import datetime

class DatabaseManager:
    """데이터베이스 연결 및 데이터 저장/로드 관리"""
    
    def __init__(self, data_dir="data", db_name="instagram.db"):
        self.data_dir = data_dir
        self.db_path = os.path.join(data_dir, db_name)
        self.conn = None
        
        # 디렉토리가 없으면 생성
        os.makedirs(data_dir, exist_ok=True)
        
        # 연결 초기화
        self.init_database()
    
    def init_database(self):
        """DuckDB 초기화 및 테이블 생성"""
        try:
            self.conn = duckdb.connect(self.db_path)
            
            # 인플루언서 테이블 생성
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS influencers (
                    username VARCHAR PRIMARY KEY,
                    pk BIGINT,
                    full_name VARCHAR,
                    follower_count INT,
                    following_count INT,
                    media_count INT,
                    biography TEXT,
                    category VARCHAR,
                    external_url VARCHAR,
                    is_private BOOLEAN,
                    is_verified BOOLEAN
                )
            """)
            
            # 게시물 테이블 생성
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id VARCHAR PRIMARY KEY,
                    user_pk BIGINT,
                    username VARCHAR,
                    caption TEXT,
                    like_count INT,
                    comment_count INT,
                    taken_at TIMESTAMP,
                    media_type INT,
                    product_type VARCHAR,
                    image_url VARCHAR,
                    video_url VARCHAR
                )
            """)
            
            logging.info("데이터베이스 초기화 완료")
            return True
        except Exception as e:
            logging.error(f"데이터베이스 초기화 오류: {str(e)}")
            return False
    
    def save_influencer(self, influencer):
        """인플루언서 정보를 데이터베이스에 저장"""
        if not self.conn:
            return False
            
        try:
            # HttpUrl 객체는 문자열로 변환
            external_url = str(influencer.get('external_url', '')) if influencer.get('external_url') else ''
            
            self.conn.execute("""
                INSERT OR REPLACE INTO influencers 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                influencer.get('username', ''),
                influencer.get('pk', 0),
                influencer.get('full_name', ''),
                influencer.get('follower_count', 0),
                influencer.get('following_count', 0),
                influencer.get('media_count', 0),
                influencer.get('biography', ''),
                influencer.get('category', ''),
                external_url,
                influencer.get('is_private', False),
                influencer.get('is_verified', False)
            ))
            return True
        except Exception as e:
            logging.error(f"인플루언서 DB 저장 오류: {str(e)}")
            return False
    
    def save_post(self, post):
        """게시물 정보를 데이터베이스에 저장"""
        if not self.conn:
            return False
            
        try:
            # HttpUrl 객체는 문자열로 변환
            image_url = str(post.get('image_url', '')) if post.get('image_url') else ''
            video_url = str(post.get('video_url', '')) if post.get('video_url') else ''
            
            # taken_at이 문자열이면 datetime으로 변환
            taken_at = post.get('taken_at', datetime.now())
            if isinstance(taken_at, str):
                try:
                    taken_at = datetime.fromisoformat(taken_at.replace('Z', '+00:00'))
                except:
                    taken_at = datetime.now()
            
            self.conn.execute("""
                INSERT OR IGNORE INTO posts 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post.get('id', ''),
                post.get('user_pk', 0),
                post.get('username', ''),
                post.get('caption', ''),
                post.get('like_count', 0),
                post.get('comment_count', 0),
                taken_at,
                post.get('media_type', 0),
                post.get('product_type', ''),
                image_url,
                video_url
            ))
            return True
        except Exception as e:
            logging.error(f"게시물 DB 저장 오류: {str(e)}")
            return False
    
    def save_data_to_csv(self, influencers, posts, is_temp=False):
        """수집된 데이터를 CSV 파일로 저장"""
        # 디렉토리가 없으면 생성
        os.makedirs(self.data_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        
        # 파일명 설정 (임시 파일은 접두어 추가)
        prefix = "temp_" if is_temp else ""
        influencers_file = os.path.join(self.data_dir, f"{prefix}influencers.csv")
        posts_file = os.path.join(self.data_dir, f"{prefix}posts.csv")
        
        # 인플루언서 정보를 DataFrame으로 변환하여 저장
        if influencers:
            influencers_df = pd.DataFrame(list(influencers.values()))
            # HttpUrl 객체는 문자열로 변환
            if 'external_url' in influencers_df.columns:
                influencers_df['external_url'] = influencers_df['external_url'].astype(str)
                
            influencers_df.to_csv(influencers_file, index=False)
            logging.info(f"인플루언서 데이터 {len(influencers)}건을 {influencers_file}에 저장했습니다.")
            
            # DB에도 저장
            for _, row in influencers_df.iterrows():
                self.save_influencer(row.to_dict())
        
        # 게시물 정보를 DataFrame으로 변환하여 저장
        if posts:
            posts_df = pd.DataFrame(posts)
            # HttpUrl 객체는 문자열로 변환
            if 'image_url' in posts_df.columns:
                posts_df['image_url'] = posts_df['image_url'].astype(str)
            if 'video_url' in posts_df.columns:
                posts_df['video_url'] = posts_df['video_url'].astype(str)
                
            posts_df.to_csv(posts_file, index=False)
            logging.info(f"게시물 데이터 {len(posts)}건을 {posts_file}에 저장했습니다.")
            
            # DB에도 저장
            for _, row in posts_df.iterrows():
                self.save_post(row.to_dict())
        
        # 백업 파일 생성 (3시간마다)
        if not is_temp and (int(timestamp.split("_")[1]) % 300 == 0):
            backup_dir = os.path.join(self.data_dir, "backup")
            os.makedirs(backup_dir, exist_ok=True)
            
            if influencers:
                backup_influencers = os.path.join(backup_dir, f"influencers_{timestamp}.csv")
                influencers_df.to_csv(backup_influencers, index=False)
                
            if posts:
                backup_posts = os.path.join(backup_dir, f"posts_{timestamp}.csv")
                posts_df.to_csv(backup_posts, index=False)
                
            logging.info(f"백업 파일 생성 완료: {timestamp}")
    
    def load_checkpoint(self):
        """체크포인트 파일에서 이미 처리된 사용자 목록 로드"""
        checkpoint_file = os.path.join(self.data_dir, "crawler_checkpoint.csv")
        processed_users = set()
        
        if os.path.exists(checkpoint_file):
            try:
                df = pd.read_csv(checkpoint_file)
                if 'username' in df.columns:
                    processed_users = set(df['username'].values)
                logging.info(f"체크포인트 파일에서 {len(processed_users)}명의 처리된 사용자 로드")
            except Exception as e:
                logging.error(f"체크포인트 로드 오류: {str(e)}")
                    
        return processed_users
    
    def save_checkpoint(self, processed, force_save=False):
        """체크포인트 파일에 처리된 사용자 목록 저장"""
        if not processed:
            return
                
        checkpoint_file = os.path.join(self.data_dir, "crawler_checkpoint.csv")
        
        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(checkpoint_file), exist_ok=True)
        
        # 체크포인트 저장
        df = pd.DataFrame({'username': list(processed)})
        df.to_csv(checkpoint_file, index=False)
        logging.info(f"체크포인트 업데이트: 현재까지 {len(processed)}명 저장 ({checkpoint_file})")
    
    def load_target_usernames(self, specific_users=None):
        """파일에서 대상 사용자명 목록 로드"""
        if specific_users:
            usernames = [u.strip() for u in specific_users.split(',')]
            logging.info(f"특정 사용자 로드: {len(usernames)}명")
            return usernames
        
        # 체크포인트에서 모든 사용자 로드
        checkpoint_file = os.path.join(self.data_dir, "crawler_checkpoint.csv")
        if os.path.exists(checkpoint_file):
            try:
                df = pd.read_csv(checkpoint_file)
                if 'username' in df.columns:
                    usernames = df['username'].values.tolist()
                    logging.info(f"체크포인트에서 {len(usernames)}명의 대상 사용자 로드")
                    return usernames
            except Exception as e:
                logging.error(f"체크포인트에서 대상 로드 오류: {str(e)}")
        
        # 데이터 디렉토리에서 인플루언서 목록 파일 찾기 시도
        influencers_file = os.path.join(self.data_dir, "lens_influencers.txt")
        test_file = os.path.join(self.data_dir, "lens_influencers_test.txt")
        
        if os.path.exists(test_file):
            with open(test_file, 'r', encoding='utf-8') as f:
                usernames = [line.strip() for line in f if line.strip()]
            logging.info(f"테스트 인플루언서 목록 로드: {len(usernames)}명")
            return usernames
        elif os.path.exists(influencers_file):
            with open(influencers_file, 'r', encoding='utf-8') as f:
                usernames = [line.strip() for line in f if line.strip()]
            logging.info(f"인플루언서 목록 로드: {len(usernames)}명")
            return usernames
        else:
            logging.warning("인플루언서 목록 파일을 찾을 수 없습니다. 해시태그 검색만 사용합니다.")
            return []
    
    def load_temp_data(self):
        """임시 저장된 데이터 로드 (충돌 후 복구)"""
        temp_influencers = os.path.join(self.data_dir, "temp_influencers.csv")
        temp_posts = os.path.join(self.data_dir, "temp_posts.csv")
        
        influencers = {}
        posts = []
        
        if os.path.exists(temp_influencers):
            try:
                df = pd.read_csv(temp_influencers)
                for _, row in df.iterrows():
                    username = row['username']
                    influencers[username] = row.to_dict()
                logging.info(f"임시 인플루언서 데이터 {len(influencers)}건 로드 완료")
            except Exception as e:
                logging.error(f"임시 인플루언서 데이터 로드 실패: {str(e)}")
        
        if os.path.exists(temp_posts):
            try:
                posts = pd.read_csv(temp_posts).to_dict('records')
                logging.info(f"임시 게시물 데이터 {len(posts)}건 로드 완료")
            except Exception as e:
                logging.error(f"임시 게시물 데이터 로드 실패: {str(e)}")
                
        return influencers, posts
    
    def close(self):
        """데이터베이스 연결 종료"""
        if self.conn:
            self.conn.close()
            logging.info("데이터베이스 연결 종료") 
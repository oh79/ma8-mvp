import pandas as pd

# 데이터 로드
influencers = pd.read_csv('data/influencers.csv')
posts = pd.read_csv('data/posts.csv')

# 기본 통계 출력
print("=== 인플루언서 통계 ===")
print(f"총 인플루언서 수: {len(influencers)}")
print(f"평균 팔로워 수: {influencers['follower_count'].mean()}")

print("\n=== 게시물 통계 ===")
print(f"총 게시물 수: {len(posts)}")
print(f"평균 좋아요 수: {posts['like_count'].mean()}")
print(f"평균 댓글 수: {posts['comment_count'].mean()}")

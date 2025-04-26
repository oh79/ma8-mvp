import re
import math
from konlpy.tag import Okt # KoNLPy의 Okt 형태소 분석기 사용

# --- Okt 형태소 분석기 초기화 ---
okt = Okt()

# --- 상수 정의 ---
# 팔로워 수 파싱을 위한 정규 표현식 패턴
# 패턴 순서 중요: 더 구체적인 패턴(범위)을 먼저 매칭
# 예: 1만~5만, 10만 이상, 5천명, 1만명 등
FOLLOWER_PATTERNS = [
    # 1. X만 ~ Y만 (명 포함 가능)
    re.compile(r'(\d+)\s*만(?:\s*명)?\s*~\s*(\d+)\s*만(?:\s*명)?'),
    # 2. X천 ~ Y만 (명 포함 가능)
    re.compile(r'(\d+)\s*천(?:\s*명)?\s*~\s*(\d+)\s*만(?:\s*명)?'),
    # 3. X만 ~ Y천 (명 포함 가능)
    re.compile(r'(\d+)\s*만(?:\s*명)?\s*~\s*(\d+)\s*천(?:\s*명)?'),
    # 4. X천 ~ Y천 (명 포함 가능)
    re.compile(r'(\d+)\s*천(?:\s*명)?\s*~\s*(\d+)\s*천(?:\s*명)?'),
    # 5. X만 이상/넘는 (명 포함 가능)
    re.compile(r'(\d+)\s*만(?:\s*명)?\s*(?:이상|넘는)'),
    # 6. X천 이상/넘는 (명 포함 가능)
    re.compile(r'(\d+)\s*천(?:\s*명)?\s*(?:이상|넘는)'),
    # 7. X만 이하/미만 (명 포함 가능)
    re.compile(r'(\d+)\s*만(?:\s*명)?\s*(?:이하|미만)'),
    # 8. X천 이하/미만 (명 포함 가능)
    re.compile(r'(\d+)\s*천(?:\s*명)?\s*(?:이하|미만)'),
    # 9. X만 (명 포함 가능) - 기본적으로 이상으로 간주
    re.compile(r'(\d+)\s*만(?:\s*명)?'),
    # 10. X천 (명 포함 가능) - 기본적으로 이상으로 간주
    re.compile(r'(\d+)\s*천(?:\s*명)?'),
    # 11. 숫자만 있는 경우 - 우선순위 낮음. (명 등 단위 명시 없을 때)
    # TODO: 숫자만 있을 경우의 처리 정책 재검토 필요 (예: '가격 20000')
    re.compile(r'(\d+)'),
]

# 카테고리 사전 정의
# TODO: 더 많은 카테고리 및 동의어/유의어 확장 필요
CATEGORIES = {
    "뷰티": ["뷰티", "화장품", "메이크업", "코스메틱"],
    "패션": ["패션", "옷", "스타일", "의류"],
    "푸드": ["푸드", "음식", "맛집", "요리", "먹방"],
    "여행": ["여행", "숙소", "관광"],
    "IT": ["IT", "테크", "전자기기", "개발"],
    "게임": ["게임", "게이밍"],
    # 추가 카테고리...
}

# --- 헬퍼 함수 ---
def _convert_korean_num(num_str, unit):
    """'만', '천' 단위 숫자를 정수로 변환"""
    try:
        num = int(num_str)
        if unit == '만':
            return num * 10000
        elif unit == '천':
            return num * 1000
        else: # 단위가 없거나 숫자만 있는 경우 (패턴 11)
             # TODO: 숫자만 있을 때 단위를 어떻게 가정할지? 일단 그대로 반환 후 parse_followers에서 조정
            return num
    except ValueError:
        return 0

# --- 파싱 함수 ---
def parse_followers(text):
    """텍스트에서 팔로워 최소/최대값을 파싱하여 튜플로 반환 (min, max)"""
    # 기본값 설정: 최소 0, 최대 무한대(inf)
    follower_min = 0
    follower_max = math.inf

    # 정규표현식 패턴 순차 적용
    for idx, pattern in enumerate(FOLLOWER_PATTERNS):
        match = pattern.search(text)
        if match:
            groups = match.groups()
            pattern_index = idx + 1 # 패턴 번호 (1부터 시작)

            if pattern_index == 1: # X만 ~ Y만
                follower_min = _convert_korean_num(groups[0], '만')
                follower_max = _convert_korean_num(groups[1], '만')
            elif pattern_index == 2: # X천 ~ Y만
                follower_min = _convert_korean_num(groups[0], '천')
                follower_max = _convert_korean_num(groups[1], '만')
            elif pattern_index == 3: # X만 ~ Y천
                follower_min = _convert_korean_num(groups[0], '만')
                follower_max = _convert_korean_num(groups[1], '천')
            elif pattern_index == 4: # X천 ~ Y천
                follower_min = _convert_korean_num(groups[0], '천')
                follower_max = _convert_korean_num(groups[1], '천')
            elif pattern_index == 5: # X만 이상
                follower_min = _convert_korean_num(groups[0], '만')
                follower_max = math.inf
            elif pattern_index == 6: # X천 이상
                follower_min = _convert_korean_num(groups[0], '천')
                follower_max = math.inf
            elif pattern_index == 7: # X만 이하
                follower_min = 0
                follower_max = _convert_korean_num(groups[0], '만')
            elif pattern_index == 8: # X천 이하
                follower_min = 0
                follower_max = _convert_korean_num(groups[0], '천')
            elif pattern_index == 9: # X만 (이상으로 간주)
                num = _convert_korean_num(groups[0], '만')
                # 만약 이미 min/max가 설정되었다면(범위형 패턴 매칭 후) 덮어쓰지 않음
                if follower_min == 0 and follower_max == math.inf:
                     follower_min = num
                     follower_max = math.inf # 또는 num? 정책 결정 필요. 우선 이상으로 처리.
            elif pattern_index == 10: # X천 (이상으로 간주)
                num = _convert_korean_num(groups[0], '천')
                if follower_min == 0 and follower_max == math.inf:
                     follower_min = num
                     follower_max = math.inf
            elif pattern_index == 11: # 숫자만
                 # 숫자만 단독으로 나올 경우 처리 (예: '5000') - 다른 패턴에 매칭 안됐을 때만
                 # TODO: 이 부분의 정확성 개선 필요 (예: '팔로워 5000' vs '가격 5000')
                 # 현재는 다른 패턴이 먼저 매칭되면 이 패턴은 무시될 가능성 높음
                 # 만약 다른 명확한 팔로워 표현이 없다면, 이 숫자를 팔로워 수로 가정해볼 수 있음
                 num = _convert_korean_num(groups[0], None)
                 # 다른 팔로워 정보가 전혀 없을 때만 이 값을 min으로 사용 (매우 낮은 우선순위)
                 if follower_min == 0 and follower_max == math.inf:
                     # 숫자의 크기에 따라 단위를 추정해볼 수도 있음 (예: 1000 이상이면 천 단위?)
                     # 일단은 그대로 min 값으로 사용. max는 불명확하므로 inf 유지
                     follower_min = num


            # 첫 번째 매칭되는 패턴을 찾으면 더 이상 진행하지 않음
            break

    # 만약 min > max 인 경우가 발생하면 (예: '5만~1천'), 값을 교환
    if follower_min > follower_max:
        follower_min, follower_max = follower_max, follower_min

    return follower_min, follower_max

def parse_category(text):
    """텍스트에서 카테고리 키워드를 찾아 대표 카테고리명을 반환"""
    # 형태소 분석을 통해 명사 추출
    nouns = okt.nouns(text)

    # 카테고리 사전 순회하며 매칭되는 키워드 찾기
    for category_name, keywords in CATEGORIES.items():
        for keyword in keywords:
            if keyword in text or keyword in nouns:
                 # 대표 카테고리 이름을 반환 (예: '화장품' -> '뷰티')
                return category_name
    return None # 매칭되는 카테고리 없음

# --- 메인 파싱 함수 --- #
def parse(text):
    """입력 텍스트를 파싱하여 필터링 조건 딕셔너리 반환"""
    if not text:
        return {}

    follower_min, follower_max = parse_followers(text)
    category = parse_category(text)

    # --- 제품 키워드 추출 로직 추가 ---
    product = None
    nouns = okt.nouns(text) # 형태소 분석기에서 명사 추출

    # 카테고리 키워드 목록 준비 (중첩 리스트 펼치기)
    category_keywords = set()
    if category and category in CATEGORIES:
        category_keywords.update(CATEGORIES[category]) # 해당 카테고리의 키워드 추가
        category_keywords.add(category) # 대표 카테고리명도 추가 (e.g., "뷰티")

    # 팔로워 관련 단어 및 일반적인 단어 제외 (간단한 필터링)
    # TODO (Week 2): 더 정교한 불용어 처리 필요 (예: 품사 태깅 활용, 불용어 사전 확장)
    follower_words = {'팔로워', '명', '이상', '이하', '미만', '사이', '정도', '만', '천'}
    stop_words = category_keywords.union(follower_words)

    # 추출된 명사 중에서, 카테고리 키워드나 팔로워 관련 단어가 아닌 첫 번째 명사를 제품 후보로 선택
    # TODO (Week 2): 여러 제품 후보 처리, 키워드 중요도 계산, 의미 분석 등 정확도 개선 필요
    potential_products = [noun for noun in nouns if noun not in stop_words and len(noun) > 1] # 한 글자 명사 제외
    if potential_products:
        product = potential_products[0]
    # --- 제품 키워드 추출 로직 끝 ---

    filters = {}
    if follower_min > 0:
        filters['follower_min'] = follower_min
    # 최대값이 무한대가 아닌 경우에만 필터에 추가
    if follower_max != math.inf:
        filters['follower_max'] = follower_max
    if category:
        filters['category'] = category
    if product:
        filters['product'] = product # 추출된 제품 키워드 추가

    return filters

# --- 단위 테스트 케이스 --- #
# TODO: 정식 테스트 프레임워크(예: pytest) 사용 고려
CASES = [
  ("선크림 홍보, 팔로워 1만~5만, 뷰티", {
    "product": "선크림", # 제품 추출 예상 결과 추가
    "follower_min": 10000, "follower_max": 50000,
    "category": "뷰티"
  }),
  ("팔로워 10만 이상 IT 유튜버", {
      "follower_min": 100000,
      "category": "IT",
      "product": "유튜버" # 제품 예시 추가 (개선 필요)
  }),
  ("5천명 ~ 2만명 사이 패션 인플루언서", {
      "follower_min": 5000, "follower_max": 20000,
      "category": "패션",
      "product": "인플루언서" # 제품 예시 추가
  }),
   ("여행 관련 3천 이상", {
      "follower_min": 3000,
      "category": "여행",
      "product": "관련" # 제품 예시 추가 (개선 필요)
  }),
  ("팔로워 7만명", {
      "follower_min": 70000
      # 카테고리 없음, 제품 없음
  }),
  ("대략 5천명 이하 음식 먹방 유튜버", { # 입력 텍스트 수정 (유튜버 추가)
      "follower_max": 5000,
      "category": "푸드",
      "product": "유튜버" # 제품 예시 추가
  }),
   ("게임 유튜버 20000명", {
      "follower_min": 20000,
      "category": "게임",
      "product": "유튜버" # 제품 예시 추가
  }),
  ("팔로워 만명", {
       # 필터 없음
  }),
  ("화장품 광고", {
      "category": "뷰티",
      "product": "광고" # 제품 예시 추가
  }),
   ("1만 팔로워 스타일리스트", {
      "follower_min": 10000,
      "category": "패션",
      "product": "스타일리스트" # 제품 예시 추가
  }),
   ("갤럭시 휴대폰 IT", { # 새 테스트 케이스
       "category": "IT",
       "product": "갤럭시" # 또는 휴대폰? 현재 로직으론 첫번째 명사
   })
]

# --- 테스트 실행 코드 --- #
if __name__ == "__main__":
    print("--- 팔로워 파싱 테스트 (기존) ---")
    test_texts_followers = [
        "선크림 홍보, 팔로워 1만~5만, 뷰티",
        "팔로워 10만 이상 IT 유튜버",
        "5천명 ~ 2만명 사이 패션 인플루언서",
        "여행 관련 3천 이상",
        "팔로워 7만명",
        "대략 5천명 이하",
        "게임 유튜버 20000명",
        "팔로워 만명"
    ]
    for text in test_texts_followers:
        f_min, f_max = parse_followers(text)
        print(f"텍스트: '{text}'")
        print(f"  -> 팔로워: min={f_min}, max={'무한대' if f_max == math.inf else f_max}")

    print("\n--- 통합 파싱 단위 테스트 ---")
    pass_count = 0
    for i, (text, expected) in enumerate(CASES):
        result = parse(text)
        is_pass = result == expected
        if is_pass:
            pass_count += 1
            status = "PASS"
        else:
            status = "FAIL"
        print(f"Case {i+1}: {status}")
        print(f"  Input: '{text}'")
        print(f"  Result: {result}")
        print(f"  Expected: {expected}")

    print(f"\n테스트 완료: {pass_count}/{len(CASES)} 통과") 
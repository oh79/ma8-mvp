# -*- coding: utf-8 -*-
import re
from konlpy.tag import Okt

# --- Okt 형태소 분석기 초기화 ---
okt = Okt()

# --- 상수 정의 ---
# 카테고리 사전 정의 (기존 유지)
CATEGORIES = {
    "뷰티": ["뷰티", "화장품", "메이크업", "코스메틱", "스킨케어"],
    "패션": ["패션", "옷", "스타일", "의류", "신발", "악세사리"],
    "푸드": ["푸드", "음식", "맛집", "요리", "먹방", "레시피"],
    "여행": ["여행", "숙소", "관광", "항공권"],
    "IT": ["IT", "테크", "전자기기", "개발", "소프트웨어", "앱"],
    "게임": ["게임", "게이밍"],
    "육아": ["육아", "아기", "출산", "유아용품"],
    "운동": ["운동", "헬스", "피트니스", "요가", "스포츠"],
}

# 제품명 추출 시 제외할 일반적인 단어 (기본 불용어)
# TODO: 필요에 따라 불용어 확장
BASE_STOP_WORDS = {
    "관련", "추천", "좀", "주세요", "알려줘", "찾아줘",
    "사람", "인플루언서", "유튜버", "광고", "협찬", "홍보",
    "스타일", "느낌", "종류",
    "#", # 해시태그 기호 자체
    # 실패 분석 기반 추가
    "남자", "여자", "요즘", "게임", "정보", "후기", "가격"
}

# --- 파싱 함수 ---
def parse_category(text: str) -> str | None:
    """텍스트에서 카테고리 키워드를 찾아 대표 카테고리명을 반환"""
    if not text:
        return None

    # 형태소 분석을 통해 명사 추출
    # TODO: 명사 외 다른 품사(예: 형용사)도 고려하여 카테고리 매칭 정확도 향상 검토
    nouns = set(okt.nouns(text))

    # 카테고리 사전 순회하며 매칭되는 키워드 찾기
    for category_name, keywords in CATEGORIES.items():
        # 키워드 중 하나라도 텍스트에 직접 포함되거나, 추출된 명사 집합에 있는지 확인
        if any(keyword in text for keyword in keywords) or not nouns.isdisjoint(keywords):
            return category_name
    return None # 매칭되는 카테고리 없음

def parse_product(text: str, category: str | None) -> str | None:
    """텍스트에서 제품 관련 키워드를 추출 (카테고리 정보 활용)"""
    if not text:
        return None

    # nouns = okt.nouns(text)
    phrases = okt.phrases(text) # 명사 대신 구(phrase) 추출
    if not phrases:
        return None

    # 불용어 목록 준비
    stop_words = BASE_STOP_WORDS.copy()
    category_keywords = set()
    if category and category in CATEGORIES:
        category_keywords.update(CATEGORIES[category]) # 해당 카테고리의 키워드 추가
        category_keywords.add(category) # 대표 카테고리명도 추가

    stop_words.update(category_keywords)

    # 추출된 구(phrase) 중에서, 불용어가 아니고 길이가 1 이상인 후보 단어 추출
    # TODO: 키워드 중요도 계산, 연어(collocation) 분석 등 정확도 개선 필요
    # potential_products = [noun for noun in nouns if noun not in stop_words and len(noun) > 1]
    potential_products = []
    for phrase in phrases:
        # 구 전체가 불용어이거나, 구를 구성하는 단어가 모두 불용어인 경우 제외?
        # 우선 간단하게 구 자체가 불용어인지 확인
        if phrase not in stop_words and len(phrase) > 1:
             # 구를 구성하는 단일 명사들도 불용어인지 체크 (선택적)
             # nouns_in_phrase = okt.nouns(phrase)
             # if not any(n in stop_words for n in nouns_in_phrase):
             potential_products.append(phrase)

    if potential_products:
        # 현재는 가장 처음 나오는 후보 단어를 반환 (개선 필요)
        # TODO: 후보 중 가장 긴 구를 선택하거나, 더 나은 로직 적용
        return potential_products[0]
    else:
        # 명사에서 못 찾으면 원문에서 카테고리 키워드 제외하고 남은 부분 고려?
        # TODO: 대체 제품 키워드 추출 로직 추가 검토
        return None

def parse(text: str) -> dict:
    """입력 텍스트를 파싱하여 카테고리와 제품 키워드 딕셔너리 반환"""
    if not text:
        return {"product": None, "category": None}

    category = parse_category(text)
    product = parse_product(text, category)

    return {
        "product": product,
        "category": category
    }

# --- 단위 테스트 케이스 --- #
CASES = [
    ("선크림 추천해줘", {"product": "선크림", "category": None}),
    ("아이폰 15 사전예약 정보 (IT)", {"product": "아이폰 15", "category": "IT"}), # 가장 긴 구 "아이폰 15" 선택 기대
    ("성수동 맛집 알려줘", {"product": "성수동 맛집", "category": "푸드"}), # 가장 긴 구 "성수동 맛집" 선택 기대
    ("남자 패션 스타일", {"product": None, "category": "패션"}), # "남자 패션"의 명사 "남자", "패션" 모두 불용어 -> 제외 기대
    ("요즘 유행하는 운동화", {"product": "운동화", "category": "패션"}), # "요즘 유행" 제외, 카테고리 순서 변경으로 "패션" 기대
    ("제주도 숙소", {"product": "제주도 숙소", "category": "여행"}), # 가장 긴 구 "제주도 숙소" 선택 기대
    ("캠핑용품 뭐가 좋아?", {"product": "캠핑용품", "category": None}),
    ("게임 개발 정보", {"product": "게임 개발", "category": "IT"}) # "게임 개발"의 명사 "게임", "개발" 중 "개발"은 불용어 아님 -> 유지됨
]

# --- 테스트 실행 코드 --- #
if __name__ == "__main__":
    print("--- NLP Parser 경량화 버전 테스트 --- ")
    pass_count = 0
    total_count = len(CASES)

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

    accuracy = (pass_count / total_count) * 100 if total_count > 0 else 0
    print(f"테스트 완료: {pass_count}/{total_count} 통과 ({accuracy:.2f}%)")

    if accuracy < 90:
        print("[주의] 목표 정확도(90%) 미달. 파싱 로직 개선이 필요합니다.") 
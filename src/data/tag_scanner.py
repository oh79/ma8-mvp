#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
태그 스캐너 모듈 - 해시태그 검색을 통한 사용자명 수집

이 모듈은 인스타그램의 해시태그 검색 기능을 사용하여 
대상 해시태그에서 사용자명을 수집하는 기능을 담당합니다.
태그당 별도의 Client 인스턴스를 사용하고, 스레드 풀을 통해 병렬 처리합니다.
"""

import os
import logging
import time
import random
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Any, Optional
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, ClientError, HashtagNotFound, 
    ClientLoginRequired, ClientJSONDecodeError,
    ClientConnectionError, RateLimitError
)

from .rate_control import DynamicDelayAdapter
from .proxy_manager import ProxyManager
from .utils import setup_logging

# 환경 변수 로드
load_dotenv()

# 상수 정의
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 284.0.0.20.117",
    "Mozilla/5.0 (Android 10; Mobile; rv:123.0) Gecko/123.0 Firefox/123.0",
    "Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; 6T; OnePlus6T; qcom; en_US; 314665256)",
    "Mozilla/5.0 (Linux; Android 13; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
]

# 인증 정보
USERNAME = os.getenv("INSTAGRAM_USERNAME")
PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

class TagScanner:
    """해시태그를 스캔하여 사용자명을 수집하는 클래스"""
    
    def __init__(
        self,
        data_dir: str = "data",
        outfile: str = "usernames.txt",
        state_file: str = "scan_state.json",
        max_workers: int = 5
    ):
        """
        초기화
        
        Args:
            data_dir: 데이터 저장 디렉토리
            outfile: 수집된 사용자명을 저장할 파일명
            state_file: 스캔 상태를 저장할 파일명
            max_workers: 병렬 작업할 최대 스레드 수
        """
        self.data_dir = data_dir
        self.outfile_path = os.path.join(data_dir, outfile)
        self.state_file_path = os.path.join(data_dir, state_file)
        self.max_workers = max_workers
        self.collected_usernames = set()  # 중복 제거를 위한 집합
        self.scan_state = self._load_state()
        
        # 저장 디렉토리가 없으면 생성
        os.makedirs(data_dir, exist_ok=True)
        
        # 이미 파일이 있으면 기존 사용자명 로드
        if os.path.exists(self.outfile_path):
            self._load_existing_usernames()
            
        # 세션 파일 경로
        self.session_file = os.path.join(data_dir, "session.json")
    
    def _load_existing_usernames(self) -> None:
        """기존 파일에서 사용자명 로드"""
        try:
            with open(self.outfile_path, "r", encoding="utf-8") as f:
                for line in f:
                    username = line.strip()
                    if username:
                        self.collected_usernames.add(username)
            logging.info(f"기존 파일에서 {len(self.collected_usernames)}개의 사용자명 로드됨")
        except Exception as e:
            logging.error(f"기존 사용자명 로드 중 오류: {str(e)}")
    
    def _load_state(self) -> Dict[str, Any]:
        """이전 스캔 상태 로드"""
        try:
            if os.path.exists(self.state_file_path):
                with open(self.state_file_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                logging.info(f"스캔 상태 로드됨: {self.state_file_path}")
                return state
        except Exception as e:
            logging.error(f"스캔 상태 로드 중 오류: {str(e)}")
        
        # 기본 상태
        return {"tags_processed": [], "last_tag": None, "last_timestamp": None}
    
    def _save_state(self, tag: str, completed: bool = False) -> None:
        """현재 스캔 상태 저장"""
        try:
            # 완료된 태그 추가
            if completed and tag not in self.scan_state["tags_processed"]:
                self.scan_state["tags_processed"].append(tag)
            
            # 마지막 처리 태그 및 타임스탬프 업데이트
            self.scan_state["last_tag"] = tag
            self.scan_state["last_timestamp"] = datetime.now().isoformat()
            
            with open(self.state_file_path, "w", encoding="utf-8") as f:
                json.dump(self.scan_state, f, ensure_ascii=False, indent=2)
                
            logging.debug(f"스캔 상태 저장됨: {tag} ({'완료' if completed else '진행 중'})")
        except Exception as e:
            logging.error(f"스캔 상태 저장 중 오류: {str(e)}")
    
    def _save_usernames(self, new_usernames: Set[str]) -> None:
        """새 사용자명을 파일에 추가"""
        try:
            # 새로운 사용자만 추가 (차집합)
            usernames_to_add = new_usernames - self.collected_usernames
            
            if not usernames_to_add:
                return
                
            # 파일에 추가
            with open(self.outfile_path, "a", encoding="utf-8") as f:
                for username in usernames_to_add:
                    f.write(f"{username}\n")
            
            # 집합에 추가
            self.collected_usernames.update(usernames_to_add)
            
            logging.info(f"{len(usernames_to_add)}개의 새 사용자명 저장됨 (총 {len(self.collected_usernames)}개)")
        except Exception as e:
            logging.error(f"사용자명 저장 중 오류: {str(e)}")
    
    def _setup_client(self, proxy_manager: Optional[ProxyManager] = None) -> Client:
        """
        인스타그램 클라이언트 설정 및 로그인
        
        Args:
            proxy_manager: 프록시 관리자 (선택 사항)
            
        Returns:
            초기화된 Client 인스턴스
        """
        cl = Client()
        cl.delay_range = [1, 3]  # 초기 딜레이 범위
        
        # 프록시 설정
        if proxy_manager:
            proxy = proxy_manager.get_proxy()
            if proxy:
                cl.set_proxy(proxy)
        
        # 랜덤 User-Agent 설정
        cl.user_agent = random.choice(USER_AGENTS)
        
        # 세션 파일이 있으면 로드
        if os.path.exists(self.session_file):
            try:
                logging.info("세션 파일에서 로그인 시도 중...")
                cl.load_settings(self.session_file)
                cl.get_timeline_feed()  # 세션 유효성 확인
                logging.info("세션 파일로 로그인 성공")
                return cl
            except Exception as e:
                logging.warning(f"세션 파일 로드 실패, 일반 로그인으로 전환: {str(e)}")
        
        # 일반 로그인
        if USERNAME and PASSWORD:
            try:
                logging.info("사용자명/비밀번호로 로그인 시도 중...")
                cl.login(USERNAME, PASSWORD)
                # 세션 저장
                cl.dump_settings(self.session_file)
                logging.info("로그인 성공, 세션 저장됨")
            except Exception as e:
                logging.error(f"로그인 실패: {str(e)}")
        else:
            logging.warning("로그인 정보가 설정되지 않았습니다. 인증되지 않은 상태로 진행합니다.")
        
        return cl
    
    def _scan_hashtag(self, tag: str, amount: int, proxy_manager: ProxyManager) -> Set[str]:
        """
        단일 해시태그 스캔 작업
        
        Args:
            tag: 검색할 해시태그
            amount: 가져올 미디어 수
            proxy_manager: 프록시 관리자
        
        Returns:
            수집된 사용자명 집합
        """
        usernames = set()
        
        # 클라이언트 설정 및 로그인
        cl = self._setup_client(proxy_manager)
        
        # 동적 딜레이 어댑터 설정
        delay_adapter = DynamicDelayAdapter()
        
        try:
            logging.info(f"해시태그 '{tag}' 스캔 시작 (목표: {amount}개)")
            
            try:
                # 최신 미디어 시도
                medias = cl.hashtag_medias_recent(tag, amount=amount)
                logging.info(f"해시태그 '{tag}'에서 최신 미디어 {len(medias)}개 로드됨")
            except (HashtagNotFound, ClientError) as e:
                # 최신 미디어 실패 시 인기 미디어로 폴백
                logging.warning(f"최신 미디어 로드 실패, 인기 미디어로 시도: {str(e)}")
                medias = cl.hashtag_medias_top(tag, amount=min(50, amount))  # 인기는 최대 50개만
                logging.info(f"해시태그 '{tag}'에서 인기 미디어 {len(medias)}개 로드됨")
            
            # 사용자명 추출
            for media in medias:
                username = media.user.username
                if username:
                    usernames.add(username)
            
            logging.info(f"해시태그 '{tag}'에서 {len(usernames)}개의 고유 사용자명 수집됨")
            
        except RateLimitError:
            logging.warning(f"해시태그 '{tag}' 스캔 중 속도 제한 감지")
            time.sleep(60)  # 속도 제한 시 1분 대기
        except Exception as e:
            logging.error(f"해시태그 '{tag}' 스캔 중 오류: {str(e)}")
        
        return usernames
    
    def scan_hashtags(
        self, 
        tags: List[str], 
        amount: int = 100, 
        proxy_manager: Optional[ProxyManager] = None,
        limit: Optional[int] = None
    ) -> Set[str]:
        """
        여러 해시태그 병렬 스캔
        
        Args:
            tags: 스캔할 해시태그 목록
            amount: 태그당 가져올 미디어 수
            proxy_manager: 프록시 관리자 (옵션)
            limit: 수집할 최대 사용자 수 (옵션)
        
        Returns:
            수집된 전체 사용자명 집합
        """
        # 이미 처리된 태그 건너뛰기
        tags_to_process = [tag for tag in tags if tag not in self.scan_state["tags_processed"]]
        
        if not tags_to_process:
            logging.info("모든 태그가 이미 처리되었습니다.")
            return self.collected_usernames
        
        logging.info(f"{len(tags_to_process)}개 태그 스캔 예정: {', '.join(tags_to_process)}")
        
        # 태그당 개별 스레드에서 처리
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(tags_to_process))) as executor:
            future_to_tag = {
                executor.submit(self._scan_hashtag, tag, amount, proxy_manager): tag
                for tag in tags_to_process
            }
            
            for future in as_completed(future_to_tag.keys()):
                tag = future_to_tag[future]
                try:
                    new_usernames = future.result()
                    self._save_usernames(new_usernames)
                    self._save_state(tag, completed=True)
                    
                    # 최대 제한 확인
                    if limit and len(self.collected_usernames) >= limit:
                        logging.info(f"최대 사용자 수 {limit}명에 도달했습니다. 스캔 중단.")
                        break
                        
                except Exception as e:
                    logging.error(f"태그 '{tag}' 작업 실패: {str(e)}")
        
        return self.collected_usernames


def run_tag_scanner(
    tags: List[str],
    amount: int = 100,
    data_dir: str = "data", 
    proxies: List[str] = None,
    max_workers: int = 5,
    limit: Optional[int] = None
) -> None:
    """
    태그 스캐너 실행 함수
    
    Args:
        tags: 스캔할 해시태그 목록
        amount: 태그당 가져올 미디어 수
        data_dir: 데이터 저장 디렉토리
        proxies: 프록시 목록
        max_workers: 병렬 작업할 최대 스레드 수
        limit: 수집할 최대 사용자 수 (옵션)
    """
    # 로깅 설정
    setup_logging(level=logging.INFO)
    
    # 프록시 관리자 초기화
    proxy_manager = ProxyManager(proxies=proxies) if proxies else None
    
    # 스캐너 초기화 및 실행
    scanner = TagScanner(data_dir=data_dir, max_workers=max_workers)
    collected = scanner.scan_hashtags(
        tags=tags,
        amount=amount,
        proxy_manager=proxy_manager,
        limit=limit
    )
    
    logging.info(f"스캔 완료: 총 {len(collected)}개의 사용자명 수집됨") 
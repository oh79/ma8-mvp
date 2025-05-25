#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
디테일 크롤러 모듈 - 사용자 정보 및 게시물 상세 크롤링

이 모듈은 수집된 사용자명을 바탕으로 사용자 프로필 정보와
게시물 상세 정보를 수집하는 기능을 담당합니다.
체크포인트 관리 및 병렬 처리를 지원합니다.
"""

import os
import time
import logging
import random
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import (
    UserNotFound, PrivateAccount, LoginRequired, 
    ClientError, ClientLoginRequired, ClientJSONDecodeError,
    ClientConnectionError, RateLimitError
)

from .db import DatabaseManager
from .proxy_manager import ProxyManager
from .rate_control import DynamicDelayAdapter
from .utils import setup_logging, with_retry, parse_category

# 상수 정의
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 284.0.0.20.117",
    "Mozilla/5.0 (Android 10; Mobile; rv:123.0) Gecko/123.0 Firefox/123.0",
    "Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; 6T; OnePlus6T; qcom; en_US; 314665256)",
    "Mozilla/5.0 (Linux; Android 13; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
]

class DetailCrawler:
    """사용자 세부 정보 및 게시물 크롤러"""
    
    def __init__(
        self,
        data_dir: str = "data",
        input_file: str = "usernames.txt",
        checkpoint_file: str = "checkpoint_crawl.csv",
        save_interval: int = 10,
        db_name: str = "instagram.db"
    ):
        """
        초기화
        
        Args:
            data_dir: 데이터 저장 디렉토리
            input_file: 수집할 사용자명 목록 파일
            checkpoint_file: 처리 완료된 사용자명을 기록할 체크포인트 파일
            save_interval: 중간 저장 간격 (사용자 수)
            db_name: DuckDB 데이터베이스 파일명
        """
        self.data_dir = data_dir
        self.input_file_path = os.path.join(data_dir, input_file)
        self.checkpoint_file_path = os.path.join(data_dir, checkpoint_file)
        self.save_interval = save_interval
        
        # 데이터베이스 매니저 초기화
        self.db_manager = DatabaseManager(data_dir=data_dir, db_name=db_name)
        
        # 수집 데이터 저장소
        self.influencers_info = {}
        self.post_details = []
        
        # 처리된 사용자 집합
        self.processed_users = self._load_checkpoint()
        
        # 저장 디렉토리가 없으면 생성
        os.makedirs(data_dir, exist_ok=True)
    
    def _load_checkpoint(self) -> Set[str]:
        """체크포인트 파일에서 이미 처리된 사용자 목록 로드"""
        processed_users = set()
        
        if os.path.exists(self.checkpoint_file_path):
            try:
                df = pd.read_csv(self.checkpoint_file_path)
                if 'username' in df.columns:
                    processed_users = set(df['username'].values)
                logging.info(f"체크포인트 파일에서 {len(processed_users)}명의 처리된 사용자 로드")
            except Exception as e:
                logging.error(f"체크포인트 로드 오류: {str(e)}")
        
        return processed_users
    
    def _save_checkpoint(self) -> None:
        """체크포인트 파일에 처리된 사용자 목록 저장"""
        if not self.processed_users:
            return
        
        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(self.checkpoint_file_path), exist_ok=True)
        
        # 체크포인트 저장
        df = pd.DataFrame({'username': list(self.processed_users)})
        df.to_csv(self.checkpoint_file_path, index=False)
        logging.info(f"체크포인트 업데이트: 현재까지 {len(self.processed_users)}명 처리")
    
    def _load_target_usernames(self, specific_users: Optional[str] = None) -> List[str]:
        """
        처리할 사용자명 목록 로드
        
        Args:
            specific_users: 쉼표로 구분된 특정 사용자명 (옵션)
        
        Returns:
            처리할 사용자명 목록
        """
        # 특정 사용자가 지정된 경우
        if specific_users:
            usernames = [u.strip() for u in specific_users.split(',')]
            logging.info(f"특정 사용자 {len(usernames)}명 로드")
            return usernames
        
        # 파일에서 로드
        if os.path.exists(self.input_file_path):
            try:
                with open(self.input_file_path, 'r', encoding='utf-8') as f:
                    usernames = [line.strip() for line in f if line.strip()]
                logging.info(f"입력 파일에서 {len(usernames)}명의 사용자 로드")
                
                # 이미 처리된 사용자 제외
                usernames_to_process = [u for u in usernames if u not in self.processed_users]
                logging.info(f"처리할 사용자 {len(usernames_to_process)}명 (이미 처리된 {len(usernames) - len(usernames_to_process)}명 제외)")
                
                return usernames_to_process
            except Exception as e:
                logging.error(f"사용자명 로드 오류: {str(e)}")
        else:
            logging.error(f"입력 파일을 찾을 수 없음: {self.input_file_path}")
        
        return []
    
    def _save_data(self, is_temp: bool = False) -> None:
        """
        수집된 데이터 저장
        
        Args:
            is_temp: 임시 저장 여부
        """
        # 데이터베이스에 저장
        self.db_manager.save_data_to_csv(
            self.influencers_info,
            self.post_details,
            is_temp=is_temp
        )
        
        # 체크포인트 저장
        if not is_temp:
            self._save_checkpoint()
    
    @with_retry(max_retries=3)
    def _fetch_user_info(self, cl: Client, username: str) -> Optional[Dict[str, Any]]:
        """
        사용자 정보 조회
        
        Args:
            cl: 인스타그램 클라이언트
            username: 사용자명
        
        Returns:
            사용자 정보 딕셔너리 또는 None
        """
        try:
            user_info = cl.user_info_by_username(username)
            
            # 딕셔너리로 변환
            user_dict = user_info.dict()
            
            # 카테고리 파싱
            if "biography" in user_dict:
                user_dict["category"] = parse_category(user_dict.get("biography", ""))
            
            return user_dict
        except UserNotFound:
            logging.warning(f"사용자를 찾을 수 없음: {username}")
            return None
        except PrivateAccount:
            logging.warning(f"비공개 계정: {username}")
            
            # 비공개 계정은 기본 정보만 저장
            return {
                "username": username,
                "is_private": True,
                "pk": 0,
                "follower_count": 0,
                "following_count": 0,
                "media_count": 0
            }
        except Exception as e:
            logging.error(f"사용자 정보 조회 오류: {username} - {str(e)}")
            raise
    
    @with_retry(max_retries=3)
    def _fetch_user_medias(self, cl: Client, user_info: Dict[str, Any], amount: int = 10) -> List[Dict[str, Any]]:
        """
        사용자 게시물 목록 조회
        
        Args:
            cl: 인스타그램 클라이언트
            user_info: 사용자 정보
            amount: 가져올 게시물 수
        
        Returns:
            게시물 정보 목록
        """
        posts = []
        
        # 비공개 계정이면 스킵
        if user_info.get("is_private", False):
            return posts
            
        try:
            username = user_info.get("username")
            pk = user_info.get("pk")
            
            # 게시물 수가 0이면 스킵
            if user_info.get("media_count", 0) == 0:
                return posts
                
            # 게시물 조회
            medias = cl.user_medias(pk, amount=amount)
            
            for media in medias:
                # 딕셔너리로 변환
                media_dict = media.dict()
                
                # 추가 필드
                media_dict["user_pk"] = pk
                media_dict["username"] = username
                
                # 필요한 필드만 추출
                post = {
                    "id": media_dict.get("id", ""),
                    "user_pk": pk,
                    "username": username,
                    "caption": media_dict.get("caption_text", ""),
                    "like_count": media_dict.get("like_count", 0),
                    "comment_count": media_dict.get("comment_count", 0),
                    "taken_at": media_dict.get("taken_at", datetime.now()),
                    "media_type": media_dict.get("media_type", 0),
                    "product_type": media_dict.get("product_type", ""),
                    "image_url": str(media_dict.get("thumbnail_url", "")),
                    "video_url": str(media_dict.get("video_url", ""))
                }
                
                posts.append(post)
            
            return posts
        except Exception as e:
            logging.error(f"게시물 조회 오류: {user_info.get('username')} - {str(e)}")
            raise
    
    def _fetch_user_detail(
        self, 
        username: str, 
        proxy_manager: Optional[ProxyManager] = None,
        amount: int = 10
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        사용자 세부 정보 및 게시물 수집
        
        Args:
            username: 사용자명
            proxy_manager: 프록시 관리자
            amount: 가져올 게시물 수
        
        Returns:
            (사용자 정보, 게시물 목록) 튜플
        """
        # 클라이언트 초기화
        cl = Client()
        
        # 프록시 설정
        if proxy_manager:
            proxy = proxy_manager.get_proxy()
            if proxy:
                cl.set_proxy(proxy)
        
        # 동적 딜레이 어댑터 설정
        delay_adapter = DynamicDelayAdapter()
        cl.delay_adapter = delay_adapter
        cl.delay_range = delay_adapter.get_delay_range()
        
        # 랜덤 User-Agent 설정
        cl.user_agent = random.choice(USER_AGENTS)
        
        try:
            # 사용자 정보 조회
            user_info = self._fetch_user_info(cl, username)
            
            if not user_info:
                return None, []
                
            # 게시물 조회
            posts = []
            if not user_info.get("is_private", False):
                posts = self._fetch_user_medias(cl, user_info, amount)
                
            return user_info, posts
        except Exception as e:
            logging.error(f"사용자 세부 정보 수집 오류: {username} - {str(e)}")
            return None, []
        finally:
            # 클라이언트 종료
            cl.close()
    
    def crawl_users(
        self, 
        specific_users: Optional[str] = None,
        proxy_manager: Optional[ProxyManager] = None,
        max_workers: int = 5,
        posts_per_user: int = 10,
        max_users: Optional[int] = None,
        dry_run: bool = False
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        사용자 크롤링 실행
        
        Args:
            specific_users: 쉼표로 구분된 특정 사용자명 (옵션)
            proxy_manager: 프록시 관리자
            max_workers: 병렬 작업할 최대 스레드 수
            posts_per_user: 사용자당 수집할 게시물 수
            max_users: 최대 처리할 사용자 수
            dry_run: 테스트 실행 여부 (소량만 처리)
        
        Returns:
            (인플루언서 정보, 게시물 목록) 튜플
        """
        # 처리할 사용자 목록 로드
        usernames = self._load_target_usernames(specific_users)
        
        if not usernames:
            logging.warning("처리할 사용자가 없습니다.")
            return self.influencers_info, self.post_details
        
        # 최대 사용자 수 적용
        if max_users and len(usernames) > max_users:
            usernames = usernames[:max_users]
            logging.info(f"최대 {max_users}명으로 제한됨")
        
        # 테스트 실행인 경우 처음 몇 명만 처리
        if dry_run:
            test_count = min(3, len(usernames))
            usernames = usernames[:test_count]
            logging.info(f"테스트 실행: 처음 {test_count}명만 처리")
        
        logging.info(f"총 {len(usernames)}명 크롤링 시작")
        start_time = time.time()
        processed_count = 0
        
        # 병렬 처리
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_username = {
                executor.submit(
                    self._fetch_user_detail, 
                    username, 
                    proxy_manager,
                    posts_per_user
                ): username
                for username in usernames
            }
            
            for future in as_completed(future_to_username):
                username = future_to_username[future]
                try:
                    user_info, posts = future.result()
                    
                    # 사용자 정보가 있으면 저장
                    if user_info:
                        self.influencers_info[username] = user_info
                        self.post_details.extend(posts)
                        
                        # 처리 완료 표시
                        self.processed_users.add(username)
                        processed_count += 1
                        
                        # 진행 상황 로깅
                        elapsed = time.time() - start_time
                        per_user = elapsed / processed_count if processed_count > 0 else 0
                        remaining = len(usernames) - processed_count
                        eta = per_user * remaining
                        
                        logging.info(
                            f"[{processed_count}/{len(usernames)}] {username} 완료 "
                            f"(게시물: {len(posts)}개, "
                            f"경과: {elapsed:.1f}초, "
                            f"남은 시간: {eta:.1f}초)"
                        )
                        
                        # 중간 저장
                        if processed_count % self.save_interval == 0:
                            self._save_data()
                    
                except Exception as e:
                    logging.error(f"사용자 {username} 처리 중 오류: {str(e)}")
        
        # 최종 저장
        self._save_data()
        
        # 완료 로깅
        total_time = time.time() - start_time
        logging.info(
            f"크롤링 완료: {processed_count}명 처리됨, "
            f"게시물 {len(self.post_details)}개 수집, "
            f"총 소요 시간: {total_time:.1f}초"
        )
        
        return self.influencers_info, self.post_details


def run_detail_crawler(
    data_dir: str = "data",
    specific_users: Optional[str] = None,
    proxies: List[str] = None,
    max_workers: int = 5,
    posts_per_user: int = 10,
    max_users: Optional[int] = None,
    dry_run: bool = False
) -> None:
    """
    디테일 크롤러 실행 함수
    
    Args:
        data_dir: 데이터 저장 디렉토리
        specific_users: 쉼표로 구분된 특정 사용자명 (옵션)
        proxies: 프록시 목록
        max_workers: 병렬 작업할 최대 스레드 수
        posts_per_user: 사용자당 수집할 게시물 수
        max_users: 최대 처리할 사용자 수
        dry_run: 테스트 실행 여부 (소량만 처리)
    """
    # 로깅 설정
    setup_logging(level=logging.INFO)
    
    # 프록시 관리자 초기화
    proxy_manager = ProxyManager(proxies=proxies) if proxies else None
    
    # 크롤러 초기화 및 실행
    crawler = DetailCrawler(data_dir=data_dir)
    crawler.crawl_users(
        specific_users=specific_users,
        proxy_manager=proxy_manager,
        max_workers=max_workers,
        posts_per_user=posts_per_user,
        max_users=max_users,
        dry_run=dry_run
    ) 
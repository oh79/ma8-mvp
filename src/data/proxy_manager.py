#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
프록시 관리 모듈 - 다중 프록시 관리 및 자동 전환

이 모듈은 여러 프록시를 관리하고 실패에 따라 자동으로 다른 프록시로
전환하는 기능을 제공합니다. 프록시의 상태를 모니터링하고 최적의
프록시를 선택합니다.
"""

import time
import logging
import random
import threading
from typing import List, Dict, Optional, Tuple, Any

class ProxyManager:
    """다중 프록시 관리 및 자동 전환 매니저"""
    
    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        max_failures: int = 5,
        cooldown_period: int = 300
    ):
        """
        초기화
        
        Args:
            proxies: 프록시 URL 목록 (http://user:pass@host:port 형식)
            max_failures: 프록시당 최대 실패 허용 횟수
            cooldown_period: 실패한 프록시 재사용 전 대기 시간 (초)
        """
        self.proxies = proxies or []
        self.max_failures = max_failures
        self.cooldown_period = cooldown_period
        
        # 프록시가 없으면 직접 연결을 의미하는 빈 문자열 추가
        if not self.proxies:
            self.proxies = [""]
        
        # 프록시별 상태 추적
        self.failures = {proxy: 0 for proxy in self.proxies}
        self.last_used = {proxy: 0 for proxy in self.proxies}
        self.last_failure = {proxy: 0 for proxy in self.proxies}
        self.success_rates = {proxy: 1.0 for proxy in self.proxies}  # 초기값은 100%
        self.total_requests = {proxy: 0 for proxy in self.proxies}
        self.successful_requests = {proxy: 0 for proxy in self.proxies}
        
        # 현재 사용 중인 프록시 인덱스
        self.current_index = 0
        
        # 연속 실패 카운터
        self.consecutive_failures = 0
        
        # 마지막 프록시 전환 시간
        self.last_proxy_switch = time.time()
        
        # 스레드 안전을 위한 락
        self.lock = threading.RLock()
        
        # 프록시 목록 로깅
        proxy_count = len(self.proxies)
        if proxy_count <= 1:
            logging.info("프록시 없음, 직접 연결 사용")
        else:
            logging.info(f"{proxy_count}개 프록시 로드됨")
    
    def get_proxy(self) -> Optional[str]:
        """
        현재 사용할 프록시 반환
        
        Returns:
            프록시 URL 또는 None (직접 연결)
        """
        with self.lock:
            # 프록시가 없으면 None 반환 (직접 연결)
            if not self.proxies or len(self.proxies) == 0:
                return None
            
            # 현재 프록시
            current_proxy = self.proxies[self.current_index]
            
            # 직접 연결이면 빈 문자열 대신 None 반환
            if current_proxy == "":
                return None
                
            # 모든 프록시가 너무 많이 실패했는지 확인
            all_failed = True
            for proxy, failures in self.failures.items():
                # 특정 시간이 지났으면 실패 카운트 리셋
                if failures >= self.max_failures:
                    if time.time() - self.last_failure.get(proxy, 0) > self.cooldown_period:
                        self.failures[proxy] = 0
                        logging.info(f"프록시 쿨다운 완료: {self._mask_proxy(proxy)}")
                        all_failed = False
                else:
                    all_failed = False
            
            # 모든 프록시가 실패했으면 랜덤 선택으로 초기화
            if all_failed:
                self._reset_all_proxies()
                
            # 현재 프록시 업데이트
            self.last_used[current_proxy] = time.time()
            
            return current_proxy
    
    def _reset_all_proxies(self) -> None:
        """모든 프록시 상태 리셋"""
        logging.warning("모든 프록시가 실패 상태입니다. 상태 초기화 중...")
        for proxy in self.proxies:
            self.failures[proxy] = 0
        
        # 랜덤한 프록시로 전환
        self.current_index = random.randint(0, len(self.proxies) - 1)
        logging.info(f"랜덤 프록시로 전환: {self._mask_proxy(self.proxies[self.current_index])}")
        
        # 대기
        time.sleep(2)
    
    def report_failure(self, proxy: Optional[str] = None) -> None:
        """
        프록시 실패 보고
        
        Args:
            proxy: 실패한 프록시 URL (None이면 현재 프록시)
        """
        with self.lock:
            # proxy가 None이면 현재 프록시 사용
            if proxy is None and self.proxies:
                proxy = self.proxies[self.current_index]
            
            # 직접 연결이면 빈 문자열로 표준화
            if proxy is None:
                proxy = ""
                
            if proxy in self.failures:
                self.failures[proxy] += 1
                self.last_failure[proxy] = time.time()
                self.total_requests[proxy] = self.total_requests.get(proxy, 0) + 1
                
                # 성공률 갱신
                successful = self.successful_requests.get(proxy, 0)
                total = self.total_requests.get(proxy, 0)
                self.success_rates[proxy] = successful / total if total > 0 else 0
                
                logging.debug(
                    f"프록시 실패: {self._mask_proxy(proxy)} "
                    f"(실패 횟수: {self.failures[proxy]}/{self.max_failures}, "
                    f"성공률: {self.success_rates[proxy]:.1%})"
                )
            
            # 연속 실패 카운터 증가
            self.consecutive_failures += 1
            
            # 현재 프록시 실패 횟수가 임계값을 초과하면 프록시 전환
            if (proxy in self.failures and self.failures[proxy] >= self.max_failures) or \
               self.consecutive_failures >= 3:
                self.switch_proxy("과도한 실패")
                self.consecutive_failures = 0
    
    def report_success(self, proxy: Optional[str] = None) -> None:
        """
        프록시 성공 보고
        
        Args:
            proxy: 성공한 프록시 URL (None이면 현재 프록시)
        """
        with self.lock:
            # 연속 실패 카운터 리셋
            self.consecutive_failures = 0
            
            # proxy가 None이면 현재 프록시 사용
            if proxy is None and self.proxies:
                proxy = self.proxies[self.current_index]
            
            # 직접 연결이면 빈 문자열로 표준화
            if proxy is None:
                proxy = ""
                
            if proxy in self.successful_requests:
                self.successful_requests[proxy] = self.successful_requests.get(proxy, 0) + 1
                self.total_requests[proxy] = self.total_requests.get(proxy, 0) + 1
                
                # 성공률 갱신
                successful = self.successful_requests.get(proxy, 0)
                total = self.total_requests.get(proxy, 0)
                self.success_rates[proxy] = successful / total if total > 0 else 0
    
    def switch_proxy(self, reason: str = "수동 전환") -> str:
        """
        다음 프록시로 전환
        
        Args:
            reason: 전환 이유
            
        Returns:
            새로 선택된 프록시 URL
        """
        with self.lock:
            # 프록시가 없거나 하나뿐이면 전환하지 않음
            if not self.proxies or len(self.proxies) <= 1:
                return self.proxies[0] if self.proxies else ""
                
            # 프록시 전환 속도 제한 (10초에 한 번만)
            current_time = time.time()
            if current_time - self.last_proxy_switch < 10:
                return self.proxies[self.current_index]
                
            # 이전 프록시 기록
            old_index = self.current_index
            old_proxy = self.proxies[old_index]
            
            # 가장 성공률이 높은 프록시 찾기
            best_proxy_index = None
            best_success_rate = -1
            
            for i, proxy in enumerate(self.proxies):
                # 현재 프록시는 제외
                if i == old_index:
                    continue
                    
                # 실패 횟수가 최대를 넘은 프록시는 제외
                if self.failures.get(proxy, 0) >= self.max_failures:
                    # 단, 쿨다운 시간이 지났으면 재사용 가능
                    if time.time() - self.last_failure.get(proxy, 0) > self.cooldown_period:
                        self.failures[proxy] = 0
                    else:
                        continue
                
                # 성공률 비교
                success_rate = self.success_rates.get(proxy, 1.0)
                if success_rate > best_success_rate:
                    best_success_rate = success_rate
                    best_proxy_index = i
            
            # 적절한 프록시가 없으면 랜덤 선택 (현재 제외)
            if best_proxy_index is None:
                available_indices = [i for i in range(len(self.proxies)) if i != old_index 
                                    and self.failures.get(self.proxies[i], 0) < self.max_failures]
                
                if available_indices:
                    best_proxy_index = random.choice(available_indices)
                else:
                    # 모든 프록시가 실패 상태면 랜덤하게 하나 선택하고 초기화
                    best_proxy_index = random.randint(0, len(self.proxies) - 1)
                    if best_proxy_index == old_index:
                        best_proxy_index = (best_proxy_index + 1) % len(self.proxies)
                    self.failures[self.proxies[best_proxy_index]] = 0
            
            # 새 프록시 설정
            self.current_index = best_proxy_index
            new_proxy = self.proxies[self.current_index]
            
            logging.info(
                f"프록시 전환: {self._mask_proxy(old_proxy)} -> "
                f"{self._mask_proxy(new_proxy)} (이유: {reason})"
            )
            
            self.last_proxy_switch = current_time
            
            # 잠시 대기하여 API 속도 제한 회피
            time.sleep(2)
            
            return new_proxy
    
    def _mask_proxy(self, proxy: str) -> str:
        """
        로깅용 프록시 URL 마스킹
        
        Args:
            proxy: 원본 프록시 URL
            
        Returns:
            마스킹된 프록시 URL
        """
        if not proxy:
            return "직접 연결"
            
        try:
            # http://user:pass@host:port 형식 마스킹
            if "@" in proxy:
                protocol_part, address_part = proxy.split("@", 1)
                host_port = address_part.split(":", 1)[0]
                return f"***@{host_port}"
            else:
                return proxy.split(":", 1)[0] + ":***"
        except:
            return "***"
    
    def get_stats(self) -> Dict[str, Any]:
        """
        프록시 사용 통계
        
        Returns:
            통계 정보 딕셔너리
        """
        with self.lock:
            stats = {
                "proxy_count": len(self.proxies),
                "current_proxy": self._mask_proxy(self.proxies[self.current_index]) if self.proxies else "없음",
                "consecutive_failures": self.consecutive_failures,
                "proxies": {}
            }
            
            for proxy in self.proxies:
                masked_proxy = self._mask_proxy(proxy)
                stats["proxies"][masked_proxy] = {
                    "failures": self.failures.get(proxy, 0),
                    "success_rate": self.success_rates.get(proxy, 0),
                    "total_requests": self.total_requests.get(proxy, 0),
                    "last_used": time.time() - self.last_used.get(proxy, 0),
                    "last_failure": time.time() - self.last_failure.get(proxy, 0) if self.last_failure.get(proxy, 0) else None
                }
            
            return stats 
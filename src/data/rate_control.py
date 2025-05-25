#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
요청 속도 제어 모듈 - 동적 딜레이 조정 및 속도 제한 관리

이 모듈은 API 응답 시간에 기반하여 요청 딜레이를 동적으로 조정하고
429 오류 등의 속도 제한을 관리하는 기능을 제공합니다.
"""

import time
import logging
import random
from typing import List, Tuple, Dict, Any, Optional
from statistics import mean, median

class DynamicDelayAdapter:
    """API 응답 시간에 기반한 동적 딜레이 조정 어댑터"""
    
    def __init__(
        self, 
        base_low: float = 1.0, 
        base_high: float = 3.0, 
        window_size: int = 10,
        max_delay: float = 10.0
    ):
        """
        초기화
        
        Args:
            base_low: 기본 최소 딜레이 (초)
            base_high: 기본 최대 딜레이 (초)
            window_size: 응답 시간 히스토리 윈도우 크기
            max_delay: 최대 딜레이 제한 (초)
        """
        self.base_low = base_low
        self.base_high = base_high
        self.window_size = window_size
        self.max_delay = max_delay
        self.rtt_history = []  # 응답 시간 히스토리 (ms)
        self.failures = 0  # 연속 실패 카운터
        self.rate_limit_hits = 0  # 속도 제한 발생 횟수
        self.last_delay_adjust = time.time()  # 마지막 딜레이 조정 시간
    
    def add_rtt(self, rtt_ms: float) -> None:
        """
        응답 시간 기록
        
        Args:
            rtt_ms: API 응답 시간 (밀리초)
        """
        self.rtt_history.append(rtt_ms)
        
        # 윈도우 크기 유지
        if len(self.rtt_history) > self.window_size:
            self.rtt_history.pop(0)
    
    def report_failure(self, is_rate_limit: bool = False) -> None:
        """
        요청 실패 보고
        
        Args:
            is_rate_limit: 속도 제한 오류 여부
        """
        self.failures += 1
        
        if is_rate_limit:
            self.rate_limit_hits += 1
            logging.warning(f"속도 제한 감지 (총 {self.rate_limit_hits}회)")
    
    def report_success(self) -> None:
        """요청 성공 보고"""
        # 성공 시 실패 카운터 감소
        self.failures = max(0, self.failures - 1)
    
    def get_retry_delay(self, attempt: int) -> float:
        """
        재시도 딜레이 계산
        
        Args:
            attempt: 재시도 횟수 (1부터 시작)
            
        Returns:
            딜레이 시간 (초)
        """
        # 속도 제한 발생 시 더 긴 대기 시간
        if self.rate_limit_hits > 0:
            # 속도 제한이 여러 번 발생했을 경우 지수적으로 대기 시간 증가
            base_delay = 60 * min(5, self.rate_limit_hits)
            jitter = random.uniform(0, 10)
            return base_delay + jitter
        
        # 일반적인 재시도는 지수 백오프 적용
        base_delay = 5.0  # 초기 대기 시간 (초)
        max_delay = 120.0  # 최대 대기 시간 (초)
        
        # 지수 백오프: 기본 대기 시간 * 2^(재시도 횟수-1) * 무작위 요소
        delay = base_delay * (2 ** (attempt - 1)) * (0.5 + random.random())
        
        # 최대 대기 시간 제한
        return min(delay, max_delay)
    
    def get_delay_range(self) -> List[float]:
        """
        현재 상황에 기반한 딜레이 범위 계산
        
        Returns:
            [최소 딜레이, 최대 딜레이] (초)
        """
        # 히스토리가 없으면 기본값 반환
        if not self.rtt_history:
            return [self.base_low, self.base_high]
        
        # 현재 평균 응답 시간 (밀리초)
        avg_rtt = mean(self.rtt_history)
        
        # 딜레이 스케일링 팩터 계산
        # 1. 응답 시간에 따라 증가 (RTT가 길수록 딜레이도 길게)
        # 2. 실패 횟수에 따라 증가 (실패가 많을수록 딜레이도 길게)
        # 3. 속도 제한 발생 횟수에 따라 증가
        base_factor = 1.0
        failure_factor = 1.0 + (0.2 * self.failures)  # 실패당 20% 증가
        rate_limit_factor = 1.0 + (0.5 * self.rate_limit_hits)  # 속도 제한당 50% 증가
        
        # 최종 스케일링 팩터
        factor = base_factor * failure_factor * rate_limit_factor
        
        # RTT를 초 단위로 변환하고 스케일링
        low = self.base_low + (avg_rtt * 0.5 * factor) / 1000
        high = self.base_high + (avg_rtt * 1.0 * factor) / 1000
        
        # 최대 딜레이 제한
        low = min(low, self.max_delay * 0.5)
        high = min(high, self.max_delay)
        
        # 최소값이 최대값보다 크면 조정
        if low > high:
            low, high = high * 0.5, high
        
        logging.debug(
            f"딜레이 조정: [{low:.2f}, {high:.2f}] "
            f"(avg_rtt={avg_rtt:.0f}ms, 실패={self.failures}, 속도제한={self.rate_limit_hits})"
        )
        
        return [low, high]
    
    def should_pause(self) -> Tuple[bool, float]:
        """
        요청 일시 중지 여부 및 시간 결정
        
        Returns:
            (일시 중지 여부, 중지 시간)
        """
        # 속도 제한이 많이 발생한 경우 일시 중지
        if self.rate_limit_hits >= 3:
            pause_time = 300.0  # 5분
            
            # 마지막 조정 후 일정 시간이 지났으면 중지
            if time.time() - self.last_delay_adjust > 600:  # 10분
                self.last_delay_adjust = time.time()
                logging.warning(f"속도 제한 다수 발생: {pause_time}초 일시 중지")
                return True, pause_time
        
        # 연속 실패가 많은 경우 짧게 일시 중지
        if self.failures >= 5:
            pause_time = 60.0  # 1분
            
            # 마지막 조정 후 일정 시간이 지났으면 중지
            if time.time() - self.last_delay_adjust > 300:  # 5분
                self.last_delay_adjust = time.time()
                logging.warning(f"연속 실패 다수 발생: {pause_time}초 일시 중지")
                return True, pause_time
        
        return False, 0.0
    
    def reset_rate_limits(self) -> None:
        """속도 제한 카운터 리셋"""
        if self.rate_limit_hits > 0:
            logging.info(f"속도 제한 카운터 리셋 (이전: {self.rate_limit_hits})")
            self.rate_limit_hits = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        현재 상태 통계
        
        Returns:
            통계 정보 딕셔너리
        """
        stats = {
            "rtt_avg": mean(self.rtt_history) if self.rtt_history else 0,
            "rtt_median": median(self.rtt_history) if self.rtt_history else 0,
            "failures": self.failures,
            "rate_limit_hits": self.rate_limit_hits,
            "delay_range": self.get_delay_range(),
            "samples": len(self.rtt_history)
        }
        
        return stats 
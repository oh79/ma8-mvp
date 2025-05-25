import os
import yaml
import json
import logging
from typing import Dict, List, Any, Optional

# 기본 설정값
DEFAULT_CONFIG = {
    "save_interval": 10,
    "proxy_switch_threshold": 3,
    "rate_limit_cooldown": 60,
    "max_proxy_failures": 5,
    "num_posts_to_fetch": 10,
    "max_workers": 5,
    "proxies": [],
    "log_level": "INFO",
    "user_agents": [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 284.0.0.20.117",
        "Mozilla/5.0 (Android 10; Mobile; rv:123.0) Gecko/123.0 Firefox/123.0",
        "Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; 6T; OnePlus6T; qcom; en_US; 314665256)",
        "Mozilla/5.0 (Linux; Android 13; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
    ],
    "target_hashtags": [
        "렌즈", 
        "콘택트렌즈", 
        "컬러렌즈", 
        "소프트렌즈", 
        "contactlens", 
        "colorlens", 
        "lens", 
        "softlens"
    ]
}

class Config:
    """애플리케이션 설정 관리"""
    
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()
    
    def load_config(self) -> bool:
        """YAML 설정 파일에서 설정 로드"""
        if not os.path.exists(self.config_path):
            logging.warning(f"설정 파일 {self.config_path}를 찾을 수 없습니다. 기본값 사용.")
            return False
            
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = yaml.safe_load(f)
            
            if loaded_config:
                # 기존 기본값에 로드된 설정 병합
                self.config.update(loaded_config)
                logging.info(f"설정 파일 {self.config_path}에서 설정 로드 완료")
                return True
        except Exception as e:
            logging.error(f"설정 파일 {self.config_path} 로드 중 오류: {str(e)}")
            return False
    
    def save_config(self) -> bool:
        """현재 설정을 YAML 파일로 저장"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            logging.info(f"설정 저장 완료: {self.config_path}")
            return True
        except Exception as e:
            logging.error(f"설정 저장 중 오류: {str(e)}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """설정값 가져오기"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """설정값 설정하기"""
        self.config[key] = value
    
    def load_proxies_from_env(self) -> List[str]:
        """환경 변수에서 프록시 목록 로드"""
        proxies = []
        env_proxies = os.getenv('PROXIES')
        
        if env_proxies:
            try:
                proxies = json.loads(env_proxies)
                logging.info(f"환경 변수에서 {len(proxies)}개 프록시 로드됨")
            except Exception as e:
                logging.warning(f"환경 변수에서 프록시 로드 실패: {str(e)}")
        
        # 설정에 병합
        if proxies:
            self.config['proxies'] = proxies
        
        return proxies
    
    def create_default_config(self) -> bool:
        """기본 설정 파일 생성"""
        # 이미 파일이 있으면 덮어쓰지 않음
        if os.path.exists(self.config_path):
            logging.warning(f"설정 파일 {self.config_path}가 이미 존재합니다.")
            return False
            
        return self.save_config()
        
    @property
    def proxies(self) -> List[str]:
        return self.config.get('proxies', [])
    
    @property
    def user_agents(self) -> List[str]:
        return self.config.get('user_agents', [])
    
    @property
    def save_interval(self) -> int:
        return self.config.get('save_interval', 10)
    
    @property
    def proxy_switch_threshold(self) -> int:
        return self.config.get('proxy_switch_threshold', 3)
    
    @property
    def rate_limit_cooldown(self) -> int:
        return self.config.get('rate_limit_cooldown', 60)
    
    @property
    def max_proxy_failures(self) -> int:
        return self.config.get('max_proxy_failures', 5)
    
    @property
    def num_posts_to_fetch(self) -> int:
        return self.config.get('num_posts_to_fetch', 10)
    
    @property
    def max_workers(self) -> int:
        return self.config.get('max_workers', 5)
    
    @property
    def target_hashtags(self) -> List[str]:
        return self.config.get('target_hashtags', [])

# 기본 설정 생성 예시
def create_sample_config(path="config.yaml"):
    """샘플 설정 파일 생성"""
    config = Config(path)
    config.create_default_config()
    return config 
import yaml
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f)
                logger.info(f"Loaded config from: {self.config_path}")
            else:
                logger.warning(f"Config file not found: {self.config_path}, using defaults")
                self.config = self._get_default_config()
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        return {
            'window': {
                'title_keywords': ['梦幻西游'],
                'class_names': ['UnityWndClass'],
                'blacklist_title_keywords': ['Visual Studio', 'PyCharm', 'VS Code', 'cmd', 'powershell'],
                'blacklist_class_names': ['Qt5QWindowIcon', 'Qt5QWindow', 'Chrome_WidgetWin_1', 'MozillaWindowClass']
            },
            'vision': {
                'template_dir': 'templates',
                'use_paddle_ocr': True,
                'ocr_lang': 'ch',
                'yolo_model_path': None,
                'template_match_threshold': 0.8,
                'ocr_confidence_threshold': 0.6,
                'yolo_confidence_threshold': 0.5
            },
            'state_machine': {
                'state_timeout': 30.0,
                'max_no_match_count': 10
            },
            'agent': {
                'update_interval': 0.5,
                'window_check_interval': 10
            },
            'logging': {
                'level': 'INFO',
                'file_path': 'game_agent.log'
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def get_window_config(self) -> Dict[str, Any]:
        return self.config.get('window', {})
    
    def get_vision_config(self) -> Dict[str, Any]:
        return self.config.get('vision', {})
    
    def get_state_machine_config(self) -> Dict[str, Any]:
        return self.config.get('state_machine', {})
    
    def get_agent_config(self) -> Dict[str, Any]:
        return self.config.get('agent', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        return self.config.get('logging', {})
    
    def reload(self):
        self._load_config()
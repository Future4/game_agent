import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.orchestrator import AgentOrchestrator
from application.controller import AutomationController
from client.app import DesktopClient
from config.loader import ConfigLoader
from tasks.registry import TaskRegistry

def setup_logging(config):
    log_config = config.get_logging_config()
    level = getattr(logging, log_config.get('level', 'INFO').upper(), logging.INFO)
    file_path = log_config.get('file_path', 'game_agent.log')
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(file_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def build_controller(config):
    window_config = config.get_window_config()
    vision_config = config.get_vision_config()
    orchestrator = AgentOrchestrator(
        target_title_keywords=window_config.get('title_keywords', ['梦幻西游']),
        target_class_names=window_config.get('class_names', ['UnityWndClass']),
        template_dir=vision_config.get('template_dir', 'templates'),
        blacklist_title_keywords=window_config.get('blacklist_title_keywords', []) + ['梦幻西游自动化助手'],
        blacklist_class_names=window_config.get('blacklist_class_names', []),
    )
    registry = TaskRegistry()
    registry.register_builtins()
    return AutomationController(orchestrator, registry)

def main():
    config = ConfigLoader()
    setup_logging(config)
    
    logger = logging.getLogger(__name__)
    logger.info("启动自动化客户端...")
    DesktopClient(build_controller(config)).run()

if __name__ == "__main__":
    main()

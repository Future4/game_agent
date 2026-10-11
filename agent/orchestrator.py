import time
import logging
from typing import Dict, List, Optional
from core.window_manager import WindowManager, WindowInfo
from agent.game_agent import GameAgent

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    def __init__(self, target_title_keywords: Optional[List[str]] = None,
                 target_class_names: Optional[List[str]] = None,
                 template_dir: str = "templates",
                 blacklist_title_keywords: Optional[List[str]] = None,
                 blacklist_class_names: Optional[List[str]] = None):
        self.window_manager = WindowManager(
            target_title_keywords=target_title_keywords,
            target_class_names=target_class_names,
            blacklist_title_keywords=blacklist_title_keywords,
            blacklist_class_names=blacklist_class_names,
        )
        self.template_dir = template_dir
        self.agents: Dict[int, GameAgent] = {}
        self._is_running = False
    
    def discover_windows(self) -> List[WindowInfo]:
        return self.window_manager.find_windows()
    
    def create_agent(self, window_info: WindowInfo) -> GameAgent:
        agent = GameAgent(window_info, template_dir=self.template_dir)
        self.agents[window_info.hwnd] = agent
        logger.info(f"Created agent for window: {window_info.hwnd} - {window_info.title}")
        return agent
    
    def create_agents_for_all_windows(self) -> List[GameAgent]:
        windows = self.discover_windows()
        agents = []
        
        for window in windows:
            if window.hwnd not in self.agents:
                agent = self.create_agent(window)
                agents.append(agent)
        
        logger.info(f"Created {len(agents)} agents")
        return agents
    
    def get_agent(self, hwnd: int) -> Optional[GameAgent]:
        return self.agents.get(hwnd)
    
    def remove_agent(self, hwnd: int) -> bool:
        agent = self.agents.pop(hwnd, None)
        if agent:
            agent.stop()
            logger.info(f"Removed agent for window: {hwnd}")
            return True
        return False
    
    def start_all_agents(self):
        for agent in self.agents.values():
            agent.start()
        self._is_running = True
        logger.info(f"Started {len(self.agents)} agents")
    
    def stop_all_agents(self):
        for agent in self.agents.values():
            agent.stop()
        self._is_running = False
        logger.info("Stopped all agents")
    
    def update_agents(self):
        current_windows = set(w.hwnd for w in self.discover_windows())
        existing_hwnds = set(self.agents.keys())
        
        new_windows = current_windows - existing_hwnds
        closed_windows = existing_hwnds - current_windows
        
        for hwnd in closed_windows:
            self.remove_agent(hwnd)
        
        for hwnd in new_windows:
            window_info = self.window_manager.get_window_by_hwnd(hwnd)
            if window_info:
                self.create_agent(window_info)
        
        return len(new_windows), len(closed_windows)
    
    def get_active_agents(self) -> List[GameAgent]:
        return [agent for agent in self.agents.values() if agent.is_running()]
    
    def run(self, update_interval: int = 10):
        self._is_running = True
        logger.info("Orchestrator started")
        
        while self._is_running:
            try:
                new_count, closed_count = self.update_agents()
                if new_count > 0:
                    for agent in self.get_active_agents():
                        if not agent.is_running():
                            agent.start()
                
                time.sleep(update_interval)
                
            except KeyboardInterrupt:
                logger.info("Received interrupt, stopping...")
                self.stop_all_agents()
                break
            except Exception as e:
                logger.error(f"Orchestrator error: {e}")
                time.sleep(5)
        
        logger.info("Orchestrator stopped")
    
    def stop(self):
        self._is_running = False
        self.stop_all_agents()

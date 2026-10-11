import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class GameState(ABC):
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def enter(self, context: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def update(self, context: Dict[str, Any]) -> Optional[str]:
        pass
    
    @abstractmethod
    def exit(self, context: Dict[str, Any]) -> None:
        pass

class StateMachine:
    def __init__(self, state_timeout: float = 30.0, max_no_match_count: int = 10,
                 initial_state_name: str = None):
        self.states: Dict[str, GameState] = {}
        self.current_state: Optional[GameState] = None
        self.previous_state: Optional[GameState] = None
        self.initial_state_name = initial_state_name
        self.context: Dict[str, Any] = {}
        self._is_running = False
        self._last_state_change_time = 0
        self._state_timeout = state_timeout
        self._max_no_match_count = max_no_match_count
        self._no_match_count = 0
    
    def add_state(self, state: GameState) -> None:
        self.states[state.name] = state
    
    def set_initial_state(self, state_name: str) -> None:
        self.initial_state_name = state_name
        if state_name in self.states:
            self.current_state = self.states[state_name]
            self._last_state_change_time = time.time()
    
    def transition_to(self, state_name: str) -> bool:
        if state_name not in self.states:
            logger.error(f"State not found: {state_name}")
            return False
        
        if self.current_state:
            logger.debug(f"Exiting state: {self.current_state.name}")
            self.current_state.exit(self.context)
            self.previous_state = self.current_state
        
        self.current_state = self.states[state_name]
        self._last_state_change_time = time.time()
        self._no_match_count = 0
        logger.info(f"Entering state: {self.current_state.name}")
        self.current_state.enter(self.context)
        
        return True
    
    def _increment_no_match(self):
        self._no_match_count += 1
        logger.debug(f"No match count: {self._no_match_count}/{self._max_no_match_count}")
    
    def _reset_no_match(self):
        self._no_match_count = 0
    
    def _handle_no_match(self):
        if self._no_match_count >= self._max_no_match_count:
            logger.warning(f"Max no_match count reached in {self.current_state.name}, triggering degradation")
            self._degrade_state()
            return True
        return False
    
    def _degrade_state(self):
        screenshot_capture = self.context.get('screenshot_capture')
        hwnd = self.context.get('hwnd')
        
        if screenshot_capture and hwnd:
            logger.info("Attempting to refresh screenshot rect")
            try:
                client_rect = screenshot_capture.get_client_rect(hwnd)
                if client_rect:
                    logger.info(f"Refreshed client rect: {client_rect}")
            except Exception as e:
                logger.error(f"Failed to refresh client rect: {e}")
        
        if self.previous_state:
            logger.info(f"Rolling back to previous state: {self.previous_state.name}")
            self.transition_to(self.previous_state.name)
        elif self.initial_state_name:
            logger.info(f"Rolling back to initial state: {self.initial_state_name}")
            self.transition_to(self.initial_state_name)
        else:
            logger.error("No previous or initial state to rollback to")
        
        self._no_match_count = 0
    
    def update(self) -> None:
        if not self.current_state:
            logger.warning("No current state set")
            return
        
        elapsed = time.time() - self._last_state_change_time
        if elapsed > self._state_timeout:
            logger.warning(f"State {self.current_state.name} timed out after {elapsed:.1f}s")
            self._handle_timeout()
            return
        
        try:
            next_state = self.current_state.update(self.context)
            
            if next_state is None:
                self._increment_no_match()
                if self._handle_no_match():
                    return
            elif next_state == "no_match":
                self._increment_no_match()
                if self._handle_no_match():
                    return
            elif next_state != self.current_state.name:
                self._reset_no_match()
                self.transition_to(next_state)
            else:
                self._reset_no_match()
                
        except Exception as e:
            logger.error(f"Error in state {self.current_state.name}: {e}")
            self._handle_error()
    
    def _handle_timeout(self):
        logger.error(f"State timeout in {self.current_state.name}")
        self._degrade_state()
    
    def _handle_error(self):
        logger.error(f"Error handling in {self.current_state.name}")
        self._degrade_state()
    
    def start(self) -> None:
        if self.current_state:
            logger.info(f"Starting state machine with initial state: {self.current_state.name}")
            self.current_state.enter(self.context)
            self._is_running = True
    
    def stop(self) -> None:
        if self.current_state:
            self.current_state.exit(self.context)
        self._is_running = False
        logger.info("State machine stopped")
    
    def is_running(self) -> bool:
        return self._is_running
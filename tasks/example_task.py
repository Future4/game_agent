import time
import logging
from core.state_machine import GameState
from typing import Optional

logger = logging.getLogger(__name__)

class IdleState(GameState):
    def __init__(self):
        super().__init__("idle")
    
    def enter(self, context):
        logger.info("Entering idle state")
    
    def update(self, context):
        vision = context['vision']
        screenshot_capture = context['screenshot_capture']
        hwnd = context['hwnd']
        
        img = screenshot_capture.capture_to_cv2(hwnd)
        if img is None:
            return None
        
        text_result = vision.detect_text(img, "师门")
        if text_result:
            logger.info("Detected '师门' text, transitioning to task selection")
            return "select_task"
        
        task_button = vision.detect_template(img, "task_button")
        if task_button:
            logger.info("Detected task button, transitioning to task selection")
            return "select_task"
        
        return None
    
    def exit(self, context):
        logger.info("Exiting idle state")

class SelectTaskState(GameState):
    def __init__(self):
        super().__init__("select_task")
        self._selected = False
    
    def enter(self, context):
        logger.info("Entering select task state")
        self._selected = False
    
    def update(self, context):
        if self._selected:
            time.sleep(2)
            return "execute_task"
        
        action_executor = context['action_executor']
        vision = context['vision']
        screenshot_capture = context['screenshot_capture']
        hwnd = context['hwnd']
        
        img = screenshot_capture.capture_to_cv2(hwnd)
        if img is None:
            return None
        
        shi_men_pos = vision.detect_text(img, "师门")
        if shi_men_pos:
            logger.info(f"Clicking '师门' at {shi_men_pos}")
            action_executor.click(shi_men_pos[0], shi_men_pos[1])
            self._selected = True
            return None
        
        start_button = vision.detect_template(img, "start_button")
        if start_button:
            logger.info(f"Clicking start button at {start_button[:2]}")
            action_executor.click(start_button[0], start_button[1])
            self._selected = True
            return None
        
        return "idle"
    
    def exit(self, context):
        logger.info("Exiting select task state")

class ExecuteTaskState(GameState):
    def __init__(self):
        super().__init__("execute_task")
        self._task_count = 0
        self._max_tasks = 20
    
    def enter(self, context):
        logger.info("Entering execute task state")
        self._task_count = 0
    
    def update(self, context):
        if self._task_count >= self._max_tasks:
            logger.info("Completed all tasks")
            return "idle"
        
        vision = context['vision']
        action_executor = context['action_executor']
        screenshot_capture = context['screenshot_capture']
        hwnd = context['hwnd']
        
        img = screenshot_capture.capture_to_cv2(hwnd)
        if img is None:
            return None
        
        confirm_button = vision.detect_template(img, "confirm_button")
        if confirm_button:
            logger.info(f"Clicking confirm at {confirm_button[:2]}")
            action_executor.click(confirm_button[0], confirm_button[1])
            time.sleep(1)
            return None
        
        accept_button = vision.detect_template(img, "accept_button")
        if accept_button:
            logger.info(f"Clicking accept at {accept_button[:2]}")
            action_executor.click(accept_button[0], accept_button[1])
            time.sleep(1)
            return None
        
        finish_button = vision.detect_template(img, "finish_button")
        if finish_button:
            logger.info(f"Clicking finish at {finish_button[:2]}")
            action_executor.click(finish_button[0], finish_button[1])
            self._task_count += 1
            logger.info(f"Completed task {self._task_count}/{self._max_tasks}")
            time.sleep(2)
            return None
        
        auto_fight = vision.detect_template(img, "auto_fight")
        if auto_fight:
            logger.info(f"Clicking auto fight at {auto_fight[:2]}")
            action_executor.click(auto_fight[0], auto_fight[1])
            time.sleep(5)
            return None
        
        text_results = vision.get_all_text(img)
        for result in text_results:
            if "完成" in result['text'] or "结束" in result['text']:
                box = result['box']
                center_x = (box[0][0] + box[2][0]) // 2
                center_y = (box[0][1] + box[2][1]) // 2
                logger.info(f"Clicking '完成' text at ({center_x}, {center_y})")
                action_executor.click(center_x, center_y)
                self._task_count += 1
                time.sleep(2)
                return None
        
        return None
    
    def exit(self, context):
        logger.info("Exiting execute task state")
import time
import logging
import threading
import os
import win32gui
from typing import Optional, Dict, Any
from core.window_manager import WindowInfo
from core.screenshot import ScreenshotCapture
from core.action_executor import ActionExecutor
from core.state_machine import StateMachine
from vision.vision import Vision

logger = logging.getLogger(__name__)

class GameAgent:
    # Fixed anchors were measured from the 774x581 client screenshot used by
    # the supplied templates. Recognition results are already in live pixels
    # and must not pass through this transform.
    BASE_CLIENT_SIZE = (774, 581)

    def __init__(self, window_info: WindowInfo, template_dir: str = "templates"):
        self.window_info = window_info
        self.hwnd = window_info.hwnd
        self.screenshot_capture = ScreenshotCapture()
        # Game-rendered controls do not reliably handle PostMessage. The
        # desktop client therefore uses real foreground mouse input for all
        # automation actions.
        self.action_executor = ActionExecutor(self.hwnd, mode="foreground")
        self.vision = Vision(template_dir=template_dir)
        self.state_machine = StateMachine()
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.context: Dict[str, Any] = {
            'hwnd': self.hwnd,
            'window_info': window_info,
            'screenshot_capture': self.screenshot_capture,
            'action_executor': self.action_executor,
            'vision': self.vision,
            'agent': self,
        }
        self.state_machine.context = self.context
    
    def add_state(self, state):
        self.state_machine.add_state(state)
    
    def set_initial_state(self, state_name: str):
        self.state_machine.set_initial_state(state_name)
    
    def capture(self) -> Optional[Any]:
        with self._lock:
            return self.screenshot_capture.capture_to_cv2(self.hwnd)
    
    def click(self, x: int, y: int, client_coords: bool = True):
        self._save_click_debug(x, y, None, client_coords, phase="before")
        with self._lock:
            result = self.action_executor.click(x, y, client_coords)
        self._save_click_debug(x, y, result, client_coords, phase="after")
        return result

    def click_foreground(self, x: int, y: int, client_coords: bool = True):
        """Send one real mouse click, used for game-rendered map layers."""
        return self.click(x, y, client_coords)

    def click_fixed(self, x: int, y: int) -> bool:
        """Click a coordinate measured on the reference client size."""
        image = self.capture()
        if image is None:
            logger.warning("窗口=%s 无法缩放固定点击坐标：截图失败", self.hwnd)
            return False
        height, width = image.shape[:2]
        base_w, base_h = self.BASE_CLIENT_SIZE
        scaled = (round(x * width / base_w), round(y * height / base_h))
        logger.info("窗口=%s 固定坐标参考=(%s,%s)，当前尺寸=%sx%s，缩放后=%s",
                    self.hwnd, x, y, width, height, scaled)
        return self.click(*scaled)

    def _save_click_debug(self, x: int, y: int, result: bool, client_coords: bool, phase: str = "after") -> None:
        """Save every client click with a marker for visual verification."""
        try:
            import cv2
            image = self.capture()
            if image is None:
                return
            os.makedirs("debug/clicks", exist_ok=True)
            marked = image.copy()
            px, py = int(x), int(y)
            cv2.drawMarker(marked, (px, py), (0, 0, 255), cv2.MARKER_CROSS, 28, 3)
            cv2.circle(marked, (px, py), 14, (255, 0, 0), 2)
            cv2.putText(marked, f"{phase} click=({px},{py}) foreground result={result}",
                        (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
            filename = f"click_{self.hwnd}_{time.time_ns()}_{phase}.png"
            path = os.path.abspath(os.path.join("debug", "clicks", filename))
            cv2.imwrite(path, marked)
            logger.info("窗口=%s 点击调试截图：%s", self.hwnd, path)
        except Exception:
            logger.exception("窗口=%s 保存点击调试截图失败", self.hwnd)
    
    def press_key(self, key: str):
        with self._lock:
            return self.action_executor.press_key(key)

    def scroll(self, lines: int, x: int = 500, y: int = 320) -> bool:
        """Scroll at a client/screenshot coordinate using foreground input."""
        with self._lock:
            return self.action_executor.scroll(lines, client_coords=True, x=x, y=y)
    
    def detect_template(self, template_name: str, threshold: float = 0.8):
        img = self.capture()
        if img is None:
            logger.warning("窗口=%s 识别模板%s时截图失败", self.hwnd, template_name)
        else:
            logger.debug("窗口=%s 识别模板=%s，阈值=%.2f，截图=%s", self.hwnd, template_name, threshold, img.shape)
        if img is not None:
            return self.vision.detect_template(img, template_name, threshold)
        return None

    def detect_template_multiscale(self, template_name: str, threshold: float = 0.7):
        img = self.capture()
        if img is not None:
            return self.vision.detect_template_multiscale(img, template_name, threshold)
        return None

    def detect_template_region(self, template_name: str, region, threshold: float = 0.8):
        img = self.capture()
        if img is not None:
            return self.vision.detect_template_region(img, template_name, region, threshold)
        return None

    def detect_template_multiscale_region(self, template_name: str, region, threshold: float = 0.7):
        img = self.capture()
        if img is not None:
            return self.vision.detect_template_multiscale_region(img, template_name, region, threshold)
        return None
    
    def detect_text(self, text: str, threshold: float = 0.6):
        img = self.capture()
        if img is None:
            logger.warning("窗口=%s 识别文字%s时截图失败", self.hwnd, text)
        if img is not None:
            return self.vision.detect_text(img, text, threshold)
        return None
    
    def _run_loop(self):
        logger.info(f"窗口={self.hwnd} Agent已启动")
        
        while self._is_running:
            try:
                if not win32gui.IsWindowVisible(self.hwnd):
                    logger.warning(f"窗口={self.hwnd} 当前不可见")
                    time.sleep(1)
                    continue
                
                self.state_machine.update()
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"窗口={self.hwnd} Agent运行错误：{e}")
                time.sleep(1)
        
        logger.info(f"窗口={self.hwnd} Agent已停止")
    
    def start(self):
        if self._is_running:
            logger.warning(f"窗口={self.hwnd} Agent已经运行")
            return
        
        self._is_running = True
        self.state_machine.start()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._is_running = False
        self.state_machine.stop()
        if self._thread:
            self._thread.join(timeout=5)
    
    def is_running(self) -> bool:
        return self._is_running
    
    def get_window_info(self) -> WindowInfo:
        return self.window_info

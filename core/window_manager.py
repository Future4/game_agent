import win32gui
import win32con
import win32api
import ctypes
from typing import List, Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

class WindowInfo:
    def __init__(self, hwnd: int, title: str, class_name: str, rect: Tuple[int, int, int, int]):
        self.hwnd = hwnd
        self.title = title
        self.class_name = class_name
        self.rect = rect
        self.width = rect[2] - rect[0]
        self.height = rect[3] - rect[1]
    
    def __repr__(self):
        return f"WindowInfo(hwnd={self.hwnd}, title={self.title[:30]}, class={self.class_name}, rect={self.rect})"

class WindowManager:
    BLACKLIST_CLASS_NAMES = {
        "Qt5QWindowIcon",
        "Qt5QWindow",
        "Chrome_WidgetWin_1",
        "MozillaWindowClass",
    }
    
    BLACKLIST_TITLE_KEYWORDS = {
        "Visual Studio",
        "PyCharm",
        "VS Code",
        "cmd",
        "powershell",
    }
    
    def __init__(self, target_title_keywords: Optional[List[str]] = None,
                 target_class_names: Optional[List[str]] = None,
                 blacklist_title_keywords: Optional[List[str]] = None,
                 blacklist_class_names: Optional[List[str]] = None):
        self.target_title_keywords = target_title_keywords or []
        self.target_class_names = target_class_names or []
        self.blacklist_title_keywords = set(blacklist_title_keywords or self.BLACKLIST_TITLE_KEYWORDS)
        self.blacklist_class_names = set(blacklist_class_names or self.BLACKLIST_CLASS_NAMES)
        self.windows: Dict[int, WindowInfo] = {}
    
    def is_blacklisted(self, title: str, class_name: str) -> bool:
        title_lower = title.lower()
        for kw in self.blacklist_title_keywords:
            if kw.lower() in title_lower:
                return True
        if class_name in self.blacklist_class_names:
            return True
        return False
    
    def enum_callback(self, hwnd: int, extra: None) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        
        if self.is_blacklisted(title, class_name):
            return True
        
        if not title and not class_name:
            return True
        
        rect = win32gui.GetWindowRect(hwnd)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        
        if width < 100 or height < 100:
            return True
        
        matched = False
        if self.target_title_keywords:
            for kw in self.target_title_keywords:
                if kw in title:
                    matched = True
                    break
        if self.target_class_names and not matched:
            if class_name in self.target_class_names:
                matched = True
        
        if not self.target_title_keywords and not self.target_class_names:
            matched = True
        
        if matched:
            self.windows[hwnd] = WindowInfo(hwnd, title, class_name, rect)
            logger.debug(f"Found window: {self.windows[hwnd]}")
        
        return True
    
    def find_windows(self) -> List[WindowInfo]:
        self.windows.clear()
        win32gui.EnumWindows(self.enum_callback, None)
        return list(self.windows.values())
    
    def get_window_by_hwnd(self, hwnd: int) -> Optional[WindowInfo]:
        return self.windows.get(hwnd)
    
    def activate_window(self, hwnd: int) -> bool:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            logger.error(f"Failed to activate window {hwnd}: {e}")
            return False
    
    def get_client_rect(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        try:
            client_rect = win32gui.GetClientRect(hwnd)
            screen_rect = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
            screen_rect2 = win32gui.ClientToScreen(hwnd, (client_rect[2], client_rect[3]))
            return (screen_rect[0], screen_rect[1], screen_rect2[0], screen_rect2[1])
        except Exception as e:
            logger.error(f"Failed to get client rect for {hwnd}: {e}")
            return None
    
    def close_window(self, hwnd: int) -> bool:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return True
        except Exception as e:
            logger.error(f"Failed to close window {hwnd}: {e}")
            return False
    
    def move_window(self, hwnd: int, x: int, y: int, width: int, height: int) -> bool:
        try:
            win32gui.MoveWindow(hwnd, x, y, width, height, True)
            return True
        except Exception as e:
            logger.error(f"Failed to move window {hwnd}: {e}")
            return False

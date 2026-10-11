import win32gui
import win32api
import win32con
import ctypes
import time
import random
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = ctypes.c_int
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = ctypes.c_int


class ActionExecutor:
    """操作执行器 - 支持后台和前台两种模式
    
    验证结论：
    - PostMessage/SendMessage有效（正确坐标下）- 支持后台多窗口并行
    - SetCursorPos + mouse_event有效 - 需管理员权限，仅前台
    - 默认使用后台模式（PostMessage），支持多窗口同时操作
    
    拟人化功能：
    - click_human: 模拟人类点击，包含随机偏移和随机延迟
    """

    def __init__(self, hwnd: int, mode: str = "background",
                 screenshot_offset: Tuple[int, int] = (0, 0),
                 humanize: bool = True):
        """初始化

        Args:
            hwnd: 窗口句柄
            mode: "background"=后台PostMessage(默认,支持多窗口)
                  "foreground"=前台真实鼠标(需管理员权限)
            screenshot_offset: 截图坐标到客户区坐标的偏移量 (offset_x, offset_y)
                              截图坐标 + offset = 客户区坐标
            humanize: 是否启用拟人化点击（随机偏移+随机延迟）
        """
        self.hwnd = hwnd
        self.mode = mode
        self.offset_x, self.offset_y = screenshot_offset
        self.humanize = humanize

    def _to_client_coords(self, x: int, y: int) -> Tuple[int, int]:
        """截图坐标转客户区坐标"""
        return (x + self.offset_x, y + self.offset_y)

    def _get_lparam(self, x: int, y: int) -> int:
        """生成鼠标消息的lParam"""
        return (y << 16) | (x & 0xFFFF)

    def _activate_window(self):
        """激活窗口到前台。

        重要：窗口已经是前台时，SetForegroundWindow 仍可能抛 “拒绝访问”(error 5)，
        因此不能因为它失败就放弃点击——只要窗口当前就是前台就继续执行输入。
        """
        try:
            if win32gui.GetForegroundWindow() == self.hwnd:
                return True
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            time.sleep(0.1)
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.2)
            return True
        except Exception as e:
            foreground = None
            try:
                foreground = win32gui.GetForegroundWindow()
            except Exception:
                pass
            if foreground == self.hwnd:
                return True
            logger.error(f"激活窗口失败: {e}")
            return False

    def _client_to_screen(self, x: int, y: int) -> Tuple[int, int]:
        """客户区坐标转屏幕坐标"""
        return win32gui.ClientToScreen(self.hwnd, (x, y))

    def _set_cursor_pos(self, x: int, y: int) -> bool:
        """使用ctypes设置鼠标位置"""
        result = user32.SetCursorPos(x, y)
        return result != 0

    def click(self, x: int, y: int, client_coords: bool = True,
              button: str = "left", double_click: bool = False):
        """点击

        Args:
            x, y: 截图坐标（来自模板匹配/截图）
            client_coords: True=客户区/截图坐标, False=屏幕坐标
            button: "left" 或 "right"
            double_click: 是否双击
        """
        # 截图坐标转客户区坐标
        if client_coords:
            x, y = self._to_client_coords(x, y)
            client_coords = True  # 转换后仍是客户区坐标

        if self.mode == "background":
            return self._click_background(x, y, client_coords, button, double_click)
        else:
            return self._click_foreground(x, y, client_coords, button, double_click)

    def click_human(self, cx: int, cy: int, w: int = 0, h: int = 0,
                    button: str = "left", delay_range: Tuple[float, float] = (0.5, 2.0)):
        """拟人化点击 - 模拟人类操作

        1. 随机延迟0.5-2秒后点击
        2. 在按钮范围内随机偏移点击位置（不会点出按钮外）

        Args:
            cx, cy: 按钮中心坐标（截图坐标）
            w, h: 按钮宽高（用于随机偏移范围，0=不偏移）
            button: "left" 或 "right"
            delay_range: 随机延迟范围（秒），默认0.5-2秒
        """
        # 随机延迟
        delay = random.uniform(*delay_range)
        logger.debug(f"拟人化: 等待{delay:.2f}秒")
        time.sleep(delay)

        # 随机偏移（在按钮范围内）
        if w > 0 and h > 0:
            # 保留20%边距，确保点在按钮内
            margin_x = int(w * 0.2)
            margin_y = int(h * 0.2)
            offset_x = random.randint(-margin_x, margin_x)
            offset_y = random.randint(-margin_y, margin_y)
            final_x = cx + offset_x
            final_y = cy + offset_y
            logger.debug(f"拟人化: 偏移({offset_x},{offset_y}) → ({final_x},{final_y})")
        else:
            final_x, final_y = cx, cy

        # 执行点击
        return self.click(final_x, final_y, button=button)

    def _click_background(self, x: int, y: int, client_coords: bool,
                          button: str, double_click: bool):
        """后台点击（PostMessage）- 支持多窗口并行"""
        if not client_coords:
            client_pos = win32gui.ScreenToClient(self.hwnd, (x, y))
            if client_pos is None:
                return False
            x, y = client_pos

        pos = self._get_lparam(x, y)

        try:
            if button == "left":
                down_msg = win32con.WM_LBUTTONDOWN
                up_msg = win32con.WM_LBUTTONUP
                wparam = win32con.MK_LBUTTON
            elif button == "right":
                down_msg = win32con.WM_RBUTTONDOWN
                up_msg = win32con.WM_RBUTTONUP
                wparam = win32con.MK_RBUTTON
            else:
                logger.error(f"不支持的按钮: {button}")
                return False

            win32api.PostMessage(self.hwnd, down_msg, wparam, pos)
            time.sleep(0.05)
            win32api.PostMessage(self.hwnd, up_msg, 0, pos)

            if double_click:
                time.sleep(0.1)
                win32api.PostMessage(self.hwnd, down_msg, wparam, pos)
                time.sleep(0.05)
                win32api.PostMessage(self.hwnd, up_msg, 0, pos)

            time.sleep(0.05)
            logger.debug(f"后台点击 ({x}, {y})")
            return True

        except Exception as e:
            logger.error(f"后台点击失败: {e}")
            return False

    def _click_foreground(self, x: int, y: int, client_coords: bool,
                          button: str, double_click: bool):
        """前台点击（真实鼠标）- 需管理员权限"""
        if client_coords:
            # 截图(ScreenshotCapture)抓的是「客户区」，根在客户区左上角(实测验证)，
            # 因此必须用 ClientToScreen 转换；此前用 GetWindowRect 原点会多算
            # 标题栏/边框偏移(本机约 9px/38px)，导致点击整体偏高而点空。
            screen_x, screen_y = win32gui.ClientToScreen(self.hwnd, (int(x), int(y)))
            logger.debug("截图坐标转换 hwnd=%s screenshot=(%s,%s) screen=(%s,%s)",
                         self.hwnd, x, y, screen_x, screen_y)
        else:
            screen_x, screen_y = x, y

        try:
            logger.info("前台点击坐标 hwnd=%s screenshot=(%s,%s) screen=(%s,%s)",
                        self.hwnd, x, y, screen_x, screen_y)
            if not self._activate_window():
                return False

            self._set_cursor_pos(screen_x, screen_y)
            time.sleep(0.1)

            if button == "left":
                down_flag = win32con.MOUSEEVENTF_LEFTDOWN
                up_flag = win32con.MOUSEEVENTF_LEFTUP
            elif button == "right":
                down_flag = win32con.MOUSEEVENTF_RIGHTDOWN
                up_flag = win32con.MOUSEEVENTF_RIGHTUP
            else:
                logger.error(f"不支持的按钮: {button}")
                return False

            win32api.mouse_event(down_flag, screen_x, screen_y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(up_flag, screen_x, screen_y, 0, 0)

            if double_click:
                time.sleep(0.1)
                win32api.mouse_event(down_flag, screen_x, screen_y, 0, 0)
                time.sleep(0.05)
                win32api.mouse_event(up_flag, screen_x, screen_y, 0, 0)

            time.sleep(0.05)
            logger.debug(f"前台点击 ({x}, {y}) -> screen({screen_x}, {screen_y})")
            return True

        except Exception as e:
            logger.error(f"前台点击失败: {e}")
            return False

    def move_to(self, x: int, y: int, client_coords: bool = True):
        """移动鼠标"""
        if client_coords:
            x, y = self._to_client_coords(x, y)
        if self.mode == "background":
            if not client_coords:
                client_pos = win32gui.ScreenToClient(self.hwnd, (x, y))
                if client_pos is None:
                    return False
                x, y = client_pos
            pos = self._get_lparam(x, y)
            try:
                win32api.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, pos)
                return True
            except Exception as e:
                logger.error(f"后台移动失败: {e}")
                return False
        else:
            if client_coords:
                screen_x, screen_y = self._client_to_screen(x, y)
            else:
                screen_x, screen_y = x, y
            try:
                self._set_cursor_pos(screen_x, screen_y)
                return True
            except Exception as e:
                logger.error(f"前台移动失败: {e}")
                return False

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int,
             client_coords: bool = True, duration: float = 0.5):
        """拖拽"""
        if client_coords:
            start_x, start_y = self._to_client_coords(start_x, start_y)
            end_x, end_y = self._to_client_coords(end_x, end_y)
        if self.mode == "background":
            return self._drag_background(start_x, start_y, end_x, end_y, client_coords, duration)
        else:
            return self._drag_foreground(start_x, start_y, end_x, end_y, client_coords, duration)

    def _drag_background(self, start_x: int, start_y: int, end_x: int, end_y: int,
                         client_coords: bool, duration: float):
        """后台拖拽"""
        if not client_coords:
            start_pos = win32gui.ScreenToClient(self.hwnd, (start_x, start_y))
            end_pos = win32gui.ScreenToClient(self.hwnd, (end_x, end_y))
            if start_pos is None or end_pos is None:
                return False
            start_x, start_y = start_pos
            end_x, end_y = end_pos

        try:
            start_lparam = self._get_lparam(start_x, start_y)
            win32api.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, start_lparam)
            time.sleep(0.05)
            win32api.PostMessage(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, start_lparam)
            time.sleep(0.05)

            steps = max(int(duration / 0.05), 1)
            dx = (end_x - start_x) / steps
            dy = (end_y - start_y) / steps

            for i in range(steps):
                cx = int(start_x + dx * i)
                cy = int(start_y + dy * i)
                win32api.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, self._get_lparam(cx, cy))
                time.sleep(0.05)

            end_lparam = self._get_lparam(end_x, end_y)
            win32api.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, end_lparam)
            win32api.PostMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, end_lparam)
            return True
        except Exception as e:
            logger.error(f"后台拖拽失败: {e}")
            return False

    def _drag_foreground(self, start_x: int, start_y: int, end_x: int, end_y: int,
                         client_coords: bool, duration: float):
        """前台拖拽"""
        if client_coords:
            start_screen = self._client_to_screen(start_x, start_y)
            end_screen = self._client_to_screen(end_x, end_y)
        else:
            start_screen = (start_x, start_y)
            end_screen = (end_x, end_y)

        try:
            if not self._activate_window():
                return False

            self._set_cursor_pos(start_screen[0], start_screen[1])
            time.sleep(0.1)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, start_screen[0], start_screen[1], 0, 0)
            time.sleep(0.05)

            steps = max(int(duration / 0.05), 1)
            dx = (end_screen[0] - start_screen[0]) / steps
            dy = (end_screen[1] - start_screen[1]) / steps

            for i in range(steps):
                cx = int(start_screen[0] + dx * i)
                cy = int(start_screen[1] + dy * i)
                self._set_cursor_pos(cx, cy)
                time.sleep(0.05)

            self._set_cursor_pos(end_screen[0], end_screen[1])
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, end_screen[0], end_screen[1], 0, 0)
            return True
        except Exception as e:
            logger.error(f"前台拖拽失败: {e}")
            return False

    def press_key(self, key: str, hold_time: float = 0.1):
        """按键"""
        key_map = {
            'enter': win32con.VK_RETURN, 'esc': win32con.VK_ESCAPE,
            'space': win32con.VK_SPACE, 'tab': win32con.VK_TAB,
            'backspace': win32con.VK_BACK, 'delete': win32con.VK_DELETE,
            'up': win32con.VK_UP, 'down': win32con.VK_DOWN,
            'left': win32con.VK_LEFT, 'right': win32con.VK_RIGHT,
            'f1': win32con.VK_F1, 'f2': win32con.VK_F2, 'f3': win32con.VK_F3,
            'f4': win32con.VK_F4, 'f5': win32con.VK_F5, 'f6': win32con.VK_F6,
            'f7': win32con.VK_F7, 'f8': win32con.VK_F8, 'f9': win32con.VK_F9,
            'f10': win32con.VK_F10, 'f11': win32con.VK_F11, 'f12': win32con.VK_F12,
        }

        vk_code = key_map.get(key.lower())
        if not vk_code and len(key) == 1:
            vk_code = ord(key.upper())

        if vk_code is None:
            logger.error(f"未知按键: {key}")
            return False

        try:
            if self.mode == "background":
                scan_code = win32api.MapVirtualKey(vk_code, 0)
                win32api.PostMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, scan_code << 16)
                time.sleep(hold_time)
                win32api.PostMessage(self.hwnd, win32con.WM_KEYUP, vk_code, (scan_code << 16) | 0xC0000000)
            else:
                if not self._activate_window():
                    return False
                scan_code = win32api.MapVirtualKey(vk_code, 0)
                win32api.keybd_event(vk_code, scan_code, 0, 0)
                time.sleep(hold_time)
                win32api.keybd_event(vk_code, scan_code, win32con.KEYEVENTF_KEYUP, 0)

            logger.debug(f"按键: {key}")
            return True
        except Exception as e:
            logger.error(f"按键失败: {e}")
            return False

    def type_text(self, text: str, delay: float = 0.05):
        """输入文本"""
        try:
            for char in text:
                vk_code = ord(char.upper())
                scan_code = win32api.MapVirtualKey(vk_code, 0)

                if self.mode == "background":
                    win32api.PostMessage(self.hwnd, win32con.WM_KEYDOWN, vk_code, scan_code << 16)
                    time.sleep(0.02)
                    win32api.PostMessage(self.hwnd, win32con.WM_KEYUP, vk_code, (scan_code << 16) | 0xC0000000)
                else:
                    if not self._activate_window():
                        return False
                    win32api.keybd_event(vk_code, scan_code, 0, 0)
                    time.sleep(0.02)
                    win32api.keybd_event(vk_code, scan_code, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(delay)

            logger.debug(f"输入文本: {text}")
            return True
        except Exception as e:
            logger.error(f"输入文本失败: {e}")
            return False

    def scroll(self, lines: int, client_coords: bool = True, x: int = 0, y: int = 0):
        """滚轮"""
        if client_coords:
            x, y = self._to_client_coords(x, y)
        if not client_coords:
            client_pos = win32gui.ScreenToClient(self.hwnd, (x, y))
            if client_pos is None:
                return False
            x, y = client_pos

        pos = self._get_lparam(x, y)

        try:
            if self.mode == "background":
                for _ in range(abs(lines)):
                    delta = 120 if lines > 0 else -120
                    win32api.PostMessage(self.hwnd, win32con.WM_MOUSEWHEEL, delta << 16, pos)
                    time.sleep(0.1)
            else:
                if not self._activate_window():
                    return False
                # 与前台点击一致：截图坐标 = 客户区坐标，用 ClientToScreen 转换
                screen_x, screen_y = win32gui.ClientToScreen(self.hwnd, (int(x), int(y)))
                self._set_cursor_pos(screen_x, screen_y)
                time.sleep(0.1)
                for _ in range(abs(lines)):
                    delta = 120 if lines > 0 else -120
                    win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, screen_x, screen_y, delta, 0)
                    time.sleep(0.1)

            logger.debug(f"滚轮 {lines} 行 at ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"滚轮失败: {e}")
            return False

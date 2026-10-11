import win32gui
import win32ui
import win32con
import ctypes
from ctypes import wintypes
from PIL import Image
import numpy as np
import cv2
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.SetProcessDPIAware()

# 定义PrintWindow的flag常量
PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002

# 设置函数签名 - user32
# Capture from the client DC. Using GetWindowDC here made the bitmap start at
# the non-client window origin while its dimensions were taken from the client
# rect, producing the observed ~10px/~40px click-marker offset.
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]

user32.PrintWindow.restype = ctypes.c_int
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_uint]

user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

user32.GetClientRect.restype = ctypes.c_int
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

# 设置函数签名 - gdi32
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]

gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]

gdi32.GetDIBits.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]

gdi32.BitBlt.restype = ctypes.c_int
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]

gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]

gdi32.DeleteDC.restype = ctypes.c_int
gdi32.DeleteDC.argtypes = [wintypes.HDC]

gdi32.DeleteObject.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]

PW_RENDERCLIENT = 0
PW_RENDERFULLCONTENT = 2

# 定义BITMAPINFO结构体
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', ctypes.c_uint32),
        ('biWidth', ctypes.c_int32),
        ('biHeight', ctypes.c_int32),
        ('biPlanes', ctypes.c_uint16),
        ('biBitCount', ctypes.c_uint16),
        ('biCompression', ctypes.c_uint32),
        ('biSizeImage', ctypes.c_uint32),
        ('biXPelsPerMeter', ctypes.c_int32),
        ('biYPelsPerMeter', ctypes.c_int32),
        ('biClrUsed', ctypes.c_uint32),
        ('biClrImportant', ctypes.c_uint32),
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ('bmiHeader', BITMAPINFOHEADER),
        ('bmiColors', ctypes.c_uint32 * 3),
    ]

class ScreenshotCapture:
    def __init__(self, printwindow_flags: List[int] = None):
        self._mem_dc = None
        self._bmp = None
        self._bmp_handle = None
        if printwindow_flags is None:
            # 只使用「仅客户区(PW_CLIENTONLY)」的变体，保证 PrintWindow 输出与 BitBlt
            # 一样以「客户区左上角」为原点。整窗变体(PW_RENDERFULLCONTENT 单独使用)
            # 会把标题栏/边框算进原点，同一份点击换算会瞬时偏移约 38px。
            self.printwindow_flags = [PW_CLIENTONLY | PW_RENDERFULLCONTENT, PW_CLIENTONLY]
        else:
            self.printwindow_flags = printwindow_flags
    
    def _release_resources(self):
        if self._bmp_handle:
            win32gui.DeleteObject(self._bmp_handle)
            self._bmp_handle = None
        if self._mem_dc:
            win32gui.DeleteDC(self._mem_dc)
            self._mem_dc = None
    
    def _is_blank_image(self, img: Image.Image) -> bool:
        if img is None:
            return True
        np_img = np.array(img)
        if np_img.size == 0:
            return True
        if np.mean(np_img) < 5:
            return True
        return False
    
    def capture_printwindow_with_flag(self, hwnd: int, flag: int) -> Optional[Image.Image]:
        hwnd_dc = None
        mem_dc = None
        bitmap = None
        
        try:
            rect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            
            if width <= 0 or height <= 0:
                logger.error(f"Invalid client area: {width}x{height}")
                return None
            
            hwnd_dc = user32.GetDC(hwnd)
            if not hwnd_dc:
                logger.error("GetDC failed")
                return None
            
            mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            if not mem_dc:
                logger.error("CreateCompatibleDC failed")
                user32.ReleaseDC(hwnd, hwnd_dc)
                return None
            
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
            if not bitmap:
                logger.error("CreateCompatibleBitmap failed")
                gdi32.DeleteDC(mem_dc)
                user32.ReleaseDC(hwnd, hwnd_dc)
                return None
            
            gdi32.SelectObject(mem_dc, bitmap)
            
            result = user32.PrintWindow(hwnd, mem_dc, flag)
            
            bitmap_info = BITMAPINFO()
            bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bitmap_info.bmiHeader.biWidth = width
            bitmap_info.bmiHeader.biHeight = -height
            bitmap_info.bmiHeader.biPlanes = 1
            bitmap_info.bmiHeader.biBitCount = 32
            bitmap_info.bmiHeader.biCompression = 0
            
            buffer = ctypes.create_string_buffer(width * height * 4)
            
            got_bits = gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(bitmap_info), 0)
            
            if got_bits == 0:
                logger.error(f"GetDIBits failed for flag={flag}")
                gdi32.DeleteObject(bitmap)
                gdi32.DeleteDC(mem_dc)
                user32.ReleaseDC(hwnd, hwnd_dc)
                return None
            
            img = Image.frombuffer('RGB', (width, height), buffer, 'raw', 'BGRX', 0, 1)
            
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, hwnd_dc)
            
            if result == 0:
                logger.debug(f"PrintWindow(flag={flag}) returned 0")
            
            if self._is_blank_image(img):
                logger.debug(f"PrintWindow(flag={flag}) returned blank image")
                return None
            
            return img
        
        except Exception as e:
            logger.error(f"PrintWindow(flag={flag}) capture failed: {e}")
            if bitmap:
                try:
                    gdi32.DeleteObject(bitmap)
                except:
                    pass
            if mem_dc:
                try:
                    gdi32.DeleteDC(mem_dc)
                except:
                    pass
            if hwnd_dc:
                try:
                    user32.ReleaseDC(hwnd, hwnd_dc)
                except:
                    pass
            return None
    
    def capture_printwindow(self, hwnd: int) -> Optional[Image.Image]:
        for flag in self.printwindow_flags:
            img = self.capture_printwindow_with_flag(hwnd, flag)
            if img is not None:
                logger.debug(f"PrintWindow succeeded with flag={flag}")
                return img
        
        logger.warning("All PrintWindow flags failed")
        return None
    
    def capture_bitblt(self, hwnd: int) -> Optional[Image.Image]:
        hwnd_dc = None
        mem_dc = None
        bitmap = None
        
        try:
            rect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            
            if width <= 0 or height <= 0:
                logger.error(f"Invalid client area: {width}x{height}")
                return None
            
            hwnd_dc = user32.GetDC(hwnd)
            if not hwnd_dc:
                logger.error("GetDC failed")
                return None
            
            mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            if not mem_dc:
                logger.error("CreateCompatibleDC failed")
                user32.ReleaseDC(hwnd, hwnd_dc)
                return None
            
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
            if not bitmap:
                logger.error("CreateCompatibleBitmap failed")
                gdi32.DeleteDC(mem_dc)
                user32.ReleaseDC(hwnd, hwnd_dc)
                return None
            
            gdi32.SelectObject(mem_dc, bitmap)
            
            gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, win32con.SRCCOPY)
            
            bitmap_info = BITMAPINFO()
            bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bitmap_info.bmiHeader.biWidth = width
            bitmap_info.bmiHeader.biHeight = -height
            bitmap_info.bmiHeader.biPlanes = 1
            bitmap_info.bmiHeader.biBitCount = 32
            bitmap_info.bmiHeader.biCompression = 0
            
            buffer = ctypes.create_string_buffer(width * height * 4)
            
            got_bits = gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(bitmap_info), 0)
            
            if got_bits == 0:
                logger.error("GetDIBits failed")
                gdi32.DeleteObject(bitmap)
                gdi32.DeleteDC(mem_dc)
                user32.ReleaseDC(hwnd, hwnd_dc)
                return None
            
            img = Image.frombuffer('RGB', (width, height), buffer, 'raw', 'BGRX', 0, 1)
            
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, hwnd_dc)
            
            if self._is_blank_image(img):
                logger.debug("BitBlt returned blank image")
                return None
            
            return img
        
        except Exception as e:
            logger.error(f"BitBlt capture failed: {e}")
            if bitmap:
                try:
                    gdi32.DeleteObject(bitmap)
                except:
                    pass
            if mem_dc:
                try:
                    gdi32.DeleteDC(mem_dc)
                except:
                    pass
            if hwnd_dc:
                try:
                    user32.ReleaseDC(hwnd, hwnd_dc)
                except:
                    pass
            return None
    
    def capture(self, hwnd: int, fallback: bool = True) -> Optional[Image.Image]:
        """抓取窗口截图，坐标系固定为「客户区左上角」。

        BitBlt 从窗口客户区 DC 抓取，原点确定为客户区左上角（实测与整屏抓取客户区
        平均像素差 0.31）。旧实现优先 PrintWindow，而它的整窗变体以窗口左上角为原点，
        导致同一份「截图坐标->屏幕坐标」换算时而正确、时而整体偏移约 38px。
        这里改为 BitBlt 优先，PrintWindow 仅作兜底且只用客户区变体，从根上统一坐标系。
        """
        img = self.capture_bitblt(hwnd)

        if img is None and fallback:
            logger.info("BitBlt failed, trying PrintWindow fallback")
            img = self.capture_printwindow(hwnd)

        if img is not None:
            logger.debug(f"Captured image: {img.size}")

        return img
    
    def capture_to_cv2(self, hwnd: int) -> Optional[np.ndarray]:
        img = self.capture(hwnd)
        if img is not None:
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        return None
    
    def get_window_rect(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception as e:
            logger.error(f"Failed to get window rect: {e}")
            return None
    
    def get_client_rect(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        try:
            client_rect = win32gui.GetClientRect(hwnd)
            left, top = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
            right, bottom = win32gui.ClientToScreen(hwnd, (client_rect[2], client_rect[3]))
            return (left, top, right, bottom)
        except Exception as e:
            logger.error(f"Failed to get client rect: {e}")
            return None
    
    def __del__(self):
        self._release_resources()

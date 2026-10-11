import win32gui
import win32api
import win32con
import ctypes
from ctypes import wintypes
from PIL import Image
import numpy as np
import cv2
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.SetProcessDPIAware()

# 设置函数签名
user32.GetWindowDC.restype = wintypes.HDC
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.PrintWindow.restype = ctypes.c_int
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_uint]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.GetClientRect.restype = ctypes.c_int
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

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

def find_game_window():
    target_windows = []
    def callback(hwnd, extra):
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if win32gui.IsWindowVisible(hwnd) and ("梦幻西游" in title or class_name == "UnityWndClass"):
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if width > 100 and height > 100:
                target_windows.append({
                    'hwnd': hwnd, 'title': title, 'class_name': class_name, 'rect': rect
                })
        return True
    win32gui.EnumWindows(callback, None)
    return target_windows

def capture_bitblt(hwnd):
    hwnd_dc = None
    mem_dc = None
    bitmap = None
    try:
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None
        
        hwnd_dc = user32.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None
        
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        if not mem_dc:
            user32.ReleaseDC(hwnd, hwnd_dc)
            return None
        
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
        if not bitmap:
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
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, hwnd_dc)
            return None
        
        img = Image.frombuffer('RGB', (width, height), buffer, 'raw', 'BGRX', 0, 1)
        
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)
        
        return img
    except Exception as e:
        print(f"截图失败: {e}")
        if bitmap:
            try: gdi32.DeleteObject(bitmap)
            except: pass
        if mem_dc:
            try: gdi32.DeleteDC(mem_dc)
            except: pass
        if hwnd_dc:
            try: user32.ReleaseDC(hwnd, hwnd_dc)
            except: pass
        return None

def find_button_by_color(img_cv2):
    """通过颜色分析查找可能的"参加"按钮"""
    hsv = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2HSV)
    
    results = []
    
    # 方案1: 查找橙色/黄色按钮 (常见参加按钮颜色)
    # 橙色: H=10-30, S=100-255, V=100-255
    lower_orange = np.array([10, 100, 100])
    upper_orange = np.array([30, 255, 255])
    mask_orange = cv2.inRange(hsv, lower_orange, upper_orange)
    
    # 方案2: 查找黄色按钮
    lower_yellow = np.array([26, 100, 100])
    upper_yellow = np.array([34, 255, 255])
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
    
    # 方案3: 查找亮蓝色按钮
    lower_blue = np.array([100, 100, 100])
    upper_blue = np.array([130, 255, 255])
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
    
    # 方案4: 查找亮绿色按钮
    lower_green = np.array([35, 100, 100])
    upper_green = np.array([85, 255, 255])
    mask_green = cv2.inRange(hsv, lower_green, upper_green)
    
    masks = [
        ("橙色", mask_orange),
        ("黄色", mask_yellow),
        ("蓝色", mask_blue),
        ("绿色", mask_green),
    ]
    
    for name, mask in masks:
        # 形态学操作去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            # 按钮面积通常在500-20000之间
            if 500 < area < 20000:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = float(w) / h if h > 0 else 0
                # 按钮宽高比通常在1.5-5之间
                if 1.0 < aspect_ratio < 6.0:
                    results.append({
                        'color': name,
                        'x': x + w // 2,
                        'y': y + h // 2,
                        'rect': (x, y, w, h),
                        'area': area,
                        'aspect_ratio': aspect_ratio
                    })
    
    # 按面积排序
    results.sort(key=lambda r: r['area'], reverse=True)
    return results

def find_button_by_template(img_cv2):
    """通过模板匹配查找"参加"按钮文字区域"""
    gray = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2GRAY)
    
    # 使用自适应阈值二值化
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    # 查找文字区域（白色文字在深色背景上）
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    text_regions = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if 200 < area < 5000 and 0.5 < float(w) / h < 5.0:
            text_regions.append((x, y, w, h))
    
    return text_regions

def draw_results(img_cv2, button_results, save_path):
    """在图像上标记找到的按钮"""
    result_img = img_cv2.copy()
    
    for i, btn in enumerate(button_results):
        x, y, w, h = btn['rect']
        color = (0, 255, 0) if i == 0 else (0, 255, 255)
        cv2.rectangle(result_img, (x, y), (x + w, y + h), color, 2)
        label = f"{i+1}.{btn['color']} ({btn['x']},{btn['y']})"
        cv2.putText(result_img, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    cv2.imwrite(save_path, result_img)

def send_click(hwnd, x, y):
    """发送SendMessage点击"""
    pos = (y << 16) | (x & 0xFFFF)
    try:
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        time.sleep(0.1)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        return True
    except Exception as e:
        print(f"点击失败: {e}")
        return False

def main():
    print("=== 查找并点击参加按钮 ===")
    
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return
    
    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: HWND={hwnd}, Title={windows[0]['title']}")
    
    # 截图
    print("\n正在截图...")
    img = capture_bitblt(hwnd)
    if img is None:
        print("截图失败！")
        return
    
    img_cv2 = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "current_screen.png")
    cv2.imwrite(save_path, img_cv2)
    print(f"截图已保存: {save_path}")
    print(f"图像尺寸: {img_cv2.shape[1]}x{img_cv2.shape[0]}")
    
    # 分析图像查找按钮
    print("\n正在分析图像查找按钮...")
    button_results = find_button_by_color(img_cv2)
    
    if button_results:
        print(f"\n找到 {len(button_results)} 个候选按钮区域:")
        for i, btn in enumerate(button_results[:10]):
            print(f"  {i+1}. 颜色={btn['color']}, 中心=({btn['x']},{btn['y']}), "
                  f"区域={btn['rect']}, 面积={btn['area']:.0f}, 宽高比={btn['aspect_ratio']:.2f}")
        
        # 保存标记图
        marked_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "marked_screen.png")
        draw_results(img_cv2, button_results[:10], marked_path)
        print(f"\n标记图已保存: {marked_path}")
        print("请查看marked_screen.png确认哪个是参加按钮")
        
        # 自动点击第一个候选（最大面积的）
        print(f"\n尝试点击第1个候选按钮 (最大面积): ({button_results[0]['x']}, {button_results[0]['y']})")
        send_click(hwnd, button_results[0]['x'], button_results[0]['y'])
        print("点击已发送，等待3秒观察响应...")
        time.sleep(3)
        
        # 重新截图确认
        print("\n重新截图确认点击效果...")
        img2 = capture_bitblt(hwnd)
        if img2:
            img2_cv2 = cv2.cvtColor(np.array(img2), cv2.COLOR_RGB2BGR)
            after_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "after_click.png")
            cv2.imwrite(after_path, img2_cv2)
            print(f"点击后截图已保存: {after_path}")
    else:
        print("未找到候选按钮区域")
        print("请查看current_screen.png手动确认按钮位置")
    
    print("\n=== 完成 ===")

if __name__ == "__main__":
    main()
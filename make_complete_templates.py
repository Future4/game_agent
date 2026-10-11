import cv2
import os
import time
import numpy as np
import win32gui
import win32con
import ctypes

templates_dir = "templates"

def find_game_window():
    results = []
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            if "梦幻西游" in title or "Unity" in class_name:
                results.append({'hwnd': hwnd, 'title': title, 'class': class_name})
    win32gui.EnumWindows(callback, None)
    return results

def capture_window(hwnd):
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width = right - left
    height = bottom - top

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = ctypes.windll.user32.GetDC(0)
    save_dc = ctypes.windll.gdi32.CreateCompatibleDC(mfc_dc)
    save_bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(mfc_dc, width, height)
    ctypes.windll.gdi32.SelectObject(save_dc, save_bitmap)
    ctypes.windll.user32.PrintWindow(hwnd, save_dc, 2)

    bmp_info = ctypes.create_string_buffer(1024)
    ctypes.windll.gdi32.GetDIBits(save_dc, save_bitmap, 0, height, bmp_info, 40)
    img = np.frombuffer(bmp_info.raw, dtype=np.uint8).reshape((height, width, 4))
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    ctypes.windll.gdi32.DeleteObject(save_bitmap)
    ctypes.windll.gdi32.DeleteDC(save_dc)
    ctypes.windll.user32.ReleaseDC(hwnd, hwnd_dc)
    ctypes.windll.user32.ReleaseDC(0, mfc_dc)
    return img

print("=== 制作师门任务完成模板 ===")
print("\n请先完成师门任务，确保出现【师门任务完成】弹窗")
print("然后按回车开始截图")
input()

windows = find_game_window()
if not windows:
    print("未找到游戏窗口")
    exit()

hwnd = windows[0]['hwnd']
print(f"游戏窗口: {windows[0]['title']}")

print("\n3秒后截图...")
time.sleep(3)

img = capture_window(hwnd)
cv2.imwrite("complete_screenshot.png", img)
print(f"截图已保存: complete_screenshot.png ({img.shape[1]}x{img.shape[0]})")

h, w = img.shape[:2]
print(f"\n截图尺寸: {w}x{h}")

# 显示图像供用户选择
print("\n=== 请在弹出的窗口中选择模板区域 ===")
print("1. 先用鼠标框选【师门任务完成】弹窗整体 → 回车")
print("2. 再框选【确定】按钮 → 回车")

# 转换RGB供显示
display = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

# 让用户选择弹窗区域
print("\n--- 步骤1: 框选【师门任务完成】弹窗 ---")
roi1 = cv2.selectROI("Select complete popup (press ENTER to confirm)", display, showCrosshair=True)
cv2.destroyAllWindows()

if roi1[2] > 0 and roi1[3] > 0:
    x, y, rw, rh = roi1
    popup_img = img[y:y+rh, x:x+rw]
    cv2.imwrite(os.path.join(templates_dir, "sect_complete.png"), popup_img)
    print(f"✓ 师门任务完成弹窗: 位置({x},{y}) 尺寸{rw}x{rh}")
else:
    print("✗ 未选择弹窗区域")

# 让用户选择确定按钮
print("\n--- 步骤2: 框选【确定】按钮 ---")
roi2 = cv2.selectROI("Select confirm button (press ENTER to confirm)", display, showCrosshair=True)
cv2.destroyAllWindows()

if roi2[2] > 0 and roi2[3] > 0:
    x, y, rw, rh = roi2
    btn_img = img[y:y+rh, x:x+rw]
    cv2.imwrite(os.path.join(templates_dir, "confirm_btn.png"), btn_img)
    print(f"✓ 确定按钮: 位置({x},{y}) 尺寸{rw}x{rh}")
else:
    print("✗ 未选择按钮区域")

# 标注并保存结果
annotated = img.copy()
if roi1[2] > 0 and roi1[3] > 0:
    x, y, rw, rh = roi1
    cv2.rectangle(annotated, (x, y), (x+rw, y+rh), (0, 255, 0), 2)
    cv2.putText(annotated, "complete", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
if roi2[2] > 0 and roi2[3] > 0:
    x, y, rw, rh = roi2
    cv2.rectangle(annotated, (x, y), (x+rw, y+rh), (0, 0, 255), 2)
    cv2.putText(annotated, "confirm", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
cv2.imwrite("complete_templates_annotated.png", annotated)

print("\n✓ 模板制作完成!")
print(f"  - {templates_dir}/sect_complete.png (师门任务完成弹窗)")
print(f"  - {templates_dir}/confirm_btn.png (确定按钮)")
print(f"\n标注图已保存: complete_templates_annotated.png")

# 测试模板匹配
print("\n=== 测试模板匹配 ===")
time.sleep(1)
test_img = capture_window(hwnd)

for tpl_file, label in [("sect_complete.png", "完成弹窗"), ("confirm_btn.png", "确定按钮")]:
    tpl_path = os.path.join(templates_dir, tpl_file)
    if os.path.exists(tpl_path):
        tpl = cv2.imread(tpl_path)
        result = cv2.matchTemplate(test_img, tpl, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        th, tw = tpl.shape[:2]
        if max_val > 0.7:
            print(f"  ✓ {label}: 位置({max_loc[0]},{max_loc[1]}) 尺寸{tw}x{th} 置信度{max_val:.3f}")
        else:
            print(f"  ✗ {label}: 置信度{max_val:.3f} 太低，可能需要重新制作")

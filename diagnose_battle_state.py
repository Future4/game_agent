"""战斗状态特征诊断脚本

分析多个候选区域的图像特征，找出最可靠的战斗/非战斗区分方法。

使用方法：
1. 在战斗中运行：python diagnose_battle_state.py
2. 在非战斗中运行：python diagnose_battle_state.py
3. 对比两次输出的特征值，找出差异最大的区域和特征
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
import cv2
import numpy as np
import win32gui


def find_game_window():
    results = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            c = win32gui.GetClassName(hwnd)
            if "梦幻西游" in t or c == "UnityWndClass":
                results.append((hwnd, t))
    win32gui.EnumWindows(cb, None)
    return results


def calc_features(region_bgr):
    """计算区域的多个特征"""
    gray = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2GRAY)
    # Canny 边缘密度（边缘像素占比）
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.count_nonzero(edges) / edges.size
    return {
        'mean': float(np.mean(gray)),
        'std': float(np.std(gray)),
        'edge_density': float(edge_density),
    }


def main():
    print("=== 战斗状态特征诊断 ===")
    print("请在战斗中或非战斗中运行，对比特征差异")
    print()

    results = find_game_window()
    if not results:
        print("未找到游戏窗口")
        return

    hwnd = results[0][0]
    print(f"窗口: {results[0][1]}")

    sc = ScreenshotCapture()
    img = sc.capture_to_cv2(hwnd)
    if img is None:
        print("截图失败")
        return

    h, w = img.shape[:2]
    print(f"尺寸: {w}x{h}")

    # 保存全图
    cv2.imwrite("diag_state_full.png", img)

    # 候选区域
    regions = {
        "顶部中间-阵法图案区": (int(w*0.55), 40, int(w*0.10), 60),
        "顶部中间-大区域": (w//4, 0, w//2, 100),
        "顶部正中间-回合数": (int(w*0.45), 30, int(w*0.10), 50),
        "底部-全宽技能栏": (0, h-120, w, 120),
        "底部中间-技能栏": (int(w*0.2), h-100, int(w*0.6), 100),
        "底部左-技能栏": (0, h-100, int(w*0.5), 100),
    }

    print(f"\n{'区域':<25} {'均值':>8} {'标准差':>8} {'边缘密度':>10}")
    print("-" * 55)

    annotated = img.copy()
    colors = [(0,255,0), (255,255,0), (0,255,255), (255,0,0), (0,0,255), (255,0,255)]

    for i, (name, (x, y, rw, rh)) in enumerate(regions.items()):
        x2 = min(x + rw, w)
        y2 = min(y + rh, h)
        region = img[y:y2, x:x2]
        feat = calc_features(region)
        print(f"{name:<25} {feat['mean']:>8.1f} {feat['std']:>8.1f} {feat['edge_density']:>10.4f}")

        # 标注
        color = colors[i % len(colors)]
        cv2.rectangle(annotated, (x, y), (x2, y2), color, 2)
        cv2.putText(annotated, str(i+1), (x, y-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    cv2.imwrite("diag_state_annotated.png", annotated)
    print(f"\n已保存:")
    print(f"  diag_state_full.png (全图)")
    print(f"  diag_state_annotated.png (标注各区域)")
    print(f"\n请对比战斗中/非战斗中的特征值，找出差异最大的区域")


if __name__ == "__main__":
    main()

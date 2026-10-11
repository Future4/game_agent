import cv2
import os

img = cv2.imread("current_screen.png")
if img is None:
    print("无法读取current_screen.png")
    exit()

buttons = [
    (1, 51, 446, 106, 56),
    (2, 52, 139, 105, 38),
    (3, 358, 226, 57, 36),
    (4, 612, 296, 57, 36),
    (5, 358, 296, 57, 36),
    (6, 612, 226, 57, 36),
    (7, 612, 157, 57, 35),
    (8, 53, 286, 103, 26),
    (9, 230, 408, 52, 51),
    (10, 53, 241, 91, 26),
]

out_dir = "button_crops"
os.makedirs(out_dir, exist_ok=True)

for idx, x, y, w, h in buttons:
    crop = img[y:y+h, x:x+w]
    path = os.path.join(out_dir, f"btn_{idx}.png")
    cv2.imwrite(path, crop)
    print(f"btn_{idx}: ({x},{y}) {w}x{h} -> {path}")

# 同时生成一张放大2倍的标注图方便查看
marked = img.copy()
for idx, x, y, w, h in buttons:
    color = (0, 0, 255) if idx <= 3 else (0, 255, 255)
    cv2.rectangle(marked, (x, y), (x+w, y+h), color, 2)
    cv2.putText(marked, str(idx), (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

# 放大1.5倍
h, w = marked.shape[:2]
marked_big = cv2.resize(marked, (int(w*1.5), int(h*1.5)), interpolation=cv2.INTER_LINEAR)
cv2.imwrite("marked_big.png", marked_big)
print("\nmarked_big.png saved")
print("done")
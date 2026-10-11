import cv2
import numpy as np
from PIL import Image
from typing import Optional, List, Tuple, Dict, Any
import logging
import os

logger = logging.getLogger(__name__)

try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except Exception as exc:
    # PaddleOCR may fail while loading optional Torch/oneDNN DLLs. Vision
    # still supports template matching and Tesseract, so do not prevent the
    # desktop client from starting.
    logger = logging.getLogger(__name__)
    logger.warning("PaddleOCR不可用，将不使用该识别引擎：%s", exc)
    PaddleOCR = None
    PADDLE_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except Exception as exc:
    logger = logging.getLogger(__name__)
    logger.warning("Tesseract不可用，将不使用该识别引擎：%s", exc)
    pytesseract = None
    TESSERACT_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except Exception as exc:
    logger = logging.getLogger(__name__)
    logger.warning("YOLO不可用，将不使用该识别引擎：%s", exc)
    YOLO = None
    YOLO_AVAILABLE = False

# Windows 内置 OCR（首选：本机 PaddleOCR/Tesseract 都因原生库初始化失败不可用）
try:
    from .windows_ocr import WindowsOCR
    WINDOWS_OCR_AVAILABLE = True
except Exception as exc:
    logger.warning("Windows内置OCR不可用，将不使用该识别引擎：%s", exc)
    WindowsOCR = None
    WINDOWS_OCR_AVAILABLE = False


class ImagePreprocessor:
    """图像预处理工具"""

    @staticmethod
    def to_grayscale(img: np.ndarray) -> np.ndarray:
        """转换为灰度图"""
        if len(img.shape) == 3:
            return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img

    @staticmethod
    def threshold(img: np.ndarray, threshold: int = 127, max_val: int = 255,
                  mode: int = cv2.THRESH_BINARY) -> np.ndarray:
        """二值化处理"""
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, result = cv2.threshold(img, threshold, max_val, mode)
        return result

    @staticmethod
    def adaptive_threshold(img: np.ndarray, block_size: int = 11, C: int = 2) -> np.ndarray:
        """自适应阈值"""
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, C)

    @staticmethod
    def denoise(img: np.ndarray, ksize: int = 3) -> np.ndarray:
        """去噪"""
        return cv2.GaussianBlur(img, (ksize, ksize), 0)

    @staticmethod
    def sharpen(img: np.ndarray) -> np.ndarray:
        """锐化"""
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        return cv2.filter2D(img, -1, kernel)

    @staticmethod
    def crop(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
        """裁剪区域"""
        h_img, w_img = img.shape[:2]
        x_start = max(0, x)
        y_start = max(0, y)
        x_end = min(w_img, x + w)
        y_end = min(h_img, y + h)
        return img[y_start:y_end, x_start:x_end]

    @staticmethod
    def resize(img: np.ndarray, scale: float) -> np.ndarray:
        """缩放图像"""
        return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    @staticmethod
    def preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
        """OCR预处理流程"""
        # 转换为灰度
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # 去噪
        denoised = cv2.GaussianBlur(gray, (3, 3), 0)
        # 自适应阈值
        result = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        return result

    @staticmethod
    def preprocess_for_template(img: np.ndarray) -> np.ndarray:
        """模板匹配预处理流程"""
        # 转换为灰度
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # 去噪
        result = cv2.GaussianBlur(gray, (3, 3), 0)
        return result


class TemplateMatcher:
    """模板匹配器"""

    def __init__(self, template_dir: str = "templates"):
        self.template_dir = template_dir
        self.templates: Dict[str, np.ndarray] = {}
        self.templates_gray: Dict[str, np.ndarray] = {}
        self._load_templates()

    def _load_templates(self):
        """加载模板。

        支持两种命名：
          1. 根目录平铺：templates/daily_activity.png        -> 名字 "daily_activity"
          2. 子目录（与 Maa_MHXY 一致）：templates/zonghe/jiahao.png -> 名字 "zonghe/jiahao"
             这样 pipeline 里的 "template": ["zonghe/jiahao.png"] 可以直接对应过来。
        子目录模板同时用 basename 注册一个别名（若未被占用），方便简写引用。
        """
        if not os.path.exists(self.template_dir):
            logger.warning(f"模板目录不存在: {self.template_dir}")
            return

        def _register(name, path):
            template = cv2.imread(path, cv2.IMREAD_COLOR)
            if template is None:
                logger.warning(f"模板读取失败: {path}")
                return
            self.templates[name] = template
            self.templates_gray[name] = ImagePreprocessor.preprocess_for_template(template)
            logger.debug(f"加载模板: {name} ({template.shape})")

        paths = []
        for root, _dirs, files in os.walk(self.template_dir):
            for filename in files:
                if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                    paths.append(os.path.join(root, filename))
        # 根目录优先，保证既有平铺模板名不被同名子目录模板覆盖
        paths.sort(key=lambda p: (os.path.dirname(p) != self.template_dir, p))

        for path in paths:
            rel = os.path.relpath(path, self.template_dir).replace(os.sep, "/")
            name = os.path.splitext(rel)[0]
            if name not in self.templates:
                _register(name, path)
            basename = os.path.splitext(os.path.basename(path))[0]
            if basename != name and basename not in self.templates and name in self.templates:
                self.templates[basename] = self.templates[name]
                self.templates_gray[basename] = self.templates_gray[name]
        logger.info("已加载模板 %d 个（根目录+子目录）", len(self.templates))

    def match(self, source_img: np.ndarray, template_name: str,
              threshold: float = 0.8, method: int = cv2.TM_CCOEFF_NORMED,
              use_preprocess: bool = True) -> Optional[Tuple[int, int, float]]:
        """模板匹配，返回中心点坐标和置信度"""
        if template_name not in self.templates:
            logger.error(f"模板不存在: {template_name}")
            return None

        template = self.templates_gray[template_name] if use_preprocess else self.templates[template_name]
        source = ImagePreprocessor.preprocess_for_template(source_img) if use_preprocess else source_img

        h, w = template.shape[:2]

        if source.shape[0] < h or source.shape[1] < w:
            logger.error(f"源图像太小: {source.shape} vs 模板: {template.shape}")
            return None

        result = cv2.matchTemplate(source, template, method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            if min_val < (1 - threshold):
                return (min_loc[0] + w // 2, min_loc[1] + h // 2, 1 - min_val)
        else:
            if max_val >= threshold:
                return (max_loc[0] + w // 2, max_loc[1] + h // 2, max_val)

        return None

    def match_multiscale(self, source_img: np.ndarray, template_name: str,
                         threshold: float = 0.7,
                         scales: Tuple[float, ...] = (0.50, 0.60, 0.75, 0.85, 1.0, 1.15, 1.30, 1.50, 1.75, 2.0)) -> Optional[Tuple[int, int, float, float]]:
        """Match a template when source and template have different DPI scales."""
        if template_name not in self.templates:
            logger.error("模板不存在: %s", template_name)
            return None
        source = ImagePreprocessor.preprocess_for_template(source_img)
        original = self.templates_gray[template_name]
        best = None
        for scale in scales:
            h0, w0 = original.shape[:2]
            resized = cv2.resize(original, (max(1, int(w0 * scale)), max(1, int(h0 * scale))), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
            h, w = resized.shape[:2]
            if h > source.shape[0] or w > source.shape[1]:
                continue
            result = cv2.matchTemplate(source, resized, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(result)
            candidate = (loc[0] + w // 2, loc[1] + h // 2, float(score), scale)
            if best is None or candidate[2] > best[2]:
                best = candidate
        logger.debug("多尺度模板=%s，最佳结果=%s，阈值=%.2f", template_name, best, threshold)
        return best if best and best[2] >= threshold else None

    def match_multiscale_region(self, source_img: np.ndarray, template_name: str,
                                region: Tuple[int, int, int, int],
                                threshold: float = 0.7):
        """Multi-scale match in a region, returning coordinates in full image."""
        x, y, w, h = region
        cropped = ImagePreprocessor.crop(source_img, x, y, w, h)
        result = self.match_multiscale(cropped, template_name, threshold)
        if result is None:
            return None
        return (result[0] + x, result[1] + y, result[2], result[3])

    def match_all(self, source_img: np.ndarray, template_name: str,
                  threshold: float = 0.8) -> List[Tuple[int, int, float]]:
        """查找所有匹配位置"""
        if template_name not in self.templates:
            logger.error(f"模板不存在: {template_name}")
            return []

        template = self.templates_gray[template_name]
        source = ImagePreprocessor.preprocess_for_template(source_img)

        h, w = template.shape[:2]

        if source.shape[0] < h or source.shape[1] < w:
            return []

        result = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        matches = []
        for pt in zip(*locations[::-1]):
            matches.append((pt[0] + w // 2, pt[1] + h // 2, result[pt[1], pt[0]]))

        return matches

    def add_template(self, name: str, template: np.ndarray):
        """添加模板"""
        self.templates[name] = template
        self.templates_gray[name] = ImagePreprocessor.preprocess_for_template(template)
        logger.debug(f"添加模板: {name} ({template.shape})")

    def match_region(self, source_img: np.ndarray, template_name: str,
                     region: Tuple[int, int, int, int], threshold: float = 0.8) -> Optional[Tuple[int, int, float]]:
        """在指定区域内进行模板匹配"""
        x, y, w, h = region
        region_img = ImagePreprocessor.crop(source_img, x, y, w, h)
        result = self.match(region_img, template_name, threshold)

        if result:
            # 转换为全局坐标
            return (result[0] + x, result[1] + y, result[2])
        return None


class OCREngine:
    """OCR识别引擎

    优先级：Windows 内置 OCR(winsdk) > PaddleOCR > Tesseract。
    本机 PaddleOCR 因 torch c10.dll、Tesseract 因 numpy ABI 均初始化失败，
    因此 Windows 内置识别器实际承担全部 OCR 工作。
    """

    def __init__(self, use_paddle: bool = True, lang: str = "ch"):
        self.lang = lang
        self.windows_ocr = None
        if WINDOWS_OCR_AVAILABLE and WindowsOCR is not None:
            candidate = WindowsOCR()
            if candidate.available:
                self.windows_ocr = candidate
        # Windows OCR 可用时不再加载 PaddleOCR（它本就加载失败且拖慢启动）
        self.use_paddle = use_paddle and PADDLE_AVAILABLE and self.windows_ocr is None
        self.paddle_ocr = None
        self._init_ocr()

    def _init_ocr(self):
        if self.use_paddle:
            try:
                self.paddle_ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang=self.lang,
                    show_log=False,
                    use_gpu=False
                )
                logger.info("PaddleOCR 初始化成功")
            except Exception as e:
                logger.error(f"PaddleOCR 初始化失败: {e}")
                self.use_paddle = False

        if not self.use_paddle:
            if TESSERACT_AVAILABLE:
                logger.info("使用 Tesseract OCR 作为备用")
            else:
                logger.warning("PaddleOCR 和 Tesseract 都不可用")

    def recognize(self, img: np.ndarray, use_preprocess: bool = True) -> List[Dict[str, Any]]:
        """OCR识别，返回文本列表"""
        # 1) Windows 内置 OCR：直接用原始彩色图，避免二值化破坏游戏字体
        if self.windows_ocr is not None:
            results = self.windows_ocr.recognize(img)
            if results:
                return results

        results = []

        if use_preprocess:
            processed_img = ImagePreprocessor.preprocess_for_ocr(img)
        else:
            processed_img = img

        if self.use_paddle and self.paddle_ocr:
            try:
                ocr_results = self.paddle_ocr.ocr(processed_img, cls=True)
                if ocr_results and ocr_results[0]:
                    for line in ocr_results[0]:
                        results.append({
                            'text': line[1][0],
                            'confidence': line[1][1],
                            'box': line[0],
                            'center': (
                                int((line[0][0][0] + line[0][2][0]) / 2),
                                int((line[0][0][1] + line[0][2][1]) / 2)
                            )
                        })
            except Exception as e:
                logger.error(f"PaddleOCR 识别失败: {e}")

        elif TESSERACT_AVAILABLE:
            try:
                img_pil = Image.fromarray(cv2.cvtColor(processed_img, cv2.COLOR_BGR2RGB))
                data = pytesseract.image_to_data(img_pil, lang=self.lang, output_type=pytesseract.Output.DICT)

                for i in range(len(data['text'])):
                    text = data['text'][i].strip()
                    if text:
                        left, top, width, height = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                        results.append({
                            'text': text,
                            'confidence': int(data['conf'][i]) / 100.0 if data['conf'][i] != '-1' else 0.0,
                            'box': [
                                [left, top],
                                [left + width, top],
                                [left + width, top + height],
                                [left, top + height]
                            ],
                            'center': (left + width // 2, top + height // 2)
                        })
            except Exception as e:
                logger.error(f"Tesseract 识别失败: {e}")

        return results

    def find_text(self, img: np.ndarray, target_text: str,
                  threshold: float = 0.6, use_preprocess: bool = True) -> Optional[Tuple[int, int]]:
        """查找指定文本，返回中心点坐标"""
        results = self.recognize(img, use_preprocess)
        for result in results:
            if result['confidence'] >= threshold and target_text in result['text']:
                return result['center']
        return None

    def find_text_region(self, img: np.ndarray, target_text: str,
                         region: Tuple[int, int, int, int],
                         threshold: float = 0.6) -> Optional[Tuple[int, int]]:
        """在指定区域内查找文本"""
        x, y, w, h = region
        region_img = ImagePreprocessor.crop(img, x, y, w, h)
        result = self.find_text(region_img, target_text, threshold)

        if result:
            return (result[0] + x, result[1] + y)
        return None

    def contains_text(self, img: np.ndarray, target_text: str,
                      threshold: float = 0.6) -> bool:
        """检查图像中是否包含指定文本"""
        results = self.recognize(img)
        for result in results:
            if result['confidence'] >= threshold and target_text in result['text']:
                return True
        return False


class YOLODetector:
    """YOLO目标检测器"""

    def __init__(self, model_path: str = "yolov8n.pt", conf_threshold: float = 0.5):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.model = None
        self._init_yolo()

    def _init_yolo(self):
        if not YOLO_AVAILABLE:
            logger.warning("YOLO 不可用 (ultralytics 未安装)")
            return

        try:
            self.model = YOLO(self.model_path)
            logger.info(f"YOLO 模型加载成功: {self.model_path}")
        except Exception as e:
            logger.error(f"YOLO 模型加载失败: {e}")

    def detect(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """目标检测"""
        results = []

        if not self.model:
            return results

        try:
            detections = self.model(img, conf=self.conf_threshold, verbose=False)

            if detections and len(detections) > 0:
                for det in detections[0].boxes:
                    x1, y1, x2, y2 = det.xyxy[0].cpu().numpy()
                    center_x = int((x1 + x2) // 2)
                    center_y = int((y1 + y2) // 2)

                    results.append({
                        'class': int(det.cls[0].cpu().numpy()),
                        'class_name': detections[0].names[int(det.cls[0].cpu().numpy())],
                        'confidence': float(det.conf[0].cpu().numpy()),
                        'box': [x1, y1, x2, y2],
                        'center': (center_x, center_y)
                    })

            logger.debug(f"YOLO 检测到 {len(results)} 个目标")
        except Exception as e:
            logger.error(f"YOLO 检测失败: {e}")

        return results

    def find_object(self, img: np.ndarray, class_name: str,
                    threshold: float = 0.5) -> Optional[Tuple[int, int, float]]:
        """查找指定类别的目标"""
        if not self.model:
            return None

        try:
            detections = self.model(img, conf=threshold, verbose=False)

            if detections and len(detections) > 0:
                for det in detections[0].boxes:
                    name = detections[0].names[int(det.cls[0].cpu().numpy())]
                    if name == class_name:
                        x1, y1, x2, y2 = det.xyxy[0].cpu().numpy()
                        center_x = int((x1 + x2) // 2)
                        center_y = int((y1 + y2) // 2)
                        confidence = float(det.conf[0].cpu().numpy())
                        return (center_x, center_y, confidence)

            return None
        except Exception as e:
            logger.error(f"YOLO 查找目标失败: {e}")
            return None


class GameStateDetector:
    """游戏状态检测器"""

    def __init__(self, vision: 'Vision'):
        self.vision = vision

    def detect_state(self, img: np.ndarray) -> str:
        """检测当前游戏状态"""
        # 检查是否在主界面
        if self.is_main_menu(img):
            return "main_menu"

        # 检查是否在任务界面
        if self.is_task_interface(img):
            return "task_interface"

        # 检查是否在战斗界面
        if self.is_battle(img):
            return "battle"

        # 检查是否在移动中
        if self.is_moving(img):
            return "moving"

        # 默认状态
        return "unknown"

    def is_main_menu(self, img: np.ndarray) -> bool:
        """检测是否在主菜单"""
        # 通过OCR识别关键文本
        if self.vision.ocr.contains_text(img, "开始游戏"):
            return True
        if self.vision.ocr.contains_text(img, "登录"):
            return True
        return False

    def is_task_interface(self, img: np.ndarray) -> bool:
        """检测是否在任务界面"""
        if self.vision.ocr.contains_text(img, "任务"):
            return True
        if self.vision.ocr.contains_text(img, "师门"):
            return True
        if self.vision.ocr.contains_text(img, "参加"):
            return True
        return False

    def is_battle(self, img: np.ndarray) -> bool:
        """检测是否在战斗中"""
        if self.vision.ocr.contains_text(img, "战斗"):
            return True
        if self.vision.ocr.contains_text(img, "攻击"):
            return True
        if self.vision.ocr.contains_text(img, "逃跑"):
            return True
        return False

    def is_moving(self, img: np.ndarray) -> bool:
        """检测是否在移动中"""
        # 通过模板匹配检测移动指示器
        if self.vision.matcher.match(img, "moving_indicator"):
            return True
        return False

    def find_task_button(self, img: np.ndarray) -> Optional[Tuple[int, int]]:
        """查找任务按钮"""
        # 先尝试模板匹配
        result = self.vision.matcher.match(img, "task_button")
        if result:
            return (result[0], result[1])

        # 再尝试OCR
        result = self.vision.ocr.find_text(img, "任务")
        if result:
            return result

        return None

    def find_join_button(self, img: np.ndarray) -> Optional[Tuple[int, int]]:
        """查找参加按钮"""
        # OCR查找"参加"文本
        result = self.vision.ocr.find_text(img, "参加")
        if result:
            return result

        # 模板匹配
        result = self.vision.matcher.match(img, "join_button")
        if result:
            return (result[0], result[1])

        return None


class Vision:
    """视觉模块主类"""

    def __init__(self, template_dir: str = "templates", use_paddle_ocr: bool = True,
                 yolo_model_path: str = None):
        self.preprocessor = ImagePreprocessor()
        self.matcher = TemplateMatcher(template_dir)
        self.ocr = OCREngine(use_paddle=use_paddle_ocr)
        self.yolo = YOLODetector(model_path=yolo_model_path) if yolo_model_path else None
        self.state_detector = GameStateDetector(self)

    def detect_template(self, img: np.ndarray, template_name: str,
                        threshold: float = 0.8) -> Optional[Tuple[int, int, float]]:
        """模板匹配"""
        return self.matcher.match(img, template_name, threshold)

    def detect_template_multiscale(self, img: np.ndarray, template_name: str,
                                   threshold: float = 0.7):
        return self.matcher.match_multiscale(img, template_name, threshold)

    def detect_template_multiscale_region(self, img: np.ndarray, template_name: str,
                                          region: Tuple[int, int, int, int], threshold: float = 0.7):
        return self.matcher.match_multiscale_region(img, template_name, region, threshold)

    def detect_template_region(self, img: np.ndarray, template_name: str,
                               region: Tuple[int, int, int, int],
                               threshold: float = 0.8) -> Optional[Tuple[int, int, float]]:
        """在指定区域内模板匹配"""
        return self.matcher.match_region(img, template_name, region, threshold)

    def detect_text(self, img: np.ndarray, text: str,
                    threshold: float = 0.6) -> Optional[Tuple[int, int]]:
        """查找文本"""
        return self.ocr.find_text(img, text, threshold)

    def detect_text_region(self, img: np.ndarray, text: str,
                           region: Tuple[int, int, int, int],
                           threshold: float = 0.6) -> Optional[Tuple[int, int]]:
        """在指定区域内查找文本"""
        return self.ocr.find_text_region(img, text, region, threshold)

    def get_all_text(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """获取图像中所有文本"""
        return self.ocr.recognize(img)

    def contains_text(self, img: np.ndarray, text: str,
                      threshold: float = 0.6) -> bool:
        """检查是否包含文本"""
        return self.ocr.contains_text(img, text, threshold)

    def detect_objects(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """YOLO目标检测"""
        if self.yolo:
            return self.yolo.detect(img)
        return []

    def find_object(self, img: np.ndarray, class_name: str,
                    threshold: float = 0.5) -> Optional[Tuple[int, int, float]]:
        """查找指定目标"""
        if self.yolo:
            return self.yolo.find_object(img, class_name, threshold)
        return None

    def detect_state(self, img: np.ndarray) -> str:
        """检测游戏状态"""
        return self.state_detector.detect_state(img)

    def find_task_button(self, img: np.ndarray) -> Optional[Tuple[int, int]]:
        """查找任务按钮"""
        return self.state_detector.find_task_button(img)

    def find_join_button(self, img: np.ndarray) -> Optional[Tuple[int, int]]:
        """查找参加按钮"""
        return self.state_detector.find_join_button(img)

    def add_template(self, name: str, template: np.ndarray):
        """添加模板"""
        self.matcher.add_template(name, template)

    def preprocess(self, img: np.ndarray, mode: str = "ocr") -> np.ndarray:
        """预处理图像"""
        if mode == "ocr":
            return self.preprocessor.preprocess_for_ocr(img)
        elif mode == "template":
            return self.preprocessor.preprocess_for_template(img)
        else:
            return img

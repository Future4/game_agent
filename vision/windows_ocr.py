# -*- coding: utf-8 -*-
"""Windows 内置 OCR（Windows.Media.Ocr）封装，通过 winsdk 调用。

本机 PaddleOCR(torch c10.dll) 与 Tesseract(numpy ABI) 都因原生库初始化失败不可用，
但系统自带的 zh-Hans-CN 识别器可用，因此作为首选 OCR 引擎。

返回结构与 vision.OCREngine.recognize 一致：
    [{'text': str, 'confidence': float, 'box': [[x,y],...], 'center': (cx, cy)}, ...]
"""
import asyncio
import logging
import os
import tempfile
from typing import Any, Dict, List

import cv2

logger = logging.getLogger(__name__)

try:
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage import FileAccessMode, StorageFile

    WINSDK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.warning("Windows OCR(winsdk) 不可用：%s", exc)
    WINSDK_AVAILABLE = False


class WindowsOCR:
    """基于 Windows.Media.Ocr 的离线中文 OCR。"""

    def __init__(self, lang: str = "zh-Hans-CN"):
        self.lang = lang
        self._engine = None
        if not WINSDK_AVAILABLE:
            return
        try:
            self._engine = OcrEngine.try_create_from_language(Language(lang))
            if self._engine is None:
                self._engine = OcrEngine.try_create_from_user_profile_languages()
            if self._engine is not None:
                logger.info("Windows OCR 就绪：%s", self._engine.recognizer_language.language_tag)
            else:
                logger.warning("Windows OCR 无可用识别语言")
        except Exception as exc:
            logger.error("Windows OCR 初始化失败：%s", exc)

    @property
    def available(self) -> bool:
        return self._engine is not None

    async def _recognize_path(self, path: str) -> List[Dict[str, Any]]:
        storage_file = await StorageFile.get_file_from_path_async(path)
        stream = await storage_file.open_async(FileAccessMode.READ)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await self._engine.recognize_async(bitmap)

        out: List[Dict[str, Any]] = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            xs = [w.bounding_rect.x for w in words]
            ys = [w.bounding_rect.y for w in words]
            xe = [w.bounding_rect.x + w.bounding_rect.width for w in words]
            ye = [w.bounding_rect.y + w.bounding_rect.height for w in words]
            x, y = int(min(xs)), int(min(ys))
            bw, bh = int(max(xe)) - x, int(max(ye)) - y
            out.append({
                "text": "".join(w.text for w in words),
                "confidence": 1.0,
                "box": [[x, y], [x + bw, y], [x + bw, y + bh], [x, y + bh]],
                "center": (x + bw // 2, y + bh // 2),
            })
        return out

    def recognize(self, img) -> List[Dict[str, Any]]:
        if not self.available or img is None:
            return []
        fd, path = tempfile.mkstemp(suffix=".png", prefix="mhxy_ocr_")
        os.close(fd)
        try:
            cv2.imwrite(path, img)
            return asyncio.run(self._recognize_path(path))
        except Exception as exc:
            logger.error("Windows OCR 识别失败：%s", exc)
            return []
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

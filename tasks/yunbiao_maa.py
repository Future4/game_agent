# -*- coding: utf-8 -*-
"""运镖普通 —— 按 Maa_MHXY 的 yunbiao_renwu2.json 流水线原样移植到 game_agent。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/yunbiao_renwu2.json
    (+ 共享节点: my_task.json「panduan_zhujiemian / 识别拓印_停止 / 关闭拓印界面 /
       战斗中-等待20秒」 baotu_renwu.json「baotu_huodong_down / 战斗平衡弹窗-点击关闭」
       sanjieqiyuan.json「活动-界面-打开失败-点击活动图片」)

======================= Maa 原始流程(节点图) =======================
yunbiao_renwu2 (entry)
  next:
    主界面-运镖                   主界面(+/称号/包裹) -> ClickKey[57,31](Alt+C 打开活动)
    [JumpBack]panduan_zhujiemian  不在主界面 -> ESC 返回

主界面-运镖 next:
    活动-运镖                            活动面板判断(huodong_jiemian_panduan)
    [JumpBack]活动-界面-打开失败-点击活动图片  点活动图标(huodong1/2 或 OCR"活动")
    [JumpBack]战斗平衡弹窗-点击关闭

活动-运镖 -> 活动-运镖-检查活跃度agent (OCRNum, 选项"是否检测活力到50"=Yes 时;
             No 时直接进下一步) -> 活动-运镖-点击日常活动 (OCR"日常活动")
  -> 活动-运镖-向上滑动到顶端 (MultiSwipe x2)
  -> 活动-运镖-开始 (yunbiao_cishu0/1/2[+_2], 阈值0.9; 找不到 [JumpBack]baotu_huodong_down 下滑, max_hit 6)
  -> 活动-运镖-开始-点击参加 (OCR"参加")

点击参加 next (监控循环):
    识别拓印_停止                 遇见拓印 -> 关闭拓印界面(guanbi6/7) -> 停止所有任务
    [JumpBack]点击押送普通镖银(三次)  OCR"押送普通镖银"(max_hit 3) -> 点击押送普通镖_确定(OCR"确定")
    [JumpBack]运镖中              OCR"距离运镖完成" -> 等10秒
    [JumpBack]战斗中-等待20秒
    运镖完成                     回到主界面(+/称号/包裹) -> 结束

======================= 移植适配说明 =======================
官网 PC 客户端(Unity) 与 Maa 的模拟器(1280x720) 不同:
  1. 布局非等比, roi 由 Maa 像素坐标换算为窗口比例并适当放大, 模板匹配用多尺度。
  2. ClickKey[57,31] = Alt+C 开活动面板, 用 win32 keybd_event 实现;
     失败回退点活动图标(zonghe/huodong1|2, 官网实测可命中)。
  3. OCR(日常活动/参加/押送普通镖银/确定/距离运镖完成) 走整图识别+ROI 中心过滤(带缓存)。
  4. 战斗检测沿用本机已验证的「顶部圆形一致性(HoughCircles)」方案。
  5. 运镖行模板: Maa 的 yunbiao_cishu* 优先, 匹配不上回退本机采集的 escort_module。
  6. 选项"是否检测活力到50"映射为类常量 CHECK_HUODU_50(默认 False, 与 Maa 建议一致)。
"""

import logging
import re
import time
from typing import Callable, Optional, Sequence, Tuple

from domain.tasks import TaskContext, TaskDefinition, TaskSnapshot, TaskStatus
from tasks.base import AutomationTask

logger = logging.getLogger(__name__)

Region = Tuple[int, int, int, int]  # x, y, w, h（截图坐标）


class _Aborted(Exception):
    """停止/超时信号。"""


class YunbiaoMaaTask(AutomationTask):
    definition = TaskDefinition(
        "yunbiao_maa", "运镖普通", "移植自 Maa_MHXY 的 yunbiao_renwu2 流水线"
    )

    # ---------------- 时序参数（对应 Maa 流水线字段）----------------
    poll_interval = 0.5
    node_timeout = 90.0          # 单节点等待上限(秒)
    battle_wait = 20.0           # Maa: 战斗中-等待20秒 (pre_delay 20000)
    escorting_wait = 10.0        # Maa: 运镖中 (pre_delay 10000)
    list_swipe_max = 6           # Maa: baotu_huodong_down (max_hit 6)
    total_timeout = 3600.0       # 3 趟镖耗时较长，整个任务上限 60 分钟

    # ---------------- 可调开关 ----------------
    CHECK_HUODU_50 = False       # Maa 选项「是否检测活力到50」(建议不检测, 默认 False)
    HUODU_MIN = 50               # 活跃度低于该值则不做运镖(对应 OCRNum 的判断)
    yasong_max = 3               # Maa: 点击押送普通镖银(三次) max_hit 3
    ocr_cache_seconds = 2.0      # OCR 整图识别结果缓存时长(秒)
    finish_confirm_hits = 2      # 连续 N 次判定在主界面才认定运镖完成

    # ---------------- 阈值（官网客户端实测校准，沿用宝图任务经验值）----------------
    TH_MAIN_INDICATOR = 0.75
    TH_ACTIVITY_PANEL = 0.75
    TH_ACTIVITY_BUTTON = 0.60
    TH_YUNBIAO_START = 0.90      # Maa: 活动-运镖-开始 threshold 0.9
    TH_ESCORT_MODULE = 0.80      # 本机采集的 escort_module 兜底
    TH_POPUP_CLOSE = 0.88
    TH_TAYIN = 0.90              # Maa: 识别拓印-子2/子3 threshold 0.9
    TH_TAYIN_CLOSE = 0.80

    # ---------------- 模板名（templates/ 目录，不带 .png）----------------
    # 命名与 Maa_MHXY-main/assets/resource/base/image 完全一致（保留子目录/相对路径）。
    # Maa「主界面-运镖」/「运镖完成」: zonghe/jiahao|chenghao|baoguo|baoguo_man
    T_MAIN_INDICATORS = ("zonghe/jiahao", "zonghe/baoguo", "zonghe/baoguo_man", "zonghe/chenghao")
    # Maa「活动-运镖」活动界面判断
    T_ACTIVITY_PANEL = ("zonghe/huodong_jiemian_panduan",)
    # Maa「活动-界面-打开失败-点击活动图片」优先，再回退本机采集的 activity_button
    T_ACTIVITY_BUTTON = ("zonghe/huodong1", "zonghe/huodong2", "activity_button")
    # Maa「活动-运镖-开始」: yunbiao_cishu0/1/2(+_2) + 本机实测运镖行模板
    T_YUNBIAO_START = (
        "yunbiao/yunbiao_cishu0", "yunbiao/yunbiao_cishu1", "yunbiao/yunbiao_cishu2",
        "yunbiao/yunbiao_cishu0_2", "yunbiao/yunbiao_cishu1_2", "yunbiao/yunbiao_cishu2_2",
        "escort_module",
    )
    # Maa「战斗平衡弹窗-点击关闭」
    T_POPUP_CLOSE = ("zonghe/zhandoupingheng_guanbi1",)
    # Maa「识别拓印-子2/子3」
    T_TAYIN = ("tayin/tayin", "tayin/tayin2")
    # Maa「关闭拓印界面」
    T_TAYIN_CLOSE = ("zonghe/guanbi6", "zonghe/guanbi7")

    # 参加按钮在运镖行模板内相对中心的像素偏移（与宝图任务 treasure_row 同版式）
    JOIN_BTN_OFFSET_X = 105

    # ---------------- 区域比例（由 Maa 1280x720 像素 roi 换算并适当放大）----------------
    ROI_MAIN_INDICATOR = (0.86, 0.72, 0.14, 0.28)   # 右下角 +/称号/包裹
    ROI_ACTIVITY_PANEL = (0.20, 0.00, 0.62, 0.14)   # Maa [350,23,600,62] 放大
    ROI_ACTIVITY_BUTTON = (0.00, 0.00, 0.45, 0.30)  # 左上角活动入口
    ROI_DAILY_LEFT = (0.00, 0.05, 0.35, 0.50)       # Maa OCR"日常活动" [132,90,156,59] 放大
    ROI_LIST = (0.15, 0.08, 0.82, 0.72)             # Maa [316,76,834,433] 放大
    ROI_HUODU = (0.20, 0.78, 0.70, 0.16)            # Maa OCRNum 活跃度 [305,586,862,70] 放大
    ROI_YASONG = (0.64, 0.30, 0.34, 0.44)           # Maa OCR"押送普通镖银" [933,262,307,237] 放大
    ROI_QUEDING = (0.42, 0.42, 0.34, 0.28)          # Maa OCR"确定" [656,367,189,96] 放大
    ROI_ESCORTING = (0.04, 0.00, 0.38, 0.16)        # Maa OCR"距离运镖完成" [150,1,195,49] 放大
    ROI_TAYIN_OCR = (0.15, 0.18, 0.20, 0.25)        # Maa 识别拓印-子1 [295,185,51,84] 放大
    ROI_TAYIN_TPL1 = (0.14, 0.16, 0.22, 0.36)       # Maa 识别拓印-子2 [268,165,102,170] 放大
    ROI_TAYIN_TPL2 = (0.10, 0.45, 0.32, 0.48)       # Maa 识别拓印-子3 [205,381,269,249] 放大
    ROI_TAYIN_CLOSE = (0.62, 0.00, 0.36, 0.26)      # Maa 关闭拓印界面 [967,35,79,83] 放大

    # 滑动坐标（比例）
    SWIPE_LIST_X = 0.571         # Maa x=731~735/1280
    SWIPE_LIST_TOP_FROM = 0.179  # 滑到顶端：手指下滑 129 -> 444
    SWIPE_LIST_TOP_TO = 0.617
    SWIPE_LIST_DOWN_FROM = 0.528 # 列表向下翻：手指上滑 380 -> 250
    SWIPE_LIST_DOWN_TO = 0.347

    # ==================================================================
    # 主流程
    # ==================================================================
    def __init__(self) -> None:
        super().__init__()
        self._on_update = None
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._yasong_count = 0
        self._finished_hits = 0
        self._alt_c_pressed = False
        self._daily_clicked = False
        self._list_swipes = 0
        self._swipe_vertical = self._do_swipe_vertical
        self._ocr_cache = None

    def run(self, context: TaskContext,
            on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._yasong_count = 0
        self._finished_hits = 0
        self._alt_c_pressed = False
        self._daily_clicked = False
        self._list_swipes = 0
        self._swipe_vertical = self._do_swipe_vertical  # 允许测试替换
        self._ocr_cache = None

        logger.info("运镖普通启动 hwnd=%s", getattr(agent, "hwnd", None))
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 5
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            # 步骤2: Maa「主界面-运镖」—— Alt+C 打开活动面板
            ok_open = self._stage(agent, 2, "打开活动面板", self._node_open_activity)
            if not ok_open:
                self.snapshot.status = TaskStatus.FAILED
                self._report("未能打开活动界面，请检查窗口状态与模板")
                logger.error("窗口=%s 未能打开活动界面，任务未开始", agent.hwnd)
                return

            # Maa 选项「是否检测活力到50」-> OCRNum
            if self.CHECK_HUODU_50 and not self._check_huodu(agent):
                self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "收尾回主界面")
                self._finish(f"活跃度不足 {self.HUODU_MIN}，按 Maa 语义结束运镖")
                return

            # 步骤3: Maa「点击日常活动」-> 滑到顶端 -> 找运镖行(下滑最多6次)
            ok_find = self._stage(agent, 3, "进入日常活动并找到运镖", self._node_find_yunbiao)
            if not ok_find:
                self.snapshot.status = TaskStatus.FAILED
                self._report("未找到运镖任务入口（可能已完成或活动面板异常）")
                logger.error("窗口=%s 未找到运镖任务入口", agent.hwnd)
                return

            # 步骤4: Maa「活动-运镖-开始-点击参加」
            self._stage(agent, 4, "点击参加运镖", self._node_join)

            # 步骤5: Maa 监控循环（拓印/押送普通镖银/运镖中/战斗/完成判断）
            self._report("运镖进行中，等待完成")
            result = self._monitor_loop(agent)

            self.snapshot.completed_steps = self.snapshot.total_steps
            if result == "tayin":
                self.snapshot.status = TaskStatus.COMPLETED
                self._report("遇见拓印，按 Maa 语义停止任务")
            else:
                self.snapshot.status = TaskStatus.COMPLETED
                self._report("运镖普通完成")
            logger.info("运镖普通结束(%s) hwnd=%s", result, agent.hwnd)
        except _Aborted:
            logger.info("运镖普通停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("运镖普通执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("运镖普通执行异常，详见日志")

    # ------------------------------------------------------------------
    # 节点调度
    # ------------------------------------------------------------------
    def _stage(self, agent, index: int, label: str, node) -> bool:
        self.snapshot.completed_steps = index - 1
        self._report(f"步骤 {index}/{self.snapshot.total_steps}：{label}")
        logger.info("窗口=%s 开始步骤 %d：%s", agent.hwnd, index, label)
        ok = self._run_node(agent, node, self.node_timeout, label)
        logger.info("窗口=%s 步骤结束：%s -> %s", agent.hwnd, label, ok)
        return ok

    def _run_node(self, agent, node, timeout: float, label: str) -> bool:
        started = time.monotonic()
        while True:
            self._check_stop(agent)
            if node(agent):
                return True
            if time.monotonic() - started > timeout:
                logger.warning("窗口=%s 节点等待超时：%s", agent.hwnd, label)
                return False
            if self._sleep(self.poll_interval):
                raise _Aborted()

    def _sleep(self, seconds: float) -> bool:
        return self._stop_event.wait(seconds)

    def _check_stop(self, agent) -> None:
        if self._stop_event.is_set() or time.monotonic() > self._deadline:
            raise _Aborted()

    # ==================================================================
    # 节点1: panduan_zhujiemian
    # ==================================================================
    def _node_panduan_zhujiemian(self, agent) -> bool:
        if self._on_main_interface(agent):
            return True
        if self._in_battle(self._image(agent)):
            return False  # 战斗中不按 ESC
        if self._esc_presses >= 6:
            logger.warning("窗口=%s 已按 ESC 6 次仍未回主界面，继续后续流程", agent.hwnd)
            return True
        logger.info("窗口=%s 不在主界面，按 ESC 返回(%d/6)", agent.hwnd, self._esc_presses + 1)
        agent.press_key("esc")
        self._esc_presses += 1
        time.sleep(0.8)
        return False

    def _on_main_interface(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_MAIN_INDICATOR)
        return self._match_any(agent, self.T_MAIN_INDICATORS, roi, self.TH_MAIN_INDICATOR) is not None

    # ==================================================================
    # 节点2: 主界面-运镖 —— Alt+C 打开活动面板
    # ==================================================================
    def _node_open_activity(self, agent) -> bool:
        self._dismiss_popups(agent)  # [JumpBack]战斗平衡弹窗-点击关闭
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        panel_roi = self._fraction_region(w, h, self.ROI_ACTIVITY_PANEL)
        if self._match_any(agent, self.T_ACTIVITY_PANEL, panel_roi, self.TH_ACTIVITY_PANEL):
            logger.info("窗口=%s 活动面板已打开", agent.hwnd)
            return True
        if not getattr(self, "_alt_c_pressed", False):
            # Maa ClickKey[57,31] = Alt+C（安卓 keycode 57=ALT_LEFT, 31=C）
            self._press_hotkey(agent, "C")
            self._alt_c_pressed = True
            time.sleep(1.0)
            return False
        # [JumpBack]活动-界面-打开失败-点击活动图片：模板优先，OCR"活动"兜底
        btn_roi = self._fraction_region(w, h, self.ROI_ACTIVITY_BUTTON)
        m = self._match_any(agent, self.T_ACTIVITY_BUTTON, btn_roi, self.TH_ACTIVITY_BUTTON)
        if not m:
            pos = self._find_label_in(self._ocr_lines(agent), ("活动", "舌动"), btn_roi)
            if pos:
                m = (pos[0], pos[1], 0.0)
        if m:
            logger.info("窗口=%s 点击活动入口 %s", agent.hwnd, m[:2])
            agent.click(m[0], m[1])
            time.sleep(1.0)
        else:
            self._press_hotkey(agent, "C")  # 图标也没找到就再按一次快捷键
            time.sleep(1.0)
        return False

    def _press_hotkey(self, agent, letter: str) -> None:
        """Maa ClickKey[57, X] = Alt+字母，用 win32 keybd_event 实现。"""
        try:
            import win32api
            import win32con
        except Exception:
            return
        try:
            self._ensure_foreground(agent.hwnd)
            time.sleep(0.2)
            vk = ord(letter.upper())
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            logger.info("窗口=%s 按下 Alt+%s", agent.hwnd, letter.upper())
        except Exception:
            logger.exception("窗口=%s Alt+%s 按键失败", getattr(agent, "hwnd", None), letter)

    # ==================================================================
    # 选项: 活跃度检查（Maa OCRNum 的移植）
    # ==================================================================
    def _check_huodu(self, agent) -> bool:
        """OCR 活动面板底部的活跃度数字，>= HUODU_MIN 才继续做运镖。"""
        img = self._image(agent)
        if img is None:
            return True  # 识别不了不阻塞，与 Maa"识别不到活跃度"的宽松语义一致
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_HUODU)
        best = None
        for item in self._ocr_lines(agent):
            cx, cy = item["center"]
            if not (x <= cx <= x + rw and y <= cy <= y + rh):
                continue
            for m in re.finditer(r"\d+", item.get("text") or ""):
                num = int(m.group(0))
                if best is None or num > best:
                    best = num
        if best is None:
            logger.info("窗口=%s 没有识别到活跃度，按可执行处理", agent.hwnd)
            return True
        logger.info("窗口=%s 活跃度识别为 %d（要求 >= %d）", agent.hwnd, best, self.HUODU_MIN)
        return best >= self.HUODU_MIN

    # ==================================================================
    # 节点3: 点击日常活动 -> 滑到顶端 -> 找运镖行
    # ==================================================================
    def _node_find_yunbiao(self, agent) -> bool:
        # 已找到运镖行则直接成功（幂等，便于 _run_node 轮询）
        if self._find_yunbiao_row(agent):
            return True
        # Maa「活动-运镖-点击日常活动」
        if not getattr(self, "_daily_clicked", False):
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            roi = self._fraction_region(w, h, self.ROI_DAILY_LEFT)
            pos = self._find_label_in(self._ocr_lines(agent), ("日常活动",), roi)
            if not pos:
                return False
            logger.info("窗口=%s 点击日常活动 %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
            time.sleep(1.0)
            self._ocr_cache = None
            # Maa「活动-运镖-向上滑动到顶端」MultiSwipe x2
            for _ in range(2):
                self._swipe_vertical(agent, self.SWIPE_LIST_X,
                                     self.SWIPE_LIST_TOP_FROM, self.SWIPE_LIST_TOP_TO)
                time.sleep(0.4)
            self._daily_clicked = True
            return False
        # [JumpBack]baotu_huodong_down：列表向下翻找（max_hit 6）
        swipes = getattr(self, "_list_swipes", 0)
        if swipes >= self.list_swipe_max:
            logger.warning("窗口=%s 活动列表翻页 %d 次仍未找到运镖", agent.hwnd, self.list_swipe_max)
            return True  # 返回 True 让上层按"未找到"处理前再查一次
        self._swipe_vertical(agent, self.SWIPE_LIST_X,
                             self.SWIPE_LIST_DOWN_FROM, self.SWIPE_LIST_DOWN_TO)
        self._list_swipes = swipes + 1
        self._ocr_cache = None
        time.sleep(1.0)
        return self._find_yunbiao_row(agent)

    def _find_yunbiao_row(self, agent):
        """Maa「活动-运镖-开始」：在活动列表里找运镖行。"""
        img = self._image(agent)
        if img is None:
            return None
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_LIST)
        m = self._match_any(agent, self.T_YUNBIAO_START[:6], roi, self.TH_YUNBIAO_START)
        if not m:
            m = self._match_any(agent, ("escort_module",), roi, self.TH_ESCORT_MODULE)
        return m

    # ==================================================================
    # 节点4: 点击参加
    # ==================================================================
    def _node_join(self, agent) -> bool:
        """Maa「活动-运镖-开始-点击参加」：OCR"参加"优先，行内偏移兜底。"""
        m = self._find_yunbiao_row(agent)
        if not m:
            return False
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_LIST)
        pos = self._find_label_in(self._ocr_lines(agent), ("参加",), roi)
        if pos:
            logger.info("窗口=%s 点击参加(OCR) %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
        else:
            scale = m[3] if len(m) > 3 else 1.0
            target = (int(m[0] + self.JOIN_BTN_OFFSET_X * scale), int(m[1]))
            logger.info("窗口=%s 点击参加(行偏移) %s (行中心=%s scale=%.2f)",
                        agent.hwnd, target, m[:2], scale)
            agent.click(target[0], target[1])
        time.sleep(1.2)
        self._ocr_cache = None
        return True

    # ==================================================================
    # 节点5: 监控循环（拓印 / 押送普通镖银 / 运镖中 / 战斗 / 完成）
    # ==================================================================
    def _monitor_loop(self, agent) -> str:
        """返回 "done"(运镖完成) 或 "tayin"(遇见拓印停止)。"""
        while True:
            self._check_stop(agent)

            # Maa「识别拓印_停止」->「关闭拓印界面」-> 停止所有任务
            if self._check_tayin(agent):
                logger.info("窗口=%s 遇见拓印，停止所有任务", agent.hwnd)
                self._close_tayin(agent)
                return "tayin"

            # [JumpBack]点击押送普通镖银(三次) -> 点击押送普通镖_确定
            if self._yasong_count < self.yasong_max and self._click_yasong(agent):
                self._yasong_count += 1
                self._report(f"已接第 {self._yasong_count}/{self.yasong_max} 趟镖")
                self._click_queding(agent)
                continue

            img = self._image(agent)

            # [JumpBack]运镖中：OCR"距离运镖完成"
            if self._is_escorting(agent):
                if self._sleep(self.escorting_wait):
                    raise _Aborted()
                self._finished_hits = 0
                continue

            # [JumpBack]战斗中-等待20秒
            if self._in_battle(img):
                logger.info("窗口=%s 战斗中，等待 %.0f 秒", agent.hwnd, self.battle_wait)
                if self._sleep(self.battle_wait):
                    raise _Aborted()
                self._finished_hits = 0
                continue

            # Maa「运镖完成」：回到主界面
            if self._on_main_interface(agent):
                self._finished_hits += 1
                if self._finished_hits >= self.finish_confirm_hits:
                    logger.info("窗口=%s 运镖完成判断成立", agent.hwnd)
                    return "done"
            else:
                self._finished_hits = 0

            if self._sleep(self.poll_interval):
                raise _Aborted()

    def _check_tayin(self, agent) -> bool:
        """Maa「识别拓印_停止」= Or(OCR"拓印", tayin 模板 x2)。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        # 子1: OCR
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_TAYIN_OCR)
        for item in self._ocr_lines(agent):
            text = (item.get("text") or "").strip()
            if not any(k in text for k in ("拓印", "拓", "印")):
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return True
        # 子2/子3: 模板
        if self._match_any(agent, self.T_TAYIN,
                           self._fraction_region(w, h, self.ROI_TAYIN_TPL1), self.TH_TAYIN):
            return True
        if self._match_any(agent, self.T_TAYIN,
                           self._fraction_region(w, h, self.ROI_TAYIN_TPL2), self.TH_TAYIN):
            return True
        return False

    def _close_tayin(self, agent) -> None:
        """Maa「关闭拓印界面」：点右上角关闭(guanbi6/7)。"""
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            img = self._image(agent)
            if img is None:
                return
            h, w = img.shape[:2]
            m = self._match_any(agent, self.T_TAYIN_CLOSE,
                                self._fraction_region(w, h, self.ROI_TAYIN_CLOSE),
                                self.TH_TAYIN_CLOSE)
            if m:
                logger.info("窗口=%s 关闭拓印界面 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(0.8)
                return
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 未找到拓印界面关闭按钮", agent.hwnd)

    def _click_yasong(self, agent) -> bool:
        """Maa「点击押送普通镖银(三次)」：OCR 找选项并点击。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_YASONG)
        for item in self._ocr_lines(agent):
            if "押送普通镖银" not in (item.get("text") or ""):
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                logger.info("窗口=%s 点击押送普通镖银 %s", agent.hwnd, (int(cx), int(cy)))
                agent.click(int(cx), int(cy))
                time.sleep(1.0)
                self._ocr_cache = None
                return True
        return False

    def _click_queding(self, agent) -> bool:
        """Maa「点击押送普通镖_确定」：OCR"确定"并点击（最多等 15 秒）。"""
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                roi = self._fraction_region(w, h, self.ROI_QUEDING)
                pos = self._find_label_in(self._ocr_lines(agent), ("确定",), roi)
                if pos:
                    logger.info("窗口=%s 点击确定 %s", agent.hwnd, pos)
                    agent.click(pos[0], pos[1])
                    time.sleep(1.0)
                    self._ocr_cache = None
                    return True
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 未等到\"确定\"按钮，继续监控", agent.hwnd)
        return False

    def _is_escorting(self, agent) -> bool:
        """Maa「运镖中」：OCR"距离运镖完成"。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_ESCORTING)
        for item in self._ocr_lines(agent):
            if "距离运镖完成" not in (item.get("text") or ""):
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return True
        return False

    def _dismiss_popups(self, agent) -> bool:
        """Maa「战斗平衡弹窗-点击关闭」。"""
        m = self._match_any(agent, self.T_POPUP_CLOSE, None, self.TH_POPUP_CLOSE)
        if not m:
            return False
        agent.click(m[0], m[1])
        logger.info("窗口=%s 关闭战斗平衡弹窗 %s", agent.hwnd, m[:2])
        time.sleep(0.6)
        return True

    # ==================================================================
    # 战斗判定（本机已验证方案：顶部圆形一致性）
    # ==================================================================
    def _in_battle(self, img) -> bool:
        if img is None:
            return False
        try:
            import cv2
        except Exception:
            return False
        h, w = img.shape[:2]
        region = img[0:int(h * 0.16), int(w * 0.25):int(w * 0.75)]
        if region.size == 0:
            return False
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        params = [(50, 30, 10, 40), (50, 25, 8, 35), (40, 20, 10, 40)]
        results = []
        for p1, p2, minr, maxr in params:
            circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
                                       param1=p1, param2=p2, minRadius=minr, maxRadius=maxr)
            if circles is None or len(circles[0]) == 0:
                return False
            results.append(circles[0])
        counts = [len(r) for r in results]
        if counts[0] != counts[1] or counts[0] != counts[2]:
            return False
        c1, c2, c3 = results[0][0], results[1][0], results[2][0]
        pos_ok = (abs(c1[0] - c2[0]) < 10 and abs(c1[1] - c2[1]) < 10 and
                  abs(c1[0] - c3[0]) < 10 and abs(c1[1] - c3[1]) < 10)
        radius_ok = abs(c1[2] - c2[2]) < 5 and abs(c1[2] - c3[2]) < 5
        return bool(pos_ok and radius_ok)

    # ==================================================================
    # 通用工具
    # ==================================================================
    def _image(self, agent):
        try:
            return agent.capture()
        except Exception:
            logger.exception("窗口=%s 截图失败", getattr(agent, "hwnd", None))
            return None

    @staticmethod
    def _fraction_region(w: int, h: int, frac) -> Region:
        fx, fy, fw, fh = frac
        return (int(w * fx), int(h * fy), int(w * fw), int(h * fh))

    def _match_any(self, agent, names: Sequence[str], region: Optional[Region], threshold: float):
        """在（可选）区域内对一组模板做多尺度匹配，返回 (cx, cy, score, scale)。

        未加载的模板直接跳过 —— 可选/预留模板不存在时不再刷 "模板不存在" 的 ERROR 日志。
        """
        available = None
        try:
            available = agent.vision.matcher.templates
        except Exception:
            available = None
        for name in names:
            if available is not None and name not in available:
                logger.debug("跳过未加载的模板: %s", name)
                continue
            try:
                if region is None:
                    m = agent.detect_template_multiscale(name, threshold)
                else:
                    m = agent.detect_template_multiscale_region(name, region, threshold)
            except Exception:
                logger.exception("窗口=%s 模板匹配异常 %s", getattr(agent, "hwnd", None), name)
                continue
            if m:
                logger.debug("命中模板 %s -> %s", name, m)
                return m
        return None

    def _ocr_lines(self, agent):
        """整图 OCR 结果（带 ocr_cache_seconds 秒缓存）。"""
        now = time.monotonic()
        if self._ocr_cache is not None and now - self._ocr_cache[0] < self.ocr_cache_seconds:
            return self._ocr_cache[1]
        try:
            img = self._image(agent)
            results = agent.vision.get_all_text(img) if img is not None else []
        except Exception:
            logger.debug("OCR 不可用或失败", exc_info=True)
            results = []
        self._ocr_cache = (now, results)
        return results

    def _find_label_in(self, lines, labels, region: Region) -> Optional[Tuple[int, int]]:
        """在整图 OCR 结果里、于指定区域内找**精确等于** labels 之一的文字，返回中心。"""
        x, y, rw, rh = region
        for item in lines:
            text = (item.get("text") or "").strip()
            if text not in labels:
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return (int(cx), int(cy))
        return None

    @staticmethod
    def _ensure_foreground(hwnd) -> bool:
        """尽量把窗口切到前台；失败不抛异常。"""
        try:
            import win32con
            import win32gui
        except Exception:
            return False
        try:
            if win32gui.GetForegroundWindow() == hwnd:
                return True
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as exc:
            logger.debug("窗口=%s 置前失败：%s", hwnd, exc)
            try:
                return win32gui.GetForegroundWindow() == hwnd
            except Exception:
                return False

    def _do_swipe_vertical(self, agent, fx: float, fy_start: float, fy_end: float,
                           steps: int = 1) -> None:
        """按客户端比例坐标做一次垂直拖拽（内容跟随手指）。"""
        try:
            import win32api
            import win32con
            import win32gui
        except Exception:
            return
        img = self._image(agent)
        if img is None:
            return
        h, w = img.shape[:2]
        x = int(w * fx)
        y1, y2 = int(h * fy_start), int(h * fy_end)
        try:
            hwnd = agent.hwnd
            self._ensure_foreground(hwnd)
            time.sleep(0.2)
            # 截图(客户区)坐标 -> 屏幕坐标：用 ClientToScreen，与前台点击保持一致
            sx, sy1 = win32gui.ClientToScreen(hwnd, (x, y1))
            _sx, sy2 = win32gui.ClientToScreen(hwnd, (x, y2))
            for _ in range(max(1, steps)):
                win32api.SetCursorPos((sx, sy1))
                time.sleep(0.08)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, sx, sy1, 0, 0)
                time.sleep(0.08)
                n = 12
                for i in range(1, n + 1):
                    win32api.SetCursorPos((sx, int(sy1 + (sy2 - sy1) * i / n)))
                    time.sleep(0.02)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, sx, sy2, 0, 0)
                time.sleep(0.3)
        except Exception:
            logger.exception("窗口=%s 滑动失败", getattr(agent, "hwnd", None))

    def _finish(self, message: str) -> None:
        self.snapshot.completed_steps = self.snapshot.total_steps
        self.snapshot.status = TaskStatus.COMPLETED
        self._report(message)

    def _report(self, message: str) -> None:
        self.snapshot.message = message
        if self._on_update:
            self._on_update(self.snapshot)

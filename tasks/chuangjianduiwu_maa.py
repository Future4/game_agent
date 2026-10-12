# -*- coding: utf-8 -*-
"""创建队伍（副本/捉鬼） —— 按 Maa_MHXY 的 chuangjianduiwu.json 流水线原样移植。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/chuangjianduiwu.json
    (+ 共享节点: my_task.json「panduan_zhujiemian」)

======================= Maa 原始流程(节点图) =======================
chuangjianduiwu -> 队伍-打开界面(主界面 +/称号 -> ClickKey[57,48]=Alt+T)
  -> 队伍-进入主界面(duiwu-zudui/duiwu-duiwu)
     next: 队伍-点击创建队伍(OCR 创建队伍) | 队伍-已创建队伍(OCR 退出队伍)
  -> 队伍-目标已设置(title OCR 非"无") | [JumpBack]队伍-设置目标:
       队伍-设置目标(duiwu-mubiao) -> 目标-主界面(OCR 调整目标)
       -> 点击日常任务(OCR) -> 按选项:
            创建520副本任务: 点击副本任务 -> 已选择90-115(ColorMatch金, 否则点白)
                             -> 等级(左)向下滑动-一个等级单位 直到 OCR 89
            创建320副本任务: 点击副本任务 -> 已选择1-69(ColorMatch金, 否则点白)
            创建捉鬼任务:   点击捉鬼任务 -> 已选择90-115(同上)
                             -> 等级(左)向下滑动-max20 直到 OCR 20
       -> 队伍-任务描述(点固定位) -> 用户输入(InputText) -> 输入框确定
       -> 目标设置完成-点击确定
  -> 目标已设置 next (组队监控循环):
       队伍-人员已满(OCR 门派名) -> 人员已满-且未有暂离/离线(inverse 离线 -> 退出组队界面, 结束)
                                  | [JumpBack]有暂离/离线(点离线 -> 请离队伍)
       [JumpBack]队伍-点击自动匹配
       [JumpBack]队伍-点击一键喊话-当前(一键喊话 -> 当前频道, post 7s)

======================= Maa 任务选项映射 =======================
「创建（副本/捉鬼）任务」: TEAM_TARGET = "520"(创建520副本任务) / "320"(创建320副本任务)
                          / "zhuogui"(创建捉鬼任务), 默认 "520"
「任务描述(用户输入)」:    TASK_DESC, 默认 "" (对应 input_text)

======================= 移植适配说明 =======================
官网 PC 客户端(Unity) 与 Maa 的模拟器(1280x720) 不同:
  1. 布局非等比, roi 由 Maa 像素坐标换算为窗口比例并适当放大, 模板匹配用多尺度。
  2. ClickKey[57,48] = Alt+T(队伍界面)。
  3. InputText: 本机 type_text 仅支持 ASCII, 中文任务描述改用「写剪贴板 + Ctrl+V」粘贴;
     剪贴板不可用且文本为纯 ASCII 时回退逐键输入。
  4. ColorMatch 与宝图任务的 _colormatch 等价实现(金色已选/白色未选两组阈值)。
  5. regex(^(?!无$)[一-龥]+$) 按「含中文字符且不等于'无'」近似。
"""

import logging
import time
from typing import Callable, Optional, Sequence, Tuple

from domain.tasks import TaskContext, TaskDefinition, TaskSnapshot, TaskStatus
from tasks.base import AutomationTask

logger = logging.getLogger(__name__)

Region = Tuple[int, int, int, int]  # x, y, w, h（截图坐标）


class _Aborted(Exception):
    """停止/超时信号。"""


class ChuangjianDuiwuMaaTask(AutomationTask):
    definition = TaskDefinition(
        "chuangjianduiwu_maa", "创建队伍", "移植自 Maa_MHXY 的 chuangjianduiwu 流水线"
    )

    # ---------------- 任务选项（对应 Maa 任务选项，见模块 docstring）----------------
    TEAM_TARGET = "520"          # "520"(创建520副本任务) / "320"(创建320副本任务) / "zhuogui"(创建捉鬼任务)
    TASK_DESC = ""               # 任务描述（对应 Maa input_text，空串=不输入）

    # ---------------- 时序参数（对应 Maa 流水线字段）----------------
    poll_interval = 0.5
    node_timeout = 90.0
    level_swipe_max = 20         # Maa: 等级（左）-向下滑动-max20 (max_hit 20)
    total_timeout = 1800.0       # 组队满员可能较慢，整个任务上限 30 分钟

    # ---------------- 可调开关 ----------------
    ocr_cache_seconds = 2.0

    # ---------------- 阈值 ----------------
    TH_MAIN_INDICATOR = 0.75
    TH_DUIWU_ICON = 0.80
    TH_DUIWU_PANEL = 0.80
    TH_MUBIAO = 0.80
    TH_DUIWU_GUANBI = 0.80

    # Maa「队伍-人员已满」门派名（OCR 预期）
    MENPAI_NAMES = (
        "大唐官府", "方寸山", "狮驼岭", "普陀山", "阴曹地府", "龙宫", "魔王寨",
        "化生寺", "月宫", "女儿村", "小雷音", "花果山", "须弥海", "盘丝洞",
    )

    # ---------------- 模板名（templates/ 目录，不带 .png）----------------
    T_MAIN_INDICATORS = ("zonghe/jiahao", "zonghe/baoguo", "zonghe/baoguo_man", "zonghe/chenghao")
    T_JIAHAO_CHENGHAO = ("zonghe/chenghao", "zonghe/jiahao")  # Maa 队伍-打开界面
    T_DUIWU_ICON = ("duiwu/duiwu",)
    T_DUIWU_PANEL = ("duiwu/duiwu-zudui", "duiwu/duiwu-duiwu")
    T_MUBIAO = ("duiwu/duiwu-mubiao",)
    T_DUIWU_GUANBI = ("duiwu/duiwu-guanbi",)

    # ---------------- 区域比例（由 Maa 1280x720 像素 roi 换算并适当放大）----------------
    ROI_MAIN_INDICATOR = (0.86, 0.72, 0.14, 0.28)
    ROI_JIAHAO_BR = (0.86, 0.80, 0.14, 0.20)       # Maa [1206,637,66,57] 放大
    ROI_DUIWU_ICON = (0.80, 0.08, 0.20, 0.20)      # Maa [1161,104,119,65] 放大
    ROI_DUIWU_PANEL = (0.00, 0.00, 0.30, 0.25)     # Maa [0,0,229,106] 放大
    ROI_CREATE_QUIT = (0.02, 0.80, 0.28, 0.18)     # Maa 创建队伍/退出队伍 [85,632,188,60] 放大
    ROI_MUBIAO = (0.52, 0.03, 0.16, 0.18)          # Maa [761,52,69,69] 放大
    ROI_TIAOZHENG = (0.36, 0.00, 0.28, 0.14)       # Maa 调整目标 [560,6,157,51] 放大
    ROI_TASK_LIST = (0.14, 0.12, 0.30, 0.72)       # Maa 日常任务/副本任务/捉鬼任务 [259,123,261,472] 放大
    ROI_LEVEL_RIGHT = (0.66, 0.36, 0.18, 0.14)     # Maa 90-115 [936,309,80,39] 放大
    ROI_LEVEL_LEFT_320 = (0.52, 0.36, 0.20, 0.14)  # Maa 1-69 [760,309,80,39] 放大
    ROI_LEVEL_NUM = (0.55, 0.24, 0.15, 0.14)       # Maa 89/20 [775,220,45,44] 放大
    ROI_QUEDING_INPUT = (0.85, 0.00, 0.15, 0.15)   # Maa 输入框确定 [1208,0,67,65] 放大
    ROI_QUEDING_DONE = (0.36, 0.80, 0.26, 0.18)    # Maa 目标设置完成-确定 [554,627,172,55] 放大
    ROI_TARGET_SET = (0.28, 0.04, 0.24, 0.14)      # Maa 目标已设置 [430,64,170,48] 放大
    ROI_ZIDONG_PIPEI = (0.70, 0.03, 0.28, 0.18)    # Maa 自动匹配 [1024,57,152,60] 放大
    ROI_YIJIAN = (0.70, 0.82, 0.28, 0.16)          # Maa 一键喊话 [998,634,178,55] 放大
    ROI_DANGQIAN = (0.70, 0.36, 0.26, 0.52)        # Maa 当前频道 [1003,302,171,319] 放大
    ROI_MEMBER_FULL = (0.72, 0.68, 0.22, 0.14)     # Maa 人员已满 [1028,540,102,42] 放大
    ROI_OFFLINE = (0.20, 0.50, 0.70, 0.20)         # Maa 离线 [341,432,757,41] 放大
    ROI_QINGLI = (0.20, 0.15, 0.68, 0.52)          # Maa 请离队伍 [336,153,767,295] 放大
    ROI_DUIWU_GUANBI = (0.80, 0.00, 0.20, 0.22)    # Maa [1153,0,100,98] 放大

    # 固定点击位（比例坐标）
    POS_DESC_INPUT = (0.662, 0.611)   # Maa 队伍-任务描述 target [778,422,138,36] 中心

    # 等级调整滑动（比例）
    SWIPE_LEVEL_X = 0.624             # Maa x=799~800/1280
    SWIPE_LEVEL_STEP_FROM = 0.292     # 520: 一个等级单位 210 -> 235 (end_hold 500)
    SWIPE_LEVEL_STEP_TO = 0.326
    SWIPE_LEVEL_MAX_FROM = 0.207      # 捉鬼: max20 149 -> 285
    SWIPE_LEVEL_MAX_TO = 0.396

    # ColorMatch 参数（RGB, 与 Maa upper/lower 同序）
    CM_GOLD_LOWER = (252, 207, 102)   # 已选择(金色高亮): 90-115 / 1-69
    CM_GOLD_UPPER = (253, 213, 109)
    CM_GOLD_COUNT = 700
    CM_WHITE_LOWER = (239, 226, 210)  # 未选择(白色, 点击)
    CM_WHITE_UPPER = (240, 227, 211)
    CM_WHITE_COUNT = 2000

    # ==================================================================
    # 主流程
    # ==================================================================
    def __init__(self) -> None:
        super().__init__()
        self._on_update = None
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._swipe_vertical = self._do_swipe_vertical
        self._ocr_cache = None

    def run(self, context: TaskContext,
            on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._alt_t_pressed = False
        self._team_entered = False
        self._mubiao_clicked = False
        self._daily_clicked = False
        self._task_type_clicked = False
        self._level_done = False
        self._level_swipes = 0
        self._desc_done = False
        self._desc_input_done = False
        self._input_confirmed = False
        self._swipe_vertical = self._do_swipe_vertical  # 允许测试替换
        self._ocr_cache = None

        target_label = {"520": "520副本", "320": "320副本", "zhuogui": "捉鬼"}[self.TEAM_TARGET]
        logger.info("创建队伍启动 hwnd=%s (目标=%s, 描述=%r)",
                    getattr(agent, "hwnd", None), target_label, self.TASK_DESC)
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 4
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            # 步骤2: Maa「队伍-打开界面」—— Alt+T 打开队伍界面
            ok = self._stage(agent, 2, "打开队伍界面", self._node_open_team)
            if not ok:
                self.snapshot.status = TaskStatus.FAILED
                self._report("未能打开队伍界面，请检查窗口状态与模板")
                logger.error("窗口=%s 未能打开队伍界面", agent.hwnd)
                return

            # 步骤3: 创建/进入队伍 -> 设置目标(按选项) -> 任务描述 -> 确定
            ok = self._stage(agent, 3, f"创建{target_label}队伍并设置目标",
                             self._node_setup_target)
            if not ok:
                self.snapshot.status = TaskStatus.FAILED
                self._report("未能完成队伍目标设置，请检查窗口状态")
                logger.error("窗口=%s 队伍目标设置失败", agent.hwnd)
                return

            # 步骤4: 组队监控循环（自动匹配/喊话/满员判断/踢离线）
            self._report("组队中，等待人员满员")
            self._match_loop(agent)

            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            self._report("队伍人员已满，创建队伍完成")
            logger.info("创建队伍完成 hwnd=%s", agent.hwnd)
        except _Aborted:
            logger.info("创建队伍停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("创建队伍执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("创建队伍执行异常，详见日志")

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
    # 节点2: 队伍-打开界面（Alt+T，失败点队伍图标）
    # ==================================================================
    def _node_open_team(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        # 队伍-进入主界面
        if self._match_any(agent, self.T_DUIWU_PANEL,
                           self._fraction_region(w, h, self.ROI_DUIWU_PANEL),
                           self.TH_DUIWU_PANEL):
            logger.info("窗口=%s 队伍界面已打开", agent.hwnd)
            return True
        if not getattr(self, "_alt_t_pressed", False):
            self._press_hotkey(agent, "T")  # Maa ClickKey[57,48] = Alt+T
            self._alt_t_pressed = True
            time.sleep(1.0)
            return False
        # [JumpBack]队伍界面-按键打开失败-点击队伍图标
        icon_roi = self._fraction_region(w, h, self.ROI_DUIWU_ICON)
        m = self._match_any(agent, self.T_DUIWU_ICON, icon_roi, self.TH_DUIWU_ICON)
        if not m:
            pos = self._find_text_in(self._ocr_lines(agent), ("队伍",), icon_roi)
            if pos:
                m = (pos[0], pos[1], 0.0)
        if m:
            logger.info("窗口=%s 点击队伍图标 %s", agent.hwnd, m[:2])
            agent.click(m[0], m[1])
            time.sleep(1.0)
        else:
            self._press_hotkey(agent, "T")
            time.sleep(1.0)
        return False

    # ==================================================================
    # 节点3: 创建/进入队伍 -> 设置目标
    # ==================================================================
    def _node_setup_target(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]

        # 队伍-点击创建队伍（不在队就先创建）
        if not getattr(self, "_team_entered", False):
            if self._click_text_once(agent, ("创建队伍",), self.ROI_CREATE_QUIT, wait=1.0):
                self._team_entered = True
                return False
            # 队伍-已创建队伍（OCR 退出队伍 -> 已在队中）
            if self._find_text_in(self._ocr_lines(agent), ("退出队伍",),
                                  self._fraction_region(w, h, self.ROI_CREATE_QUIT)):
                logger.info("窗口=%s 已在队伍中", agent.hwnd)
                self._team_entered = True
                return False
            return False

        # 队伍-目标已设置：标题 OCR 含中文且非"无" -> 跳过目标设置
        if self._target_already_set(agent):
            logger.info("窗口=%s 队伍目标已设置，跳过目标设置", agent.hwnd)
            return True

        # [JumpBack]队伍-设置目标
        if not getattr(self, "_mubiao_clicked", False):
            m = self._match_any(agent, self.T_MUBIAO,
                                self._fraction_region(w, h, self.ROI_MUBIAO), self.TH_MUBIAO)
            if m:
                logger.info("窗口=%s 点击队伍目标 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(1.0)
                self._mubiao_clicked = True
                return False
            return False

        # 队伍-目标-主界面（OCR 调整目标）-> 点击日常任务 -> 按选项设置 -> 描述 -> 确定
        return self._setup_target_detail(agent)

    def _target_already_set(self, agent) -> bool:
        """Maa「队伍-目标已设置」regex ^(?!无$)[一-龥]+$ 的近似。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_TARGET_SET)
        for item in self._ocr_lines(agent):
            text = (item.get("text") or "").strip()
            if not text or text == "无":
                continue
            if not any("一" <= ch <= "鿿" for ch in text):
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return True
        return False

    def _setup_target_detail(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        # 队伍-目标-主界面：OCR 调整目标
        if not self._find_text_in(self._ocr_lines(agent), ("调整目标",),
                                  self._fraction_region(w, h, self.ROI_TIAOZHENG)):
            return False
        # 队伍-点击日常任务
        if not getattr(self, "_daily_clicked", False):
            if self._click_text_once(agent, ("日常任务",), self.ROI_TASK_LIST, wait=1.0):
                self._daily_clicked = True
            return False
        # 按选项选择任务类型
        if not getattr(self, "_task_type_clicked", False):
            keyword = "捉鬼任务" if self.TEAM_TARGET == "zhuogui" else "副本任务"
            if self._click_text_once(agent, (keyword,), self.ROI_TASK_LIST, wait=1.0):
                self._task_type_clicked = True
            return False
        # 等级区间选择
        if not getattr(self, "_level_done", False):
            self._level_done = self._setup_level_range(agent)
            return False
        # 队伍-任务描述 -> 用户输入 -> 输入框确定 -> 目标设置完成-点击确定
        if not getattr(self, "_desc_done", False):
            self._desc_done = self._setup_desc(agent)
            return False
        return True

    def _setup_level_range(self, agent) -> bool:
        """等级区间：520/捉鬼 选 90-115（520 再把下限滑到 89，捉鬼滑到 20）；320 选 1-69。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if self.TEAM_TARGET == "320":
            roi = self._fraction_region(w, h, self.ROI_LEVEL_LEFT_320)
        else:
            roi = self._fraction_region(w, h, self.ROI_LEVEL_RIGHT)
        # 已选择（金色高亮 ColorMatch）
        if not self._colormatch(img, roi, self.CM_GOLD_LOWER, self.CM_GOLD_UPPER,
                                self.CM_GOLD_COUNT):
            # [JumpBack]点击90-115 / 点击1-69（白色 -> 点击）
            if self._colormatch(img, roi, self.CM_WHITE_LOWER, self.CM_WHITE_UPPER,
                                self.CM_WHITE_COUNT):
                cx, cy = roi[0] + roi[2] // 2, roi[1] + roi[3] // 2
                logger.info("窗口=%s 点击等级区间 (%d,%d)", agent.hwnd, cx, cy)
                agent.click(cx, cy)
                time.sleep(0.5)
            return False
        # 已选区间后的下限微调
        if self.TEAM_TARGET == "520":
            # 队伍-副本任务520-调整下限至89：OCR 89
            if self._find_text_in(self._ocr_lines(agent), ("89",),
                                  self._fraction_region(w, h, self.ROI_LEVEL_NUM), exact=True):
                logger.info("窗口=%s 等级下限已到 89", agent.hwnd)
                return True
            # [JumpBack]等级（左）-向下滑动-一个等级单位
            self._swipe_vertical(agent, self.SWIPE_LEVEL_X,
                                 self.SWIPE_LEVEL_STEP_FROM, self.SWIPE_LEVEL_STEP_TO,
                                 end_hold_ms=500)
            self._ocr_cache = None
            time.sleep(0.5)
            return False
        if self.TEAM_TARGET == "zhuogui":
            # 队伍-捉鬼任务-最低20级：OCR 20
            if self._find_text_in(self._ocr_lines(agent), ("20",),
                                  self._fraction_region(w, h, self.ROI_LEVEL_NUM), exact=True):
                logger.info("窗口=%s 等级下限已到 20", agent.hwnd)
                return True
            # [JumpBack]等级（左）-向下滑动-max20
            swipes = getattr(self, "_level_swipes", 0)
            if swipes >= self.level_swipe_max:
                logger.warning("窗口=%s 等级滑动 %d 次仍未到 20，按当前等级继续",
                               agent.hwnd, self.level_swipe_max)
                return True
            self._swipe_vertical(agent, self.SWIPE_LEVEL_X,
                                 self.SWIPE_LEVEL_MAX_FROM, self.SWIPE_LEVEL_MAX_TO)
            self._level_swipes = swipes + 1
            self._ocr_cache = None
            time.sleep(0.5)
            return False
        # 320：选中 1-69 即可
        logger.info("窗口=%s 等级区间 1-69 已选择", agent.hwnd)
        return True

    def _setup_desc(self, agent) -> bool:
        """队伍-任务描述 -> 用户输入 -> 输入框确定 -> 目标设置完成-点击确定。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if not getattr(self, "_desc_input_done", False):
            # 队伍-任务描述：点固定位打开输入框
            fx, fy = int(w * self.POS_DESC_INPUT[0]), int(h * self.POS_DESC_INPUT[1])
            logger.info("窗口=%s 点击任务描述输入框 (%d,%d)", agent.hwnd, fx, fy)
            agent.click(fx, fy)
            time.sleep(1.0)
            # 队伍-任务描述-用户输入（InputText）
            if self.TASK_DESC:
                self._input_text(agent, self.TASK_DESC)
                time.sleep(2.0)
            self._desc_input_done = True
            return False
        if not getattr(self, "_input_confirmed", False):
            # 队伍-输入框确定
            if self._click_text_once(agent, ("确定",), self.ROI_QUEDING_INPUT, wait=1.0,
                                     exact=True):
                self._input_confirmed = True
            return False
        # 队伍-目标设置完成-点击确定
        if self._click_text_once(agent, ("确定",), self.ROI_QUEDING_DONE, wait=2.0, exact=True):
            logger.info("窗口=%s 队伍目标设置完成", agent.hwnd)
            return True
        return False

    # ==================================================================
    # 节点4: 组队监控循环（目标已设置 的 next 列表）
    # ==================================================================
    def _match_loop(self, agent) -> None:
        while True:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                if self._sleep(self.poll_interval):
                    raise _Aborted()
                continue
            h, w = img.shape[:2]

            # 队伍-人员已满（OCR 门派名）
            if self._find_text_in(self._ocr_lines(agent), self.MENPAI_NAMES,
                                  self._fraction_region(w, h, self.ROI_MEMBER_FULL)):
                # [JumpBack]队伍-有暂离/离线：点离线 -> 请离队伍
                pos = self._find_text_in(self._ocr_lines(agent), ("离线",),
                                         self._fraction_region(w, h, self.ROI_OFFLINE))
                if pos:
                    logger.info("窗口=%s 满员但有离线队员，点击 %s", agent.hwnd, pos)
                    agent.click(pos[0], pos[1])
                    time.sleep(1.0)
                    self._ocr_cache = None
                    # 队伍-有暂离/离线-点击请离队伍
                    self._click_text_once(agent, ("请离队伍",), self.ROI_QINGLI, wait=1.0)
                    continue
                # 人员已满-且未有暂离/离线 -> 退出组队界面，结束
                m = self._match_any(agent, self.T_DUIWU_GUANBI,
                                    self._fraction_region(w, h, self.ROI_DUIWU_GUANBI),
                                    self.TH_DUIWU_GUANBI)
                if m:
                    logger.info("窗口=%s 人员已满，退出组队界面 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    time.sleep(1.0)
                return

            # [JumpBack]队伍-点击自动匹配
            if self._click_text_once(agent, ("自动匹配",), self.ROI_ZIDONG_PIPEI, wait=2.0,
                                     exact=True):
                continue
            # [JumpBack]队伍-点击一键喊话-当前
            if self._click_text_once(agent, ("一键喊话", "键喊话"), self.ROI_YIJIAN, wait=1.0):
                # 队伍-点击-当前频道
                self._click_text_once(agent, ("当前频道",), self.ROI_DANGQIAN, wait=7.0)
                continue

            if self._sleep(self.poll_interval):
                raise _Aborted()

    # ==================================================================
    # 文本输入（InputText：剪贴板粘贴优先）
    # ==================================================================
    def _input_text(self, agent, text: str) -> None:
        """中文用「写剪贴板 + Ctrl+V」；失败且纯 ASCII 时回退逐键输入。"""
        try:
            import win32api
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
            self._ensure_foreground(agent.hwnd)
            time.sleep(0.2)
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord("V"), 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            logger.info("窗口=%s 粘贴任务描述: %r", agent.hwnd, text)
            return
        except Exception:
            logger.exception("窗口=%s 剪贴板粘贴失败", getattr(agent, "hwnd", None))
        if all(ord(c) < 128 for c in text):
            executor = getattr(agent, "executor", None)
            if executor is not None and hasattr(executor, "type_text"):
                executor.type_text(text)
                logger.info("窗口=%s 逐键输入任务描述: %r", agent.hwnd, text)

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
        """在（可选）区域内对一组模板做多尺度匹配，返回 (cx, cy, score, scale)。"""
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

    @staticmethod
    def _find_text_in(lines, keywords, region: Region, exact: bool = False):
        """在整图 OCR 结果里、于指定区域内找含关键字的文字（exact=True 时精确等于），返回中心。"""
        x, y, rw, rh = region
        for item in lines:
            text = (item.get("text") or "").strip()
            if exact:
                hit = text in keywords
            else:
                hit = any(k in text for k in keywords)
            if not hit:
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return (int(cx), int(cy))
        return None

    def _click_text_once(self, agent, keywords, roi_frac, wait: float = 1.0,
                         exact: bool = False) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        pos = self._find_text_in(self._ocr_lines(agent), keywords,
                                 self._fraction_region(w, h, roi_frac), exact=exact)
        if not pos:
            return False
        agent.click(pos[0], pos[1])
        logger.info("窗口=%s 点击 %s %s", agent.hwnd, "/".join(keywords), pos)
        time.sleep(wait)
        self._ocr_cache = None
        return True

    @staticmethod
    def _colormatch(img, region: Region, lower, upper, count: int) -> bool:
        """Maa ColorMatch 的等价实现：区域内落在 [lower, upper] 的像素数 >= count。"""
        try:
            import numpy as np
        except Exception:
            return False
        x, y, rw, rh = region
        patch = img[max(0, y):y + rh, max(0, x):x + rw]
        if patch.size == 0:
            return False
        lo = np.array(lower, dtype=np.int16)
        hi = np.array(upper, dtype=np.int16)
        px = patch[:, :, ::-1].astype(np.int16)  # BGR -> RGB，与 Maa 的 upper/lower 同序
        inside = np.all((px >= lo) & (px <= hi), axis=2)
        return int(inside.sum()) >= count

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
                           steps: int = 1, end_hold_ms: int = 0) -> None:
        """按客户端比例坐标做一次垂直拖拽（内容跟随手指），可选末端停留。"""
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
                if end_hold_ms > 0:
                    time.sleep(end_hold_ms / 1000.0)  # Maa end_hold：到达后停留再抬手
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, sx, sy2, 0, 0)
                time.sleep(0.3)
        except Exception:
            logger.exception("窗口=%s 滑动失败", getattr(agent, "hwnd", None))

    def _report(self, message: str) -> None:
        self.snapshot.message = message
        if self._on_update:
            self._on_update(self.snapshot)

# -*- coding: utf-8 -*-
"""秘境降妖 —— 按 Maa_MHXY 的 mijing_renwu.json 流水线原样移植到 game_agent。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/mijing_renwu.json
    (+ 共享节点: my_task.json「panduan_zhujiemian / panduan_zhujiemian_ks / 识别拓印_停止 /
       战斗中-等待20秒 / 战斗中-等待5秒 / 关闭整点活动弹窗 / 自动寻路中-图片识别」
       wabaotu.json「清理主界面使用-关闭」 baotu_renwu.json「baotu_huodong_down /
       战斗平衡弹窗-点击关闭」 sanjieqiyuan.json「活动-界面-打开失败-点击活动图片」
       chongwuqifu.json「小地图-按键打开失败-点击小地图图标」)
    (+ 自定义: agent/custom/recognition/ExpressionRecognition.py「指定关卡结束任务」)

======================= Maa 原始流程(节点图) =======================
mijing_renwu -> 识别位置-东海湾-秘境-过渡(主界面 +/称号)
  next: 识别位置-东海湾-秘境(OCR 东海湾) -> click_tab_mijing(ClickKey[61]=Tab)
        [JumpBack]dakai_map(Alt+M -> 打开大地图成功 -> chuansong_donghaiwan 点东海湾)

click_tab_mijing -> 东海湾小地图打开成功(donghaiwan_tab_panduan)
  -> click_map_yunleyou(OCR 云乐游 -> 点击)
     next: mijingxiangyao | [JumpBack]秘境-云乐游失败-走活动入口(max_hit 1:
             panduan_ks -> 主界面-秘境降妖(Alt+C) -> 活动面板 -> 日常活动 ->
             滑到顶端 -> 活动-秘境降妖-开始(And mijing_rukou 0.9 + OCR) -> 点击参加)

mijingxiangyao(OCR 秘境降妖 -> 点击)
  -> 识别拓印_停止
  -> 秘境降妖-选择模式(mijing_moshi):
       海底秘境(默认): 选择海底秘境(OCR 进入) -> 模式确认(moshi_queding) -> 继续挑战(OCR 挑战)
       日月之井(选项): 点击日月之井(OCR 进入) -> 日月之井-确认 -> 继续挑战(OCR 挑战)

继续挑战 -> 关卡监控循环:
    [JumpBack]海底/日月-关闭进入战斗(OCR 进入战斗 -> 点固定位关闭)
    海底/日月-指定关卡结束任务(ExpressionRecognition: {关卡识别}>=N
        -> 清理主界面使用-关闭 -> 秘境-点击离开 -> 战斗5秒 -> panduan, 结束)
    [JumpBack]秘境-点击进入战斗
    [JumpBack]海底/日月-点击关卡(OCR 第N关 -> 点击 -> 进入战斗/战斗5秒)
    [JumpBack]关闭酒店老板弹窗(guanbi1/2)
    mijing_tongguan/日月之井-通关(OCR 通关 -> 离开 -> 返回东海湾, 结束)
    mijing_shibai/日月之井-失败(模板 -> 离开 -> 返回东海湾/panduan, 结束)
    [JumpBack]战斗中-等待20秒

======================= Maa 任务选项映射 =======================
「海底秘境模式」: MIJING_MODE = "haidi"(默认) / "riyue"(日月之井)
「秘境-海底-结束关卡」: END_LEVEL_HAIDI, 默认 60(不提前退出), 可选 25/24/21/18
「秘境-日月-结束关卡」: END_LEVEL_RIYUE, 默认 60, 可选 25/24/18
  —— 对应 ExpressionRecognition 的 expression "{关卡识别}>=N": OCR 关卡区域取第一个
     数字与 N 比较(ExpressionRecognition 通用表达式引擎的全部用法仅此一种比较,
     移植时按语义实现为 数值>=阈值)。

======================= 移植适配说明 =======================
官网 PC 客户端(Unity) 与 Maa 的模拟器(1280x720) 不同:
  1. 布局非等比, roi 由 Maa 像素坐标换算为窗口比例并适当放大, 模板匹配用多尺度。
  2. ClickKey[57,41]=Alt+M(大地图), ClickKey[61]=Tab(小地图), ClickKey[57,31]=Alt+C(活动)。
  3. OCR 走整图识别+ROI 中心过滤(带缓存); regex(第N关)按 第..关 包含关系近似。
  4. 战斗判断: Maa 模板(zhandou/zidong|quxiao 0.9)优先, HoughCircles 兜底。
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


class MijingMaaTask(AutomationTask):
    definition = TaskDefinition(
        "mijing_maa", "秘境降妖", "移植自 Maa_MHXY 的 mijing_renwu 流水线"
    )

    # ---------------- 任务选项（对应 Maa 任务选项，见模块 docstring）----------------
    MIJING_MODE = "haidi"        # "haidi"=海底秘境(默认) / "riyue"=日月之井
    END_LEVEL_HAIDI = 60         # 海底秘境结束关卡：60=不提前退出(Maa 默认), 可选 25/24/21/18
    END_LEVEL_RIYUE = 60         # 日月之井结束关卡：60=不提前退出, 可选 25/24/18

    # ---------------- 时序参数（对应 Maa 流水线字段）----------------
    poll_interval = 0.5
    node_timeout = 90.0
    battle_wait = 20.0           # Maa: 战斗中-等待20秒
    battle_wait_short = 5.0      # Maa: 战斗中-等待5秒
    list_swipe_max = 6           # Maa: baotu_huodong_down (max_hit 6)
    total_timeout = 3600.0       # 整个任务上限

    # ---------------- 可调开关 ----------------
    ocr_cache_seconds = 2.0

    # ---------------- 阈值 ----------------
    TH_MAIN_INDICATOR = 0.75
    TH_MAP_PANEL = 0.75
    TH_DONGHAIWAN_MAP = 0.75
    TH_MINIMAP = 0.85
    TH_DONGHAIWAN_TAB = 0.75
    TH_MOSHI = 0.75
    TH_MOSHI_QUEDING = 0.80
    TH_SHIBAI = 0.80
    TH_JIUDIAN = 0.80
    TH_MIJING_RUKOU = 0.90       # Maa: 活动-秘境降妖-开始 threshold 0.9
    TH_ACTIVITY_PANEL = 0.75
    TH_ACTIVITY_BUTTON = 0.60
    TH_CHA = 0.80
    TH_BATTLE = 0.90
    TH_TAYIN = 0.90
    TH_TAYIN_CLOSE = 0.80
    TH_POPUP_CLOSE = 0.88

    # ---------------- 模板名（templates/ 目录，不带 .png）----------------
    T_MAIN_INDICATORS = ("zonghe/jiahao", "zonghe/baoguo", "zonghe/baoguo_man", "zonghe/chenghao")
    T_MAP_PANEL = ("zonghe/ditu_jiemian_panduan", "zonghe/ditu_jiemian_panduan2")
    # Maa「chuansong_donghaiwan」
    T_DONGHAIWAN_MAP = ("mijing/ditu_donghaiwan", "mijing/ditu_donghaiwan1", "mijing/ditu_donghaiwan2")
    T_MINIMAP = ("zonghe/xiaoditu_taiyang", "zonghe/xiaoditu_yueliang")
    # Maa「东海湾小地图打开成功」
    T_DONGHAIWAN_TAB = ("mijing/donghaiwan_tab_panduan",)
    # Maa「秘境降妖-选择模式」/「秘境降妖-(海底秘境|日月之井)-确认」
    T_MOSHI = ("mijing/mijing_moshi",)
    T_MOSHI_QUEDING = ("mijing/moshi_queding",)
    # Maa「mijing_shibai」/「日月之井-失败」
    T_SHIBAI_HAIDI = ("mijing/mijing_shibai",)
    T_SHIBAI_RIYUE = ("mijing/mijing_shibai", "mijing/mijing_shibai2", "mijing/mijing_riyue_shibai")
    # Maa「关闭酒店老板弹窗」
    T_JIUDIAN = ("zonghe/guanbi1", "zonghe/guanbi2")
    # Maa「活动-秘境降妖-开始」
    T_MIJING_RUKOU = ("mijing/mijing_rukou",)
    # Maa 活动入口/面板
    T_ACTIVITY_PANEL = ("zonghe/huodong_jiemian_panduan",)
    T_ACTIVITY_BUTTON = ("zonghe/huodong1", "zonghe/huodong2", "activity_button")
    # Maa「清理主界面使用-关闭」/「识别拓印_停止」/「关闭拓印界面」/「战斗平衡弹窗」
    T_CHA = ("zonghe/zhujiemian_shiyong_cha",)
    T_TAYIN = ("tayin/tayin", "tayin/tayin2")
    T_TAYIN_CLOSE = ("zonghe/guanbi6", "zonghe/guanbi7")
    T_POPUP_CLOSE = ("zonghe/zhandoupingheng_guanbi1",)
    # Maa 战斗判定模板
    T_BATTLE_BTN = ("zhandou/zidong", "zhandou/quxiao")
    T_BATTLE_ICON = ("zhandou/zhandou1", "zhandou/zhandou2", "zhandou/zhandou3")

    # ---------------- 区域比例（由 Maa 1280x720 像素 roi 换算并适当放大）----------------
    ROI_MAIN_INDICATOR = (0.86, 0.72, 0.14, 0.28)
    ROI_DONGHAIWAN_OCR = (0.02, 0.00, 0.25, 0.12)  # Maa [105,22,124,34] 放大
    ROI_MAP_PANEL = (0.00, 0.00, 0.28, 0.24)
    ROI_MINIMAP = (0.00, 0.00, 0.18, 0.20)
    ROI_DONGHAIWAN_TAB = (0.28, 0.03, 0.18, 0.20)  # Maa [444,56,60,64] 放大
    ROI_YUNLEYOU = (0.30, 0.45, 0.24, 0.16)        # Maa [500,382,89,37] 放大
    ROI_MIJING_DIALOG = (0.64, 0.06, 0.34, 0.70)   # Maa [921,89,324,405] 放大
    ROI_MOSHI = (0.12, 0.06, 0.72, 0.26)           # Maa [231,85,774,106] 放大
    ROI_ENTER_HAIDI = (0.16, 0.78, 0.24, 0.16)     # Maa [311,610,137,44] 放大
    ROI_ENTER_RIYUE = (0.50, 0.76, 0.30, 0.20)     # Maa [776,605,205,59] 放大
    ROI_MOSHI_QUEDING = (0.44, 0.48, 0.24, 0.20)   # Maa [671,405,149,59] 放大
    ROI_TIAOZHAN = (0.68, 0.58, 0.20, 0.36)        # Maa [996,481,78,179] 放大
    ROI_ENTER_BATTLE = (0.64, 0.42, 0.34, 0.20)    # Maa [939,366,285,63] 放大
    ROI_JIUDIAN = (0.76, 0.00, 0.24, 0.22)         # Maa [1106,7,77,84] 放大
    ROI_LIKAI = (0.80, 0.36, 0.20, 0.44)           # Maa 秘境-点击离开 [1135,318,145,243] 放大
    # 海底秘境：关卡识别 [1041,256,28,51] / 点击关卡 [1014,209,101,109] / 通关 [1014,260,122,56]
    ROI_LEVEL_HAIDI = (0.72, 0.28, 0.20, 0.16)
    ROI_LEVEL_CLICK_HAIDI = (0.70, 0.22, 0.24, 0.26)
    ROI_TONGGUAN_HAIDI = (0.70, 0.28, 0.26, 0.18)
    ROI_SHIBAI_HAIDI = (0.16, 0.12, 0.62, 0.48)    # Maa [304,130,654,275] 放大
    # 日月之井：关卡识别/点击关卡 [1012,169,115,74] / 通关 [1012,169,115,100] / 失败 [304,130,654,375]
    ROI_LEVEL_RIYUE = (0.70, 0.16, 0.26, 0.20)
    ROI_TONGGUAN_RIYUE = (0.70, 0.16, 0.26, 0.24)
    ROI_SHIBAI_RIYUE = (0.16, 0.12, 0.62, 0.60)
    # 活动入口兜底（云乐游失败）
    ROI_ACTIVITY_PANEL = (0.20, 0.00, 0.62, 0.14)
    ROI_ACTIVITY_BUTTON = (0.00, 0.00, 0.45, 0.30)
    ROI_DAILY_LEFT = (0.00, 0.05, 0.35, 0.50)
    ROI_LIST = (0.12, 0.08, 0.85, 0.70)
    ROI_CHA = (0.82, 0.42, 0.18, 0.20)
    ROI_BATTLE_BTN = (0.88, 0.70, 0.12, 0.28)
    ROI_BATTLE_ICON = (0.38, 0.00, 0.24, 0.20)
    ROI_TAYIN_OCR = (0.15, 0.18, 0.20, 0.25)
    ROI_TAYIN_TPL1 = (0.14, 0.16, 0.22, 0.36)
    ROI_TAYIN_TPL2 = (0.10, 0.45, 0.32, 0.48)
    ROI_TAYIN_CLOSE = (0.62, 0.00, 0.36, 0.26)

    # 固定点击位（比例坐标）
    POS_CLOSE_ENTER_BATTLE = (0.842, 0.351)  # Maa 关闭进入战斗 target [1039,235,79,35] 中心

    # 滑动坐标（比例，与宝图任务一致）
    SWIPE_LIST_X = 0.571
    SWIPE_LIST_TOP_FROM = 0.179
    SWIPE_LIST_TOP_TO = 0.617
    SWIPE_LIST_DOWN_FROM = 0.528
    SWIPE_LIST_DOWN_TO = 0.347

    # ==================================================================
    # 主流程
    # ==================================================================
    def __init__(self) -> None:
        super().__init__()
        self._on_update = None
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._list_swipes = 0
        self._alt_c_pressed = False
        self._activity_tried = False
        self._swipe_vertical = self._do_swipe_vertical
        self._ocr_cache = None

    def run(self, context: TaskContext,
            on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._list_swipes = 0
        self._alt_c_pressed = False
        self._activity_tried = False
        self._swipe_vertical = self._do_swipe_vertical  # 允许测试替换
        self._ocr_cache = None

        mode_name = "海底秘境" if self.MIJING_MODE == "haidi" else "日月之井"
        end_level = self.END_LEVEL_HAIDI if self.MIJING_MODE == "haidi" else self.END_LEVEL_RIYUE
        logger.info("秘境降妖启动 hwnd=%s (模式=%s, 结束关卡>=%d)",
                    getattr(agent, "hwnd", None), mode_name, end_level)
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 4
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            # 步骤2: Maa「识别位置-东海湾-秘境-过渡」—— 回东海湾(必要时大地图传送)
            self._stage(agent, 2, "回到东海湾", self._node_back_to_donghaiwan)

            # 步骤3: 小地图 -> 云乐游 -> 秘境降妖入口 -> 选择模式 -> 继续挑战
            ok = self._stage(agent, 3, f"进入{mode_name}", self._node_enter_mijing)
            if not ok:
                self.snapshot.status = TaskStatus.FAILED
                self._report("未能进入秘境，请检查窗口状态与模板")
                logger.error("窗口=%s 未能进入秘境", agent.hwnd)
                return

            # 步骤4: 关卡监控循环（指定关卡结束/通关/失败/战斗）
            self._report(f"{mode_name}关卡推进中")
            result = self._level_loop(agent, end_level)

            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            messages = {
                "level": f"已到指定关卡(>={end_level})，离开秘境",
                "tongguan": "秘境正常通关",
                "shibai": "秘境战斗失败，提前退出秘境任务",
                "tayin": "遇见拓印，按 Maa 语义停止任务",
            }
            self._report(messages.get(result, "秘境降妖结束"))
            logger.info("秘境降妖结束(%s) hwnd=%s", result, agent.hwnd)
        except _Aborted:
            logger.info("秘境降妖停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("秘境降妖执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("秘境降妖执行异常，详见日志")

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
        if self._in_battle(agent, self._image(agent)):
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
    # 节点2: 识别位置-东海湾-秘境-过渡（回东海湾）
    # ==================================================================
    def _node_back_to_donghaiwan(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        # 识别位置-东海湾-秘境：OCR 东海湾
        if self._find_text_in(self._ocr_lines(agent), ("东海湾",),
                              self._fraction_region(w, h, self.ROI_DONGHAIWAN_OCR)):
            logger.info("窗口=%s 已在东海湾", agent.hwnd)
            return True
        # [JumpBack]dakai_map：Alt+M -> 打开大地图成功 -> chuansong_donghaiwan
        logger.info("窗口=%s 不在东海湾，打开大地图传送", agent.hwnd)
        self._press_hotkey(agent, "M")
        time.sleep(2.0)
        self._teleport_donghaiwan(agent)
        return False

    def _teleport_donghaiwan(self, agent) -> bool:
        deadline = time.monotonic() + 30.0
        clicked_icon = False
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            # 打开大地图成功_传送东海湾_秘境任务
            if self._match_any(agent, self.T_MAP_PANEL,
                               self._fraction_region(w, h, self.ROI_MAP_PANEL),
                               self.TH_MAP_PANEL):
                m = self._match_any(agent, self.T_DONGHAIWAN_MAP, None, self.TH_DONGHAIWAN_MAP)
                if m:
                    logger.info("窗口=%s 大地图点击东海湾 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    time.sleep(1.5)
                    self._ocr_cache = None
                    return True
            # [JumpBack]大地图界面-按键打开失败_点击图标
            if not clicked_icon:
                m = self._match_any(agent, self.T_MINIMAP,
                                    self._fraction_region(w, h, self.ROI_MINIMAP),
                                    self.TH_MINIMAP)
                if m:
                    logger.info("窗口=%s 点击小地图图标 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    clicked_icon = True
                    time.sleep(1.0)
                    continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 打开大地图/传送东海湾超时", agent.hwnd)
        return False

    # ==================================================================
    # 节点3: 小地图 -> 云乐游 -> 秘境入口 -> 选择模式 -> 继续挑战
    # ==================================================================
    def _node_enter_mijing(self, agent) -> bool:
        # click_tab_mijing: Tab 打开小地图
        agent.press_key("tab")
        time.sleep(1.5)
        # 东海湾小地图打开成功 -> click_map_yunleyou
        deadline = time.monotonic() + 45.0
        clicked_icon = False
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            tab_ok = self._match_any(agent, self.T_DONGHAIWAN_TAB,
                                     self._fraction_region(w, h, self.ROI_DONGHAIWAN_TAB),
                                     self.TH_DONGHAIWAN_TAB)
            if tab_ok and self._click_text_once(agent, ("云乐游", "云乐"), self.ROI_YUNLEYOU,
                                                wait=5.0):
                break
            # [JumpBack]小地图-按键打开失败-点击小地图图标
            if not clicked_icon:
                m = self._match_any(agent, self.T_MINIMAP,
                                    self._fraction_region(w, h, self.ROI_MINIMAP),
                                    self.TH_MINIMAP)
                if m:
                    logger.info("窗口=%s 点击小地图图标 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    clicked_icon = True
                    time.sleep(1.0)
                    continue
                agent.press_key("tab")
                time.sleep(1.0)
            if self._sleep(self.poll_interval):
                raise _Aborted()
        else:
            logger.warning("窗口=%s 小地图点击云乐游超时", agent.hwnd)

        # mijingxiangyao：OCR 秘境降妖（云乐游对话/秘境面板）
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            # 秘境降妖-选择模式 已出现 / 继续挑战 已出现 -> 直接进入模式选择
            if self._mode_panel_visible(agent):
                return self._select_mode_and_challenge(agent)
            if self._click_text_once(agent, ("秘境降妖",), self.ROI_MIJING_DIALOG, wait=1.0):
                continue
            # [JumpBack]秘境-云乐游失败-走活动入口（max_hit 1）
            if not self._activity_tried:
                self._activity_tried = True
                logger.info("窗口=%s 云乐游入口失败，改走活动入口", agent.hwnd)
                self._enter_via_activity(agent)
                continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 秘境入口超时", agent.hwnd)
        return False

    def _mode_panel_visible(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if self._match_any(agent, self.T_MOSHI,
                           self._fraction_region(w, h, self.ROI_MOSHI), self.TH_MOSHI):
            return True
        # 继续挑战按钮已可见（之前打过，直接续打）
        return self._find_text_in(self._ocr_lines(agent), ("挑战",),
                                  self._fraction_region(w, h, self.ROI_TIAOZHAN)) is not None

    def _select_mode_and_challenge(self, agent) -> bool:
        """秘境降妖-选择模式 -> 选择海底秘境/点击日月之井 -> 确认 -> 继续挑战。"""
        enter_roi = self.ROI_ENTER_HAIDI if self.MIJING_MODE == "haidi" else self.ROI_ENTER_RIYUE
        mode_name = "海底秘境" if self.MIJING_MODE == "haidi" else "日月之井"
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            if self._check_tayin(agent):
                self._close_tayin(agent)
                raise _Aborted()
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            # 继续挑战（OCR 挑战）—— 模式确认完成后的入口
            pos = self._find_text_in(self._ocr_lines(agent), ("挑战",),
                                     self._fraction_region(w, h, self.ROI_TIAOZHAN))
            if pos and not self._match_any(agent, self.T_MOSHI,
                                           self._fraction_region(w, h, self.ROI_MOSHI),
                                           self.TH_MOSHI):
                logger.info("窗口=%s 点击继续挑战 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(1.0)
                self._ocr_cache = None
                return True
            # 秘境降妖-选择模式 -> 选择海底秘境/点击日月之井（OCR 进入）
            if self._match_any(agent, self.T_MOSHI,
                               self._fraction_region(w, h, self.ROI_MOSHI), self.TH_MOSHI):
                pos = self._find_text_in(self._ocr_lines(agent), ("进入",),
                                         self._fraction_region(w, h, enter_roi), exact=True)
                if pos:
                    logger.info("窗口=%s 选择%s，点击进入 %s", agent.hwnd, mode_name, pos)
                    agent.click(pos[0], pos[1])
                    time.sleep(1.0)
                    self._ocr_cache = None
                    continue
            # 秘境降妖-(海底|日月)-确认（moshi_queding）
            m = self._match_any(agent, self.T_MOSHI_QUEDING,
                                self._fraction_region(w, h, self.ROI_MOSHI_QUEDING),
                                self.TH_MOSHI_QUEDING)
            if m:
                logger.info("窗口=%s 模式确认 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(0.5)
                continue
            # [JumpBack]清理主界面使用-关闭
            m = self._match_any(agent, self.T_CHA,
                                self._fraction_region(w, h, self.ROI_CHA), self.TH_CHA)
            if m:
                logger.info("窗口=%s 关闭主界面\"使用\"弹窗 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(1.0)
                continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        return False

    def _enter_via_activity(self, agent) -> None:
        """Maa「主界面-秘境降妖」：panduan_ks -> Alt+C -> 活动 -> 日常活动 -> 找秘境 -> 参加。"""
        agent.press_key("esc")  # panduan_zhujiemian_ks
        time.sleep(0.8)
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            self._dismiss_popups(agent)
            img = self._image(agent)
            if img is None:
                return
            h, w = img.shape[:2]
            # 活动-秘境降妖：面板判断
            panel = self._match_any(agent, self.T_ACTIVITY_PANEL,
                                    self._fraction_region(w, h, self.ROI_ACTIVITY_PANEL),
                                    self.TH_ACTIVITY_PANEL)
            if panel is None:
                if not self._alt_c_pressed:
                    self._press_hotkey(agent, "C")  # Maa ClickKey[57,31] = Alt+C
                    self._alt_c_pressed = True
                    time.sleep(1.0)
                    continue
                m = self._match_any(agent, self.T_ACTIVITY_BUTTON,
                                    self._fraction_region(w, h, self.ROI_ACTIVITY_BUTTON),
                                    self.TH_ACTIVITY_BUTTON)
                if m:
                    agent.click(m[0], m[1])
                    time.sleep(1.0)
                continue
            # 活动-秘境降妖-点击日常活动
            if self._click_text_once(agent, ("日常活动",), self.ROI_DAILY_LEFT, wait=1.0):
                # 活动-秘境降妖-向上滑动到顶端 MultiSwipe x2
                for _ in range(2):
                    self._swipe_vertical(agent, self.SWIPE_LIST_X,
                                         self.SWIPE_LIST_TOP_FROM, self.SWIPE_LIST_TOP_TO)
                    time.sleep(0.4)
                continue
            # 活动-秘境降妖-开始：And(mijing_rukou 模板 0.9, OCR 秘境降妖)
            list_roi = self._fraction_region(w, h, self.ROI_LIST)
            if self._match_any(agent, self.T_MIJING_RUKOU, list_roi, self.TH_MIJING_RUKOU):
                pos = self._find_text_in(self._ocr_lines(agent), ("秘境降妖",), list_roi)
                if pos:
                    logger.info("窗口=%s 活动列表找到秘境降妖", agent.hwnd)
                    # 活动-秘境降妖-开始-点击参加
                    join = self._find_text_in(self._ocr_lines(agent), ("参加",), list_roi,
                                              exact=True)
                    if join:
                        logger.info("窗口=%s 点击参加 %s", agent.hwnd, join)
                        agent.click(join[0], join[1])
                        time.sleep(4.0)
                        self._ocr_cache = None
                        return
            # [JumpBack]baotu_huodong_down：列表翻页
            if self._list_swipes < self.list_swipe_max:
                self._swipe_vertical(agent, self.SWIPE_LIST_X,
                                     self.SWIPE_LIST_DOWN_FROM, self.SWIPE_LIST_DOWN_TO)
                self._list_swipes += 1
                self._ocr_cache = None
                time.sleep(1.0)
                continue
            return
        logger.warning("窗口=%s 活动入口进入秘境超时", agent.hwnd)

    # ==================================================================
    # 节点4: 关卡监控循环（继续挑战 的 next 列表）
    # ==================================================================
    def _level_loop(self, agent, end_level: int) -> str:
        """返回 "level"(指定关卡结束) / "tongguan" / "shibai" / "tayin"。"""
        riyue = self.MIJING_MODE == "riyue"
        level_roi = self.ROI_LEVEL_RIYUE if riyue else self.ROI_LEVEL_HAIDI
        level_click_roi = self.ROI_LEVEL_RIYUE if riyue else self.ROI_LEVEL_CLICK_HAIDI
        tongguan_roi = self.ROI_TONGGUAN_RIYUE if riyue else self.ROI_TONGGUAN_HAIDI
        shibai_roi = self.ROI_SHIBAI_RIYUE if riyue else self.ROI_SHIBAI_HAIDI
        shibai_tpls = self.T_SHIBAI_RIYUE if riyue else self.T_SHIBAI_HAIDI

        while True:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                if self._sleep(self.poll_interval):
                    raise _Aborted()
                continue
            h, w = img.shape[:2]

            # Maa「识别拓印_停止」
            if self._check_tayin(agent):
                logger.info("窗口=%s 遇见拓印，停止所有任务", agent.hwnd)
                self._close_tayin(agent)
                return "tayin"

            # [JumpBack]海底/日月-关闭进入战斗：OCR 进入战斗 -> 点固定位关闭
            if self._find_text_in(self._ocr_lines(agent), ("进入战斗",),
                                  self._fraction_region(w, h, self.ROI_ENTER_BATTLE)):
                fx = int(w * self.POS_CLOSE_ENTER_BATTLE[0])
                fy = int(h * self.POS_CLOSE_ENTER_BATTLE[1])
                logger.info("窗口=%s 关闭进入战斗 (%d,%d)", agent.hwnd, fx, fy)
                agent.click(fx, fy)
                time.sleep(0.8)
                self._ocr_cache = None
                continue

            # 海底/日月-指定关卡结束任务（ExpressionRecognition: {关卡识别}>=N）
            level = self._ocr_level(agent, level_roi)
            if level is not None and level >= end_level:
                logger.info("窗口=%s 当前关卡 %d >= %d，指定关卡结束任务",
                            agent.hwnd, level, end_level)
                self._leave_mijing(agent)
                return "level"

            # [JumpBack]海底/日月-点击关卡：OCR 第N关 -> 点击 -> 进入战斗/战斗5秒
            pos = self._find_level_click(agent, level_click_roi)
            if pos:
                logger.info("窗口=%s 点击关卡 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(1.5 if riyue else 0.5)
                self._ocr_cache = None
                # 秘境-点击进入战斗
                if self._click_text_once(agent, ("进入战斗",), self.ROI_ENTER_BATTLE, wait=1.0):
                    pass
                elif self._in_battle(agent, self._image(agent)):
                    if self._sleep(self.battle_wait_short):
                        raise _Aborted()
                continue

            # [JumpBack]关闭酒店老板弹窗
            m = self._match_any(agent, self.T_JIUDIAN,
                                self._fraction_region(w, h, self.ROI_JIUDIAN), self.TH_JIUDIAN)
            if m:
                logger.info("窗口=%s 关闭酒店老板弹窗 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(0.5)
                continue

            # mijing_tongguan / 日月之井-通关：OCR 通关
            if self._find_text_in(self._ocr_lines(agent), ("通关",),
                                  self._fraction_region(w, h, tongguan_roi)):
                logger.info("窗口=%s 秘境正常通关", agent.hwnd)
                self._leave_mijing(agent)
                return "tongguan"

            # mijing_shibai / 日月之井-失败：模板
            if self._match_any(agent, shibai_tpls,
                               self._fraction_region(w, h, shibai_roi), self.TH_SHIBAI):
                logger.info("窗口=%s 秘境战斗失败，提前退出", agent.hwnd)
                self._leave_mijing(agent)
                return "shibai"

            # [JumpBack]战斗中-等待20秒
            if self._in_battle(agent, img):
                logger.info("窗口=%s 战斗中，等待 %.0f 秒", agent.hwnd, self.battle_wait)
                if self._sleep(self.battle_wait):
                    raise _Aborted()
                continue

            if self._sleep(self.poll_interval):
                raise _Aborted()

    def _ocr_level(self, agent, roi_frac) -> Optional[int]:
        """Maa「海底/日月-关卡识别」：OCR 关卡区域，取第一个数字。"""
        img = self._image(agent)
        if img is None:
            return None
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, roi_frac)
        for item in self._ocr_lines(agent):
            cx, cy = item["center"]
            if not (x <= cx <= x + rw and y <= cy <= y + rh):
                continue
            m = re.search(r"\d+", item.get("text") or "")
            if m:
                return int(m.group(0))
        return None

    def _find_level_click(self, agent, roi_frac) -> Optional[Tuple[int, int]]:
        """Maa「海底/日月-点击关卡」：OCR"第N关"的近似（含"第"和"关"且有数字）。"""
        img = self._image(agent)
        if img is None:
            return None
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, roi_frac)
        for item in self._ocr_lines(agent):
            text = (item.get("text") or "").strip()
            if not ("第" in text and "关" in text and re.search(r"\d+", text)):
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return (int(cx), int(cy))
        return None

    def _leave_mijing(self, agent) -> None:
        """指定关卡结束/通关/失败的收尾：清理弹窗 -> 秘境-点击离开 -> 回东海湾/主界面。"""
        # [JumpBack]清理主界面使用-关闭
        img = self._image(agent)
        if img is not None:
            h, w = img.shape[:2]
            m = self._match_any(agent, self.T_CHA,
                                self._fraction_region(w, h, self.ROI_CHA), self.TH_CHA)
            if m:
                agent.click(m[0], m[1])
                time.sleep(0.8)
        # 秘境-点击离开（OCR 离开，等它出现）
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            if self._click_text_once(agent, ("离开",), self.ROI_LIKAI, wait=2.0, exact=True):
                break
            # [JumpBack]战斗中-等待5秒
            if self._in_battle(agent, self._image(agent)):
                if self._sleep(self.battle_wait_short):
                    raise _Aborted()
                continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        # 秘境-完成-返回东海湾 / panduan_zhujiemian
        self._run_node(agent, self._node_back_to_donghaiwan, 30.0, "返回东海湾")

    def _dismiss_popups(self, agent) -> bool:
        """Maa「战斗平衡弹窗-点击关闭」。"""
        m = self._match_any(agent, self.T_POPUP_CLOSE, None, self.TH_POPUP_CLOSE)
        if not m:
            return False
        agent.click(m[0], m[1])
        logger.info("窗口=%s 关闭战斗平衡弹窗 %s", agent.hwnd, m[:2])
        time.sleep(0.6)
        return True

    # ------------------------------------------------------------------
    # 拓印
    # ------------------------------------------------------------------
    def _check_tayin(self, agent) -> bool:
        """Maa「识别拓印_停止」= Or(OCR"拓印", tayin 模板 x2)。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_TAYIN_OCR)
        for item in self._ocr_lines(agent):
            text = (item.get("text") or "").strip()
            if not any(k in text for k in ("拓印", "拓", "印")):
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return True
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
                self._ocr_cache = None
                return
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 未找到拓印界面关闭按钮", agent.hwnd)

    # ==================================================================
    # 战斗判定（Maa 模板优先，HoughCircles 兜底）
    # ==================================================================
    def _in_battle(self, agent, img) -> bool:
        if img is None:
            return False
        h, w = img.shape[:2]
        if self._match_any(agent, self.T_BATTLE_BTN,
                           self._fraction_region(w, h, self.ROI_BATTLE_BTN), self.TH_BATTLE):
            return True
        if self._match_any(agent, self.T_BATTLE_ICON,
                           self._fraction_region(w, h, self.ROI_BATTLE_ICON), self.TH_BATTLE):
            return True
        return self._in_battle_circles(img)

    def _in_battle_circles(self, img) -> bool:
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

    def _report(self, message: str) -> None:
        self.snapshot.message = message
        if self._on_update:
            self._on_update(self.snapshot)

# -*- coding: utf-8 -*-
"""捉鬼任务 —— 按 Maa_MHXY 的 zhuoguirenwu.json 流水线原样移植到 game_agent。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/zhuoguirenwu.json
    (+ 共享节点: my_task.json「panduan_zhujiemian / 识别拓印_停止 / 自动寻路中-图片识别 /
       战斗中-等待100秒」 fuben69.json「大地图界面-按键打开失败_点击图标 / 关闭福利弹窗」
       chongwuqifu.json「小地图-按键打开失败-点击小地图图标」
       chuangjianduiwu.json「队伍界面-按键打开失败-点击队伍图标」)

======================= Maa 原始流程(节点图) =======================
zhuoguirenwu -> 识别位置-长安城-抓鬼-过渡(主界面 +/称号)
  next: [JumpBack]展开-首页任务栏 / 任务栏切换为任务
        点击任务栏-捉鬼任务          已领取(捉鬼(x/y)/捉拿.*鬼/千年厉鬼) -> 抓鬼循环
        识别位置-长安城-抓鬼         OCR 长安城 -> 打开小地图-钟馗
        [JumpBack]打开大地图_捉鬼    Alt+M -> 传送长安城_捉鬼

打开小地图-钟馗: ClickKey[61](Tab) -> 点击钟馗(小地图CA模板/OCR 钟馗, 点固定位)
  -> 钟馗-捉鬼任务-循环           OCR 捉鬼任务 -> 点击领取
     next: 识别拓印_停止 / 抓鬼领取双倍弹窗->确定 / 没有辅助提示-点击取消 /
           抓鬼不足五人(取消->钟馗->捉鬼任务) / 任务栏三件套 / 点击任务栏-捉鬼任务
  -> 钟馗-捉鬼任务-已领取捉鬼任务  模板0.9 -> ESC -> 任务栏点击捉鬼任务

点击任务栏-捉鬼任务 next (抓鬼监控循环):
    [JumpBack]捉鬼-领取双倍点数弹窗  OCR"双倍点数不足..." -> 点确定固定位
    抓鬼一轮完成                   OCR"少侠已经捉完1轮鬼..." -> 点确定 -> 再次点击确定
                                   -> 捉鬼-队伍人员满员判断(选项: 人员检测)
                                   -> 抓鬼轮次计算-max(选项: 轮次选择) / 捉鬼-结束
    [JumpBack]自动寻路中-图片识别   等3秒
    [JumpBack]战斗中-等待100秒
    [JumpBack]抓鬼-点击任务栏-通用  再点任务栏捉鬼条目
    [JumpBack]任务栏切换为任务
    [JumpBack]关闭福利弹窗

捉鬼-队伍人员满员判断: Alt+T -> 进入组队界面成功(duiwu-duiwu 0.9)
    ([JumpBack]取消钟馗接取任务列表 / 队伍界面-按键打开失败-点击队伍图标)
  -> 识别队伍离线/暂离(OCR -> 点人 -> 请离队伍 -> 自动匹配)
  -> 未识别离线/暂离(inverse) -> 点击自动匹配2 -> 抓鬼-关闭组队界面(duiwu-guanbi)
  -> 钟馗-捉鬼任务-循环 / [JumpBack]抓鬼-关闭组队后打开小地图 -> 点击钟馗 -> 领取下一轮

======================= Maa 任务选项映射 =======================
「（开启/关闭）人员检测-（是否）进入轮次选择」:
  - 开启人员检测-不进入轮次选择(默认): TEAM_CHECK=True,  ROUNDS=0(无限)
  - 开启人员检测-进入轮次选择:         TEAM_CHECK=True,  ROUNDS=N(抓鬼轮次输入2)
  - 关闭人员检测-进入轮次选择:         TEAM_CHECK=False, ROUNDS=N
  - 关闭人员检测-不进入轮次选择:       TEAM_CHECK=False, ROUNDS=0

======================= 移植适配说明 =======================
官网 PC 客户端(Unity) 与 Maa 的模拟器(1280x720) 不同:
  1. 布局非等比, roi 由 Maa 像素坐标换算为窗口比例并适当放大, 模板匹配用多尺度。
  2. ClickKey[57,41]=Alt+M(大地图), ClickKey[61]=Tab(小地图), ClickKey[57,48]=Alt+T(队伍),
     均用 win32 keybd_event / agent.press_key 实现。
  3. OCR 走整图识别+ROI 中心过滤(带缓存); regex 预期(捉鬼(x/y)/捉拿.*鬼)按包含关系近似。
  4. 战斗判断: Maa 模板(zhandou/zidong|quxiao 0.9)优先, HoughCircles 兜底;
     战斗中等待与 Maa 一致为 100 秒。
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


class ZhuoguiMaaTask(AutomationTask):
    definition = TaskDefinition(
        "zhuogui_maa", "捉鬼任务", "移植自 Maa_MHXY 的 zhuoguirenwu 流水线"
    )

    # ---------------- 任务选项（对应 Maa 任务选项，见模块 docstring）----------------
    TEAM_CHECK = True            # 人员检测（抓鬼一轮完成后检查离线/暂离并自动匹配）
    ROUNDS = 0                   # 轮次上限：0=无限(Maa 默认)；N=捉 N 轮后结束

    # ---------------- 时序参数（对应 Maa 流水线字段）----------------
    poll_interval = 0.5
    node_timeout = 90.0
    battle_wait = 100.0          # Maa: 战斗中-等待100秒 (pre_delay 100000)
    autopath_wait = 3.0          # Maa: 自动寻路中-图片识别 (pre_delay 3000)
    taskbar_swipe_max = 4        # Maa: 捉鬼-下滑任务栏 (max_hit 4)
    total_timeout = 7200.0       # 整个任务上限(无限模式下靠 Ctrl+C / 超时停止)

    # ---------------- 可调开关 ----------------
    ocr_cache_seconds = 2.0

    # ---------------- 阈值 ----------------
    TH_MAIN_INDICATOR = 0.75
    TH_TASKBAR_TAB = 0.80
    TH_YILINGQU = 0.90           # Maa: 钟馗-捉鬼任务-已领取捉鬼任务 threshold 0.9
    TH_ZAIQUE = 0.90             # Maa: 抓鬼一轮完成-再次点击确定(图) threshold 0.9
    TH_DUIWU_PANEL = 0.90        # Maa: 捉鬼-进入组队界面成功 threshold 0.9
    TH_BUZU5 = 0.80
    TH_ZHONGKUI = 0.75
    TH_XIAODITU_CA = 0.75
    TH_SHUANGBEI_TPL = 0.80
    TH_FULI = 0.80
    TH_DUIWU_GUANBI = 0.80
    TH_DUIWU_ICON = 0.80
    TH_MINIMAP = 0.85            # Maa: 小地图-按键打开失败 threshold 0.85
    TH_MAP_PANEL = 0.75
    TH_CHANGAN_TAB = 0.75
    TH_POPUP_CLOSE = 0.88
    TH_AUTOPATH = 0.90
    TH_BATTLE = 0.90
    TH_TAYIN = 0.90
    TH_TAYIN_CLOSE = 0.80

    # ---------------- 模板名（templates/ 目录，不带 .png）----------------
    T_MAIN_INDICATORS = ("zonghe/jiahao", "zonghe/baoguo", "zonghe/baoguo_man", "zonghe/chenghao")
    T_MAIN_JIAHAO_CHENGHAO = ("zonghe/chenghao", "zonghe/jiahao")  # Maa 识别位置-长安城-抓鬼-过渡
    T_TASKBAR_COLLAPSED = ("zonghe/rwl_suojin", "zonghe/rwl_suojin2")
    # Maa「钟馗-捉鬼任务-已领取捉鬼任务」
    T_YILINGQU = ("zhuagui/zhuagui_yilingqurenwu1", "zhuagui/zhuagui_yilingqurenwu2")
    # Maa「抓鬼一轮完成-再次点击确定」(图)
    T_ZAIQUE = ("zhuagui/zhuaguijiesu3",)
    # Maa「捉鬼-进入组队界面成功」/「抓鬼-关闭组队界面」/「队伍界面-按键打开失败-点击队伍图标」
    T_DUIWU_PANEL = ("duiwu/duiwu-duiwu",)
    T_DUIWU_GUANBI = ("duiwu/duiwu-guanbi",)
    T_DUIWU_ICON = ("duiwu/duiwu",)
    # Maa「抓鬼不足五人-图片识别」/「抓鬼不足五人-点击钟馗」
    T_BUZU5 = ("zhuagui/buzu5ren",)
    T_ZHONGKUI = ("zhuagui/zhongkui",)
    # Maa「点击钟馗」(小地图上的 CA 标记)
    T_XIAODITU_CA = ("zonghe/xiaoditu_CA",)
    # Maa「抓鬼领取双倍弹窗」
    T_SHUANGBEI = ("zhuagui/zhuagui_shuangbei",)
    # Maa「关闭福利弹窗」
    T_FULI = ("qiandao/fuli",)
    # Maa「打开大地图成功_传送长安城」/「传送长安城」/「大小地图图标」
    T_MAP_PANEL = ("zonghe/ditu_jiemian_panduan", "zonghe/ditu_jiemian_panduan2")
    T_CHANGAN_TAB = ("zonghe/tab_changancheng", "zonghe/tab_changancheng2", "zonghe/tab_changancheng3")
    T_MINIMAP = ("zonghe/xiaoditu_taiyang", "zonghe/xiaoditu_yueliang")
    # Maa「战斗平衡弹窗-点击关闭」/「识别拓印_停止」/「关闭拓印界面」
    T_POPUP_CLOSE = ("zonghe/zhandoupingheng_guanbi1",)
    T_TAYIN = ("tayin/tayin", "tayin/tayin2")
    T_TAYIN_CLOSE = ("zonghe/guanbi6", "zonghe/guanbi7")
    # Maa「自动寻路中-图片识别」/「战斗中-等待100秒」
    T_AUTOPATH = ("zonghe/zidongxunlu1", "zonghe/zidongxunlu2", "zonghe/zidongxunlu3", "zonghe/zidongxunlu4")
    T_BATTLE_BTN = ("zhandou/zidong", "zhandou/quxiao")
    T_BATTLE_ICON = ("zhandou/zhandou1", "zhandou/zhandou2", "zhandou/zhandou3")

    # ---------------- 区域比例（由 Maa 1280x720 像素 roi 换算并适当放大）----------------
    ROI_MAIN_INDICATOR = (0.86, 0.72, 0.14, 0.28)
    ROI_JIAHAO_BR = (0.86, 0.80, 0.14, 0.20)       # Maa [1206,637,66,57] 放大
    ROI_TASKBAR_TAB = (0.86, 0.08, 0.14, 0.22)
    ROI_TASKBAR_TABS = (0.80, 0.12, 0.20, 0.07)
    # Maa 点击任务栏-捉鬼任务 [1035,170,243,334] / 通用 [1032,165,247,300]；官网客户端任务栏更靠左
    ROI_TASKBAR_TEXT = (0.68, 0.10, 0.32, 0.62)
    ROI_CHANGAN_OCR = (0.02, 0.00, 0.25, 0.12)     # Maa [108,22,117,31] 放大
    ROI_MAP_PANEL = (0.00, 0.00, 0.28, 0.24)
    ROI_MINIMAP = (0.00, 0.00, 0.18, 0.20)         # Maa [58,1,75,79] 放大
    ROI_XIAODITU_CA = (0.05, 0.05, 0.90, 0.90)     # Maa [114,69,1040,630] 放大
    ROI_ZHONGKUI_MINIMAP_OCR = (0.20, 0.44, 0.25, 0.20)  # Maa [357,391,72,43] 放大
    ROI_ZHONGKUI_DIALOG = (0.64, 0.05, 0.34, 0.80) # Maa [925,73,312,482] 放大
    ROI_YILINGQU = (0.60, 0.06, 0.38, 0.75)        # Maa [872,94,355,441] 放大
    ROI_YILUN_OCR = (0.25, 0.30, 0.50, 0.25)       # Maa [420,270,450,110] 放大
    ROI_ZAIQUE_TPL = (0.42, 0.42, 0.30, 0.25)      # Maa [654,370,180,96] 放大
    ROI_ZAIQUE_OCR = (0.25, 0.25, 0.50, 0.55)      # Maa [385,225,540,325] 放大
    ROI_SHUANGBEI_OCR = (0.25, 0.34, 0.45, 0.24)   # Maa [430,300,393,100] 放大
    ROI_SHUANGBEI_TPL = (0.24, 0.28, 0.50, 0.40)   # Maa [402,263,475,196] 放大
    ROI_QUXIAO_FUZHU = (0.24, 0.42, 0.34, 0.30)    # Maa [403,367,265,124] 放大
    ROI_BUZU5 = (0.22, 0.24, 0.52, 0.50)           # Maa [384,224,502,280] 放大
    ROI_ZHONGKUI_NPC_TPL = (0.15, 0.08, 0.60, 0.70)  # Maa [294,102,583,386] 放大
    ROI_ZHONGKUI_NPC_OCR = (0.10, 0.18, 0.75, 0.66)  # Maa [186,157,853,426] 放大
    ROI_FULI = (0.28, 0.00, 0.46, 0.22)            # Maa [414,17,487,103] 放大
    ROI_DUIWU_PANEL = (0.00, 0.00, 0.30, 0.25)     # Maa [0,0,229,106] 放大
    ROI_DUIWU_ICON = (0.80, 0.08, 0.20, 0.20)      # Maa [1161,104,119,65] 放大
    ROI_ZHONGKUI_BOTTOMLEFT = (0.02, 0.82, 0.30, 0.18)  # Maa [91,646,204,74] 放大
    ROI_OFFLINE = (0.20, 0.50, 0.70, 0.20)         # Maa [341,432,757,41] 放大
    ROI_QINGLI = (0.20, 0.15, 0.68, 0.52)          # Maa [336,153,767,295] 放大
    ROI_ZIDONG_PIPEI = (0.70, 0.03, 0.28, 0.18)    # Maa [1024,57,152,60] 放大
    ROI_DUIWU_GUANBI = (0.80, 0.00, 0.20, 0.22)    # Maa [1153,0,100,98] 放大
    ROI_AUTOPATH = (0.20, 0.18, 0.60, 0.64)
    ROI_BATTLE_BTN = (0.88, 0.70, 0.12, 0.28)      # Maa [1175,549,103,159]
    ROI_BATTLE_ICON = (0.38, 0.00, 0.24, 0.20)     # Maa [568,0,140,101]
    ROI_TAYIN_OCR = (0.15, 0.18, 0.20, 0.25)
    ROI_TAYIN_TPL1 = (0.14, 0.16, 0.22, 0.36)
    ROI_TAYIN_TPL2 = (0.10, 0.45, 0.32, 0.48)
    ROI_TAYIN_CLOSE = (0.62, 0.00, 0.36, 0.26)

    # 固定点击位（比例坐标）
    POS_ZHONGKUI_CLICK = (0.309, 0.572)   # Maa 点击钟馗 target [377,403,38,19] 中心
    POS_CONFIRM = (0.583, 0.581)          # Maa 双倍/一轮完成 target [718,403,57,31] 中心
    POS_FULI_CLOSE = (0.891, 0.079)       # Maa 关闭福利弹窗 target [1140,57,32,35] 中心

    # 滑动坐标（比例）
    SWIPE_TASKBAR_X = 0.896        # Maa x=1147/1280
    SWIPE_TASKBAR_FROM = 0.2875    # 捉鬼-下滑任务栏: 207 -> 403 (手指下滑)
    SWIPE_TASKBAR_TO = 0.5597

    # ==================================================================
    # 主流程
    # ==================================================================
    def __init__(self) -> None:
        super().__init__()
        self._on_update = None
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._rounds_done = 0
        self._swipe_vertical = self._do_swipe_vertical
        self._ocr_cache = None

    def run(self, context: TaskContext,
            on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._rounds_done = 0
        self._swipe_vertical = self._do_swipe_vertical  # 允许测试替换
        self._ocr_cache = None

        logger.info("捉鬼任务启动 hwnd=%s (人员检测=%s, 轮次=%s)",
                    getattr(agent, "hwnd", None), self.TEAM_CHECK,
                    self.ROUNDS if self.ROUNDS > 0 else "无限")
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 3
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            # 步骤2: Maa「识别位置-长安城-抓鬼-过渡」—— 任务栏直接进 / 钟馗领取
            self._report("查找捉鬼任务入口")
            result = self._entry_flow(agent)
            if result == "tayin":
                self.snapshot.completed_steps = self.snapshot.total_steps
                self.snapshot.status = TaskStatus.COMPLETED
                self._report("遇见拓印，按 Maa 语义停止任务")
                return
            if not result:
                self.snapshot.status = TaskStatus.FAILED
                self._report("未能领取/找到捉鬼任务，请检查窗口状态与模板")
                logger.error("窗口=%s 未能进入捉鬼任务", agent.hwnd)
                return
            self.snapshot.completed_steps = 2

            # 步骤3: 抓鬼监控循环
            self._report("捉鬼进行中")
            result = self._hunt_loop(agent)

            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            if result == "tayin":
                self._report("遇见拓印，按 Maa 语义停止任务")
            elif result == "rounds":
                self._report(f"捉鬼完成，共 {self._rounds_done} 轮")
            else:
                self._report("捉鬼任务结束")
            logger.info("捉鬼任务结束(%s, 轮次=%d) hwnd=%s", result, self._rounds_done, agent.hwnd)
        except _Aborted:
            logger.info("捉鬼任务停止 hwnd=%s", getattr(agent, "hwnd", None))
        except _TayinAbort:
            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            self._report("遇见拓印，按 Maa 语义停止任务")
            logger.info("捉鬼任务因拓印停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("捉鬼任务执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("捉鬼任务执行异常，详见日志")

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
    # 节点2: 入口流程（识别位置-长安城-抓鬼-过渡 的 next 列表）
    # ==================================================================
    def _entry_flow(self, agent):
        """返回 True(已进入抓鬼) / "tayin" / False(失败)。"""
        started = time.monotonic()
        swipes = 0
        while time.monotonic() - started < self.node_timeout * 2:
            self._check_stop(agent)
            if self._check_tayin(agent):
                self._close_tayin(agent)
                return "tayin"

            # [JumpBack]展开-首页任务栏
            img = self._image(agent)
            if img is None:
                if self._sleep(self.poll_interval):
                    raise _Aborted()
                continue
            h, w = img.shape[:2]
            m = self._match_any(agent, self.T_TASKBAR_COLLAPSED,
                                self._fraction_region(w, h, self.ROI_TASKBAR_TAB),
                                self.TH_TASKBAR_TAB)
            if m:
                logger.info("窗口=%s 展开首页任务栏 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(0.8)
                continue
            # [JumpBack]任务栏切换为任务
            if self._node_switch_task_tab(agent):
                continue
            # 点击任务栏-捉鬼任务：已领取 -> 直接进抓鬼循环
            pos = self._find_zhuogui_task(agent)
            if pos:
                logger.info("窗口=%s 任务栏已有捉鬼任务，点击 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(1.0)
                self._ocr_cache = None
                return True
            # 识别位置-长安城-抓鬼：在长安 -> 打开小地图找钟馗
            if self._find_text_in(self._ocr_lines(agent), ("长安城",),
                                  self._fraction_region(w, h, self.ROI_CHANGAN_OCR)):
                logger.info("窗口=%s 已在长安城，打开小地图找钟馗", agent.hwnd)
                if self._zhongkui_accept(agent):
                    return True
                # 钟馗领取失败 -> 打开大地图重新传送再试
            # [JumpBack]捉鬼-下滑任务栏
            if swipes < self.taskbar_swipe_max:
                self._swipe_vertical(agent, self.SWIPE_TASKBAR_X,
                                     self.SWIPE_TASKBAR_FROM, self.SWIPE_TASKBAR_TO)
                swipes += 1
                self._ocr_cache = None
                time.sleep(1.0)
                continue
            # [JumpBack]打开大地图_捉鬼 -> 传送长安城
            logger.info("窗口=%s 不在长安/任务栏无捉鬼，打开大地图传送长安城", agent.hwnd)
            self._open_map_and_teleport(agent)
            swipes = 0
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 入口流程超时", agent.hwnd)
        return False

    def _node_switch_task_tab(self, agent) -> bool:
        """Maa「任务栏切换为任务」（与宝图任务一致）：OCR 页签，绝不盲点。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_TASKBAR_TABS)
        candidates = []
        for item in self._ocr_lines(agent):
            text = (item.get("text") or "").strip()
            if not text or len(text) > 4:
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                candidates.append((cx, cy, text))
        pos = None
        for cx, cy, text in candidates:
            if "务" in text:  # "任务"/"彐干务"/"仸务" 都能命中
                pos = (int(cx), int(cy))
                break
        if pos is None:
            rest = [c for c in candidates if "队" not in c[2]]
            if rest:
                rest.sort()
                pos = (int(rest[0][0]), int(rest[0][1]))
        if pos:
            logger.info("窗口=%s 点击任务栏「任务」页签 %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
            time.sleep(0.8)
            self._ocr_cache = None
            return True
        return False

    def _find_zhuogui_task(self, agent) -> Optional[Tuple[int, int]]:
        """Maa「点击任务栏-捉鬼任务」/「抓鬼-点击任务栏-通用」的 OCR 匹配。

        原 regex: 捉鬼[(（]\\d*/\\d*[)）] / 捉拿.*鬼 / 千年厉鬼 —— 按包含关系近似。
        """
        img = self._image(agent)
        if img is None:
            return None
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_TASKBAR_TEXT)
        for item in self._ocr_lines(agent):
            text = (item.get("text") or "").strip()
            hit = ("捉鬼" in text or "千年厉鬼" in text or
                   ("捉拿" in text and "鬼" in text))
            if not hit:
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return (int(cx), int(cy))
        return None

    # ==================================================================
    # 钟馗领取（打开小地图-钟馗 -> 点击钟馗 -> 循环/已领取）
    # ==================================================================
    def _zhongkui_accept(self, agent) -> bool:
        """对应 打开小地图-钟馗 / 点击钟馗 / 钟馗-捉鬼任务-循环 / 已领取捉鬼任务。"""
        agent.press_key("tab")  # Maa ClickKey[61] = Tab 打开小地图
        time.sleep(1.0)
        deadline = time.monotonic() + 45.0
        clicked_icon = False
        while time.monotonic() < deadline:
            self._check_stop(agent)
            if self._click_zhongkui_on_map(agent):
                break
            # [JumpBack]小地图-按键打开失败-点击小地图图标
            if not clicked_icon:
                img = self._image(agent)
                if img is not None:
                    h, w = img.shape[:2]
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
            logger.warning("窗口=%s 小地图点击钟馗超时", agent.hwnd)
            return False

        # 点击钟馗后：钟馗-捉鬼任务-循环(领取) 或 钟馗-捉鬼任务-已领取捉鬼任务(ESC -> 任务栏)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            # 钟馗-捉鬼任务-循环：OCR 捉鬼任务 -> 点击领取
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            pos = self._find_text_in(self._ocr_lines(agent), ("捉鬼任务",),
                                     self._fraction_region(w, h, self.ROI_ZHONGKUI_DIALOG))
            if pos:
                logger.info("窗口=%s 领取捉鬼任务，点击 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(2.0)
                self._ocr_cache = None
                self._post_accept_popups(agent)
                return True
            # 钟馗-捉鬼任务-已领取捉鬼任务：模板 0.9 -> ESC -> 点任务栏
            m = self._match_any(agent, self.T_YILINGQU,
                                self._fraction_region(w, h, self.ROI_YILINGQU),
                                self.TH_YILINGQU)
            if m:
                logger.info("窗口=%s 已领取过捉鬼任务，ESC 后点任务栏", agent.hwnd)
                agent.press_key("esc")
                time.sleep(2.0)
                self._click_taskbar_zhuogui_with_retries(agent)
                return True
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 钟馗对话未出现捉鬼任务选项", agent.hwnd)
        return False

    def _click_zhongkui_on_map(self, agent) -> bool:
        """Maa「点击钟馗」= Or(小地图CA模板, OCR 钟馗) -> 点固定位。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        hit = self._match_any(agent, self.T_XIAODITU_CA,
                              self._fraction_region(w, h, self.ROI_XIAODITU_CA),
                              self.TH_XIAODITU_CA)
        if not hit:
            hit = self._find_text_in(self._ocr_lines(agent), ("钟馗", "钟道", "钟", "道"),
                                     self._fraction_region(w, h, self.ROI_ZHONGKUI_MINIMAP_OCR))
        if not hit:
            return False
        fx, fy = int(w * self.POS_ZHONGKUI_CLICK[0]), int(h * self.POS_ZHONGKUI_CLICK[1])
        logger.info("窗口=%s 小地图点击钟馗 (%d,%d)", agent.hwnd, fx, fy)
        agent.click(fx, fy)
        time.sleep(3.0)
        self._ocr_cache = None
        return True

    def _post_accept_popups(self, agent) -> None:
        """Maa「钟馗-捉鬼任务-循环」next 里的领取后弹窗处理（拓印/双倍/辅助提示/不足五人）。"""
        for _ in range(10):
            self._check_stop(agent)
            if self._check_tayin(agent):
                self._close_tayin(agent)
                raise _TayinAbort()
            if self._handle_shuangbei(agent):
                continue
            if self._click_text_once(agent, ("取消",), self.ROI_QUXIAO_FUZHU, wait=1.0):
                continue
            if self._handle_buzu5(agent):
                continue
            # 领取后任务栏出现捉鬼任务 -> 点它开始本轮
            pos = self._find_zhuogui_task(agent)
            if pos:
                logger.info("窗口=%s 领取成功，点击任务栏捉鬼任务 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(1.0)
                self._ocr_cache = None
                return
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.info("窗口=%s 领取后未在任务栏看到捉鬼任务，直接进入监控循环", agent.hwnd)

    def _click_taskbar_zhuogui_with_retries(self, agent) -> None:
        """Maa 已领取分支的 next: 展开任务栏/切任务页/点击任务栏-捉鬼任务/下滑任务栏。"""
        for swipe in range(self.taskbar_swipe_max + 1):
            self._check_stop(agent)
            pos = self._find_zhuogui_task(agent)
            if pos:
                agent.click(pos[0], pos[1])
                time.sleep(1.0)
                self._ocr_cache = None
                return
            self._node_switch_task_tab(agent)
            if swipe < self.taskbar_swipe_max:
                self._swipe_vertical(agent, self.SWIPE_TASKBAR_X,
                                     self.SWIPE_TASKBAR_FROM, self.SWIPE_TASKBAR_TO)
                self._ocr_cache = None
                time.sleep(1.0)

    # ==================================================================
    # 节点3: 抓鬼监控循环（点击任务栏-捉鬼任务 的 next 列表）
    # ==================================================================
    def _hunt_loop(self, agent) -> str:
        """返回 "rounds"(轮次达标) / "tayin" / "timeout"。"""
        while True:
            self._check_stop(agent)

            # Maa「识别拓印_停止」
            if self._check_tayin(agent):
                logger.info("窗口=%s 遇见拓印，停止所有任务", agent.hwnd)
                self._close_tayin(agent)
                return "tayin"

            # [JumpBack]捉鬼-领取双倍点数弹窗：OCR -> 点确定固定位
            if self._handle_lingqu_double(agent):
                continue
            # [JumpBack]抓鬼领取双倍弹窗：模板 -> 确定
            if self._handle_shuangbei(agent):
                continue

            # 抓鬼一轮完成：OCR -> 点确定 -> 再次点击确定 -> 人员检测/轮次计算
            try:
                if self._check_round_done(agent):
                    continue
            except _RoundsDone:
                return "rounds"

            # [JumpBack]战斗平衡弹窗
            if self._dismiss_popups(agent):
                continue
            # [JumpBack]捉鬼-没有辅助提示-点击取消
            if self._click_text_once(agent, ("取消",), self.ROI_QUXIAO_FUZHU, wait=1.0):
                continue
            # [JumpBack]抓鬼不足五人
            if self._handle_buzu5(agent):
                continue
            # [JumpBack]关闭福利弹窗
            if self._close_fuli(agent):
                continue

            img = self._image(agent)
            # [JumpBack]自动寻路中-图片识别（等3秒）
            if img is not None:
                h, w = img.shape[:2]
                if self._match_any(agent, self.T_AUTOPATH,
                                   self._fraction_region(w, h, self.ROI_AUTOPATH),
                                   self.TH_AUTOPATH):
                    if self._sleep(self.autopath_wait):
                        raise _Aborted()
                    continue
            # [JumpBack]战斗中-等待100秒
            if self._in_battle(agent, img):
                logger.info("窗口=%s 战斗中，等待 %.0f 秒", agent.hwnd, self.battle_wait)
                if self._sleep(self.battle_wait):
                    raise _Aborted()
                continue

            # [JumpBack]抓鬼-点击任务栏-通用：再点任务栏捉鬼条目保持推进
            pos = self._find_zhuogui_task(agent)
            if pos:
                logger.info("窗口=%s 点击任务栏捉鬼任务 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(1.0)
                self._ocr_cache = None
                continue
            # [JumpBack]任务栏切换为任务
            if self._node_switch_task_tab(agent):
                continue

            if self._sleep(self.poll_interval):
                raise _Aborted()

    # ------------------------------------------------------------------
    # 抓鬼循环内的弹窗/事件
    # ------------------------------------------------------------------
    def _handle_lingqu_double(self, agent) -> bool:
        """Maa「捉鬼-领取双倍点数弹窗」：OCR 双倍点数不足 -> 点确定固定位。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if not self._find_text_in(self._ocr_lines(agent), ("双倍点数不足",),
                                  self._fraction_region(w, h, self.ROI_SHUANGBEI_OCR)):
            return False
        fx, fy = int(w * self.POS_CONFIRM[0]), int(h * self.POS_CONFIRM[1])
        logger.info("窗口=%s 领取双倍点数，点击 (%d,%d)", agent.hwnd, fx, fy)
        agent.click(fx, fy)
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    def _handle_shuangbei(self, agent) -> bool:
        """Maa「抓鬼领取双倍弹窗」->「抓鬼关闭领取双倍弹窗-点击确定」。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        tpl_roi = self._fraction_region(w, h, self.ROI_SHUANGBEI_TPL)
        if not self._match_any(agent, self.T_SHUANGBEI, tpl_roi, self.TH_SHUANGBEI_TPL):
            return False
        pos = self._find_text_in(self._ocr_lines(agent), ("确定",), tpl_roi)
        if pos:
            logger.info("窗口=%s 关闭双倍弹窗，点击确定 %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
            time.sleep(1.5)
            self._ocr_cache = None
        return True

    def _handle_buzu5(self, agent) -> bool:
        """Maa「抓鬼不足五人-图片识别」-> 点击取消 -> 点击钟馗 -> 捉鬼任务。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        tpl_roi = self._fraction_region(w, h, self.ROI_BUZU5)
        if not self._match_any(agent, self.T_BUZU5, tpl_roi, self.TH_BUZU5):
            return False
        logger.info("窗口=%s 抓鬼不足五人，点击取消", agent.hwnd)
        pos = self._find_text_in(self._ocr_lines(agent), ("取消",), tpl_roi)
        if pos:
            agent.click(pos[0], pos[1])
            time.sleep(1.5)
            self._ocr_cache = None
        # 抓鬼不足五人-点击钟馗：zhongkui 模板 / OCR 钟馗
        img = self._image(agent)
        if img is not None:
            h, w = img.shape[:2]
            hit = self._match_any(agent, self.T_ZHONGKUI,
                                  self._fraction_region(w, h, self.ROI_ZHONGKUI_NPC_TPL),
                                  self.TH_ZHONGKUI)
            if not hit:
                hit = self._find_text_in(self._ocr_lines(agent), ("钟馗", "钟道", "钟", "道"),
                                         self._fraction_region(w, h, self.ROI_ZHONGKUI_NPC_OCR))
            if hit:
                logger.info("窗口=%s 点击钟馗 %s", agent.hwnd, hit[:2])
                agent.click(hit[0], hit[1])
                time.sleep(1.5)
                self._ocr_cache = None
        # 抓鬼不足五人-捉鬼任务
        self._click_text_once(agent, ("捉鬼任务",), self.ROI_ZHONGKUI_DIALOG, wait=2.0)
        return True

    def _close_fuli(self, agent) -> bool:
        """Maa「关闭福利弹窗」：fuli 模板 -> 点固定位 X。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if not self._match_any(agent, self.T_FULI,
                               self._fraction_region(w, h, self.ROI_FULI), self.TH_FULI):
            return False
        fx, fy = int(w * self.POS_FULI_CLOSE[0]), int(h * self.POS_FULI_CLOSE[1])
        logger.info("窗口=%s 关闭福利弹窗 (%d,%d)", agent.hwnd, fx, fy)
        agent.click(fx, fy)
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    # ------------------------------------------------------------------
    # 抓鬼一轮完成 -> 人员检测 / 轮次计算 / 结束
    # ------------------------------------------------------------------
    def _check_round_done(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if not self._find_text_in(self._ocr_lines(agent), ("已经捉完1轮鬼", "已经捉完"),
                                  self._fraction_region(w, h, self.ROI_YILUN_OCR)):
            return False
        logger.info("窗口=%s 抓鬼一轮完成，点击确定", agent.hwnd)
        fx, fy = int(w * self.POS_CONFIRM[0]), int(h * self.POS_CONFIRM[1])
        agent.click(fx, fy)
        time.sleep(5.0)  # Maa post_delay 5000
        self._ocr_cache = None
        # [JumpBack]抓鬼一轮完成-再次点击确定：zhuaguijiesu3 模板 / OCR 确定
        self._confirm_again(agent)
        self._rounds_done += 1
        self._report(f"已完成第 {self._rounds_done} 轮捉鬼")
        logger.info("窗口=%s 完成第 %d 轮捉鬼", agent.hwnd, self._rounds_done)

        # 选项：人员检测
        if self.TEAM_CHECK:
            self._team_check(agent)
        # 选项：轮次选择（抓鬼轮次计算-max）
        if self.ROUNDS > 0 and self._rounds_done >= self.ROUNDS:
            logger.info("窗口=%s 轮次达标(%d/%d)，捉鬼-结束", agent.hwnd,
                        self._rounds_done, self.ROUNDS)
            self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "收尾回主界面")
            raise _RoundsDone()
        # 钟馗-捉鬼任务-循环：回钟馗处领取下一轮
        self._return_to_zhongkui(agent)
        return True

    def _confirm_again(self, agent) -> None:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return
            h, w = img.shape[:2]
            hit = self._match_any(agent, self.T_ZAIQUE,
                                  self._fraction_region(w, h, self.ROI_ZAIQUE_TPL),
                                  self.TH_ZAIQUE)
            if not hit:
                hit = self._find_text_in(self._ocr_lines(agent), ("确定",),
                                         self._fraction_region(w, h, self.ROI_ZAIQUE_OCR),
                                         exact=True)
            if hit:
                fx, fy = int(w * self.POS_CONFIRM[0]), int(h * self.POS_CONFIRM[1])
                logger.info("窗口=%s 再次点击确定 (%d,%d)", agent.hwnd, fx, fy)
                agent.click(fx, fy)
                time.sleep(1.0)
                self._ocr_cache = None
                return
            if self._sleep(self.poll_interval):
                raise _Aborted()

    def _return_to_zhongkui(self, agent) -> None:
        """Maa「抓鬼-关闭组队后打开小地图」链路：Tab -> 点击钟馗 -> 领取下一轮。"""
        agent.press_key("tab")
        time.sleep(1.0)
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            if self._click_zhongkui_on_map(agent):
                break
            if self._sleep(self.poll_interval):
                raise _Aborted()
        # 领取下一轮（钟馗-捉鬼任务-循环）
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            if self._click_text_once(agent, ("捉鬼任务",), self.ROI_ZHONGKUI_DIALOG, wait=2.0):
                self._post_accept_popups(agent)
                return
            # 已领取状态（模板） -> ESC，直接回监控循环
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                if self._match_any(agent, self.T_YILINGQU,
                                   self._fraction_region(w, h, self.ROI_YILINGQU),
                                   self.TH_YILINGQU):
                    agent.press_key("esc")
                    time.sleep(1.0)
                    return
            if self._sleep(self.poll_interval):
                raise _Aborted()

    # ------------------------------------------------------------------
    # 捉鬼-队伍人员满员判断（选项：人员检测）
    # ------------------------------------------------------------------
    def _team_check(self, agent) -> None:
        logger.info("窗口=%s 一轮完成，检查队伍人员", agent.hwnd)
        self._report("检查队伍人员")
        self._press_hotkey(agent, "T")  # Maa ClickKey[57,48] = Alt+T 队伍界面
        time.sleep(2.0)
        # 等待组队界面：duiwu-duiwu 模板
        deadline = time.monotonic() + 30.0
        opened = False
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return
            h, w = img.shape[:2]
            if self._match_any(agent, self.T_DUIWU_PANEL,
                               self._fraction_region(w, h, self.ROI_DUIWU_PANEL),
                               self.TH_DUIWU_PANEL):
                opened = True
                break
            # [JumpBack]捉鬼-取消钟馗接取任务列表
            pos = self._find_text_in(self._ocr_lines(agent), ("钟馗", "钟道", "钟", "道", "馗"),
                                     self._fraction_region(w, h, self.ROI_ZHONGKUI_BOTTOMLEFT))
            if pos:
                logger.info("窗口=%s 取消钟馗接取任务列表 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(1.0)
                self._ocr_cache = None
                continue
            # [JumpBack]队伍界面-按键打开失败-点击队伍图标
            m = self._match_any(agent, self.T_DUIWU_ICON,
                                self._fraction_region(w, h, self.ROI_DUIWU_ICON),
                                self.TH_DUIWU_ICON)
            if not m:
                pos = self._find_text_in(self._ocr_lines(agent), ("队伍",),
                                         self._fraction_region(w, h, self.ROI_DUIWU_ICON))
                if pos:
                    m = (pos[0], pos[1], 0.0)
            if m:
                logger.info("窗口=%s 点击队伍图标 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(1.0)
                continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        if not opened:
            logger.warning("窗口=%s 未能打开组队界面，跳过人员检测", agent.hwnd)
            return

        # 识别离线/暂离 -> 请离 -> 自动匹配；都没有 -> 自动匹配2 -> 关闭组队界面
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return
            h, w = img.shape[:2]
            # 抓鬼-识别队伍离线/暂离
            pos = self._find_text_in(self._ocr_lines(agent), ("离线", "暂离"),
                                     self._fraction_region(w, h, self.ROI_OFFLINE))
            if pos:
                logger.info("窗口=%s 发现离线/暂离队员，点击 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(1.0)
                self._ocr_cache = None
                # 抓鬼-踢出离线（暂离）人员：OCR 请离队伍
                if self._click_text_once(agent, ("请离队伍",), self.ROI_QINGLI, wait=1.0):
                    # 捉鬼-点击自动匹配
                    self._click_text_once(agent, ("自动匹配",), self.ROI_ZIDONG_PIPEI, wait=2.0)
                continue
            # 抓鬼-未识别队伍离线/暂离 -> 捉鬼-点击自动匹配2 / 未识别到自动匹配2 -> 关闭
            pos = self._find_text_in(self._ocr_lines(agent), ("自动匹配",),
                                     self._fraction_region(w, h, self.ROI_ZIDONG_PIPEI),
                                     exact=True)
            if pos:
                logger.info("窗口=%s 点击自动匹配 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(2.0)
                self._ocr_cache = None
            break

        # 抓鬼-关闭组队界面
        img = self._image(agent)
        if img is not None:
            h, w = img.shape[:2]
            m = self._match_any(agent, self.T_DUIWU_GUANBI,
                                self._fraction_region(w, h, self.ROI_DUIWU_GUANBI),
                                self.TH_DUIWU_GUANBI)
            if m:
                logger.info("窗口=%s 关闭组队界面 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(1.5)
        self._ocr_cache = None

    # ------------------------------------------------------------------
    # 大地图传送（打开大地图_捉鬼 -> 传送长安城_捉鬼）
    # ------------------------------------------------------------------
    def _open_map_and_teleport(self, agent) -> bool:
        self._press_hotkey(agent, "M")  # Maa ClickKey[57,41] = Alt+M
        time.sleep(1.0)
        deadline = time.monotonic() + 30.0
        clicked_icon = False
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            if self._match_any(agent, self.T_MAP_PANEL,
                               self._fraction_region(w, h, self.ROI_MAP_PANEL),
                               self.TH_MAP_PANEL):
                m = self._match_any(agent, self.T_CHANGAN_TAB, None, self.TH_CHANGAN_TAB)
                if m:
                    logger.info("窗口=%s 大地图点击长安城 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    time.sleep(1.0)
                    self._ocr_cache = None
                    return True
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
        logger.warning("窗口=%s 打开大地图/传送长安城超时", agent.hwnd)
        return False

    # ------------------------------------------------------------------
    # 拓印 / 弹窗
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


class _RoundsDone(Exception):
    """轮次达标信号（内部用于跳出监控循环）。"""


class _TayinAbort(Exception):
    """领取后弹窗处理时遇到拓印（内部用于中断）。"""

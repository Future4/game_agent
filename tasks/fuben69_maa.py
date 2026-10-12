# -*- coding: utf-8 -*-
"""副本320(69) —— 按 Maa_MHXY 的 fuben69.json 流水线原样移植到 game_agent。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/fuben69.json
    (+ 共享节点: my_task.json「panduan_zhujiemian / panduan_zhujiemian_ks / 识别拓印_停止 /
       战斗中-等待10秒 / 关闭整点活动弹窗 / 关闭任务界面」
       chongwuqifu.json「小地图-按键打开失败-点击小地图图标」
       chuangjianduiwu.json「队伍界面-按键打开失败-点击队伍图标」
       fuben115.json「再次点击地图百晓仙子 / 115进入侠士副本-等待队员同意」
       zhuoguirenwu.json「捉鬼-fuben桥接」-> 捉鬼流程)

======================= Maa 原始流程(节点图) =======================
fuben69 -> 识别位置-长安城-副本-过渡(主界面 +/称号)
  next: 已在50级侠士副本-过渡(And OCR 因缘绘 + .*侠士) -> 进入50级侠士副本-成功
        识别位置-长安城-副本(OCR 长安城) -> 打开小地图_百晓仙子
        [JumpBack]panduan_zhujiemian_ks / 打开大地图_69副本(Alt+M -> 传送长安城)

打开小地图_百晓仙子: ClickKey[61](Tab)
  -> 点击地图-百晓仙子(Or OCR 百晓仙子 / baixiao模板)
     [JumpBack]再次点击地图百晓仙子(xiaoditu_CA -> 点固定位)
  -> 百晓仙子-选择副本(OCR) -> 选择侠士副本(OCR) -> 进入50级侠士副本(OCR 进入)
     next: 识别拓印_停止 / 成功(OCR 因缘绘)
           [JumpBack]115进入侠士副本-等待队员同意(等4秒) / [JumpBack]失败-再次进入(max 2)

进入50级侠士副本-成功 -> 副本监控循环:
    50侠士-副本完成-退出(OCR 副本已完成 -> 点击 -> 打开小地图_百晓仙子-50普通-1)
    [JumpBack]点击副本-跳过剧情动画 / 战斗中-等待10秒 /
    点击副本-开始战斗(fubenzhandou 0.9 -> 副本-战斗-对话点固定位) /
    跳过剧情动画-快进键 / 推荐好友信息(ESC) / 关闭福利弹窗 / 关闭师门弹窗 /
    任务栏切换为任务 / 关闭任务界面

50普通-1(同链路) -> 50普通-1-副本完成-退出 -> 50普通-2(同链路)
  -> 50普通-2-副本完成-退出 -> [JumpBack]捉鬼-fuben桥接 -> 捉鬼流程 | panduan

======================= Maa 任务选项映射（「320或3本」）=======================
  - 3副本加两轮鬼(默认): MODE="3+2gui" 侠士+普通1+普通2, 再桥接捉鬼(无人员检测, 2轮)
  - 3副本:              MODE="3"     三本后走「退出队伍」链路结束
  - 2副本加两轮鬼:       MODE="2+2gui" 跳过侠士, 普通1+普通2 + 捉鬼2轮
  捉鬼轮数对应 GUI_ROUNDS(默认 2, 即 Maa「抓鬼轮次输入2」默认值)

======================= 移植适配说明 =======================
官网 PC 客户端(Unity) 与 Maa 的模拟器(1280x720) 不同:
  1. 布局非等比, roi 由 Maa 像素坐标换算为窗口比例并适当放大, 模板匹配用多尺度。
  2. ClickKey[57,41]=Alt+M(大地图), ClickKey[61]=Tab(小地图), ClickKey[57,48]=Alt+T(队伍)。
  3. OCR 走整图识别+ROI 中心过滤(带缓存); regex(.*侠士)按包含"侠士"近似。
  4. 战斗判断: Maa 模板(zhandou/zidong|quxiao 0.9)优先, HoughCircles 兜底; 等 10 秒。
  5. 捉鬼桥段复用 tasks/zhuogui_maa.py 的 ZhuoguiMaaTask(选项 override 为
     关闭人员检测 + 2 轮), 与 Maa 的 pipeline_override 语义一致。
"""

import logging
import time
from typing import Callable, Optional, Sequence, Tuple

from domain.tasks import TaskContext, TaskDefinition, TaskSnapshot, TaskStatus
from tasks.base import AutomationTask
from tasks.zhuogui_maa import ZhuoguiMaaTask

logger = logging.getLogger(__name__)

Region = Tuple[int, int, int, int]  # x, y, w, h（截图坐标）


class _Aborted(Exception):
    """停止/超时信号。"""


class _Fuben69Zhuogui(ZhuoguiMaaTask):
    """Maa 选项「3副本加两轮鬼」的 pipeline_override：关闭人员检测 + 2 轮。"""
    TEAM_CHECK = False
    ROUNDS = 2


class Fuben69MaaTask(AutomationTask):
    definition = TaskDefinition(
        "fuben69_maa", "副本320(69)", "移植自 Maa_MHXY 的 fuben69 流水线"
    )

    # ---------------- 任务选项（对应 Maa 选项「320或3本」）----------------
    MODE = "3+2gui"              # "3+2gui"(默认) / "3" / "2+2gui"
    GUI_ROUNDS = 2               # 捉鬼轮数（Maa「抓鬼轮次输入2」默认 2）

    # ---------------- 时序参数（对应 Maa 流水线字段）----------------
    poll_interval = 0.5
    node_timeout = 90.0
    battle_wait = 10.0           # Maa: 战斗中-等待10秒
    enter_retry_max = 2          # Maa: 进入50级侠士副本-失败-再次进入 (max_hit 2)
    total_timeout = 7200.0       # 3 副本 + 2 轮鬼，整个任务上限 2 小时

    # ---------------- 可调开关 ----------------
    ocr_cache_seconds = 2.0

    # ---------------- 阈值 ----------------
    TH_MAIN_INDICATOR = 0.75
    TH_BAIXIAO = 0.75
    TH_XIAODITU_CA = 0.75
    TH_FUBEN_ZHANDOU = 0.90      # Maa: 点击副本-开始战斗 threshold 0.9
    TH_KUAIJIN = 0.80
    TH_FULI = 0.80
    TH_SHIMEN_GB = 0.80
    TH_RENWU_LOGO = 0.80
    TH_MAP_PANEL = 0.75
    TH_CHANGAN_TAB = 0.75
    TH_MINIMAP = 0.85
    TH_DUIWU_PANEL = 0.90        # Maa: 打开队伍界面成功_退出队伍
    TH_DUIWU_ICON = 0.80
    TH_BATTLE = 0.90
    TH_TAYIN = 0.90
    TH_TAYIN_CLOSE = 0.80
    TH_POPUP_CLOSE = 0.88

    # ---------------- 模板名（templates/ 目录，不带 .png）----------------
    T_MAIN_INDICATORS = ("zonghe/jiahao", "zonghe/baoguo", "zonghe/baoguo_man", "zonghe/chenghao")
    T_JIAHAO_CHENGHAO = ("zonghe/chenghao", "zonghe/jiahao")  # Maa 识别位置-长安城-副本-过渡
    # Maa「点击地图-百晓仙子」/「再次点击地图百晓仙子」
    T_BAIXIAO = ("fuben/baixiao", "fuben/baixiao2", "fuben/baixiao3")
    T_XIAODITU_CA = ("zonghe/xiaoditu_CA",)
    # Maa「点击副本-开始战斗」
    T_FUBEN_ZHANDOU = ("fuben/fubenzhandou", "fuben/fubenzhandou2")
    # Maa「跳过剧情动画-快进键」
    T_KUAIJIN = ("fuben/fubentiaoguo1", "fuben/fubentiaoguo2", "fuben/fubentiaoguo3",
                 "fuben/fubentiaoguo4", "fuben/shimen_kuaijin")
    # Maa「关闭福利弹窗」/「关闭师门弹窗」/「关闭任务界面」
    T_FULI = ("qiandao/fuli",)
    T_SHIMEN_GB = ("zonghe/shimen_GB",)
    T_RENWU_LOGO = ("bangpairenwu/renwu_jiemian_logo",)
    # Maa 大地图/小地图/队伍
    T_MAP_PANEL = ("zonghe/ditu_jiemian_panduan", "zonghe/ditu_jiemian_panduan2")
    T_CHANGAN_TAB = ("zonghe/tab_changancheng", "zonghe/tab_changancheng2", "zonghe/tab_changancheng3")
    T_MINIMAP = ("zonghe/xiaoditu_taiyang", "zonghe/xiaoditu_yueliang")
    T_DUIWU_PANEL = ("duiwu/duiwu-zudui", "duiwu/duiwu-duiwu")
    T_DUIWU_ICON = ("duiwu/duiwu",)
    # Maa「识别拓印_停止」/「关闭拓印界面」/「战斗平衡弹窗」
    T_TAYIN = ("tayin/tayin", "tayin/tayin2")
    T_TAYIN_CLOSE = ("zonghe/guanbi6", "zonghe/guanbi7")
    T_POPUP_CLOSE = ("zonghe/zhandoupingheng_guanbi1",)
    # Maa 战斗判定模板
    T_BATTLE_BTN = ("zhandou/zidong", "zhandou/quxiao")
    T_BATTLE_ICON = ("zhandou/zhandou1", "zhandou/zhandou2", "zhandou/zhandou3")

    # ---------------- 区域比例（由 Maa 1280x720 像素 roi 换算并适当放大）----------------
    ROI_MAIN_INDICATOR = (0.86, 0.72, 0.14, 0.28)
    ROI_JIAHAO_BR = (0.86, 0.80, 0.14, 0.20)       # Maa [1206,637,66,57] 放大
    ROI_CHANGAN_OCR = (0.02, 0.00, 0.25, 0.12)     # Maa [108,22,117,31] 放大
    ROI_MAP_PANEL = (0.00, 0.00, 0.28, 0.24)
    ROI_MINIMAP = (0.00, 0.00, 0.18, 0.20)
    ROI_YINYUANHUI = (0.32, 0.03, 0.20, 0.14)      # Maa 因缘绘 [502,53,94,42] 放大
    ROI_XIASHI_OCR = (0.72, 0.18, 0.28, 0.14)      # Maa .*侠士 [1037,174,210,41] 放大
    ROI_BAIXIAO_OCR = (0.22, 0.42, 0.28, 0.16)     # Maa [396,354,153,46] 放大
    ROI_BAIXIAO_TPL = (0.24, 0.42, 0.26, 0.16)     # Maa [421,357,106,38] 放大
    ROI_XUANZE_FUBEN = (0.62, 0.15, 0.36, 0.60)    # Maa 选择副本 [923,156,324,356] 放大
    ROI_XIASHI_FUBEN = (0.24, 0.08, 0.28, 0.16)    # Maa 侠士副本 [399,104,158,42] 放大
    ROI_ENTER_XIASHI = (0.16, 0.72, 0.28, 0.18)    # Maa 进入(侠士) [316,570,150,52] 放大
    ROI_ENTER_PUTONG1 = (0.16, 0.72, 0.28, 0.18)   # Maa 进入(普通1) [319,571,145,49] 放大
    ROI_ENTER_PUTONG2 = (0.38, 0.72, 0.28, 0.18)   # Maa 进入(普通2) [603,570,147,51] 放大
    ROI_WAIT_TEAM = (0.28, 0.78, 0.42, 0.18)       # Maa 等待队员同意 [462,606,333,65] 放大
    ROI_FUBEN_DONE = (0.72, 0.22, 0.26, 0.16)      # Maa 副本已完成 [1032,208,149,56] 放大
    ROI_SKIP_STORY = (0.72, 0.26, 0.28, 0.26)      # Maa 跳过剧情动画 [1029,240,251,110] 放大
    ROI_FUBEN_ZHANDOU = (0.88, 0.24, 0.12, 0.18)   # Maa [1240,225,39,48] 放大
    ROI_ZHANDOU_DUIHUA = (0.48, 0.42, 0.52, 0.20)  # Maa [730,351,522,66] 放大
    ROI_TUIJIAN = (0.28, 0.08, 0.42, 0.20)         # Maa 推荐好友信息 [477,108,318,64] 放大
    ROI_FULI = (0.28, 0.00, 0.46, 0.22)
    ROI_SHIMEN_GB = (0.76, 0.10, 0.22, 0.20)       # Maa [1097,121,30,53] 放大
    ROI_RENWU_LOGO = (0.00, 0.00, 0.32, 0.36)      # Maa [61,0,249,208] 放大
    ROI_DUIWU_PANEL = (0.00, 0.00, 0.30, 0.25)
    ROI_DUIWU_ICON = (0.80, 0.08, 0.20, 0.20)
    ROI_TUICHU_DUIWU = (0.02, 0.80, 0.28, 0.18)    # Maa [85,632,188,60] 放大
    ROI_BATTLE_BTN = (0.88, 0.70, 0.12, 0.28)
    ROI_BATTLE_ICON = (0.38, 0.00, 0.24, 0.20)
    ROI_TAYIN_OCR = (0.15, 0.18, 0.20, 0.25)
    ROI_TAYIN_TPL1 = (0.14, 0.16, 0.22, 0.36)
    ROI_TAYIN_TPL2 = (0.10, 0.45, 0.32, 0.48)
    ROI_TAYIN_CLOSE = (0.62, 0.00, 0.36, 0.26)

    # 固定点击位（比例坐标）
    POS_BAIXIAO_AGAIN = (0.371, 0.524)    # Maa 再次点击地图百晓仙子 target [437,367,77,20] 中心
    POS_ZHANDOU_DUIHUA = (0.848, 0.646)   # Maa 副本-战斗-对话 target [951,442,268,46] 中心
    POS_FULI_CLOSE = (0.891, 0.079)       # Maa 关闭福利弹窗 target [1140,57,32,35] 中心
    POS_RENWU_CLOSE = (0.872, 0.053)      # Maa 关闭任务界面 target [1117,38,38,40] 中心

    # ==================================================================
    # 主流程
    # ==================================================================
    def __init__(self) -> None:
        super().__init__()
        self._on_update = None
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._ocr_cache = None

    def run(self, context: TaskContext,
            on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._ocr_cache = None

        logger.info("副本320(69)启动 hwnd=%s (模式=%s, 捉鬼轮数=%d)",
                    getattr(agent, "hwnd", None), self.MODE, self.GUI_ROUNDS)
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 5
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            # 步骤2: Maa「识别位置-长安城-副本-过渡」—— 回长安(必要时大地图传送)
            self._stage(agent, 2, "回到长安城", self._node_back_to_changan)

            fubens = ["putong1", "putong2"] if self.MODE == "2+2gui" else ["xiashi", "putong1", "putong2"]
            step = 3
            for fb in fubens:
                # 步骤3/4/5: 百晓仙子 -> 选择副本 -> 进入 -> 副本监控
                if not self._stage(agent, step, f"进入副本({self._fb_label(fb)})",
                                   lambda a, f=fb: self._node_enter_fuben(a, f)):
                    self.snapshot.status = TaskStatus.FAILED
                    self._report(f"未能进入副本({self._fb_label(fb)})，请检查窗口状态与模板")
                    logger.error("窗口=%s 未能进入副本 %s", agent.hwnd, fb)
                    return
                self._report(f"副本({self._fb_label(fb)})进行中")
                result = self._fuben_monitor(agent)
                if result == "tayin":
                    self.snapshot.completed_steps = self.snapshot.total_steps
                    self.snapshot.status = TaskStatus.COMPLETED
                    self._report("遇见拓印，按 Maa 语义停止任务")
                    return
                step += 1

            # 三本打完后的分支（Maa 选项）
            if self.MODE == "3":
                # 「3副本」: 50普通-2-副本完成-退出 -> 退出队伍
                self._quit_team(agent)
                self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "收尾回主界面")
            else:
                # 「3副本加两轮鬼」/「2副本加两轮鬼」: [JumpBack]捉鬼-fuben桥接 -> 捉鬼流程
                self._report("开始捉鬼(桥接)")
                self._run_zhuogui_bridge(agent)

            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            self._report("副本320(69)完成")
            logger.info("副本320(69)完成 hwnd=%s", agent.hwnd)
        except _Aborted:
            logger.info("副本320(69)停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("副本320(69)执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("副本320(69)执行异常，详见日志")

    @staticmethod
    def _fb_label(fb: str) -> str:
        return {"xiashi": "50级侠士", "putong1": "50普通-1", "putong2": "50普通-2"}[fb]

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
    # 节点2: 识别位置-长安城-副本-过渡（回长安）
    # ==================================================================
    def _node_back_to_changan(self, agent) -> bool:
        # 已在50级侠士副本-过渡：And(OCR 因缘绘, OCR .*侠士) —— 在副本里就先 ESC 出去
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if (self._find_text_in(self._ocr_lines(agent), ("因缘绘",),
                               self._fraction_region(w, h, self.ROI_YINYUANHUI))
                and self._find_text_in(self._ocr_lines(agent), ("侠士",),
                                       self._fraction_region(w, h, self.ROI_XIASHI_OCR))):
            logger.info("窗口=%s 检测到已在侠士副本中，按 ESC 先退出", agent.hwnd)
            agent.press_key("esc")
            time.sleep(1.0)
            self._ocr_cache = None
            return False
        # 识别位置-长安城-副本：OCR 长安城
        if self._find_text_in(self._ocr_lines(agent), ("长安城",),
                              self._fraction_region(w, h, self.ROI_CHANGAN_OCR)):
            logger.info("窗口=%s 已在长安城", agent.hwnd)
            return True
        # [JumpBack]panduan_zhujiemian_ks：不在主界面先 ESC
        if not self._on_main_interface(agent):
            agent.press_key("esc")
            time.sleep(0.8)
            return False
        # [JumpBack]打开大地图_69副本 -> 传送长安城
        logger.info("窗口=%s 不在长安城，打开大地图传送", agent.hwnd)
        self._open_map_and_teleport(agent)
        return False

    def _open_map_and_teleport(self, agent) -> bool:
        """Maa「打开大地图_69副本」+「传送长安城_69副本」：Alt+M -> 点长安城。"""
        self._press_hotkey(agent, "M")
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
        logger.warning("窗口=%s 打开大地图/传送长安城超时", agent.hwnd)
        return False

    # ==================================================================
    # 节点3: 百晓仙子 -> 选择副本 -> 进入
    # ==================================================================
    def _node_enter_fuben(self, agent, fb: str) -> bool:
        """对应 打开小地图_百晓仙子(-50普通-1/2) -> ... -> 进入50级侠士/普通副本(-1/2)。"""
        if self._check_tayin(agent):
            self._close_tayin(agent)
        agent.press_key("tab")  # Maa ClickKey[61] = Tab 打开小地图
        time.sleep(1.0)

        # ---- 点击地图-百晓仙子（含 再次点击/小地图图标 两个 JumpBack）----
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            if self._click_baixiao(agent):
                break
            # [JumpBack]再次点击地图百晓仙子：小地图 CA 标记 -> 点固定位
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                if self._match_any(agent, self.T_XIAODITU_CA, None, self.TH_XIAODITU_CA):
                    fx = int(w * self.POS_BAIXIAO_AGAIN[0])
                    fy = int(h * self.POS_BAIXIAO_AGAIN[1])
                    logger.info("窗口=%s 再次点击地图百晓仙子 (%d,%d)", agent.hwnd, fx, fy)
                    agent.click(fx, fy)
                    time.sleep(1.0)
                    continue
                # [JumpBack]小地图-按键打开失败-点击小地图图标
                m = self._match_any(agent, self.T_MINIMAP,
                                    self._fraction_region(w, h, self.ROI_MINIMAP),
                                    self.TH_MINIMAP)
                if m:
                    logger.info("窗口=%s 点击小地图图标 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    time.sleep(1.0)
                    continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        else:
            logger.warning("窗口=%s 点击百晓仙子超时", agent.hwnd)
            return False

        # ---- 百晓仙子-选择副本 -> (选择侠士副本) -> 进入 ----
        enter_roi = {"xiashi": self.ROI_ENTER_XIASHI,
                     "putong1": self.ROI_ENTER_PUTONG1,
                     "putong2": self.ROI_ENTER_PUTONG2}[fb]
        deadline = time.monotonic() + 60.0
        stage = "xuanze"   # xuanze -> (xiashi) -> enter
        enter_retries = 0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            if self._check_tayin(agent):
                self._close_tayin(agent)
                raise _Aborted()
            if stage == "xuanze":
                if self._click_text_once(agent, ("选择副本",), self.ROI_XUANZE_FUBEN, wait=0.5):
                    stage = "xiashi" if fb == "xiashi" else "enter"
                    continue
            elif stage == "xiashi":
                if self._click_text_once(agent, ("侠士副本",), self.ROI_XIASHI_FUBEN, wait=0.5):
                    stage = "enter"
                    continue
            else:
                # [JumpBack]115进入侠士副本-等待队员同意：OCR 等待 -> 等4秒
                img = self._image(agent)
                if img is not None:
                    h, w = img.shape[:2]
                    if self._find_text_in(self._ocr_lines(agent), ("正在等待其他玩家准备",),
                                          self._fraction_region(w, h, self.ROI_WAIT_TEAM)):
                        logger.info("窗口=%s 等待队员同意中", agent.hwnd)
                        if self._sleep(4.0):
                            raise _Aborted()
                        continue
                # 已进入副本：侠士以 OCR 因缘绘 判定成功；普通副本以"选择副本"消失+等待
                if fb == "xiashi" and self._find_text_in(
                        self._ocr_lines(agent), ("因缘绘",),
                        self._fraction_region(w, h, self.ROI_YINYUANHUI)):
                    logger.info("窗口=%s 进入50级侠士副本成功", agent.hwnd)
                    return True
                if fb != "xiashi" and not self._find_text_in(
                        self._ocr_lines(agent), ("选择副本",),
                        self._fraction_region(w, h, self.ROI_XUANZE_FUBEN)):
                    # 普通副本没有明显的副本标题判定：进入按钮消失即视为已进入
                    if not self._find_text_in(self._ocr_lines(agent), ("进入",),
                                              self._fraction_region(w, h, enter_roi),
                                              exact=True):
                        logger.info("窗口=%s 进入%s成功", agent.hwnd, self._fb_label(fb))
                        return True
                # 进入50级侠士/普通副本：OCR 进入（失败-再次进入 max_hit 2）
                if enter_retries <= self.enter_retry_max:
                    if self._click_text_once(agent, ("进入",), enter_roi, wait=1.0, exact=True):
                        enter_retries += 1
                        continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 进入副本(%s)超时", agent.hwnd, self._fb_label(fb))
        return False

    def _click_baixiao(self, agent) -> bool:
        """Maa「点击地图-百晓仙子(-50普通-1/2)」= Or(OCR 百晓仙子, baixiao 模板)。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        pos = self._find_text_in(self._ocr_lines(agent),
                                 ("百晓仙子", "百晓", "仙子", "晓仙", "晓"),
                                 self._fraction_region(w, h, self.ROI_BAIXIAO_OCR))
        if pos:
            logger.info("窗口=%s 点击百晓仙子(OCR) %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
            time.sleep(1.0)
            self._ocr_cache = None
            return True
        m = self._match_any(agent, self.T_BAIXIAO,
                            self._fraction_region(w, h, self.ROI_BAIXIAO_TPL), self.TH_BAIXIAO)
        if m:
            logger.info("窗口=%s 点击百晓仙子(模板) %s", agent.hwnd, m[:2])
            agent.click(m[0], m[1])
            time.sleep(1.0)
            self._ocr_cache = None
            return True
        return False

    # ==================================================================
    # 节点4: 副本监控循环（进入50级侠士/普通副本-成功 的 next 列表）
    # ==================================================================
    def _fuben_monitor(self, agent) -> str:
        """返回 "done"(副本已完成) / "tayin"。"""
        while True:
            self._check_stop(agent)

            # Maa「识别拓印_停止」
            if self._check_tayin(agent):
                logger.info("窗口=%s 遇见拓印，停止所有任务", agent.hwnd)
                self._close_tayin(agent)
                return "tayin"

            # 50侠士/50普通-x-副本完成-退出：OCR 副本已完成 -> 点击退出
            if self._click_text_once(agent, ("副本已完成",), self.ROI_FUBEN_DONE, wait=1.5):
                logger.info("窗口=%s 副本已完成，退出", agent.hwnd)
                time.sleep(1.5)
                return "done"

            # [JumpBack]点击副本-跳过剧情动画
            if self._click_text_once(agent, ("跳过剧情动画",), self.ROI_SKIP_STORY, wait=1.0):
                continue
            # [JumpBack]推荐好友信息：OCR -> ESC
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                if self._find_text_in(self._ocr_lines(agent), ("推荐好友信息",),
                                      self._fraction_region(w, h, self.ROI_TUIJIAN)):
                    logger.info("窗口=%s 推荐好友信息，按 ESC 关闭", agent.hwnd)
                    agent.press_key("esc")
                    time.sleep(1.0)
                    self._ocr_cache = None
                    continue
            # [JumpBack]关闭福利弹窗 / 关闭师门弹窗 / 关闭任务界面 / 战斗平衡弹窗
            if self._dismiss_popups(agent):
                continue
            # [JumpBack]战斗中-等待10秒
            if self._in_battle(agent, self._image(agent)):
                logger.info("窗口=%s 战斗中，等待 %.0f 秒", agent.hwnd, self.battle_wait)
                if self._sleep(self.battle_wait):
                    raise _Aborted()
                continue
            # [JumpBack]点击副本-开始战斗：fubenzhandou 模板 0.9
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                m = self._match_any(agent, self.T_FUBEN_ZHANDOU,
                                    self._fraction_region(w, h, self.ROI_FUBEN_ZHANDOU),
                                    self.TH_FUBEN_ZHANDOU)
                if m:
                    logger.info("窗口=%s 点击副本-开始战斗 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    time.sleep(3.0)
                    # 副本-战斗-对话：OCR 请选择要做的事 -> 点固定位
                    self._battle_dialog(agent)
                    continue
            # [JumpBack]跳过剧情动画-快进键
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                m = self._match_any(agent, self.T_KUAIJIN, None, self.TH_KUAIJIN)
                if m:
                    logger.info("窗口=%s 跳过剧情动画-快进键 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    time.sleep(1.0)
                    continue
            if self._sleep(self.poll_interval):
                raise _Aborted()

    def _battle_dialog(self, agent) -> None:
        """Maa「副本-战斗-对话」：OCR 请选择要做的事 -> 点固定位。"""
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return
            h, w = img.shape[:2]
            if self._find_text_in(self._ocr_lines(agent), ("请选择要做的事",),
                                  self._fraction_region(w, h, self.ROI_ZHANDOU_DUIHUA)):
                fx = int(w * self.POS_ZHANDOU_DUIHUA[0])
                fy = int(h * self.POS_ZHANDOU_DUIHUA[1])
                logger.info("窗口=%s 副本-战斗-对话，点击 (%d,%d)", agent.hwnd, fx, fy)
                agent.click(fx, fy)
                time.sleep(1.0)
                self._ocr_cache = None
                return
            if self._sleep(self.poll_interval):
                raise _Aborted()

    def _dismiss_popups(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        # Maa「关闭福利弹窗」：fuli 模板 -> 点固定位 X
        if self._match_any(agent, self.T_FULI,
                           self._fraction_region(w, h, self.ROI_FULI), self.TH_FULI):
            fx, fy = int(w * self.POS_FULI_CLOSE[0]), int(h * self.POS_FULI_CLOSE[1])
            logger.info("窗口=%s 关闭福利弹窗 (%d,%d)", agent.hwnd, fx, fy)
            agent.click(fx, fy)
            time.sleep(1.0)
            self._ocr_cache = None
            return True
        # Maa「关闭师门弹窗」
        m = self._match_any(agent, self.T_SHIMEN_GB,
                            self._fraction_region(w, h, self.ROI_SHIMEN_GB), self.TH_SHIMEN_GB)
        if m:
            logger.info("窗口=%s 关闭师门弹窗 %s", agent.hwnd, m[:2])
            agent.click(m[0], m[1])
            time.sleep(0.5)
            return True
        # Maa「关闭任务界面」：renwu_jiemian_logo -> 点固定位 X
        if self._match_any(agent, self.T_RENWU_LOGO,
                           self._fraction_region(w, h, self.ROI_RENWU_LOGO), self.TH_RENWU_LOGO):
            fx, fy = int(w * self.POS_RENWU_CLOSE[0]), int(h * self.POS_RENWU_CLOSE[1])
            logger.info("窗口=%s 关闭任务界面 (%d,%d)", agent.hwnd, fx, fy)
            agent.click(fx, fy)
            time.sleep(0.8)
            self._ocr_cache = None
            return True
        # Maa「战斗平衡弹窗-点击关闭」
        m = self._match_any(agent, self.T_POPUP_CLOSE, None, self.TH_POPUP_CLOSE)
        if m:
            logger.info("窗口=%s 关闭战斗平衡弹窗 %s", agent.hwnd, m[:2])
            agent.click(m[0], m[1])
            time.sleep(0.6)
            return True
        return False

    # ==================================================================
    # 收尾分支：退出队伍（MODE="3"）/ 捉鬼桥接（MODE 带 2gui）
    # ==================================================================
    def _quit_team(self, agent) -> None:
        """Maa「退出队伍」链路：Alt+T -> 打开队伍界面成功_退出队伍 -> 点击退出队伍。"""
        logger.info("窗口=%s 三本完成，退出队伍", agent.hwnd)
        self._report("退出队伍")
        self._press_hotkey(agent, "T")  # Maa ClickKey[57,48] = Alt+T
        time.sleep(1.0)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return
            h, w = img.shape[:2]
            # 打开队伍界面成功_退出队伍
            if self._match_any(agent, self.T_DUIWU_PANEL,
                               self._fraction_region(w, h, self.ROI_DUIWU_PANEL),
                               self.TH_DUIWU_PANEL):
                # 点击退出队伍
                if self._click_text_once(agent, ("退出队伍",), self.ROI_TUICHU_DUIWU, wait=0.5):
                    return
                # 退出队伍成功：OCR 创建队伍（已不在队伍中）
                if self._find_text_in(self._ocr_lines(agent), ("创建队伍",),
                                      self._fraction_region(w, h, self.ROI_TUICHU_DUIWU)):
                    return
            else:
                # [JumpBack]队伍界面-按键打开失败-点击队伍图标
                m = self._match_any(agent, self.T_DUIWU_ICON,
                                    self._fraction_region(w, h, self.ROI_DUIWU_ICON),
                                    self.TH_DUIWU_ICON)
                if m:
                    agent.click(m[0], m[1])
                    time.sleep(1.0)
                    continue
            if self._sleep(self.poll_interval):
                raise _Aborted()

    def _run_zhuogui_bridge(self, agent) -> None:
        """Maa「捉鬼-fuben桥接」-> zhuoguirenwu 流程（选项 override：无人员检测 + N 轮）。"""
        zg = _Fuben69Zhuogui()
        zg.ROUNDS = self.GUI_ROUNDS
        zg._stop_event = self._stop_event          # 共享停止信号
        zg._on_update = lambda snap: self._report(f"捉鬼: {snap.message}")
        logger.info("窗口=%s 进入捉鬼桥接(人员检测=%s, 轮数=%d)",
                    agent.hwnd, zg.TEAM_CHECK, zg.ROUNDS)
        zg.run(TaskContext(agent=agent))

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

    def _report(self, message: str) -> None:
        self.snapshot.message = message
        if self._on_update:
            self._on_update(self.snapshot)

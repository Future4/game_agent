# -*- coding: utf-8 -*-
"""挖宝图(清理) —— 按 Maa_MHXY 的 wabaotu.json 流水线原样移植到 game_agent。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/wabaotu.json
    (+ 共享节点: my_task.json「panduan_zhujiemian / amazing_discount(_close) /
       close_exit_confirm / 关闭三界热点 / 自动寻路中-图片识别 / 战斗中-等待10秒」
       baotu_renwu.json「战斗平衡弹窗-点击关闭」
       zhengli_baibao.json「整理完成 / 背包向上滑动10次」)

======================= Maa 原始流程(节点图) =======================
wabaotu_qingli (entry)
  next:
    清理主界面使用-关闭完成      inverse(主界面"使用"弹窗X) -> wabaotu
    [JumpBack]清理主界面使用-关闭  有"使用"弹窗 -> 点X关掉, 跳回
    [JumpBack]战斗平衡弹窗-点击关闭
    [JumpBack]panduan_zhujiemian  回主界面(ESC循环 / amazing_discount / 退出确认)

wabaotu -> ClickKey[57,33](Alt+E 打开背包)
  next:
    挖宝图-打开背包-成功-并向上滑动到顶端   背包界面判断 -> MultiSwipe x3 滑到顶端
    [JumpBack]背包界面-按键打开失败-点击图标  点包裹图标(模板/OCR"包裹")

挖宝图-点击整理 (OCR"整理")
  next:
    点击藏宝图                  模板 baotu/cangbaotu -> 藏宝图-背包使用
    整理完成                    beibao_konggezi|beibao_diduan -> panduan_zhujiemian(结束)
    [JumpBack]背包向上滑动10次    max_hit 10, 找不到就往下翻

藏宝图-背包使用 (OCR"使用", rate_limit 2000)
  next:
    [JumpBack]藏宝图-主界面使用      主界面弹窗"使用" -> 点击
    [JumpBack]战斗中-等待10秒
    [JumpBack]自动寻路中-图片识别    pre_delay 3000
    [JumpBack]关闭三界热点          OCR"点击下方空白处关闭界面"
    [JumpBack]战斗平衡弹窗-点击关闭
  on_error: 挖宝图完成判断          背包"使用"找不到了 -> 重新开背包找下一张

挖宝图完成判断 -> ClickKey[57,33] 重新打开背包
  -> 挖宝图完成判断-打开背包成功
     next: 点击藏宝图(循环挖下一张) | 挖宝完成(konggezi|diduan -> panduan_zhujiemian) |
           [JumpBack]背包向上滑动10次

======================= 移植适配说明 =======================
官网 PC 客户端(Unity) 与 Maa 的模拟器(1280x720) 不同:
  1. 布局非等比, roi 由 Maa 像素坐标换算为窗口比例并适当放大, 模板匹配用多尺度。
  2. ClickKey[57,33] = Alt+E 开背包, 用 win32 keybd_event 实现; 失败回退点包裹图标。
  3. 整理/使用按钮：Windows OCR 读不出官网客户端的按钮文字（白字金底+字间距大），
     "整理"用本机裁剪模板 beibao/zhengli_btn，"使用"用 run_dig_task.py 验证过的
     use_dialog1/2 + use_btn1/2 模板；OCR 仅作兜底（整图识别+ROI 中心过滤，带缓存）。
  4. 战斗检测沿用本机已验证的「顶部圆形一致性(HoughCircles)」方案。

滑动方向约定(与手指方向一致, 内容跟随手指):
  - 背包「滑到顶端」 = 手指从上往下: fy_start 小 -> fy_end 大
  - 背包「向下翻页」 = 手指从下往上: fy_start 大 -> fy_end 小
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


class WabaotuMaaTask(AutomationTask):
    definition = TaskDefinition(
        "wabaotu_maa", "挖宝图(清理)", "移植自 Maa_MHXY 的 wabaotu 流水线"
    )

    # ---------------- 时序参数（对应 Maa 流水线字段）----------------
    poll_interval = 0.5
    node_timeout = 90.0          # 单节点等待上限(秒)
    battle_wait = 10.0           # Maa: 战斗中-等待10秒 (pre_delay 10000)
    autopath_wait = 3.0          # Maa: 自动寻路中-图片识别 (pre_delay 3000)
    use_rate_limit = 2.0         # Maa: 藏宝图-背包使用 rate_limit 2000
    bag_swipe_max = 10           # Maa: 背包向上滑动10次 (max_hit 10)
    use_loop_timeout = 300.0     # 单张藏宝图挖掘等待上限
    total_timeout = 1800.0       # 整个任务上限

    # ---------------- 可调开关 ----------------
    ocr_cache_seconds = 2.0      # OCR 整图识别结果缓存时长(秒)
    zhengli_click = True         # Maa「挖宝图-点击整理」：找图前先点一次"整理"
    cha_close_max = 5            # entry 阶段关"使用"弹窗的最大次数

    # ---------------- 阈值（官网客户端实测校准，沿用宝图任务经验值）----------------
    TH_MAIN_INDICATOR = 0.75
    TH_CHA = 0.80                # 主界面"使用"弹窗的 X
    TH_BAG_ICON = 0.90           # Maa 包裹图标 threshold 0.9
    TH_BAG_PANEL = 0.75
    TH_CANGBAOTU = 0.75
    TH_BAG_BOTTOM = 0.88         # Maa: 挖宝完成 0.8 / 整理完成 0.9；0.88 避开礼包按钮(实测 0.81)误报
    TH_POPUP_CLOSE = 0.88
    TH_AUTOPATH = 0.90
    TH_AMAZING = 0.80
    TH_AMAZING_CLOSE = 0.80
    TH_EXIT_CONFIRM = 0.80
    TH_ZHENGLI_BTN = 0.85        # 整理按钮模板（裁剪自本机截图，实测 0.99）
    TH_USE_DIALOG = 0.65         # 使用对话框（use_dialog1/2）
    TH_USE_BTN = 0.70            # 使用按钮（use_btn1/2）

    # ---------------- 模板名（templates/ 目录，不带 .png）----------------
    # 命名与 Maa_MHXY-main/assets/resource/base/image 完全一致（保留子目录/相对路径）。
    # Maa「panduan_zhujiemian_ks」: zonghe/jiahao|chenghao|baoguo|baoguo_man
    T_MAIN_INDICATORS = ("zonghe/jiahao", "zonghe/baoguo", "zonghe/baoguo_man", "zonghe/chenghao")
    # Maa「清理主界面使用-关闭」: 主界面"使用"弹窗的关闭 X
    T_CHA = ("zonghe/zhujiemian_shiyong_cha",)
    # Maa「背包界面-按键打开失败-点击图标」
    T_BAG_ICON = ("zonghe/baoguo", "zonghe/baoguo_man")
    # Maa「挖宝图-打开背包-成功」背包界面判断
    T_BAG_PANEL = ("beibao/beibao_jiemian_panduan",)
    # Maa「点击藏宝图」
    T_CANGBAOTU = ("baotu/cangbaotu",)
    # Maa「整理完成」/「挖宝完成」: 背包空格/到底
    T_BAG_BOTTOM = ("beibao/beibao_konggezi", "beibao/beibao_diduan")
    # Maa「战斗平衡弹窗-点击关闭」
    T_POPUP_CLOSE = ("zonghe/zhandoupingheng_guanbi1",)
    # Maa「自动寻路中-图片识别」
    T_AUTOPATH = ("zonghe/zidongxunlu1", "zonghe/zidongxunlu2", "zonghe/zidongxunlu3", "zonghe/zidongxunlu4")
    # Maa「战斗中-等待10秒」的战斗按钮（主判定用 HoughCircles，模板作辅助）
    T_BATTLE_BTN = ("zhandou/zidong", "zhandou/quxiao")
    # Maa「amazing_discount」/「amazing_discount_close」
    T_AMAZING = ("zonghe/amazing_discount",)
    T_AMAZING_CLOSE = ("zonghe/amazing_discount_close",)
    # Maa「close_exit_confirm」
    T_EXIT_CONFIRM = ("zonghe/exit_confirm",)
    # 官网客户端补充模板（Windows OCR 读不出"整理/使用"按钮文字，改用模板）
    # 整理按钮（裁剪自本机背包截图）
    T_ZHENGLI_BTN = ("beibao/zhengli_btn",)
    # 背包使用确认对话框（点击藏宝图后弹出：丢弃/使用），沿用 run_dig_task.py 已验证模板
    T_USE_DIALOG1 = ("use_dialog1",)
    T_USE_BTN1 = ("use_btn1",)
    # 到达地点后的使用对话框（"使 用" + 关闭X）
    T_USE_DIALOG2 = ("use_dialog2",)
    T_USE_BTN2 = ("use_btn2",)

    # ---------------- 区域比例（由 Maa 1280x720 像素 roi 换算并适当放大）----------------
    ROI_MAIN_INDICATOR = (0.86, 0.72, 0.14, 0.28)   # 右下角 +/称号/包裹
    ROI_CHA = (0.82, 0.42, 0.18, 0.20)              # Maa [1135,369,50,46] 放大
    ROI_BAG_ICON = (0.86, 0.66, 0.14, 0.32)         # Maa [1185,529,95,110] 放大
    ROI_BAG_PANEL = (0.15, 0.00, 0.70, 0.25)        # Maa [335,5,577,68] 放大；官网客户端标题栏偏低(底部约16%)，需覆盖到 0.25
    ROI_BAG_GRID = (0.42, 0.14, 0.55, 0.78)         # Maa [632,140,473,484] 放大
    ROI_BAG_BOTTOM = (0.62, 0.68, 0.30, 0.24)       # Maa [905,543,187,94] 放大
    ROI_ZHENGLI = (0.55, 0.68, 0.43, 0.30)          # 官网客户端"整 理"按钮中心约在 76% 高度，旧 ROI(0.78 起)罩不住
    ROI_USE_BAG = (0.24, 0.48, 0.32, 0.24)          # Maa OCR"使用" [425,418,159,63] 放大
    ROI_USE_MAIN = (0.66, 0.62, 0.34, 0.28)         # Maa OCR"使用" [1013,536,157,73] 放大
    ROI_SANJIE = (0.28, 0.86, 0.44, 0.14)           # Maa [472,666,332,38] 放大
    ROI_AUTOPATH = (0.20, 0.18, 0.60, 0.64)
    ROI_AMAZING = (0.18, 0.05, 0.67, 0.46)          # Maa [233,40,846,324]
    ROI_AMAZING_CLOSE = (0.66, 0.04, 0.30, 0.26)    # Maa [947,61,120,127] 放大
    ROI_EXIT_CONFIRM = (0.16, 0.50, 0.68, 0.38)     # Maa [246,398,791,200] 放大

    # 滑动坐标（比例）
    SWIPE_BAG_X = 0.709          # Maa x=906~907/1280
    SWIPE_TOP_FROM = 0.257       # 滑到顶端：手指下滑 185 -> 548
    SWIPE_TOP_TO = 0.761
    SWIPE_DOWN_FROM = 0.642      # 向下翻页：手指上滑 462 -> 363
    SWIPE_DOWN_TO = 0.504

    # ==================================================================
    # 主流程
    # ==================================================================
    def __init__(self) -> None:
        super().__init__()
        self._on_update = None
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._dug_count = 0
        self._last_use_click = 0.0
        self._swipe_vertical = self._do_swipe_vertical
        self._ocr_cache = None

    def run(self, context: TaskContext,
            on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._dug_count = 0
        self._last_use_click = 0.0
        self._swipe_vertical = self._do_swipe_vertical  # 允许测试替换
        self._ocr_cache = None

        logger.info("挖宝图(清理)启动 hwnd=%s", getattr(agent, "hwnd", None))
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 4
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            # 步骤2: Maa entry「wabaotu_qingli」—— 关掉主界面"使用"弹窗/战斗平衡弹窗
            self._stage(agent, 2, "清理主界面弹窗", self._node_entry_cleanup)

            # 步骤3: Maa「wabaotu」—— Alt+E 打开背包 -> 滑到顶端 -> 点整理 -> 找藏宝图
            self._report("打开背包并整理")
            if not self._open_bag(agent):
                self.snapshot.status = TaskStatus.FAILED
                self._report("未能打开背包，请检查窗口状态与模板")
                logger.error("窗口=%s 未能打开背包，任务终止", agent.hwnd)
                return
            self._bag_scroll_to_top(agent)
            self.snapshot.completed_steps = 3

            # 步骤4: 挖宝循环（找藏宝图 -> 使用 -> 挖掘等待 -> 重开背包找下一张）
            self._report("开始挖宝循环")
            used_any = self._dig_cycle(agent, first_pass=True)

            # Maa「挖宝完成/整理完成」-> panduan_zhujiemian：收尾回主界面
            self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "收尾回主界面")

            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            msg = f"挖宝图(清理)完成，共挖 {self._dug_count} 张" if used_any else "背包中没有藏宝图，任务结束"
            self._report(msg)
            logger.info("窗口=%s %s", agent.hwnd, msg)
        except _Aborted:
            logger.info("挖宝图停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("挖宝图执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("挖宝图执行异常，详见日志")

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
    # 节点1: panduan_zhujiemian（含 amazing_discount / 退出确认处理）
    # ==================================================================
    def _node_panduan_zhujiemian(self, agent) -> bool:
        # Maa「amazing_discount」->「amazing_discount_close」
        img = self._image(agent)
        if img is not None:
            h, w = img.shape[:2]
            if self._match_any(agent, self.T_AMAZING,
                               self._fraction_region(w, h, self.ROI_AMAZING), self.TH_AMAZING):
                m_close = self._match_any(agent, self.T_AMAZING_CLOSE,
                                          self._fraction_region(w, h, self.ROI_AMAZING_CLOSE),
                                          self.TH_AMAZING_CLOSE)
                if m_close:
                    logger.info("窗口=%s 关闭限时折扣弹窗 %s", agent.hwnd, m_close[:2])
                    agent.click(m_close[0], m_close[1])
                    time.sleep(0.8)
                    return False
            # Maa「close_exit_confirm」：退出确认弹窗 -> 按 BACK(ESC) 取消
            if self._match_any(agent, self.T_EXIT_CONFIRM,
                               self._fraction_region(w, h, self.ROI_EXIT_CONFIRM),
                               self.TH_EXIT_CONFIRM):
                logger.info("窗口=%s 检测到退出确认弹窗，按 ESC 取消", agent.hwnd)
                agent.press_key("esc")
                time.sleep(0.8)
                return False

        if self._on_main_interface(agent):
            return True
        if self._in_battle(img):
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
    # 节点2: entry「wabaotu_qingli」—— 清理主界面"使用"弹窗
    # ==================================================================
    def _node_entry_cleanup(self, agent) -> bool:
        # [JumpBack]战斗平衡弹窗-点击关闭
        self._dismiss_popups(agent)
        # 清理主界面使用-关闭完成 = inverse(弹窗X 存在) -> 没有了才算完成
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_CHA)
        for attempt in range(self.cha_close_max):
            m = self._match_any(agent, self.T_CHA, roi, self.TH_CHA)
            if not m:
                return True
            logger.info("窗口=%s 关闭主界面\"使用\"弹窗(%d/%d) %s",
                        agent.hwnd, attempt + 1, self.cha_close_max, m[:2])
            agent.click(m[0], m[1])
            time.sleep(1.0)
            img = self._image(agent)
        logger.warning("窗口=%s \"使用\"弹窗关闭达上限仍未消失，继续后续流程", agent.hwnd)
        return True

    # ==================================================================
    # 节点3: 打开背包（Alt+E，失败点包裹图标）+ 滑到顶端
    # ==================================================================
    def _open_bag(self, agent) -> bool:
        """Maa「wabaotu」/「挖宝图完成判断」：ClickKey[57,33] 开背包并等待界面出现。"""
        started = time.monotonic()
        pressed = False
        while time.monotonic() - started < self.node_timeout:
            self._check_stop(agent)
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                roi = self._fraction_region(w, h, self.ROI_BAG_PANEL)
                if self._match_any(agent, self.T_BAG_PANEL, roi, self.TH_BAG_PANEL):
                    logger.info("窗口=%s 背包界面已打开", agent.hwnd)
                    return True
            if not pressed:
                self._press_bag_hotkey(agent)
                pressed = True
                time.sleep(1.0)
                continue
            # [JumpBack]背包界面-按键打开失败-点击图标：模板优先，OCR"包裹"兜底
            if not self._click_bag_icon(agent):
                self._press_bag_hotkey(agent)  # 图标也没找到就再按一次快捷键
                time.sleep(1.0)
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 打开背包超时", agent.hwnd)
        return False

    def _press_bag_hotkey(self, agent) -> None:
        """Maa ClickKey[57,33] = Alt+E（安卓 keycode 57=ALT_LEFT, 33=E）。"""
        try:
            import win32api
            import win32con
        except Exception:
            return
        try:
            self._ensure_foreground(agent.hwnd)
            time.sleep(0.2)
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord("E"), 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(ord("E"), 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            logger.info("窗口=%s 按下 Alt+E 打开背包", agent.hwnd)
        except Exception:
            logger.exception("窗口=%s Alt+E 按键失败", getattr(agent, "hwnd", None))

    def _click_bag_icon(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_BAG_ICON)
        m = self._match_any(agent, self.T_BAG_ICON, roi, self.TH_BAG_ICON)
        if not m:
            # Maa 的 Or 分支：OCR "包裹"/"包"/"裹"
            pos = self._find_label_in(self._ocr_lines(agent), ("包裹", "包", "裹"), roi)
            if pos:
                m = (pos[0], pos[1], 0.0)
        if not m:
            return False
        logger.info("窗口=%s 点击包裹图标 %s", agent.hwnd, m[:2])
        agent.click(m[0], m[1])
        time.sleep(1.0)
        return True

    def _bag_scroll_to_top(self, agent) -> None:
        """Maa「挖宝图-打开背包-成功-并向上滑动到顶端」：MultiSwipe x3。"""
        for _ in range(3):
            self._swipe_vertical(agent, self.SWIPE_BAG_X,
                                 self.SWIPE_TOP_FROM, self.SWIPE_TOP_TO)
            time.sleep(0.4)
        self._ocr_cache = None

    # ==================================================================
    # 节点4: 挖宝循环
    # ==================================================================
    def _dig_cycle(self, agent, first_pass: bool) -> bool:
        """找藏宝图 -> 使用 -> 等挖完 -> 重开背包找下一张，直到背包没有藏宝图。

        first_pass=True 对应 Maa「挖宝图-点击整理」入口（先点整理再翻页找）；
        后续每轮对应 Maa「挖宝图完成判断」（重开背包 -> 翻页找）。
        返回是否挖到过至少一张。
        """
        used_any = False
        while True:
            self._check_stop(agent)
            if first_pass:
                # Maa「挖宝图-点击整理」
                if self.zhengli_click:
                    self._click_zhengli(agent)
            else:
                # Maa「挖宝图完成判断」：重新打开背包
                self._report("重新打开背包查找藏宝图")
                if not self._open_bag(agent):
                    logger.warning("窗口=%s 重新打开背包失败，结束挖宝循环", agent.hwnd)
                    return used_any

            result = self._search_cangbaotu(agent)
            if result == "found":
                self._report(f"开始挖第 {self._dug_count + 1} 张藏宝图")
                if self._use_and_wait(agent):
                    self._dug_count += 1
                    used_any = True
                    self._report(f"已挖 {self._dug_count} 张藏宝图")
                first_pass = False
                continue
            # result == "done"：Maa「整理完成」/「挖宝完成」—— 背包已没有藏宝图
            logger.info("窗口=%s 背包中已无藏宝图", agent.hwnd)
            return used_any

    def _click_zhengli(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_ZHENGLI)
        # 模板优先（Windows OCR 读不出"整 理"按钮文字），OCR 兜底
        m = self._match_any(agent, self.T_ZHENGLI_BTN, roi, self.TH_ZHENGLI_BTN)
        pos = (m[0], m[1]) if m else self._find_label_in(self._ocr_lines(agent), ("整理",), roi)
        if not pos:
            logger.info("窗口=%s 未找到\"整理\"按钮，跳过", agent.hwnd)
            return False
        logger.info("窗口=%s 点击整理 %s", agent.hwnd, pos)
        agent.click(pos[0], pos[1])
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    def _search_cangbaotu(self, agent) -> str:
        """在背包里找藏宝图：找到返回 "found"（已点击），确认没有返回 "done"。

        对应 Maa 的 next 列表: 点击藏宝图 | 整理完成/挖宝完成 | [JumpBack]背包向上滑动10次
        """
        swipes = 0
        while True:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                if self._sleep(self.poll_interval):
                    raise _Aborted()
                continue
            h, w = img.shape[:2]
            m = self._match_any(agent, self.T_CANGBAOTU,
                                self._fraction_region(w, h, self.ROI_BAG_GRID),
                                self.TH_CANGBAOTU)
            if m:
                pos = self._confirm_stable(agent, m)
                if pos:
                    logger.info("窗口=%s 点击藏宝图 %s", agent.hwnd, pos[:2])
                    agent.click(pos[0], pos[1])
                    time.sleep(0.8)
                    self._ocr_cache = None
                    return "found"
                # 截图偶发瞬移/滚动未稳定：本轮不翻页，稍后重查
                logger.info("窗口=%s 藏宝图位置不稳定，等待画面稳定后重查", agent.hwnd)
                if self._sleep(0.6):
                    raise _Aborted()
                continue
            # 整理完成/挖宝完成：背包空格或已到底
            if self._match_any(agent, self.T_BAG_BOTTOM,
                               self._fraction_region(w, h, self.ROI_BAG_BOTTOM),
                               self.TH_BAG_BOTTOM):
                return "done"
            if swipes >= self.bag_swipe_max:
                # 翻页 10 次仍没找到也没见到底部标记：按 Maa 语义视为没有，结束
                logger.warning("窗口=%s 背包翻页 %d 次仍未找到藏宝图，按完成处理",
                               agent.hwnd, self.bag_swipe_max)
                return "done"
            swipes += 1
            logger.info("窗口=%s 背包向下翻页(%d/%d)",
                        agent.hwnd, swipes, self.bag_swipe_max)
            self._swipe_vertical(agent, self.SWIPE_BAG_X,
                                 self.SWIPE_DOWN_FROM, self.SWIPE_DOWN_TO)
            self._ocr_cache = None
            time.sleep(0.5)

    def _confirm_stable(self, agent, first, tries: int = 3,
                        tolerance: float = 25.0) -> Optional[Tuple[int, int, float]]:
        """点击前复验：连续两次匹配位置一致才返回，避免截图瞬移导致点空。"""
        prev = first
        for _ in range(tries):
            time.sleep(0.2)
            img = self._image(agent)
            if img is None:
                return None
            h, w = img.shape[:2]
            m = self._match_any(agent, self.T_CANGBAOTU,
                                self._fraction_region(w, h, self.ROI_BAG_GRID),
                                self.TH_CANGBAOTU)
            if m and abs(m[0] - prev[0]) <= tolerance and abs(m[1] - prev[1]) <= tolerance:
                return m
            prev = m
        return None

    # ==================================================================
    # 节点5: 藏宝图-背包使用 + 挖掘等待（Maa 的 JumpBack 循环）
    # ==================================================================
    def _use_and_wait(self, agent) -> bool:
        """点"使用"并等待这次挖掘结束。返回 True 表示成功使用了一张。

        循环体对应 Maa「藏宝图-背包使用」的 next 列表（全部 JumpBack）：
        主界面使用 / 战斗中等待10秒 / 自动寻路 / 关闭三界热点 / 战斗平衡弹窗。
        所有信号都消失（on_error）-> 返回，由上层重开背包。
        """
        started = time.monotonic()
        used = False
        idle_rounds = 0
        idle_rounds_max = int(12 / self.poll_interval)  # 无任何信号约 12 秒才认定结束
        while True:
            self._check_stop(agent)
            if time.monotonic() - started > self.use_loop_timeout:
                logger.warning("窗口=%s 单张藏宝图挖掘等待超时，重开背包继续", agent.hwnd)
                return used

            # [JumpBack]战斗平衡弹窗-点击关闭
            if self._dismiss_popups(agent):
                idle_rounds = 0
                continue
            # [JumpBack]关闭三界热点
            if self._close_sanjie(agent):
                idle_rounds = 0
                continue

            img = self._image(agent)
            # [JumpBack]战斗中-等待10秒
            if self._in_battle(img):
                logger.info("窗口=%s 战斗中，等待 %.0f 秒", agent.hwnd, self.battle_wait)
                if self._sleep(self.battle_wait):
                    raise _Aborted()
                idle_rounds = 0
                continue
            # [JumpBack]自动寻路中-图片识别
            if img is not None:
                h, w = img.shape[:2]
                if self._match_any(agent, self.T_AUTOPATH,
                                   self._fraction_region(w, h, self.ROI_AUTOPATH),
                                   self.TH_AUTOPATH):
                    if self._sleep(self.autopath_wait):
                        raise _Aborted()
                    idle_rounds = 0
                    continue

            # [JumpBack]藏宝图-背包使用（背包确认对话框 use_dialog1/use_btn1）
            # 官网客户端按钮文字 OCR 读不出，改用 run_dig_task.py 验证过的模板
            state = self._use_dialog_state(agent, self.T_USE_DIALOG1, self.T_USE_BTN1)
            if state is not None:
                if isinstance(state, tuple):
                    if time.monotonic() - self._last_use_click >= self.use_rate_limit:
                        logger.info("窗口=%s 点击背包对话框\"使用\" %s", agent.hwnd, state)
                        agent.click(state[0], state[1])
                        self._last_use_click = time.monotonic()
                        used = True
                        time.sleep(1.0)
                        self._ocr_cache = None
                        idle_rounds = 0
                        continue
                    # Maa rate_limit 2000：限速期内不点击也不计空闲
                    if self._sleep(self.poll_interval):
                        raise _Aborted()
                    continue
                # 对话框在但按钮未匹配上：计入空闲，防止死等
                idle_rounds += 1
                if idle_rounds >= idle_rounds_max:
                    logger.warning("窗口=%s 使用对话框按钮持续未匹配，跳过这张藏宝图", agent.hwnd)
                    return used
                if self._sleep(self.poll_interval):
                    raise _Aborted()
                continue
            # [JumpBack]藏宝图-主界面使用（到达地点后的对话框 use_dialog2/use_btn2）
            state = self._use_dialog_state(agent, self.T_USE_DIALOG2, self.T_USE_BTN2)
            if state is not None:
                if isinstance(state, tuple):
                    logger.info("窗口=%s 点击地点对话框\"使用\" %s", agent.hwnd, state)
                    agent.click(state[0], state[1])
                    used = True
                    time.sleep(1.0)
                    self._ocr_cache = None
                    idle_rounds = 0
                    continue
                idle_rounds += 1
                if idle_rounds >= idle_rounds_max:
                    logger.warning("窗口=%s 地点对话框按钮持续未匹配，跳过这张藏宝图", agent.hwnd)
                    return used
                if self._sleep(self.poll_interval):
                    raise _Aborted()
                continue

            # [JumpBack]藏宝图-主界面使用（OCR 兜底）
            pos = self._ocr_use_in(agent, self.ROI_USE_MAIN)
            if pos:
                logger.info("窗口=%s 点击主界面\"使用\" %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(1.0)
                self._ocr_cache = None
                idle_rounds = 0
                continue
            # 藏宝图-背包使用（rate_limit 2000）
            pos = self._ocr_use_in(agent, self.ROI_USE_BAG)
            if pos:
                now = time.monotonic()
                if now - self._last_use_click < self.use_rate_limit:
                    if self._sleep(self.poll_interval):
                        raise _Aborted()
                    continue
                logger.info("窗口=%s 点击背包\"使用\" %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                self._last_use_click = now
                used = True
                time.sleep(1.0)
                self._ocr_cache = None
                idle_rounds = 0
                continue

            if not used:
                # 一直没点到"使用"：详情面板可能没打开，放弃这张由上层重试
                idle_rounds += 1
                if idle_rounds >= idle_rounds_max:
                    logger.warning("窗口=%s 未找到\"使用\"按钮，跳过这张藏宝图", agent.hwnd)
                    return False
            else:
                # on_error：挖掘收尾阶段所有信号消失 -> 完成判断（重开背包）
                idle_rounds += 1
                if idle_rounds >= idle_rounds_max:
                    logger.info("窗口=%s 挖掘信号消失，本次挖宝结束", agent.hwnd)
                    return True
            if self._sleep(self.poll_interval):
                raise _Aborted()

    def _ocr_use_in(self, agent, frac) -> Optional[Tuple[int, int]]:
        img = self._image(agent)
        if img is None:
            return None
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, frac)
        return self._find_label_in(self._ocr_lines(agent), ("使用",), roi)

    def _use_dialog_state(self, agent, dialog_tpls, btn_tpls):
        """检测使用对话框：无 -> None；在但按钮未匹配 -> "wait"；按钮位置 -> (x, y)。"""
        img = self._image(agent)
        if img is None:
            return None
        if not self._match_any(agent, dialog_tpls, None, self.TH_USE_DIALOG):
            return None
        m = self._match_any(agent, btn_tpls, None, self.TH_USE_BTN)
        return (m[0], m[1]) if m else "wait"

    def _close_sanjie(self, agent) -> bool:
        """Maa「关闭三界热点」：OCR 找"点击...空白处关闭界面"并点击。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_SANJIE)
        for item in self._ocr_lines(agent):
            text = (item.get("text") or "").strip()
            text = text.replace(" ", "").replace("\u3000", "")
            if "空白处关闭界面" not in text:
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                logger.info("窗口=%s 关闭三界热点 %s", agent.hwnd, (int(cx), int(cy)))
                agent.click(int(cx), int(cy))
                time.sleep(0.5)
                self._ocr_cache = None
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
        """在整图 OCR 结果里、于指定区域内找**精确等于** labels 之一的文字，返回中心。

        比较前去掉文字内部的空格/全角空格（如"使 用"），避免 OCR 分词差异漏检。
        """
        x, y, rw, rh = region
        for item in lines:
            text = (item.get("text") or "").strip()
            text = text.replace(" ", "").replace("\u3000", "")
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

    def _report(self, message: str) -> None:
        self.snapshot.message = message
        if self._on_update:
            self._on_update(self.snapshot)

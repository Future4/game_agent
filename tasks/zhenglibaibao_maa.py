# -*- coding: utf-8 -*-
"""整理背包 —— 按 Maa_MHXY 的 zhengli_baibao.json 流水线原样移植到 game_agent。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/zhengli_baibao.json
    (+ 共享节点: my_task.json「panduan_zhujiemian / 主界面 / 关闭整点活动弹窗」
       wabaotu.json「背包界面-按键打开失败-点击图标」)

======================= Maa 原始流程(节点图) =======================
zhengli_baibao -> 整理背包-过渡(主界面 +/称号) -> ClickKey[57,33](Alt+E 打开背包)
  -> 打开背包成功-向上滑动到顶端(beibao_jiemian_panduan -> MultiSwipe x3)
  -> 点击整理(OCR 整理)
     next:
       整理完成                      beibao_konggezi|beibao_diduan(0.9) -> panduan(结束)
       主界面                        背包已关(回到主界面) -> 结束
       [JumpBack]关闭整点活动弹窗
       [JumpBack]使用红罗羹(max 10)   模板 -> 点击更多 -> 点击批量使用 -> 使用
       [JumpBack]使用绿芦羹(max 10)   模板 -> 点击更多 -> 点击批量使用 -> 使用
       [JumpBack]使用心魔宝珠(max 10)  模板 -> 点击批量使用_心魔宝珠
       [JumpBack]合成阵法(max 10)     zhenfajuan(0.98) -> 点击阵法使用
       [JumpBack]使用秘境材料(max 10)  18种材料模板(0.9) -> 秘境材料-收入
       [JumpBack]使用过期物品(max 10)  guoqi 模板 -> 连点2次
       [JumpBack]背包向上滑动10次     找不到物品就往下翻(max_hit 10)
       [JumpBack]panduan_zhujiemian

======================= Maa 任务选项映射（「使用及清理列表」checkbox, 默认全选）=======================
  USE_HONGLUO_GEN  红罗羹    USE_LVLU_GEN      绿芦羹
  USE_XINMO        心魔宝珠  USE_ZHENFAJUAN    阵法卷(合成阵法)
  USE_MIJING       秘境材料  USE_GUOQI         过期物品
  (出售百炼精铁/出售制造书/出售阵法 三个节点在 Maa 中 enabled:false 且不在选项里, 不移植)

======================= 移植适配说明 =======================
官网 PC 客户端(Unity) 与 Maa 的模拟器(1280x720) 不同:
  1. 布局非等比, roi 由 Maa 像素坐标换算为窗口比例并适当放大, 模板匹配用多尺度。
  2. ClickKey[57,33] = Alt+E 开背包(win32 keybd_event), 失败回退点包裹图标。
  3. OCR 走整图识别+ROI 中心过滤(带缓存)。
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


class ZhengliBaibaoMaaTask(AutomationTask):
    definition = TaskDefinition(
        "zhenglibaibao_maa", "整理背包", "移植自 Maa_MHXY 的 zhengli_baibao 流水线"
    )

    # ---------------- 任务选项（对应 Maa 选项「使用及清理列表」，默认全选）----------------
    USE_HONGLUO_GEN = True       # 红罗羹
    USE_LVLU_GEN = True          # 绿芦羹
    USE_XINMO = True             # 心魔宝珠
    USE_ZHENFAJUAN = True        # 阵法卷(合成阵法)
    USE_MIJING = True            # 秘境材料
    USE_GUOQI = True             # 过期物品

    # ---------------- 时序参数（对应 Maa 流水线字段）----------------
    poll_interval = 0.5
    node_timeout = 90.0
    item_use_max = 10            # Maa: 使用xx (max_hit 10)
    bag_swipe_max = 10           # Maa: 背包向上滑动10次 (max_hit 10)
    total_timeout = 900.0

    # ---------------- 可调开关 ----------------
    ocr_cache_seconds = 2.0

    # ---------------- 阈值 ----------------
    TH_MAIN_INDICATOR = 0.75
    TH_BAG_ICON = 0.90           # Maa 包裹图标 threshold 0.9
    TH_BAG_PANEL = 0.75
    TH_BAG_BOTTOM = 0.90         # Maa: 整理完成 threshold 0.9
    TH_ITEM = 0.80               # 红罗羹/绿芦羹/心魔宝珠/过期物品(Maa 默认阈值)
    TH_ZHENFAJUAN = 0.98         # Maa: 合成阵法 threshold 0.98
    TH_MIJING = 0.90             # Maa: 使用秘境材料 threshold 0.9
    TH_RENWU_TANCHUANG = 0.80

    # ---------------- 模板名（templates/ 目录，不带 .png）----------------
    T_MAIN_INDICATORS = ("zonghe/jiahao", "zonghe/baoguo", "zonghe/baoguo_man", "zonghe/chenghao")
    T_BAG_ICON = ("zonghe/baoguo", "zonghe/baoguo_man")
    T_BAG_PANEL = ("beibao/beibao_jiemian_panduan",)
    # Maa「整理完成」
    T_BAG_BOTTOM = ("beibao/beibao_konggezi", "beibao/beibao_diduan")
    # Maa「使用红罗羹」/「使用绿芦羹」/「使用心魔宝珠」/「使用过期物品」
    T_HONGLUO = ("beibao/hongluogeng",)
    T_LVLU = ("beibao/lvlugeng",)
    T_XINMO = ("beibao/xinmobaozhu",)
    T_GUOQI = ("beibao/guoqi",)
    # Maa「合成阵法」
    T_ZHENFAJUAN = ("beibao/zhenfajuan",)
    # Maa「使用秘境材料」(18 种)
    T_MIJING = (
        "mijing_cailiao/bulaogen", "mijing_cailiao/chilongjiao", "mijing_cailiao/danzhusha",
        "mijing_cailiao/donghuangjiuge", "mijing_cailiao/dushengyupo", "mijing_cailiao/jiangmulingzhong",
        "mijing_cailiao/jiaorenzhu", "mijing_cailiao/jinwuzhi", "mijing_cailiao/nanshanyu",
        "mijing_cailiao/qimingzhiyao", "mijing_cailiao/wangchuanshi", "mijing_cailiao/wutongshenmu",
        "mijing_cailiao/xiaochunlan", "mijing_cailiao/xitianqueling", "mijing_cailiao/xuannvlei",
        "mijing_cailiao/yinyangcao", "mijing_cailiao/yueguilu", "mijing_cailiao/zhurongguo",
    )
    # Maa「关闭整点活动弹窗」
    T_RENWU_TANCHUANG = ("zonghe/renwu_tanchuang",)

    # ---------------- 区域比例（由 Maa 1280x720 像素 roi 换算并适当放大）----------------
    ROI_MAIN_INDICATOR = (0.86, 0.72, 0.14, 0.28)
    ROI_BAG_ICON = (0.86, 0.66, 0.14, 0.32)
    ROI_BAG_PANEL = (0.18, 0.00, 0.64, 0.14)       # Maa [335,5,577,68] 放大
    ROI_ZHENGLI = (0.60, 0.78, 0.36, 0.20)         # Maa 整理 [873,609,241,77] 放大
    ROI_BAG_BOTTOM = (0.62, 0.68, 0.30, 0.24)      # Maa [905,543,187,94] 放大
    ROI_BAG_GRID = (0.42, 0.14, 0.55, 0.78)        # Maa 物品区 [618,140,479,479] 放大
    ROI_GENGDUO = (0.12, 0.50, 0.26, 0.20)         # Maa 更多 [242,426,173,74] 放大
    ROI_PLSY = (0.12, 0.44, 0.26, 0.16)            # Maa 批量使用 [258,381,133,37] 放大
    ROI_PLSY_XINMO = (0.26, 0.50, 0.26, 0.22)      # Maa 批量使用_心魔宝珠 [423,429,169,80] 放大
    ROI_SHIYONG_GENG = (0.28, 0.54, 0.42, 0.30)    # Maa 使用(羹类) [448,451,402,156] 放大
    ROI_SHIYONG_ZHENFA = (0.26, 0.50, 0.26, 0.20)  # Maa 使用(阵法) [424,419,161,62] 放大
    ROI_SHOURU = (0.26, 0.50, 0.24, 0.18)          # Maa 收入 [437,427,134,48] 放大
    ROI_RENWU_TANCHUANG = (0.55, 0.45, 0.22, 0.24)

    # 滑动坐标（比例）
    SWIPE_BAG_X = 0.709          # Maa x=907~908/1280
    SWIPE_TOP_FROM = 0.306       # 滑到顶端：手指下滑 220 -> 447
    SWIPE_TOP_TO = 0.621
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
        self._use_counts = {}
        self._swipe_vertical = self._do_swipe_vertical
        self._ocr_cache = None

    def run(self, context: TaskContext,
            on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._use_counts = {}
        self._swipe_vertical = self._do_swipe_vertical  # 允许测试替换
        self._ocr_cache = None

        logger.info("整理背包启动 hwnd=%s", getattr(agent, "hwnd", None))
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 3
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            # 步骤2: Maa「整理背包-过渡」—— Alt+E 打开背包 -> 滑到顶端 -> 点整理
            self._report("打开背包并整理")
            if not self._open_bag(agent):
                self.snapshot.status = TaskStatus.FAILED
                self._report("未能打开背包，请检查窗口状态与模板")
                logger.error("窗口=%s 未能打开背包，任务终止", agent.hwnd)
                return
            self._bag_scroll_to_top(agent)
            self._click_zhengli(agent)
            self.snapshot.completed_steps = 2

            # 步骤3: Maa「点击整理」的 next 列表 —— 使用/清理循环
            self._report("清理背包物品中")
            self._process_loop(agent)

            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            summary = "、".join(f"{k}x{v}" for k, v in self._use_counts.items() if v) or "无物品需要处理"
            self._report(f"整理背包完成（{summary}）")
            logger.info("整理背包完成 hwnd=%s (%s)", agent.hwnd, summary)
        except _Aborted:
            logger.info("整理背包停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("整理背包执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("整理背包执行异常，详见日志")

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

    def _bag_panel_visible(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        return self._match_any(agent, self.T_BAG_PANEL,
                               self._fraction_region(w, h, self.ROI_BAG_PANEL),
                               self.TH_BAG_PANEL) is not None

    # ==================================================================
    # 节点2: 打开背包（Alt+E，失败点包裹图标）+ 滑到顶端 + 点整理
    # ==================================================================
    def _open_bag(self, agent) -> bool:
        """Maa「整理背包-过渡」：ClickKey[57,33] 开背包并等待界面出现。"""
        started = time.monotonic()
        pressed = False
        while time.monotonic() - started < self.node_timeout:
            self._check_stop(agent)
            if self._bag_panel_visible(agent):
                logger.info("窗口=%s 背包界面已打开", agent.hwnd)
                return True
            if not pressed:
                self._press_bag_hotkey(agent)
                pressed = True
                time.sleep(1.0)
                continue
            # [JumpBack]背包界面-按键打开失败-点击图标：模板优先，OCR"包裹"兜底
            if not self._click_bag_icon(agent):
                self._press_bag_hotkey(agent)
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
            pos = self._find_text_in(self._ocr_lines(agent), ("包裹", "包", "裹"), roi)
            if pos:
                m = (pos[0], pos[1], 0.0)
        if not m:
            return False
        logger.info("窗口=%s 点击包裹图标 %s", agent.hwnd, m[:2])
        agent.click(m[0], m[1])
        time.sleep(1.0)
        return True

    def _bag_scroll_to_top(self, agent) -> None:
        """Maa「打开背包成功-向上滑动到顶端」：MultiSwipe x3。"""
        for _ in range(3):
            self._swipe_vertical(agent, self.SWIPE_BAG_X,
                                 self.SWIPE_TOP_FROM, self.SWIPE_TOP_TO)
            time.sleep(0.4)
        self._ocr_cache = None

    def _click_zhengli(self, agent) -> bool:
        """Maa「点击整理」。"""
        return self._click_text_once(agent, ("整理",), self.ROI_ZHENGLI, wait=0.5)

    # ==================================================================
    # 节点3: 使用/清理循环（点击整理 的 next 列表）
    # ==================================================================
    def _process_loop(self, agent) -> None:
        swipes = 0
        while True:
            self._check_stop(agent)

            # 整理完成：beibao_konggezi|beibao_diduan (0.9) -> panduan(结束)
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                if self._match_any(agent, self.T_BAG_BOTTOM,
                                   self._fraction_region(w, h, self.ROI_BAG_BOTTOM),
                                   self.TH_BAG_BOTTOM):
                    logger.info("窗口=%s 整理完成", agent.hwnd)
                    self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "收尾回主界面")
                    return
            # 主界面：背包已关闭 -> 结束
            if self._on_main_interface(agent) and not self._bag_panel_visible(agent):
                logger.info("窗口=%s 已回到主界面，整理结束", agent.hwnd)
                return
            # [JumpBack]关闭整点活动弹窗
            if img is not None:
                h, w = img.shape[:2]
                m = self._match_any(agent, self.T_RENWU_TANCHUANG,
                                    self._fraction_region(w, h, self.ROI_RENWU_TANCHUANG),
                                    self.TH_RENWU_TANCHUANG)
                if m:
                    logger.info("窗口=%s 关闭整点活动弹窗 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    time.sleep(0.5)
                    continue

            # [JumpBack]使用红罗羹 / 绿芦羹
            if self.USE_HONGLUO_GEN and self._use_geng(agent, self.T_HONGLUO, "红罗羹"):
                continue
            if self.USE_LVLU_GEN and self._use_geng(agent, self.T_LVLU, "绿芦羹"):
                continue
            # [JumpBack]使用心魔宝珠
            if self.USE_XINMO and self._use_xinmo(agent):
                continue
            # [JumpBack]合成阵法
            if self.USE_ZHENFAJUAN and self._use_zhenfajuan(agent):
                continue
            # [JumpBack]使用秘境材料
            if self.USE_MIJING and self._use_mijing(agent):
                continue
            # [JumpBack]使用过期物品
            if self.USE_GUOQI and self._use_guoqi(agent):
                continue

            # [JumpBack]背包向上滑动10次
            if swipes < self.bag_swipe_max:
                self._swipe_vertical(agent, self.SWIPE_BAG_X,
                                     self.SWIPE_DOWN_FROM, self.SWIPE_DOWN_TO)
                swipes += 1
                self._ocr_cache = None
                time.sleep(0.5)
                continue
            # [JumpBack]panduan_zhujiemian：翻页尽仍无物品 -> 回主界面结束
            logger.info("窗口=%s 背包翻页 %d 次后无可处理物品，结束", agent.hwnd, swipes)
            self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "收尾回主界面")
            return

    # ------------------------------------------------------------------
    # 各类物品的使用链
    # ------------------------------------------------------------------
    def _item_count(self, key: str) -> int:
        return self._use_counts.get(key, 0)

    def _bump_count(self, key: str) -> None:
        self._use_counts[key] = self._item_count(key) + 1

    def _use_geng(self, agent, templates, label: str) -> bool:
        """Maa「使用红罗羹/绿芦羹」-> 点击更多 -> 点击批量使用 -> 使用。"""
        key = label
        if self._item_count(key) >= self.item_use_max:
            return False
        img = self._image(agent)
        if img is None:
            return False
        m = self._match_any(agent, templates, None, self.TH_ITEM)
        if not m:
            return False
        logger.info("窗口=%s 点击%s(%d/%d) %s", agent.hwnd, label,
                    self._item_count(key) + 1, self.item_use_max, m[:2])
        agent.click(m[0], m[1])
        time.sleep(0.5)
        self._ocr_cache = None
        # 点击更多 -> 点击批量使用 -> 使用
        if self._click_text_once(agent, ("更多",), self.ROI_GENGDUO, wait=0.5):
            if self._click_text_once(agent, ("批量使用",), self.ROI_PLSY, wait=0.5):
                self._click_text_once(agent, ("使用",), self.ROI_SHIYONG_GENG, wait=0.5)
        self._bump_count(key)
        return True

    def _use_xinmo(self, agent) -> bool:
        """Maa「使用心魔宝珠」-> 点击批量使用_心魔宝珠。"""
        if self._item_count("心魔宝珠") >= self.item_use_max:
            return False
        m = self._match_any(agent, self.T_XINMO, None, self.TH_ITEM)
        if not m:
            return False
        logger.info("窗口=%s 点击心魔宝珠(%d/%d) %s", agent.hwnd,
                    self._item_count("心魔宝珠") + 1, self.item_use_max, m[:2])
        agent.click(m[0], m[1])
        time.sleep(0.5)
        self._ocr_cache = None
        self._click_text_once(agent, ("批量使用",), self.ROI_PLSY_XINMO, wait=0.5)
        self._bump_count("心魔宝珠")
        return True

    def _use_zhenfajuan(self, agent) -> bool:
        """Maa「合成阵法」-> 点击阵法使用。"""
        if self._item_count("阵法卷") >= self.item_use_max:
            return False
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        m = self._match_any(agent, self.T_ZHENFAJUAN,
                            self._fraction_region(w, h, self.ROI_BAG_GRID),
                            self.TH_ZHENFAJUAN)
        if not m:
            return False
        logger.info("窗口=%s 点击阵法卷(%d/%d) %s", agent.hwnd,
                    self._item_count("阵法卷") + 1, self.item_use_max, m[:2])
        agent.click(m[0], m[1])
        time.sleep(0.5)
        self._ocr_cache = None
        self._click_text_once(agent, ("使用",), self.ROI_SHIYONG_ZHENFA, wait=0.5)
        self._bump_count("阵法卷")
        return True

    def _use_mijing(self, agent) -> bool:
        """Maa「使用秘境材料」-> 秘境材料-收入。"""
        if self._item_count("秘境材料") >= self.item_use_max:
            return False
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        m = self._match_any(agent, self.T_MIJING,
                            self._fraction_region(w, h, self.ROI_BAG_GRID),
                            self.TH_MIJING)
        if not m:
            return False
        logger.info("窗口=%s 点击秘境材料(%d/%d) %s", agent.hwnd,
                    self._item_count("秘境材料") + 1, self.item_use_max, m[:2])
        agent.click(m[0], m[1])
        time.sleep(1.0)
        self._ocr_cache = None
        self._click_text_once(agent, ("收入",), self.ROI_SHOURU, wait=1.0)
        self._bump_count("秘境材料")
        return True

    def _use_guoqi(self, agent) -> bool:
        """Maa「使用过期物品」：guoqi 模板 -> 连点2次(repeat 2, repeat_delay 110)。"""
        if self._item_count("过期物品") >= self.item_use_max:
            return False
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        m = self._match_any(agent, self.T_GUOQI,
                            self._fraction_region(w, h, self.ROI_BAG_GRID),
                            self.TH_ITEM)
        if not m:
            return False
        logger.info("窗口=%s 点击过期物品x2(%d/%d) %s", agent.hwnd,
                    self._item_count("过期物品") + 1, self.item_use_max, m[:2])
        agent.click(m[0], m[1])
        time.sleep(0.11)
        agent.click(m[0], m[1])
        time.sleep(0.5)
        self._ocr_cache = None
        self._bump_count("过期物品")
        return True

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

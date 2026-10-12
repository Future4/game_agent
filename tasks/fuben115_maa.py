# -*- coding: utf-8 -*-
"""副本520(89/115) —— 按 Maa_MHXY 的 fuben115.json 流水线原样移植到 game_agent。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/fuben115.json
    (+ 共享节点与 fuben69 一致: panduan_zhujiemian(_ks) / 打开大地图_69副本 /
       小地图-按键打开失败-点击小地图图标 / 再次点击地图百晓仙子 / 识别拓印_停止 /
       战斗中-等待10秒 / 推荐好友信息 / 关闭福利弹窗 / 关闭师门弹窗 / 关闭任务界面 /
       捉鬼-fuben桥接 等; 副本监控循环/弹窗组/捉鬼桥接的实现直接复用 tasks/fuben69_maa.py)

======================= Maa 原始流程(节点图) =======================
fuben115 -> 115识别位置-长安城-副本-过渡(主界面 +/称号)
  手动接取(默认) 过渡 next: 已经在70级侠士副本-过渡(And 因缘绘 + 桃花定情/流沙净/
      万丈山/踏西行/明珠还.*侠士 -> 直接进70侠士监控) | 115识别位置-长安城-副本 |
      panduan_ks | 打开大地图_69副本
  手动接取(默认) 副本 next: 115返回长安城 -> 百晓仙子 -> 选择副本 -> 侠士副本2
      -> 115进入70级侠士副本(右侧进入按钮)
  全自动:          副本 next: 115打开小地图_百晓仙子 -> 侠士副本1 -> 进入50级侠士副本
      (仅进队不接续打) -> 115返回长安城 -> 70侠士 ...
  只打普通三本及20鬼: 副本 next: 115打开小地图-百晓仙子-50普通-1 -> 普通1 ...

115进入70级侠士副本-成功(OCR 因缘绘) -> 副本监控循环(与 fuben69 相同):
    副本已完成退出 / 跳过剧情动画 / 战斗10秒 / 点击副本-开始战斗 / 快进键 /
    推荐好友信息 / 福利弹窗 / 师门弹窗 / 任务栏切换 / 关闭任务界面 / 拓印停止
  -> 115-70级副本完成-退出 -> 百晓仙子 -> 侠士副本 -> 进入50级侠士副本(第二次进入)
  -> 50侠士监控 -> 50普通-1 -> 50普通-2 -> 70普通-3(第三个进入按钮)
  -> 115-50普通-3-副本完成-退出 -> [JumpBack]捉鬼-fuben桥接 -> 捉鬼流程 | panduan

======================= Maa 任务选项映射（「全自动/手动接取双侠士任务选项」）=======================
  - 手动接取(默认):      MODE="manual"  70侠士 -> 50侠士(二进) -> 普通1/2/3 -> 捉鬼2轮
  - 全自动:             MODE="auto"    先自动进50侠士(仅进队) -> 同 manual 后续
  - 只打普通三本及20鬼:  MODE="putong3" 普通1/2/3 -> 捉鬼2轮
  捉鬼轮数对应 GUI_ROUNDS(默认 2, 即 Maa「抓鬼轮次输入2」默认值; 三种模式 override 一致:
  关闭人员检测 + 轮次达标结束)

======================= 移植适配说明 =======================
官网 PC 客户端(Unity) 与 Maa 的模拟器(1280x720) 不同:
  1. 布局非等比, roi 由 Maa 像素坐标换算为窗口比例并适当放大, 模板匹配用多尺度。
  2. 进入按钮位置: 50侠士/50普通-1 [316,570,...], 70侠士/50普通-2 [602,570,...],
     70普通-3 [889,569,...], 均按比例换算并放大。
  3. 侠士本成功判定用 OCR 因缘绘; 普通本用「选择副本/进入 消失」间接判定(同 fuben69)。
  4. regex(桃花定情.*侠士 等)按 名称包含+"侠士" 近似。
"""

import logging
import time
from typing import Callable, Optional

from domain.tasks import TaskContext, TaskDefinition, TaskStatus
from tasks.fuben69_maa import Fuben69MaaTask, _Aborted

logger = logging.getLogger(__name__)


class Fuben115MaaTask(Fuben69MaaTask):
    definition = TaskDefinition(
        "fuben115_maa", "副本520(89/115)", "移植自 Maa_MHXY 的 fuben115 流水线"
    )

    # ---------------- 任务选项（对应 Maa 选项「全自动/手动接取双侠士任务选项」）----------------
    MODE = "manual"              # "manual"(手动接取,默认) / "auto"(全自动) / "putong3"(只打普通三本)
    GUI_ROUNDS = 2               # 捉鬼轮数（Maa「抓鬼轮次输入2」默认 2）

    # 进入按钮 roi（比例）: 70普通-3 [889,569,146,51] 放大
    ROI_ENTER_PUTONG3 = (0.60, 0.72, 0.26, 0.18)

    # Maa「已经在70级侠士副本-过渡」的 70 侠士副本名（regex 前缀）
    XIASHI70_NAMES = ("桃花定情", "流沙净", "万丈山", "踏西行", "明珠还")

    # 每个副本的进入参数: (进入按钮roi, 是否侠士本)
    _FB_CONF = {
        "xiashi50_first": ("ROI_ENTER_XIASHI", True),   # 全自动: 第一次进50侠士(仅进队)
        "xiashi50": ("ROI_ENTER_XIASHI", True),
        "xiashi70": ("ROI_ENTER_PUTONG2", True),
        "putong1": ("ROI_ENTER_XIASHI", False),
        "putong2": ("ROI_ENTER_PUTONG2", False),
        "putong3": ("ROI_ENTER_PUTONG3", False),
    }
    _FB_LABEL = {
        "xiashi50_first": "50级侠士(仅进队)",
        "xiashi50": "50级侠士(第二次进入)",
        "xiashi70": "70级侠士",
        "putong1": "50普通-1",
        "putong2": "50普通-2",
        "putong3": "70普通-3",
    }

    # ==================================================================
    # 主流程
    # ==================================================================
    def run(self, context: TaskContext,
            on_update: Optional[Callable] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._ocr_cache = None

        mode_label = {"manual": "手动接取", "auto": "全自动", "putong3": "只打普通三本"}[self.MODE]
        logger.info("副本520(89/115)启动 hwnd=%s (模式=%s, 捉鬼轮数=%d)",
                    getattr(agent, "hwnd", None), mode_label, self.GUI_ROUNDS)
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 4
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            # Maa 手动接取: 「已经在70级侠士副本-过渡」—— 已在70侠士里就直接开打
            seq = self._mode_sequence()
            if self.MODE == "manual" and self._already_in_xiashi70(agent):
                logger.info("窗口=%s 检测到已在70级侠士副本中，直接进入监控", agent.hwnd)
                self._report("70级侠士副本进行中")
                result = self._fuben_monitor(agent)
                if result == "tayin":
                    return self._end_tayin(agent)
                seq = [fb for fb in seq if fb != "xiashi70"]

            if seq:
                # 步骤2: Maa「115识别位置-长安城-副本-过渡」—— 回长安(必要时大地图传送)
                self._stage(agent, 2, "回到长安城", self._node_back_to_changan)

            # 步骤3: 依次进入各副本并监控
            for fb in seq:
                label = self._FB_LABEL[fb]
                join_only = (fb == "xiashi50_first")
                if not self._stage(agent, 3, f"进入副本({label})",
                                   lambda a, f=fb: self._node_enter_fuben115(a, f)):
                    self.snapshot.status = TaskStatus.FAILED
                    self._report(f"未能进入副本({label})，请检查窗口状态与模板")
                    logger.error("窗口=%s 未能进入副本 %s", agent.hwnd, fb)
                    return
                if join_only:
                    # 全自动的第一步: 进入50侠士仅完成进队; Maa「115返回长安城」
                    # (副本内 OCR 不到长安城 -> [JumpBack]打开大地图_69副本 传送回去)
                    logger.info("窗口=%s 已进入50级侠士副本(仅进队), 传送回长安城进70侠士", agent.hwnd)
                    self._open_map_and_teleport(agent)
                    self._stage(agent, 3, "返回长安城", self._node_back_to_changan)
                    continue
                self._report(f"副本({label})进行中")
                result = self._fuben_monitor(agent)
                if result == "tayin":
                    return self._end_tayin(agent)

            # 步骤4: [JumpBack]捉鬼-fuben桥接 -> 捉鬼流程(关闭人员检测 + N 轮)
            self._report("开始捉鬼(桥接)")
            self._run_zhuogui_bridge(agent)

            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            self._report("副本520(89/115)完成")
            logger.info("副本520(89/115)完成 hwnd=%s", agent.hwnd)
        except _Aborted:
            logger.info("副本520(89/115)停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("副本520(89/115)执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("副本520(89/115)执行异常，详见日志")

    def _end_tayin(self, agent) -> None:
        self.snapshot.completed_steps = self.snapshot.total_steps
        self.snapshot.status = TaskStatus.COMPLETED
        self._report("遇见拓印，按 Maa 语义停止任务")

    def _mode_sequence(self) -> list:
        if self.MODE == "auto":
            return ["xiashi50_first", "xiashi70", "xiashi50", "putong1", "putong2", "putong3"]
        if self.MODE == "putong3":
            return ["putong1", "putong2", "putong3"]
        return ["xiashi70", "xiashi50", "putong1", "putong2", "putong3"]  # manual(默认)

    def _already_in_xiashi70(self, agent) -> bool:
        """Maa「已经在70级侠士副本-过渡」= And(OCR 因缘绘, OCR 70侠士副本名.*侠士)。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if not self._find_text_in(self._ocr_lines(agent), ("因缘绘",),
                                  self._fraction_region(w, h, self.ROI_YINYUANHUI)):
            return False
        roi = self._fraction_region(w, h, self.ROI_XIASHI_OCR)
        x, y, rw, rh = roi
        for item in self._ocr_lines(agent):
            text = (item.get("text") or "").strip()
            cx, cy = item["center"]
            if not (x <= cx <= x + rw and y <= cy <= y + rh):
                continue
            if "侠士" in text and any(n in text for n in self.XIASHI70_NAMES):
                return True
        return False

    # ==================================================================
    # 覆盖: 回长安（去掉 fuben69 的"在侠士副本里先 ESC"分支 ——
    # 手动接取模式下 70 侠士本正是要打的, 不能 ESC 出去）
    # ==================================================================
    def _node_back_to_changan(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        # 115识别位置-长安城-副本：OCR 长安城
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

    # ==================================================================
    # 进入副本（百晓仙子 -> 选择副本 -> (侠士副本) -> 进入 -> 成功判定）
    # ==================================================================
    def _node_enter_fuben115(self, agent, fb: str) -> bool:
        roi_attr, is_xiashi = self._FB_CONF[fb]
        enter_roi = getattr(self, roi_attr)
        label = self._FB_LABEL[fb]

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
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                # [JumpBack]再次点击地图百晓仙子
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

        # ---- 选择副本 -> (侠士副本) -> 进入 ----
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
                    stage = "xiashi" if is_xiashi else "enter"
                    continue
            elif stage == "xiashi":
                if self._click_text_once(agent, ("侠士副本",), self.ROI_XIASHI_FUBEN, wait=0.5):
                    stage = "enter"
                    continue
            else:
                img = self._image(agent)
                if img is not None:
                    h, w = img.shape[:2]
                    # [JumpBack]115进入侠士副本-等待队员同意
                    if self._find_text_in(self._ocr_lines(agent), ("正在等待其他玩家准备",),
                                          self._fraction_region(w, h, self.ROI_WAIT_TEAM)):
                        logger.info("窗口=%s 等待队员同意中", agent.hwnd)
                        if self._sleep(4.0):
                            raise _Aborted()
                        continue
                    # 成功判定：侠士本用 OCR 因缘绘; 普通本用「选择副本/进入 消失」
                    if is_xiashi and self._find_text_in(
                            self._ocr_lines(agent), ("因缘绘",),
                            self._fraction_region(w, h, self.ROI_YINYUANHUI)):
                        logger.info("窗口=%s 进入%s成功", agent.hwnd, label)
                        return True
                    if not is_xiashi and not self._find_text_in(
                            self._ocr_lines(agent), ("选择副本",),
                            self._fraction_region(w, h, self.ROI_XUANZE_FUBEN)):
                        if not self._find_text_in(self._ocr_lines(agent), ("进入",),
                                                  self._fraction_region(w, h, enter_roi),
                                                  exact=True):
                            logger.info("窗口=%s 进入%s成功", agent.hwnd, label)
                            return True
                # 进入（失败-再次进入 max_hit 2）
                if enter_retries <= self.enter_retry_max:
                    if self._click_text_once(agent, ("进入",), enter_roi, wait=1.0, exact=True):
                        enter_retries += 1
                        continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 进入副本(%s)超时", agent.hwnd, label)
        return False

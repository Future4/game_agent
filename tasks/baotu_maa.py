# -*- coding: utf-8 -*-
"""宝图任务(获得) —— 按 Maa_MHXY 的 baotu_renwu.json 流水线原样移植到 game_agent。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/baotu_renwu.json
    (+ 共享节点: zhuoguirenwu.json「展开-首页任务栏」「任务栏切换为任务」
       my_task.json「panduan_zhujiemian」「战斗中-等待N秒」)

======================= Maa 原始流程(节点图) =======================
baotu_renwu
  next:
    [JumpBack]展开-首页任务栏        任务栏收起 -> 点开
    [JumpBack]任务栏切换为任务        切到「任务」页
    [JumpBack]baotu_huadong_down     任务栏列表向下滑(手指下滑 234->419, max_hit 1)
    已领取宝图任务                   任务栏已有"宝图任务" -> 点它, 进入完成循环
    主界面-宝图任务                 在主界面(右下角 +/称号/包裹) -> ClickKey[57,31](Alt+C)开活动
    [JumpBack]panduan_zhujiemian    不在主界面 -> ESC 返回

主界面-宝图任务 next: 活动-宝图任务(huodong_jiemian_panduan 面板判断)
    | [JumpBack]活动-界面-打开失败-点击活动图片 | [JumpBack]战斗平衡弹窗-点击关闭
活动-宝图任务 -> 点击日常活动 -> 向上滑动到顶端(MultiSwipe x2)
    -> 活动-宝图任务-已完成(0.9, green_mask, 跳回主界面)
    | 活动-宝图任务-开始(baotu1|2|3, 0.9) -> 开始-点击参加(OCR"参加")
    | [JumpBack]baotu_huodong_down(活动列表下滑, max_hit 6)
点击参加 -> click_baotu_ttwf (OCR"听听无妨")
    -> 循环{ 识别拓印_停止 / 九转天阶遮挡(ESC) / 九幽遮挡 / 战斗平衡弹窗 /
            战斗中-等待5秒(zhandou/zidong|quxiao) / 宝图完成判断 /
            宝图-间隔30秒-最大10分钟(20次) / 宝图任务单次点击 }
宝图完成判断 = inverse Or( OCR"宝图任务|贼王"(任务栏),
    zhandou/zidong|quxiao(0.9, 右下战斗按钮区 [1175,549,103,159]),
    zonghe/zidongxunlu1-4(0.9, 自动寻路 [257,133,770,461]),
    zhandou/zhandou1-3(0.9, 顶部战斗图标 [568,0,140,101]) ) -> panduan_zhujiemian

======================= 移植适配说明 =======================
官网 PC 客户端(Unity, 本机 832x624, 4:3) 与 Maa 的模拟器(1280x720, 16:9) 不同:
  1. 布局非等比, roi 改为「窗口相对区域 + 多尺度模板匹配」, Click 改为前台真实鼠标。
  2. ClickKey[57,31] = Alt+C 开活动面板(win32 keybd_event), 失败回退点活动图片。
  3. 战斗判断与 Maa 一致优先用模板: zhandou/zidong|quxiao(右下) 与 zhandou/zhandou1-3(顶部),
     阈值 0.9; 模板都匹配不上时回退本机已验证的「顶部圆形一致性(HoughCircles)」方案。
  4. 自动寻路判断与 Maa 一致: zonghe/zidongxunlu1-4, 阈值 0.9。
  5. 文本类节点 OCR 优先, 匹配不上回退本机针对官网客户端采集的平铺模板。

滑动方向约定(与手指方向一致, 内容跟随手指), 严格按 Maa 原坐标换算:
  - 任务栏 baotu_huadong_down        : 手指下滑 234->419 (max_hit 1)
  - 活动列表 向上滑动到顶端           : 手指下滑 129->444 (MultiSwipe x2)
  - 活动列表 baotu_huodong_down 翻页  : 手指上滑 380->250 (max_hit 6)
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


class BaotuMaaTask(AutomationTask):
    definition = TaskDefinition(
        "baotu_maa", "宝图任务(获得)", "移植自 Maa_MHXY 的 baotu_renwu 流水线"
    )

    # ---------------- 时序参数（对应 Maa 流水线字段）----------------
    poll_interval = 0.5
    node_timeout = 90.0          # 单节点等待上限(秒)
    retry_interval = 30.0        # Maa: 宝图-间隔30秒-最大10分钟
    retry_max = 20               # Maa: max_hit 20  (20 × 30s ≈ 10 分钟)
    battle_wait = 5.0            # Maa: 战斗中-等待5秒
    total_timeout = 1500.0       # 整个任务上限

    # ---------------- 可调开关 ----------------
    ENABLE_TASK_BAR_FLOW = True  # 是否走 Maa 的"任务栏优先"分支
    TASKBAR_SWIPE_DOWN = True    # Maa baotu_huadong_down：任务栏列表向下滑一次
    TASKBAR_EXPAND_CLICK = True  # Maa「展开-首页任务栏」：仅在找不到宝图任务时才点
    ocr_cache_seconds = 2.0      # OCR 整图识别结果缓存时长(秒)，避免轮询时重复识别
    finish_confirm_hits = 3      # 连续 N 次都看不到"宝图任务/寻路/战斗"才判定完成

    # ---------------- 阈值（官网客户端实测校准）----------------
    TH_MAIN_INDICATOR = 0.75
    TH_ACTIVITY_PANEL = 0.75
    TH_ACTIVITY_BUTTON = 0.60
    TH_DAILY_ACTIVITY = 0.60
    TH_TREASURE_START = 0.80         # 本机 treasure_row 实测模板
    TH_TREASURE_START_MAA = 0.90     # Maa「活动-宝图任务-开始」threshold 0.9 (baotu1|2|3)
    TH_TREASURE_COMPLETED = 0.90     # Maa「活动-宝图任务-已完成」threshold 0.9
    TH_TREASURE_OBTAINED = 0.70
    TH_DIALOGUE = 0.86   # baotu_dialogue 在主界面会误命中 0.83，抬高避免误点
    TH_POPUP_CLOSE = 0.88
    TH_JIUYOU = 0.80
    TH_AUTOPATH = 0.90               # Maa「宝图完成判断」自动寻路 threshold 0.9
    TH_BATTLE = 0.90                 # Maa 战斗按钮/战斗图标 threshold 0.9
    TH_TASKBAR_TAB = 0.80
    TH_TRACKED_TEMPLATE = 0.80
    TH_TAYIN = 0.90                  # Maa 识别拓印-子2/子3 threshold 0.9
    TH_TAYIN_CLOSE = 0.80

    # ---------------- 模板名（templates/ 目录，不带 .png）----------------
    # 命名与 Maa_MHXY-main/assets/resource/base/image 完全一致（保留子目录/相对路径），
    # 可与 pipeline JSON 的 "template": ["zonghe/jiahao.png", ...] 直接对应。
    # 官网 PC 客户端与模拟器渲染不同：Maa 模板能匹配的优先命中，匹配不上的回退到
    # 本机针对官网客户端采集的平铺模板（activity_button / daily_activity / treasure_* 等）。
    #
    # Maa「panduan_zhujiemian」: zonghe/jiahao|chenghao|baoguo|baoguo_man
    T_MAIN_INDICATORS = ("zonghe/jiahao", "zonghe/baoguo", "zonghe/baoguo_man", "zonghe/chenghao")
    # Maa「展开-首页任务栏」
    T_TASKBAR_COLLAPSED = ("zonghe/rwl_suojin", "zonghe/rwl_suojin2")
    # Maa「活动-宝图任务」活动界面判断
    T_ACTIVITY_PANEL = ("zonghe/huodong_jiemian_panduan",)
    # 活动入口：Maa「活动-界面-打开失败-点击活动图片」优先（官网实测 0.91/0.95），
    # 再回退本机采集的 activity_button
    T_ACTIVITY_BUTTON = ("zonghe/huodong1", "zonghe/huodong2", "activity_button")
    # Maa 用 OCR 认"日常活动"；本机用实测模板
    T_DAILY_ACTIVITY = "daily_activity"
    # Maa「活动-宝图任务-开始」: baotu/baotu1|2|3 (0.9) + 本机实测整行模板
    T_TREASURE_START_MAA = ("baotu/baotu1", "baotu/baotu2", "baotu/baotu3")
    T_TREASURE_START_LOCAL = ("treasure_row",)
    # Maa「活动-宝图任务-已完成」: baotu/hd_baotu_wancheng|2 + 本机实测模板
    T_TREASURE_COMPLETED = ("baotu/hd_baotu_wancheng", "baotu/hd_baotu_wancheng2", "treasure_completed")
    # Maa 用 OCR 认藏宝图获得提示；本机用实测模板
    T_TREASURE_OBTAINED = "treasure_obtained"
    # Maa 用 OCR 认"听听无妨"；本机用实测模板
    T_DIALOGUE = "baotu_dialogue"
    # Maa「战斗平衡弹窗-点击关闭」
    T_POPUP_CLOSE = ("zonghe/zhandoupingheng_guanbi1",)
    # Maa「师门完成-九幽遮挡」
    T_JIUYOU = ("zonghe/jiuyoudiyu", "zonghe/jiuyoudiyu2")
    # Maa「识别拓印_停止」/「关闭拓印界面」
    T_TAYIN = ("tayin/tayin", "tayin/tayin2")
    T_TAYIN_CLOSE = ("zonghe/guanbi6", "zonghe/guanbi7")
    # Maa「宝图完成判断」自动寻路
    T_AUTOPATH = ("zonghe/zidongxunlu1", "zonghe/zidongxunlu2", "zonghe/zidongxunlu3", "zonghe/zidongxunlu4")
    # Maa「宝图完成判断」/「战斗中-等待5秒」的战斗按钮与战斗图标
    T_BATTLE_BTN = ("zhandou/zidong", "zhandou/quxiao")
    T_BATTLE_ICON = ("zhandou/zhandou1", "zhandou/zhandou2", "zhandou/zhandou3")
    # 可选兜底：任务栏里"宝图任务"条目的图片。
    # Maa 的「已领取宝图任务」「宝图任务单次点击」两个节点用的是 OCR（项目里没有对应图片），
    # 所以这两个名字不是 Maa 模板，只是预留位：若你采集了任务栏"宝图任务"截图，
    # 存为 templates/taskbar_baotu.png 即可自动生效（不存在时静默跳过）。
    T_TRACKED_BAOTU_FALLBACK = ("taskbar_baotu", "taskbar_baotu_task")

    # 参加按钮在 treasure_row(294x76) 模板内相对中心的像素偏移
    JOIN_BTN_OFFSET_X = 105

    # ---------------- 区域比例（窗口尺寸的百分比）----------------
    ROI_MAIN_INDICATOR = (0.86, 0.72, 0.14, 0.28)   # 右下角 +/称号/包裹
    ROI_TASKBAR_TAB = (0.86, 0.08, 0.14, 0.22)      # 任务栏收起图标(右上)
    # 任务栏文本区：官网客户端任务栏在右侧，实测"宝图任务"框 x610..726 y133..149，
    # 比 Maa 模拟器的 roi 更靠左，这里放大以免漏检
    ROI_TASKBAR_TEXT = (0.68, 0.10, 0.32, 0.62)
    ROI_ACTIVITY_PANEL = (0.20, 0.00, 0.62, 0.14)   # Maa [350,23,600,62] 放大
    ROI_ACTIVITY_BUTTON = (0.00, 0.00, 0.45, 0.30)  # 左上角活动入口
    ROI_DAILY_LEFT = (0.00, 0.00, 0.35, 0.55)       # 活动面板左侧导航
    ROI_LIST = (0.12, 0.08, 0.85, 0.70)             # 活动列表主区域
    ROI_LIST_COMPLETED = (0.20, 0.10, 0.72, 0.60)
    ROI_DIALOGUE = (0.60, 0.15, 0.35, 0.60)         # Maa 听听无妨 roi 换算
    ROI_AUTOPATH = (0.20, 0.18, 0.60, 0.64)         # Maa [257,133,770,461]
    # Maa「战斗中-等待5秒」/「宝图完成判断」战斗按钮区 [1175,549,103,159]
    ROI_BATTLE_BTN = (0.88, 0.70, 0.12, 0.28)
    # Maa「宝图完成判断」顶部战斗图标 [568,0,140,101]
    ROI_BATTLE_ICON = (0.38, 0.00, 0.24, 0.20)
    # Maa「师门完成-九转天阶遮挡」[293,47,834,260]
    ROI_JIUZHUAN = (0.18, 0.04, 0.70, 0.44)
    # Maa「师门完成-九幽遮挡」[1085,128,64,71]
    ROI_JIUYOU = (0.76, 0.10, 0.24, 0.22)
    # Maa「识别拓印_停止」/「关闭拓印界面」
    ROI_TAYIN_OCR = (0.15, 0.18, 0.20, 0.25)
    ROI_TAYIN_TPL1 = (0.14, 0.16, 0.22, 0.36)
    ROI_TAYIN_TPL2 = (0.10, 0.45, 0.32, 0.48)
    ROI_TAYIN_CLOSE = (0.62, 0.00, 0.36, 0.26)

    # Maa「任务栏切换为任务」：任务栏顶部页签区。
    # 官网客户端实测页签为：[任务] center(710,100) box(689,93,42,15) / [队伍] center(808,99)，
    # 即页签带位于 y≈92..108，故 y 取 0.12..0.19（下游"宝图任务"条目在 y=140，不会误入）
    ROI_TASKBAR_TABS = (0.80, 0.12, 0.20, 0.07)
    # Maa 原节点用 ColorMatch(roi 35x35, count 950) 判定任务页；官网客户端配色/坐标未标定，
    # 默认关闭，标定后再打开（打开前请先用 _diag_ocr.py 确认页签位置与颜色）
    ENABLE_TASK_TAB_COLORMATCH = False
    COLORMATCH_TAB_ROI = (0.79, 0.14, 0.07, 0.09)
    COLORMATCH_TAB_LOWER = (28, 31, 22)
    COLORMATCH_TAB_UPPER = (177, 175, 145)
    COLORMATCH_TAB_COUNT = 950
    # 若已知「任务」页签的固定相对位置(比例坐标, 如 (0.75, 0.19))，可填在这里作为
    # OCR 之外的兜底：只有在你确认该位置确实是「任务」页签时才填写，否则保持 None
    TASK_TAB_FIXED_POS = None

    # 滑动坐标（比例，严格按 Maa 1280x720 坐标换算）
    SWIPE_TASKBAR_X = 0.895         # Maa baotu_huadong_down x=1145~1149/1280
    SWIPE_TASKBAR_FROM = 0.325      # 手指下滑 234 -> 419
    SWIPE_TASKBAR_TO = 0.582
    SWIPE_LIST_X = 0.571            # Maa x=731~735/1280
    SWIPE_LIST_TOP_FROM = 0.179     # 滑到顶端：手指下滑 129 -> 444 (MultiSwipe x2)
    SWIPE_LIST_TOP_TO = 0.617
    SWIPE_LIST_DOWN_FROM = 0.528    # Maa baotu_huodong_down(活动列表翻页)：手指上滑 380 -> 250
    SWIPE_LIST_DOWN_TO = 0.347
    LIST_SWIPE_MAX = 6              # Maa baotu_huodong_down max_hit 6

    # ==================================================================
    # 主流程
    # ==================================================================
    def __init__(self) -> None:
        super().__init__()
        # 运行状态在 __init__ 里给默认值，保证节点方法可被单独调用/验证
        self._on_update = None
        self._deadline = time.monotonic() + self.total_timeout
        self._treasure_count = 0
        self._reward_visible = False
        self._esc_presses = 0
        self._retry_hits = 0
        self._alt_c_pressed = False
        self._list_swipes = 0
        self._swipe_vertical = self._do_swipe_vertical
        self._ocr_cache = None
        self._finished_hits = 0

    def run(self, context: TaskContext,
            on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._treasure_count = 0
        self._reward_visible = False
        self._esc_presses = 0
        self._retry_hits = 0
        self._alt_c_pressed = False
        self._list_swipes = 0
        self._swipe_vertical = self._do_swipe_vertical  # 允许测试替换
        self._ocr_cache = None
        self._finished_hits = 0

        logger.info("宝图任务(获得)启动 hwnd=%s", getattr(agent, "hwnd", None))
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 6
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            already_tracked = False
            if self.ENABLE_TASK_BAR_FLOW:
                # 步骤2: Maa 任务栏分支（展开 -> 切任务页 -> 下滑 -> 是否已领取）
                self._report("检查任务栏是否已领取宝图任务")
                already_tracked = self._task_bar_flow(agent)
            self.snapshot.completed_steps = 2

            if already_tracked:
                # Maa「已领取宝图任务」：直接点任务栏里的宝图任务，进入完成循环
                logger.info("窗口=%s 任务栏已存在宝图任务，直接点击继续", agent.hwnd)
                self._node_tracked_click(agent)
            else:
                # 步骤3: Maa「主界面-宝图任务」Alt+C 开活动 +「活动-宝图任务」面板判断
                #        + 点击日常活动 + 滑到顶端 + (下滑翻页max6)找宝图行
                ok_open = self._stage(agent, 3, "打开活动并找到宝图任务",
                                      self._node_open_activity_daily_find)
                row = self._find_treasure_row(agent) if ok_open else None
                if row == "completed":
                    # Maa「活动-宝图任务-已完成」-> panduan_zhujiemian
                    self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "收尾回主界面")
                    self._finish("检测到宝图任务已完成(10/10)，无需执行")
                    return
                # 步骤4: Maa「活动-宝图任务-开始」+「开始-点击参加」
                ok_join = row == "found" and self._stage(agent, 4, "点击宝图任务参加", self._node_join)
                if ok_join:
                    # 步骤5: Maa「click_baotu_ttwf」点击"听听无妨"
                    self._stage(agent, 5, "选择听听无妨", self._node_listen)
                elif not ok_open:
                    # 活动面板都没打开 -> 直接失败，避免白等 10 分钟
                    self.snapshot.status = TaskStatus.FAILED
                    self._report("未能打开活动界面/找到宝图任务，请检查窗口状态与模板")
                    logger.error("窗口=%s 未能打开活动界面，任务未开始", agent.hwnd)
                    return
                else:
                    # 面板已打开但没有“参加”按钮 -> 按 Maa 语义视为任务已在进行中
                    logger.warning("窗口=%s 活动面板已打开但未找到“参加”按钮，"
                                   "按 Maa 语义视为宝图任务已在进行，直接进入完成循环", agent.hwnd)

            # 步骤6: Maa 完成循环（拓印/遮挡/战斗/30秒重试/完成判断）
            self._report("等待宝图任务自动执行结束")
            result = self._completion_loop(agent)

            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            if result == "tayin":
                self._report("遇见拓印，按 Maa 语义停止任务")
            else:
                self._report("宝图任务(获得)完成")
            logger.info("宝图任务(获得)结束(%s) hwnd=%s", result, agent.hwnd)
        except _Aborted:
            logger.info("宝图任务停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("宝图任务执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("宝图任务执行异常，详见日志")

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
    # 节点2: 任务栏分支（展开 / 切任务页 / 下滑 / 已领取宝图任务）
    # ==================================================================
    def _task_bar_flow(self, agent) -> bool:
        """返回 True 表示任务栏里已有"宝图任务"。

        与 Maa 的执行顺序略有调整：Maa 先点「展开-首页任务栏」，但官网客户端的任务栏
        通常本来就是展开的，那个开关点下去反而可能把任务栏收起、导致"宝图任务"看不见。
        因此这里改为 **先直接找"宝图任务"**，只有找不到时才尝试展开/下滑，然后重试。
        """
        # 1) 先直接找（任务栏多半已经展开、且停在「任务」页）
        pos = self._find_tracked_baotu(agent)
        if pos:
            logger.info("窗口=%s 任务栏检测到已领取的宝图任务 %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
            time.sleep(1.0)
            return True

        # 2) Maa「展开-首页任务栏」：找不到才尝试展开
        if self.TASKBAR_EXPAND_CLICK:
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                roi = self._fraction_region(w, h, self.ROI_TASKBAR_TAB)
                m = self._match_any(agent, self.T_TASKBAR_COLLAPSED, roi, self.TH_TASKBAR_TAB)
                if m:
                    logger.info("窗口=%s 未发现宝图任务，尝试展开任务栏 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    time.sleep(0.8)

        # 3) Maa「任务栏切换为任务」：把任务栏切到"任务"页
        self._node_switch_task_tab(agent)
        pos = self._find_tracked_baotu(agent)
        if pos:
            logger.info("窗口=%s 切到「任务」页后检测到宝图任务 %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
            time.sleep(1.0)
            return True

        # 4) Maa「baotu_huadong_down」：任务栏列表向下滑一次，再找
        if self.TASKBAR_SWIPE_DOWN:
            self._swipe_vertical(agent, self.SWIPE_TASKBAR_X,
                                 self.SWIPE_TASKBAR_FROM, self.SWIPE_TASKBAR_TO)
            self._ocr_cache = None
            pos = self._find_tracked_baotu(agent)
            if pos:
                logger.info("窗口=%s 任务栏下滑后检测到宝图任务 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(1.0)
                return True

        logger.info("窗口=%s 任务栏未发现宝图任务，改走活动界面流程", agent.hwnd)
        return False

    def _node_switch_task_tab(self, agent) -> bool:
        """Maa「任务栏切换为任务」：确保右侧任务栏停在「任务」页。

        Maa 用 ColorMatch(roi 35x35, count 950) 判定"任务页签图标点亮"，命中就点
        target(101x50) —— 属于幂等操作。官网客户端坐标系/配色与模拟器不同，这里：
          1) 优先 OCR：在任务栏顶部页签区找**恰好是**"任务"的文字并点击
             （必须精确匹配，避免命中"宝图任务/师门任务"这类任务条目）；
          2) 可选 ColorMatch 兜底（ENABLE_TASK_TAB_COLORMATCH，默认关，需标定）；
          3) 都判不出就记日志跳过（对应 Maa [JumpBack] 的"不命中就跳过"语义），
             **绝不盲点**，避免误切到"活动/副本"页反而把宝图任务藏起来。
        """
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_TASKBAR_TABS)
        pos = self._find_task_tab(self._ocr_lines(agent), roi)
        if pos:
            logger.info("窗口=%s 点击任务栏「任务」页签 %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
            time.sleep(0.8)
            self._ocr_cache = None
            return True

        if self.ENABLE_TASK_TAB_COLORMATCH:
            cm_roi = self._fraction_region(w, h, self.COLORMATCH_TAB_ROI)
            if self._colormatch(img, cm_roi, self.COLORMATCH_TAB_LOWER,
                                self.COLORMATCH_TAB_UPPER, self.COLORMATCH_TAB_COUNT):
                cx, cy = cm_roi[0] + cm_roi[2] // 2, cm_roi[1] + cm_roi[3] // 2
                logger.info("窗口=%s ColorMatch 命中，点击「任务」页签 %s", agent.hwnd, (cx, cy))
                agent.click(cx, cy)
                time.sleep(0.8)
                self._ocr_cache = None
                return True

        if self.TASK_TAB_FIXED_POS is not None:
            fx, fy = self.TASK_TAB_FIXED_POS
            cx, cy = int(w * fx), int(h * fy)
            logger.info("窗口=%s 使用固定位置点击「任务」页签 %s", agent.hwnd, (cx, cy))
            agent.click(cx, cy)
            time.sleep(0.8)
            self._ocr_cache = None
            return True

        logger.info("窗口=%s 未定位到「任务」页签（当前多半已在任务页），跳过切换", agent.hwnd)
        return False

    def _find_task_tab(self, lines, region: Region) -> Optional[Tuple[int, int]]:
        """在任务栏页签区定位「任务」页签。

        游戏内的页签文字 OCR 很不稳定：实测「任务」被读成「彐干务」，
        所以不能只做精确匹配。策略：页签区里文字较短(<=4字)的候选行，
        - 优先取含"务"的（"任务"/"彐干务"/"仸务"…）；
        - 其次取不含"队"的最左侧候选（实测页签顺序为 任务(左)/队伍(右)）；
        - 只剩"队伍"这类明显不是任务页的候选时返回 None，**绝不盲点**。
        """
        x, y, rw, rh = region
        candidates = []
        for item in lines:
            text = (item.get("text") or "").strip()
            if not text or len(text) > 4:      # 页签文字很短，借此排除任务条目
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                candidates.append((cx, cy, text))
        if not candidates:
            return None
        for cx, cy, text in candidates:
            if "务" in text:                    # "任务"/"彐干务"/"仸务" 都能命中
                return (int(cx), int(cy))
        rest = [c for c in candidates if "队" not in c[2]]
        if rest:
            rest.sort()
            return (int(rest[0][0]), int(rest[0][1]))
        return None

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

    def _node_tracked_click(self, agent) -> bool:
        """Maa「宝图任务单次点击」：点一次任务栏中的宝图任务。"""
        pos = self._find_tracked_baotu(agent)
        if not pos:
            return False
        agent.click(pos[0], pos[1])
        time.sleep(0.8)
        return True

    def _find_tracked_baotu(self, agent) -> Optional[Tuple[int, int]]:
        """在任务栏区域定位"宝图任务"文本。OCR 优先, 模板兜底。"""
        img = self._image(agent)
        if img is None:
            return None
        h, w = img.shape[:2]
        pos = self._find_tracked_in(self._ocr_lines(agent), w, h)
        if pos:
            return pos
        roi = self._fraction_region(w, h, self.ROI_TASKBAR_TEXT)
        m = self._match_any(agent, self.T_TRACKED_BAOTU_FALLBACK, roi, self.TH_TRACKED_TEMPLATE)
        return (m[0], m[1]) if m else None

    def _find_tracked_in(self, lines, w: int, h: int,
                         keywords=("宝图任务",)) -> Optional[Tuple[int, int]]:
        """在整图 OCR 结果里、于任务栏 ROI 内找 keywords 之一的文字，返回其中心。"""
        roi = self._fraction_region(w, h, self.ROI_TASKBAR_TEXT)
        x, y, rw, rh = roi
        for item in lines:
            text = item.get("text", "")
            if not any(k in text for k in keywords):
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return (int(cx), int(cy))
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

    # ==================================================================
    # 节点3: 主界面-宝图任务(Alt+C) -> 活动-宝图任务 -> 日常活动 -> 滑到顶端
    # ==================================================================
    def _node_open_activity_daily_find(self, agent) -> bool:
        # [JumpBack]战斗平衡弹窗-点击关闭
        self._dismiss_popups(agent)
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        # Maa「活动-宝图任务」：活动面板判断(huodong_jiemian_panduan)
        panel_roi = self._fraction_region(w, h, self.ROI_ACTIVITY_PANEL)
        if self._match_any(agent, self.T_ACTIVITY_PANEL, panel_roi, self.TH_ACTIVITY_PANEL) is None:
            if not self._alt_c_pressed:
                # Maa「主界面-宝图任务」ClickKey[57,31] = Alt+C 打开活动面板
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
                time.sleep(1.2)
            else:
                self._press_hotkey(agent, "C")  # 图标也没找到就再按一次快捷键
                time.sleep(1.0)
            return False
        # Maa「活动-宝图任务-点击日常活动」：OCR"日常活动"优先，本机模板兜底
        daily_roi = self._fraction_region(w, h, self.ROI_DAILY_LEFT)
        pos = self._find_label_in(self._ocr_lines(agent), ("日常活动",), daily_roi)
        if pos:
            logger.info("窗口=%s 点击日常活动(OCR) %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
        else:
            daily = self._match_any(agent, (self.T_DAILY_ACTIVITY,), daily_roi, self.TH_DAILY_ACTIVITY)
            if daily is None:
                return False
            logger.info("窗口=%s 点击日常活动(模板) %s", agent.hwnd, daily[:2])
            agent.click(daily[0], daily[1])
        time.sleep(1.0)
        self._ocr_cache = None
        # Maa「活动-宝图任务-向上滑动到顶端」MultiSwipe x2
        for _ in range(2):
            self._swipe_vertical(agent, self.SWIPE_LIST_X,
                                 self.SWIPE_LIST_TOP_FROM, self.SWIPE_LIST_TOP_TO)
            time.sleep(0.4)
        return True

    def _find_treasure_row(self, agent) -> Optional[str]:
        """在活动列表找宝图行。返回 "completed" / "found" / None(未找到)。

        对应 Maa「活动-宝图任务-向上滑动到顶端」的 next 列表:
        活动-宝图任务-开始 | 活动-宝图任务-已完成 | [JumpBack]baotu_huodong_down(max_hit 6)
        """
        while True:
            self._check_stop(agent)
            if self._node_completed_in_list(agent):
                return "completed"
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                roi = self._fraction_region(w, h, self.ROI_LIST)
                # Maa「活动-宝图任务-开始」: baotu1|2|3 (0.9)，本机 treasure_row 兜底
                if self._match_any(agent, self.T_TREASURE_START_MAA, roi, self.TH_TREASURE_START_MAA):
                    return "found"
                if self._match_any(agent, self.T_TREASURE_START_LOCAL, roi, self.TH_TREASURE_START):
                    return "found"
            # [JumpBack]baotu_huodong_down：活动列表向下翻页(max_hit 6)
            if self._list_swipes >= self.LIST_SWIPE_MAX:
                logger.warning("窗口=%s 活动列表翻页 %d 次仍未找到宝图任务",
                               agent.hwnd, self.LIST_SWIPE_MAX)
                return None
            self._swipe_vertical(agent, self.SWIPE_LIST_X,
                                 self.SWIPE_LIST_DOWN_FROM, self.SWIPE_LIST_DOWN_TO)
            self._list_swipes += 1
            self._ocr_cache = None
            time.sleep(1.0)

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
    # 节点4: 已完成判断 / 点击参加
    # ==================================================================
    def _node_completed_in_list(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_LIST_COMPLETED)
        m = self._match_any(agent, self.T_TREASURE_COMPLETED, roi, self.TH_TREASURE_COMPLETED)
        if m:
            logger.info("窗口=%s 检测到宝图任务已完成标记 %s", agent.hwnd, m[:2])
            return True
        return False

    def _node_join(self, agent) -> bool:
        """Maa「活动-宝图任务-开始」+「开始-点击参加」：OCR"参加"优先，行内偏移兜底。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_LIST)
        m = self._match_any(agent, self.T_TREASURE_START_MAA, roi, self.TH_TREASURE_START_MAA)
        if not m:
            m = self._match_any(agent, self.T_TREASURE_START_LOCAL, roi, self.TH_TREASURE_START)
        if not m:
            return False
        # Maa「活动-宝图任务-开始-点击参加」: OCR"参加"(roi 同行区域)
        pos = self._find_label_in(self._ocr_lines(agent), ("参加",), roi)
        if pos:
            logger.info("窗口=%s 点击宝图任务参加(OCR) %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
        else:
            scale = m[3] if len(m) > 3 else 1.0
            target = (int(m[0] + self.JOIN_BTN_OFFSET_X * scale), int(m[1]))
            logger.info("窗口=%s 点击宝图任务参加(行偏移) %s (行中心=%s scale=%.2f)",
                        agent.hwnd, target, m[:2], scale)
            agent.click(target[0], target[1])
        time.sleep(1.2)
        self._ocr_cache = None
        return True

    # ==================================================================
    # 节点5: 点击"听听无妨"
    # ==================================================================
    def _node_listen(self, agent) -> bool:
        # 1) OCR（Maa 原方案）
        pos = self._ocr_text_region(agent, "听听无妨", None, 0.55)
        if pos:
            agent.click(pos[0], pos[1])
            logger.info("窗口=%s 点击听听无妨(OCR) %s", agent.hwnd, pos)
            time.sleep(1.0)
            return True
        # 2) 模板兜底：baotu_dialogue 即"听听无妨"选项按钮，点其中心
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_DIALOGUE)
        m = self._match_any(agent, (self.T_DIALOGUE,), roi, self.TH_DIALOGUE)
        if m:
            agent.click(m[0], m[1])
            logger.info("窗口=%s 点击听听无妨(模板) %s", agent.hwnd, m[:2])
            time.sleep(1.0)
            return True
        return False

    # ==================================================================
    # 节点6: 完成循环（Maa click_baotu_ttwf 的 next 列表）
    # ==================================================================
    def _completion_loop(self, agent) -> str:
        """Maa click_baotu_ttwf / 已领取宝图任务 的 next 列表循环。

        返回 "done"(宝图完成判断成立) / "tayin"(遇见拓印停止) / "timeout"。
        """
        deadline = time.monotonic() + self.retry_interval * (self.retry_max + 1)
        next_retry = time.monotonic() + self.retry_interval
        while True:
            self._check_stop(agent)

            # Maa「识别拓印_停止」：遇见拓印 -> 关闭拓印界面 -> 停止所有任务
            if self._check_tayin(agent):
                logger.info("窗口=%s 遇见拓印，停止所有任务", agent.hwnd)
                self._close_tayin(agent)
                return "tayin"

            # [JumpBack]九转天阶遮挡 / 九幽遮挡 / 战斗平衡弹窗
            if self._dismiss_popups(agent):
                continue

            # [JumpBack]战斗中-等待5秒
            if self._in_battle(agent, self._image(agent)):
                logger.info("窗口=%s 战斗中，等待 %.0f 秒", agent.hwnd, self.battle_wait)
                if self._sleep(self.battle_wait):
                    raise _Aborted()
                continue

            self._tick_reward(agent)

            # 宝图完成判断
            if self._is_finished(agent):
                logger.info("窗口=%s 宝图完成判断成立，任务结束", agent.hwnd)
                return "done"

            # [JumpBack]宝图-间隔30秒-最大10分钟 + 宝图任务单次点击
            now = time.monotonic()
            if now >= next_retry:
                self._retry_hits += 1
                if self._retry_hits > self.retry_max:
                    logger.info("窗口=%s 重试达上限(%d)，按 Maa 语义结束", agent.hwnd, self.retry_max)
                    return "timeout"
                logger.info("窗口=%s 第 %d/%d 次点击任务栏宝图任务",
                            agent.hwnd, self._retry_hits, self.retry_max)
                self._node_tracked_click(agent)
                next_retry = now + self.retry_interval

            if now > deadline:
                logger.info("窗口=%s 完成循环超时，结束", agent.hwnd)
                return "timeout"
            if self._sleep(self.poll_interval):
                raise _Aborted()

    def _is_finished(self, agent) -> bool:
        """Maa「宝图完成判断」= inverse Or(宝图任务|贼王 文本, 战斗按钮, 自动寻路, 战斗图标)。

        OCR 可用，"宝图任务|贼王"按 Maa 原样用 OCR 判定；战斗(按钮+图标)与自动寻路
        按 Maa 原样用模板(0.9)判定；另外保留两条辅助信号（藏宝图集满 10 张、
        活动列表出现"已完成"）。为避免 OCR 偶发漏识别导致误判完成，要求连续
        finish_confirm_hits 次都看不到这些信号才认定结束；OCR 一个字都没读到时
        一律视为"无法判断"。
        """
        if self._treasure_count >= 10:
            return True
        if self._match_any(agent, self.T_TREASURE_COMPLETED, None, self.TH_TREASURE_COMPLETED):
            return True

        img = self._image(agent)
        if img is None:
            return False
        # Maa 子项2/4: 战斗按钮 zhandou/zidong|quxiao + 战斗图标 zhandou/zhandou1-3
        if self._in_battle(agent, img):
            self._finished_hits = 0
            return False

        h, w = img.shape[:2]
        # Maa 子项3: 自动寻路 zonghe/zidongxunlu1-4 (0.9)
        roi = self._fraction_region(w, h, self.ROI_AUTOPATH)
        if self._match_any(agent, self.T_AUTOPATH, roi, self.TH_AUTOPATH):
            self._finished_hits = 0  # 自动寻路仍在 -> 仍在跑任务
            return False

        # Maa 子项1: OCR "宝图任务" 或 "贼王"(任务栏区域)
        lines = self._ocr_lines(agent)
        if not lines:
            self._finished_hits = 0  # OCR 没读到任何文字 -> 无法判断
            return False
        if self._find_tracked_in(lines, w, h, keywords=("宝图任务", "贼王")):
            self._finished_hits = 0  # 任务栏仍显示宝图任务/贼王 -> 未完成
            return False

        self._finished_hits += 1
        logger.info("窗口=%s 未发现 宝图任务/贼王/自动寻路/战斗 信号（%d/%d）",
                    agent.hwnd, self._finished_hits, self.finish_confirm_hits)
        return self._finished_hits >= self.finish_confirm_hits

    def _tick_reward(self, agent) -> None:
        m = self._match_any(agent, (self.T_TREASURE_OBTAINED,), None, self.TH_TREASURE_OBTAINED)
        visible = m is not None
        if visible and not self._reward_visible:
            self._treasure_count += 1
            self._reward_visible = True
            self._report(f"已获得藏宝图 {self._treasure_count}/10")
            logger.info("窗口=%s 藏宝图获得提示出现，累计 %d/10", agent.hwnd, self._treasure_count)
        elif not visible:
            self._reward_visible = False

    def _dismiss_popups(self, agent) -> bool:
        """Maa「师门完成-九转天阶遮挡」/「师门完成-九幽遮挡」/「战斗平衡弹窗-点击关闭」。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        # Maa「师门完成-九转天阶遮挡」: OCR 九转天阶 -> ClickKey[4](ESC)
        if self._find_label_in(self._ocr_lines(agent), ("九转天阶",),
                               self._fraction_region(w, h, self.ROI_JIUZHUAN)):
            logger.info("窗口=%s 九转天阶遮挡，按 ESC 关闭", agent.hwnd)
            agent.press_key("esc")
            time.sleep(0.8)
            self._ocr_cache = None
            return True
        # Maa「师门完成-九幽遮挡」
        m = self._match_any(agent, self.T_JIUYOU,
                            self._fraction_region(w, h, self.ROI_JIUYOU), self.TH_JIUYOU)
        if m:
            logger.info("窗口=%s 关闭九幽遮挡 %s", agent.hwnd, m[:2])
            agent.click(m[0], m[1])
            time.sleep(1.0)
            return True
        # Maa「战斗平衡弹窗-点击关闭」
        m = self._match_any(agent, self.T_POPUP_CLOSE, None, self.TH_POPUP_CLOSE)
        if m:
            agent.click(m[0], m[1])
            logger.info("窗口=%s 关闭战斗平衡弹窗 %s", agent.hwnd, m[:2])
            time.sleep(0.6)
            return True
        return False

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
        """Maa 战斗判断的两个模板子项 + 本机已验证的圆形一致性兜底。

        - Maa「战斗中-等待5秒」/「宝图完成判断」子项: zhandou/zidong|quxiao
          (右下战斗按钮区, 阈值 0.9)
        - Maa「宝图完成判断」子项: zhandou/zhandou1|2|3 (顶部战斗图标, 阈值 0.9)
        - 模板都匹配不上时回退「顶部圆形一致性(HoughCircles)」。
        """
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

    def _ocr_text_region(self, agent, text: str, region: Optional[Region], threshold: float):
        """OCR 查找文本，返回中心坐标。

        直接对整图 OCR 再按 ROI 过滤中心点，而不是先裁剪再 OCR —— 裁剪会把
        "宝图任务" 这类跨 ROI 边界的文本切断造成漏检（实测该文本 box x610..726，
        而 Maa 换算的 roi 从 x≈649 起）。整图结果带 ocr_cache_seconds 秒缓存，
        避免 0.5s 轮询里反复识别同一帧。
        """
        now = time.monotonic()
        if self._ocr_cache is not None and now - self._ocr_cache[0] < self.ocr_cache_seconds:
            results = self._ocr_cache[1]
        else:
            try:
                img = agent.capture()
                results = agent.vision.get_all_text(img) if img is not None else []
            except Exception:
                logger.debug("OCR 不可用或失败：%s", text, exc_info=True)
                results = []
            self._ocr_cache = (now, results)

        for item in results:
            if text not in item.get("text", ""):
                continue
            if item.get("confidence", 1.0) < threshold:
                continue
            cx, cy = item["center"]
            if region is not None:
                x, y, w, h = region
                if not (x <= cx <= x + w and y <= cy <= y + h):
                    continue
            return (int(cx), int(cy))
        return None

    @staticmethod
    def _ensure_foreground(hwnd) -> bool:
        """尽量把窗口切到前台；失败不抛异常。

        窗口已是前台时 SetForegroundWindow 也可能报 “拒绝访问”(error 5)，
        这种情况直接返回 True 即可继续输入。
        """
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

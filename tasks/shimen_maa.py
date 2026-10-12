# -*- coding: utf-8 -*-
"""师门任务 —— 按 Maa_MHXY 的 shimen_renwu.json / shimen_renwu_new.json 流水线原样移植。

源流水线:
    Maa_MHXY-main/assets/resource/base/pipeline/shimen_renwu.json      (自动模式, Maa 默认)
    Maa_MHXY-main/assets/resource/base/pipeline/shimen_renwu_new.json  (手动模式, 选项"师门任务模式"=Yes)
    Maa_MHXY-main/assets/resource/base/pipeline/dazao.json             (打造子链路, 手动模式打造分支)
    (+ 共享节点: my_task.json「panduan_zhujiemian / 识别拓印 / 拓印保底-3次 / 拓印完成 /
       拓印滑动(tayin) / 关闭X9联赛弹窗 / 关闭三界热点 / 关闭整点活动弹窗 / 战斗中-等待10秒」
       baotu_renwu.json「战斗平衡弹窗-点击关闭」 fuben69.json「跳过剧情动画-快进键 /
       打开大地图_69副本 / 传送长安城_69副本」 bangpai_renwu.json「任务分支-物品提交 /
       任务分支-药店-购买 / 任务分支-摆摊购买」 wabaotu.json「清理主界面使用-关闭」)
    (+ 自定义: agent/custom/recognition/shimen_renwu.py「shimen_renwu_decide」
               agent/custom/action/tayin.py「tayin 拓印描摹」)

======================= Maa 原始流程(节点图) =======================
【自动模式 shimen_renwu, Maa 默认】
shimen_renwu -> 师门任务开始
  next: shimen_renwu2_dianji   OCR"师门任务" -> 点击 -> 师门-点击去完成(OCR 去完成/继续任务)
        shimen_renwu2_dianji2  OCR"^师门-.*"(进行中子任务) -> 点击
        [JumpBack]展开-首页任务栏 / 任务栏切换为任务 / 师门-下滑任务栏-三次(max_hit 3)
  -> 监控循环:
        师门完成确定-图片识别(shimenwancheng2) / 文字识别(OCR 师门任务完成) -> panduan(结束)
        [JumpBack]识别拓印 -> 拓印保底-3次 / 拓印完成 / [JumpBack]拓印滑动(描摹, max_hit 20)
        [JumpBack]九转天阶遮挡(ESC) / 九幽遮挡 / 战斗平衡弹窗 / X9联赛弹窗 / 剧情快进 / 三界热点
        [JumpBack]师门任务-单次点击(OCR ^师门.*, max_hit 1, post_delay 7000)
        [JumpBack]issub_sleep(等10秒)

【手动模式 shimen_renwu_new, 选项=Yes】
shimen_renwu_new -> 师门任务开始-v2
  -> 师门-点击师门主任务-v2(OCR 师门任务) -> 师门-点击去完成-v2 -> 师门-进行中状态机-v2
  -> 师门-点击师门子任务-v2(OCR ^师门.*) -> 师门-进行中状态机-v2
  状态机 next:
        完成确定-图片/文字 -> panduan(结束)
        [JumpBack]任务分支-对话(OCR 选择要做的事 -> 点 师门xx/首席/请赐教/看招, 兜底点第一个)
        [JumpBack]任务分支-兵器铺购买(OCR 兵器铺 -> 点购买)
        [JumpBack]任务分支-物品提交(OCR 任务物品选择 -> 点固定位置)
        [JumpBack]任务分支-药店-购买(OCR 购买)
        [JumpBack]任务分支-抄本(OCR 雷音法册/笔墨纸砚/秘术镜/狮驼 -> 点固定位置)
        [JumpBack]任务分支-摆摊购买(baitan_logo -> 点固定位置 -> panduan)
        [JumpBack]任务分支-问答(OCR 请选择正确答案 -> 点 孔雀石/6/30级/10个/百炼精铁, 兜底点第一个)
        [JumpBack]清理主界面使用-关闭
        [JumpBack]战斗中-等待10秒
        [JumpBack]师门任务-单次点击-v2 = shimen_renwu_decide:
            OCR 任务面板 -> 命中打造装备名且未拥有 -> override 等级/品类/装备名 -> run dazao
            否则含"师门" -> 点击 + 等7秒 + 抄本兜底
            连续5次未命中 -> 打开大地图_69副本(Alt+M) -> 传送长安城
        [JumpBack]九转天阶/九幽/战斗平衡/X9/剧情快进/三界热点
        [JumpBack]师门-间隔3秒-最大10分钟(max_hit 200)

【打造子链路 dazao(手动模式打造分支)】
dazao -> 打造-在长安主界面(OCR 长安城 + jiahao) 否则 panduan_ks / 打开大地图_69副本传送
  -> 打造-展开菜单-加号 -> 打造-点击打造入口(qianghua_rukou) -> 打造-打开成功(dazao_active/inactive)
  -> 打造-切换等级(展开等级 -> 点全部 -> 上滑x3 -> OCR 选等级, 下滑 max 10) -> 结束过渡
  -> 打造-切换装备(下滑x3 -> OCR 选品类, 上滑 max 30)
  -> 打造-打造装备-收集材料(OCR 装备名):
        [JumpBack]购买制造书(ColorMatch -> 商会 -> 购买 -> 确定 -> 返回)
        [JumpBack]购买精铁(同上)
        [JumpBack]购买打造符(ColorMatch -> 摆摊 -> 选中物品 -> 购买 -> 确定 -> 返回)
        [JumpBack]取消石头(dazao_shitou_xuanzhong)
        打造-购买材料-点击打造(OCR 普通打造 -> 确定) -> panduan(结束)

======================= 移植适配说明 =======================
官网 PC 客户端(Unity) 与 Maa 的模拟器(1280x720) 不同:
  1. 布局非等比, roi 由 Maa 像素坐标换算为窗口比例并适当放大, 模板匹配用多尺度。
  2. ClickKey[4] = ESC; ClickKey[57,41] = Alt+M(大地图), 用 win32 keybd_event 实现。
  3. OCR 走整图识别+ROI 中心过滤(带缓存); regex 预期(^师门.* 等)按包含关系近似。
  4. 战斗检测沿用本机已验证的「顶部圆形一致性(HoughCircles)」方案。
  5. ColorMatch 与宝图任务的 _colormatch 等价实现(BGR->RGB 后按上下界统计像素数)。
  6. 拓印描摹(tayin) 移植为 win32 鼠标拖拽折线; 依赖 skimage, 缺失时跳过描摹,
     仅保留 保底-3次/完成点击 两条路径。
  7. Maa 选项「师门任务模式」映射为类常量 SHIMEN_MODE: "auto"(默认) / "new"(手动)。
"""

import logging
import math
import random
import time
from typing import Callable, Optional, Sequence, Tuple

from domain.tasks import TaskContext, TaskDefinition, TaskSnapshot, TaskStatus
from tasks.base import AutomationTask

logger = logging.getLogger(__name__)

Region = Tuple[int, int, int, int]  # x, y, w, h（截图坐标）


class _Aborted(Exception):
    """停止/超时信号。"""


class ShimenMaaTask(AutomationTask):
    definition = TaskDefinition(
        "shimen_maa", "师门任务", "移植自 Maa_MHXY 的 shimen_renwu / shimen_renwu_new 流水线"
    )

    # ---------------- 模式（对应 Maa 选项「师门任务模式」）----------------
    SHIMEN_MODE = "auto"         # "auto"=自动(Maa 默认 No) / "new"=手动(Yes)

    # ---------------- 时序参数（对应 Maa 流水线字段）----------------
    poll_interval = 0.5
    node_timeout = 90.0
    battle_wait = 10.0           # Maa: 战斗中-等待10秒
    auto_idle_wait = 10.0        # Maa: issub_sleep-10分钟/无限 (pre_delay 10000)
    new_idle_wait = 3.0          # Maa: 师门-间隔3秒-最大10分钟 (pre_delay 3000)
    subtask_click_delay = 7.0    # Maa: 师门任务-单次点击 post_delay 7000
    taskbar_swipe_max = 3        # Maa: 师门-下滑任务栏-三次 (max_hit 3)
    tayin_trace_max = 20         # Maa: 拓印滑动 (max_hit 20)
    dazao_timeout = 300.0        # 打造子链路上限
    total_timeout = 2400.0       # 整个任务上限

    # ---------------- 可调开关 ----------------
    ocr_cache_seconds = 2.0
    miss_streak_limit = 5        # Maa shimen_renwu_decide: 连续未命中回长安
    finish_confirm_hits = 2

    # ---------------- 阈值 ----------------
    TH_MAIN_INDICATOR = 0.75
    TH_TASKBAR_TAB = 0.80
    TH_SHIMEN_WANCHENG = 0.80
    TH_POPUP_CLOSE = 0.88
    TH_JIUYOU = 0.80
    TH_X9 = 0.90                 # Maa: 关闭X9联赛弹窗 threshold 0.9
    TH_KUAIJIN = 0.80
    TH_CHA = 0.80
    TH_TAYIN = 0.90              # Maa: 识别拓印-子2/子3 threshold 0.9
    TH_TAYIN_CLOSE = 0.80
    TH_BAITAN = 0.80
    TH_MAP_PANEL = 0.75
    TH_MINIMAP = 0.80            # Maa: 大地图界面-按键打开失败 threshold 0.8
    TH_CHANGAN_TAB = 0.75
    TH_RENWU_TANCHUANG = 0.80
    TH_DAZAO_RUKOU = 0.75
    TH_DAZAO_TAB = 0.75
    TH_ZHANKAI = 0.70            # Maa: 打造-切换等级-点击展开等级界面 threshold 0.7
    TH_SHITOU = 0.80             # Maa: 打造-购买材料-取消石头 threshold 0.8

    # ---------------- 模板名（templates/ 目录，不带 .png）----------------
    T_MAIN_INDICATORS = ("zonghe/jiahao", "zonghe/baoguo", "zonghe/baoguo_man", "zonghe/chenghao")
    T_JIAHAO = ("zonghe/jiahao",)
    T_TASKBAR_COLLAPSED = ("zonghe/rwl_suojin", "zonghe/rwl_suojin2")
    # Maa「师门完成确定-图片识别」
    T_SHIMEN_WANCHENG = ("shimen/shimenwancheng2",)
    # Maa「战斗平衡弹窗-点击关闭」
    T_POPUP_CLOSE = ("zonghe/zhandoupingheng_guanbi1",)
    # Maa「师门完成-九幽遮挡」
    T_JIUYOU = ("zonghe/jiuyoudiyu", "zonghe/jiuyoudiyu2")
    # Maa「关闭X9联赛弹窗」
    T_X9 = ("zonghe/shouye_huodong_zedang", "zonghe/shouye_huodong_zedang2")
    # Maa「跳过剧情动画-快进键」
    T_KUAIJIN = ("fuben/fubentiaoguo1", "fuben/fubentiaoguo2", "fuben/fubentiaoguo3",
                 "fuben/fubentiaoguo4", "fuben/shimen_kuaijin")
    # Maa「清理主界面使用-关闭」
    T_CHA = ("zonghe/zhujiemian_shiyong_cha",)
    # Maa「识别拓印-子2/子3」/「关闭拓印界面」
    T_TAYIN = ("tayin/tayin", "tayin/tayin2")
    T_TAYIN_CLOSE = ("zonghe/guanbi6", "zonghe/guanbi7")
    # Maa「任务分支-摆摊购买」
    T_BAITAN = ("bangpairenwu/baitan_logo",)
    # Maa「打开大地图成功_传送长安城_69副本」/「传送长安城_69副本」/「大地图界面-按键打开失败_点击图标」
    T_MAP_PANEL = ("zonghe/ditu_jiemian_panduan", "zonghe/ditu_jiemian_panduan2")
    T_CHANGAN_TAB = ("zonghe/tab_changancheng", "zonghe/tab_changancheng2", "zonghe/tab_changancheng3")
    T_MINIMAP = ("zonghe/xiaoditu_taiyang", "zonghe/xiaoditu_yueliang")
    # Maa「关闭整点活动弹窗」
    T_RENWU_TANCHUANG = ("zonghe/renwu_tanchuang",)
    # Maa dazao 链路
    T_DAZAO_RUKOU = ("dazao/qianghua_rukou",)
    T_DAZAO_TAB = ("dazao/dazao_active", "dazao/dazao_inactive")
    T_DAZAO_TAB_ACTIVE = ("dazao/dazao_active",)
    T_ZHANKAI = ("dazao/zhankai_button",)
    T_SHITOU = ("dazao/dazao_shitou_xuanzhong",)

    # ---------------- 区域比例（由 Maa 1280x720 像素 roi 换算并适当放大）----------------
    ROI_MAIN_INDICATOR = (0.86, 0.72, 0.14, 0.28)
    ROI_TASKBAR_TAB = (0.86, 0.08, 0.14, 0.22)
    ROI_TASKBAR_TABS = (0.80, 0.12, 0.20, 0.07)
    # Maa 师门任务栏条目 [1035,112,245,294] / 单次点击 [1036,113,240,150]；
    # 官网客户端任务栏更靠左(实测 x610..726/832)，按宝图任务经验放大
    ROI_TASKBAR_TEXT = (0.68, 0.10, 0.32, 0.62)
    ROI_TASKBAR_CLICK = (0.68, 0.10, 0.32, 0.45)
    ROI_QUWANCHENG = (0.25, 0.48, 0.62, 0.20)      # Maa [398,408,704,59] 放大
    ROI_WANCHENG_IMG = (0.24, 0.16, 0.52, 0.24)    # Maa [404,181,444,80] 放大
    ROI_WANCHENG_OCR = (0.26, 0.18, 0.48, 0.24)    # Maa [430,180,410,96] 放大
    ROI_JIUZHUAN = (0.18, 0.04, 0.70, 0.44)        # Maa [293,47,834,260] 放大
    ROI_JIUYOU = (0.76, 0.10, 0.24, 0.22)          # Maa [1085,128,64,71] 放大
    ROI_X9 = (0.70, 0.02, 0.28, 0.20)              # Maa [1048,51,66,64] 放大
    ROI_KUAIJIN = (0.84, 0.00, 0.16, 0.20)         # Maa [1185,4,94,78] 放大
    ROI_SANJIE = (0.28, 0.86, 0.44, 0.14)
    ROI_CHA = (0.82, 0.42, 0.18, 0.20)
    ROI_TAYIN_OCR = (0.15, 0.18, 0.20, 0.25)
    ROI_TAYIN_TPL1 = (0.14, 0.16, 0.22, 0.36)
    ROI_TAYIN_TPL2 = (0.10, 0.45, 0.32, 0.48)
    ROI_TAYIN_CLOSE = (0.62, 0.00, 0.36, 0.26)
    ROI_TAYIN_BAODI = (0.50, 0.16, 0.16, 0.12)     # Maa [726,160,19,29] 放大
    ROI_TAYIN_WANCHENG = (0.50, 0.74, 0.26, 0.16)  # Maa [732,578,166,51] 放大
    ROI_TAYIN_DRAW = (0.402, 0.274, 0.250, 0.444)  # Maa tayin 描摹 [515,197,320,320]
    ROI_DIALOG_PANEL = (0.60, 0.00, 0.38, 0.85)    # Maa [876,5,311,544] 放大
    ROI_DIALOG_OPTS = (0.60, 0.03, 0.38, 0.80)     # Maa [876,25,321,524] 放大
    ROI_BINGQIPU = (0.34, 0.00, 0.32, 0.16)        # Maa [543,15,196,53] 放大
    ROI_GOUMAI_BQP = (0.58, 0.66, 0.32, 0.22)      # Maa [854,543,224,80] 放大
    ROI_WUPIN_TITLE = (0.66, 0.05, 0.30, 0.18)     # Maa [960,74,191,60] 放大
    ROI_GOUMAI_YD = (0.58, 0.66, 0.34, 0.22)       # Maa [866,542,210,82] 放大
    ROI_CHAOBEN_OCR = (0.70, 0.58, 0.28, 0.20)     # Maa [1025,481,142,72] 放大
    ROI_CHANGAN_OCR = (0.02, 0.00, 0.25, 0.12)     # Maa [108,22,117,31] 放大
    ROI_JIAHAO_BR = (0.86, 0.80, 0.14, 0.20)       # Maa [1206,637,66,57] 放大
    ROI_MAP_PANEL = (0.00, 0.00, 0.28, 0.24)       # Maa [111,32,83,79] 放大
    ROI_MINIMAP = (0.00, 0.00, 0.18, 0.20)         # Maa [58,1,75,79] 放大
    ROI_RENWU_TANCHUANG = (0.55, 0.45, 0.22, 0.24) # Maa [846,394,80,83] 放大
    ROI_DAZAO_RUKOU = (0.32, 0.80, 0.50, 0.20)     # Maa [531,634,439,77] 放大
    ROI_DAZAO_TAB = (0.68, 0.00, 0.32, 0.36)       # Maa [1020,21,152,190] 放大
    ROI_ZHANKAI = (0.16, 0.02, 0.20, 0.18)         # Maa [311,42,78,61] 放大
    ROI_QUANBU = (0.06, 0.08, 0.24, 0.18)          # Maa [171,109,106,53] 放大
    ROI_LEVEL_LIST = (0.16, 0.08, 0.26, 0.66)      # Maa [303,107,142,378] 放大
    ROI_CATEGORY_LIST = (0.10, 0.06, 0.24, 0.86)   # Maa [243,96,102,543] 放大
    ROI_EQUIP_NAME = (0.40, 0.46, 0.30, 0.22)      # Maa [620,391,176,70] 放大
    ROI_SHITOU = (0.66, 0.50, 0.22, 0.30)          # Maa [942,431,110,119] 放大
    ROI_SHANGHUI = (0.36, 0.16, 0.48, 0.42)        # Maa [585,178,407,212] 放大
    ROI_BAITAN_LIST = (0.36, 0.28, 0.48, 0.42)     # Maa [585,284,402,196] 放大
    ROI_GOUMAI = (0.62, 0.78, 0.32, 0.20)          # Maa [927,619,184,66] 放大
    ROI_QUEDING_BUY = (0.42, 0.48, 0.30, 0.24)     # Maa [659,423,174,78] 放大
    ROI_PUTONG_DAZAO = (0.34, 0.76, 0.36, 0.22)    # Maa [566,605,270,73] 放大
    ROI_QUEDING_DAZAO = (0.40, 0.46, 0.32, 0.24)   # Maa [647,419,190,76] 放大

    # 固定点击位（比例坐标）
    POS_WUPIN_SUBMIT = (0.822, 0.822)   # Maa 物品提交 target [997,573,111,38] 中心
    POS_BAITAN_BUY = (0.785, 0.910)     # Maa 摆摊购买 target [948,636,115,38] 中心
    POS_CHAOBEN_USE = (0.854, 0.803)    # Maa 抄本 target [1060,560,67,36] 中心
    POS_MINIMAP = (0.0336, 0.0611)      # Maa 大地图图标 target [8,7,70,74] 中心
    POS_GUODU_CLICK = (0.544, 0.194)    # Maa 打造-切换等级-结束过渡 target (696,140)

    # 滑动坐标（比例）
    SWIPE_TASKBAR_X = 0.896        # Maa x=1147/1280
    SWIPE_TASKBAR_FROM = 0.2875    # 师门-下滑任务栏: 207 -> 403 (手指下滑)
    SWIPE_TASKBAR_TO = 0.5597
    SWIPE_LEVEL_X = 0.276          # Maa x=353/1280
    SWIPE_LEVEL_UP_FROM = 0.574    # 413 -> 213 (手指上滑)
    SWIPE_LEVEL_UP_TO = 0.296
    SWIPE_LEVEL_DOWN_FROM = 0.296  # 213 -> 283 (手指下滑)
    SWIPE_LEVEL_DOWN_TO = 0.393
    SWIPE_EQUIP_X = 0.183          # Maa x=235/1280
    SWIPE_EQUIP_DOWN_FROM = 0.197  # 142 -> 542 (手指下滑)
    SWIPE_EQUIP_DOWN_TO = 0.753
    SWIPE_EQUIP_UP_FROM = 0.614    # 442 -> 302 (手指上滑)
    SWIPE_EQUIP_UP_TO = 0.419

    # ColorMatch 参数（RGB, 与 Maa upper/lower 同序）
    CM_MATERIAL_LOWER = (158, 20, 16)      # 打造-购买材料(制造书/精铁/打造符)
    CM_MATERIAL_UPPER = (248, 90, 116)
    CM_MATERIAL_COUNT = 150
    CM_SELECT_LOWER = (234, 220, 201)      # 打造-购买材料-点击摆摊-选中物品
    CM_SELECT_UPPER = (254, 240, 221)
    CM_SELECT_COUNT = 500
    CM_MINIMAP_LOWER = (130, 85, 48)       # 大地图界面-按键打开失败
    CM_MINIMAP_UPPER = (135, 88, 50)
    CM_MINIMAP_COUNT = 1000
    CM_TAYIN_LOWER = (244, 217, 180)       # 拓印完成-子2
    CM_TAYIN_UPPER = (247, 225, 194)
    CM_TAYIN_COUNT = 800
    # ColorMatch roi（比例）: 制造书 [496,201,38,24] / 精铁 [497,490,38,24] / 打造符 [901,198,38,24]
    CM_ROI_BOOK = (0.340, 0.240, 0.120, 0.100)
    CM_ROI_TIE = (0.340, 0.620, 0.120, 0.120)
    CM_ROI_FU = (0.640, 0.220, 0.140, 0.120)
    CM_ROI_SELECT = (0.680, 0.180, 0.160, 0.140)

    # 拓印描摹颜色阈值（RGB, 与 tayin.py 一致）
    TAYIN_INK_LOWER = (220, 172, 132)
    TAYIN_INK_UPPER = (233, 203, 164)

    # ---------------- 打造装备表（与 shimen_renwu.py 的 _50_MAP/_60_MAP 一致）----------------
    EQUIP_50_MAP = {
        "鞋": "绿靴", "腰带": "乱牙咬", "项链": "荧光坠子", "发钗": "媚狐头饰",
        "头盔": "羊角盔", "女衣": "金缕羽衣", "男衣": "钢甲",
        "长戈": "三星戈", "牵星尺": "星帆尺", "云锦扇": "蝉翼锦", "宝珠": "蓬莱珠",
        "弯刀": "冷月弯刀", "降魔杵": "金刚杵", "双短剑": "鱼骨双剑", "长刀": "破天宝刀",
        "鞭": "青藤鞭", "锤": "破甲战锤", "环圈": "赤炎环", "斧钺": "黄金钺",
        "飘带": "云龙绸带", "扇": "劈水扇", "爪刺": "玄冰刺", "弓": "玉腰弯弓",
        "魔棒": "幽路引魂", "枪": "墨杆金钩", "法杖": "星云杖", "剑": "黄金剑",
    }
    EQUIP_60_MAP = {
        "鞋": "追星踏月", "腰带": "双魂引", "项链": "风月宝链", "发钗": "玉女发冠",
        "头盔": "水晶帽", "女衣": "霓裳羽衣", "男衣": "夜魔披风",
        "长戈": "天山辰律", "牵星尺": "北落师门", "云锦扇": "桃之夭夭", "宝珠": "金露函烟",
        "弯刀": "埃兰弯刀", "降魔杵": "摩星杵", "双短剑": "落星双剑", "长刀": "秋水刀",
        "鞭": "雪绒鞭", "锤": "震天锤", "环圈": "蛇形月", "斧钺": "乌金鬼头镰",
        "飘带": "七彩罗刹", "扇": "清秋扇", "爪刺": "青刚刺", "魔棒": "满天星",
        "枪": "玄铁矛", "法杖": "天山雪", "剑": "游龙剑", "弓": "连珠神弓",
    }

    # ==================================================================
    # 主流程
    # ==================================================================
    def __init__(self) -> None:
        super().__init__()
        self._on_update = None
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._miss_streak = 0
        self._finished_hits = 0
        self._swipe_vertical = self._do_swipe_vertical
        self._ocr_cache = None
        self._tayin_warned = False

    def run(self, context: TaskContext,
            on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        self._deadline = time.monotonic() + self.total_timeout
        self._esc_presses = 0
        self._miss_streak = 0
        self._finished_hits = 0
        self._swipe_vertical = self._do_swipe_vertical  # 允许测试替换
        self._ocr_cache = None
        self._tayin_warned = False

        mode_name = "手动" if self.SHIMEN_MODE == "new" else "自动"
        logger.info("师门任务(%s模式)启动 hwnd=%s", mode_name, getattr(agent, "hwnd", None))
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 3
        self._report("等待游戏画面")

        try:
            # 步骤1: Maa「panduan_zhujiemian」—— 先回到主界面
            self._stage(agent, 1, "回到主界面", self._node_panduan_zhujiemian)

            # 步骤2: 任务栏找到师门任务并点击（主任务 -> 去完成 / 子任务 -> 直接继续）
            branch = self._stage_find_shimen(agent)
            if branch is None:
                self.snapshot.status = TaskStatus.FAILED
                self._report("任务栏未找到师门任务，请检查窗口状态")
                logger.error("窗口=%s 任务栏未找到师门任务", agent.hwnd)
                return
            if branch == "main":
                # Maa「师门-点击去完成(-v2)」
                self._run_node(agent, self._node_click_quwancheng, self.node_timeout,
                               "点击去完成/继续任务")
            self.snapshot.completed_steps = 2

            # 步骤3: 监控循环
            self._report("师门任务进行中")
            if self.SHIMEN_MODE == "new":
                self._monitor_loop_new(agent)
            else:
                self._monitor_loop_auto(agent)

            self.snapshot.completed_steps = self.snapshot.total_steps
            self.snapshot.status = TaskStatus.COMPLETED
            self._report("师门任务完成")
            logger.info("师门任务完成 hwnd=%s", agent.hwnd)
        except _Aborted:
            logger.info("师门任务停止 hwnd=%s", getattr(agent, "hwnd", None))
        except Exception:
            logger.exception("师门任务执行异常 hwnd=%s", getattr(agent, "hwnd", None))
            self.snapshot.status = TaskStatus.FAILED
            self._report("师门任务执行异常，详见日志")

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
    # 节点2: 任务栏找师门任务（自动/手动入口共用）
    # ==================================================================
    def _stage_find_shimen(self, agent) -> Optional[str]:
        """Maa「师门任务开始(-v2)」。返回 "main"(点了师门任务) / "sub"(点了师门-子任务) / None。"""
        self._report("步骤 2/3：任务栏查找师门任务")
        logger.info("窗口=%s 开始任务栏查找师门任务", agent.hwnd)
        started = time.monotonic()
        swipes = 0
        while time.monotonic() - started < self.node_timeout:
            self._check_stop(agent)
            lines = self._ocr_lines(agent)
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                roi = self._fraction_region(w, h, self.ROI_TASKBAR_TEXT)
                # shimen_renwu2_dianji / 师门-点击师门主任务-v2: OCR "师门任务"
                pos = self._find_text_in(lines, ("师门任务",), roi)
                if pos:
                    logger.info("窗口=%s 点击师门任务 %s", agent.hwnd, pos)
                    agent.click(pos[0], pos[1])
                    time.sleep(1.0)
                    self._ocr_cache = None
                    return "main"
                # shimen_renwu2_dianji2 / 师门-点击师门子任务-v2: OCR "^师门.*"(子任务)
                pos = self._find_shimen_sub(lines, roi)
                if pos:
                    logger.info("窗口=%s 点击师门子任务 %s", agent.hwnd, pos)
                    agent.click(pos[0], pos[1])
                    time.sleep(1.0)
                    self._ocr_cache = None
                    return "sub"
            # [JumpBack]展开-首页任务栏
            if img is not None:
                h, w = img.shape[:2]
                tab_roi = self._fraction_region(w, h, self.ROI_TASKBAR_TAB)
                m = self._match_any(agent, self.T_TASKBAR_COLLAPSED, tab_roi, self.TH_TASKBAR_TAB)
                if m:
                    logger.info("窗口=%s 展开首页任务栏 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    time.sleep(0.8)
                    continue
            # [JumpBack]任务栏切换为任务
            if self._node_switch_task_tab(agent):
                continue
            # [JumpBack]师门-下滑任务栏-三次
            if swipes < self.taskbar_swipe_max:
                self._swipe_vertical(agent, self.SWIPE_TASKBAR_X,
                                     self.SWIPE_TASKBAR_FROM, self.SWIPE_TASKBAR_TO)
                swipes += 1
                self._ocr_cache = None
                time.sleep(1.0)
                continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 任务栏查找师门任务超时", agent.hwnd)
        return None

    def _find_shimen_sub(self, lines, region: Region) -> Optional[Tuple[int, int]]:
        """OCR "^师门-.*" 的近似：含"师门"但不是"师门任务"本身（师门-xxx 子任务）。"""
        x, y, rw, rh = region
        for item in lines:
            text = (item.get("text") or "").strip()
            if "师门" not in text or "师门任务" in text:
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                return (int(cx), int(cy))
        return None

    def _node_switch_task_tab(self, agent) -> bool:
        """Maa「任务栏切换为任务」（与宝图任务一致）：OCR 页签，绝不盲点。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_TASKBAR_TABS)
        x, y, rw, rh = roi
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

    def _node_click_quwancheng(self, agent) -> bool:
        """Maa「师门-点击去完成(-v2)」：OCR 去完成/继续任务。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_QUWANCHENG)
        pos = self._find_text_in(self._ocr_lines(agent), ("去完成", "继续任务"), roi)
        if not pos:
            return False
        logger.info("窗口=%s 点击去完成/继续任务 %s", agent.hwnd, pos)
        agent.click(pos[0], pos[1])
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    # ==================================================================
    # 节点3（自动模式）: 监控循环
    # ==================================================================
    def _monitor_loop_auto(self, agent) -> None:
        """Maa shimen_renwu2_dianji2 / 师门-点击去完成 的 next 列表。"""
        while True:
            self._check_stop(agent)

            # 师门完成确定-图片识别 / 文字识别 -> panduan(结束)
            if self._check_shimen_done(agent):
                logger.info("窗口=%s 师门完成判断成立，任务结束", agent.hwnd)
                self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "收尾回主界面")
                return

            # [JumpBack]识别拓印
            if self._handle_tayin(agent):
                continue

            # 弹窗遮挡
            if self._dismiss_popups(agent):
                continue

            # [JumpBack]师门任务-单次点击 (max_hit 1, post_delay 7000)
            img = self._image(agent)
            if img is not None:
                h, w = img.shape[:2]
                roi = self._fraction_region(w, h, self.ROI_TASKBAR_CLICK)
                pos = self._find_text_in(self._ocr_lines(agent), ("师门",), roi)
                if pos:
                    logger.info("窗口=%s 单次点击师门任务 %s", agent.hwnd, pos)
                    agent.click(pos[0], pos[1])
                    self._ocr_cache = None
                    if self._sleep(self.subtask_click_delay):
                        raise _Aborted()
                    continue

            # [JumpBack]issub_sleep-10分钟/无限：等 10 秒
            if self._sleep(self.auto_idle_wait):
                raise _Aborted()

    # ==================================================================
    # 节点3（手动模式）: 师门-进行中状态机-v2
    # ==================================================================
    def _monitor_loop_new(self, agent) -> None:
        while True:
            self._check_stop(agent)

            # 师门完成确定-图片识别-v2 / 文字识别-v2 -> panduan(结束)
            if self._check_shimen_done(agent):
                logger.info("窗口=%s 师门完成判断成立，任务结束", agent.hwnd)
                self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "收尾回主界面")
                return

            # [JumpBack]师门任务-任务分支-对话
            if self._branch_dialog(agent):
                continue
            # [JumpBack]师门任务-任务分支-问答
            if self._branch_quiz(agent):
                continue
            # [JumpBack]师门任务-任务分支-兵器铺购买
            if self._branch_bingqipu(agent):
                continue
            # [JumpBack]任务分支-物品提交
            if self._branch_wupin(agent):
                continue
            # [JumpBack]任务分支-药店-购买
            if self._branch_yaodian(agent):
                continue
            # [JumpBack]师门任务-任务分支-抄本
            if self._branch_chaoben(agent):
                continue
            # [JumpBack]任务分支-摆摊购买
            if self._branch_baitan(agent):
                continue
            # [JumpBack]清理主界面使用-关闭
            if self._close_cha(agent):
                continue
            # [JumpBack]战斗中-等待10秒
            if self._in_battle(self._image(agent)):
                logger.info("窗口=%s 战斗中，等待 %.0f 秒", agent.hwnd, self.battle_wait)
                if self._sleep(self.battle_wait):
                    raise _Aborted()
                continue
            # [JumpBack]师门任务-单次点击-v2 = shimen_renwu_decide
            if self._shimen_decide(agent):
                continue
            # [JumpBack]识别拓印（状态机里也可能遇到）
            if self._handle_tayin(agent):
                continue
            # 弹窗遮挡（九转/九幽/战斗平衡/X9/剧情快进/三界热点）
            if self._dismiss_popups(agent):
                continue

            # [JumpBack]师门-间隔3秒-最大10分钟
            if self._sleep(self.new_idle_wait):
                raise _Aborted()

    def _check_shimen_done(self, agent) -> bool:
        """Maa「师门完成确定-图片识别」/「师门完成确定-文字识别」。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        m = self._match_any(agent, self.T_SHIMEN_WANCHENG,
                            self._fraction_region(w, h, self.ROI_WANCHENG_IMG),
                            self.TH_SHIMEN_WANCHENG)
        if m:
            self._finished_hits += 1
        else:
            pos = self._find_text_in(self._ocr_lines(agent), ("师门任务完成",),
                                     self._fraction_region(w, h, self.ROI_WANCHENG_OCR))
            self._finished_hits = self._finished_hits + 1 if pos else 0
        return self._finished_hits >= self.finish_confirm_hits

    # ------------------------------------------------------------------
    # 手动模式任务分支
    # ------------------------------------------------------------------
    def _branch_dialog(self, agent) -> bool:
        """Maa「师门任务-任务分支-对话」->「师门任务-对话-点击」/ 兜底点第一个。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        panel = self._fraction_region(w, h, self.ROI_DIALOG_PANEL)
        lines = self._ocr_lines(agent)
        title = self._find_text_in(lines, ("选择要做的事",), panel)
        if not title:
            return False
        opts = self._fraction_region(w, h, self.ROI_DIALOG_OPTS)
        pos = self._find_text_in(lines, ("师门", "首席", "请赐教", "看招", "赐教"), opts)
        if pos:
            logger.info("窗口=%s 对话分支：点击选项 %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
        else:
            # 兜底点第一个：Maa target_offset [100,80,-50,0] -> 标题右下方第一个选项
            fx, fy = title[0] + int(w * 0.078), title[1] + int(h * 0.111)
            logger.info("窗口=%s 对话分支：兜底点第一个 (%d,%d)", agent.hwnd, fx, fy)
            agent.click(fx, fy)
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    def _branch_quiz(self, agent) -> bool:
        """Maa「师门任务-任务分支-问答」->「师门任务-问答-点击」/ 兜底点第一个。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        panel = self._fraction_region(w, h, self.ROI_DIALOG_PANEL)
        lines = self._ocr_lines(agent)
        title = self._find_text_in(lines, ("请选择正确答案",), panel)
        if not title:
            return False
        opts = self._fraction_region(w, h, self.ROI_DIALOG_OPTS)
        pos = None
        x, y, rw, rh = opts
        for item in lines:
            text = (item.get("text") or "").strip()
            hit = any(k in text for k in ("孔雀石", "百炼精铁", "30级", "10个")) or text == "6"
            if not hit:
                continue
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                pos = (int(cx), int(cy))
                break
        if pos:
            logger.info("窗口=%s 问答分支：点击答案 %s", agent.hwnd, pos)
            agent.click(pos[0], pos[1])
        else:
            fx, fy = title[0] + int(w * 0.078), title[1] + int(h * 0.111)
            logger.info("窗口=%s 问答分支：兜底点第一个 (%d,%d)", agent.hwnd, fx, fy)
            agent.click(fx, fy)
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    def _branch_bingqipu(self, agent) -> bool:
        """Maa「师门任务-任务分支-兵器铺购买」->「兵器铺-点击」(OCR 购买)。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        lines = self._ocr_lines(agent)
        if not self._find_text_in(lines, ("兵器铺",),
                                  self._fraction_region(w, h, self.ROI_BINGQIPU)):
            return False
        pos = self._find_text_in(lines, ("购买",),
                                 self._fraction_region(w, h, self.ROI_GOUMAI_BQP))
        if not pos:
            return False
        logger.info("窗口=%s 兵器铺分支：点击购买 %s", agent.hwnd, pos)
        agent.click(pos[0], pos[1])
        time.sleep(2.0)
        self._ocr_cache = None
        return True

    def _branch_wupin(self, agent) -> bool:
        """Maa「任务分支-物品提交」：OCR 任务物品选择 -> 点固定位置。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if not self._find_text_in(self._ocr_lines(agent), ("任务物品选择",),
                                  self._fraction_region(w, h, self.ROI_WUPIN_TITLE)):
            return False
        fx, fy = int(w * self.POS_WUPIN_SUBMIT[0]), int(h * self.POS_WUPIN_SUBMIT[1])
        logger.info("窗口=%s 物品提交分支：点击 (%d,%d)", agent.hwnd, fx, fy)
        agent.click(fx, fy)
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    def _branch_yaodian(self, agent) -> bool:
        """Maa「任务分支-药店-购买」：OCR 购买。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        pos = self._find_text_in(self._ocr_lines(agent), ("购买",),
                                 self._fraction_region(w, h, self.ROI_GOUMAI_YD))
        if not pos:
            return False
        logger.info("窗口=%s 药店分支：点击购买 %s", agent.hwnd, pos)
        agent.click(pos[0], pos[1])
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    def _branch_chaoben(self, agent) -> bool:
        """Maa「师门任务-任务分支-抄本」：OCR 抄本类道具 -> 点固定位置(使用)。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if not self._find_text_in(self._ocr_lines(agent),
                                  ("雷音法册", "笔墨纸砚", "秘术镜", "狮驼"),
                                  self._fraction_region(w, h, self.ROI_CHAOBEN_OCR)):
            return False
        fx, fy = int(w * self.POS_CHAOBEN_USE[0]), int(h * self.POS_CHAOBEN_USE[1])
        logger.info("窗口=%s 抄本分支：点击使用 (%d,%d)", agent.hwnd, fx, fy)
        agent.click(fx, fy)
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    def _branch_baitan(self, agent) -> bool:
        """Maa「任务分支-摆摊购买」：baitan_logo -> 点固定位置 -> panduan。"""
        img = self._image(agent)
        if img is None:
            return False
        m = self._match_any(agent, self.T_BAITAN, None, self.TH_BAITAN)
        if not m:
            return False
        h, w = img.shape[:2]
        fx, fy = int(w * self.POS_BAITAN_BUY[0]), int(h * self.POS_BAITAN_BUY[1])
        logger.info("窗口=%s 摆摊分支：点击购买 (%d,%d)", agent.hwnd, fx, fy)
        agent.click(fx, fy)
        time.sleep(1.0)
        self._ocr_cache = None
        self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "摆摊后回主界面")
        return True

    def _close_cha(self, agent) -> bool:
        """Maa「清理主界面使用-关闭」。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        m = self._match_any(agent, self.T_CHA,
                            self._fraction_region(w, h, self.ROI_CHA), self.TH_CHA)
        if not m:
            return False
        logger.info("窗口=%s 关闭主界面\"使用\"弹窗 %s", agent.hwnd, m[:2])
        agent.click(m[0], m[1])
        time.sleep(1.0)
        return True

    # ------------------------------------------------------------------
    # 手动模式: shimen_renwu_decide 移植
    # ------------------------------------------------------------------
    def _shimen_decide(self, agent) -> bool:
        """OCR 任务面板 -> 打造分支 / 点击师门条目(+抄本兜底) / 未命中计数回长安。

        Maa 原实现对裁剪 roi 加 ±5px 抖动打破 OCR badcase 死循环；本移植用整图 OCR
        （带 2 秒缓存过期），抖动无意义，故省略。
        """
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        roi = self._fraction_region(w, h, self.ROI_TASKBAR_CLICK)
        x, y, rw, rh = roi
        panel_lines = []
        for item in self._ocr_lines(agent):
            cx, cy = item["center"]
            if x <= cx <= x + rw and y <= cy <= y + rh:
                panel_lines.append(item)
        if not panel_lines:
            return self._decide_on_miss(agent)

        panel_lines.sort(key=lambda it: (it["center"][1], it["center"][0]))
        full_text = "".join((it.get("text") or "") for it in panel_lines)
        logger.info("窗口=%s [shimen_decide] 面板 OCR: %s", agent.hwnd, full_text)

        # ① 命中打造类任务：装备名出现且未拥有 -> 走 dazao 子链路
        name_to_target = {}
        for cat, name in self.EQUIP_60_MAP.items():
            name_to_target.setdefault(name, ("60", cat))
        for cat, name in self.EQUIP_50_MAP.items():
            name_to_target.setdefault(name, ("50", cat))
        hit_name = next((n for n in name_to_target if n in full_text), None)
        not_own = ("拥有0" in full_text) or ("0/1" in full_text)
        if hit_name and not_own:
            level, category = name_to_target[hit_name]
            logger.info("窗口=%s [shimen_decide] 命中打造任务: %s级 %s -> %s",
                        agent.hwnd, level, category, hit_name)
            self._report(f"打造 {level}级{category}·{hit_name}")
            self._run_dazao(agent, level, category, hit_name)
            self._miss_streak = 0
            self._ocr_cache = None
            return True

        # ② 非打造类师门任务：点击含"师门"的条目，等7秒，跑一次抄本兜底
        for item in panel_lines:
            if "师门" not in (item.get("text") or ""):
                continue
            cx, cy = item["center"]
            logger.info("窗口=%s [shimen_decide] 点击师门任务 (%d,%d)", agent.hwnd, int(cx), int(cy))
            agent.click(int(cx), int(cy))
            self._ocr_cache = None
            if self._sleep(self.subtask_click_delay):
                raise _Aborted()
            # 抄本兜底：出现"使用"弹窗 X 时点固定位置(使用抄本)
            self._chaoben_fallback(agent)
            self._miss_streak = 0
            return True

        # ③ 都没有：未命中计数
        return self._decide_on_miss(agent)

    def _decide_on_miss(self, agent) -> bool:
        self._miss_streak += 1
        logger.info("窗口=%s [shimen_decide] 未识别到师门任务（连续 %d/%d）",
                    agent.hwnd, self._miss_streak, self.miss_streak_limit)
        if self._miss_streak >= self.miss_streak_limit:
            logger.info("窗口=%s [shimen_decide] 连续未命中，打开大地图回长安", agent.hwnd)
            self._open_map_and_teleport(agent)
            self._miss_streak = 0
        return False

    def _chaoben_fallback(self, agent) -> None:
        """Maa「师门任务-任务分支-抄本兜底」：有"使用"弹窗 X 时点固定位置。"""
        img = self._image(agent)
        if img is None:
            return
        h, w = img.shape[:2]
        m = self._match_any(agent, self.T_CHA,
                            self._fraction_region(w, h, self.ROI_CHA), self.TH_CHA)
        if m:
            fx, fy = int(w * self.POS_CHAOBEN_USE[0]), int(h * self.POS_CHAOBEN_USE[1])
            logger.info("窗口=%s 抄本兜底：点击 (%d,%d)", agent.hwnd, fx, fy)
            agent.click(fx, fy)
            time.sleep(1.0)
            self._ocr_cache = None

    # ------------------------------------------------------------------
    # 拓印处理（Maa「识别拓印」: 保底-3次 / 完成 / 描摹）
    # ------------------------------------------------------------------
    def _handle_tayin(self, agent) -> bool:
        if not self._check_tayin(agent):
            return False
        logger.info("窗口=%s 检测到拓印界面", agent.hwnd)
        self._report("处理拓印")
        traces = 0
        while True:
            self._check_stop(agent)
            # 拓印保底-3次：OCR 3/2/1 -> 关闭拓印界面
            img = self._image(agent)
            if img is None:
                return True
            h, w = img.shape[:2]
            x, y, rw, rh = self._fraction_region(w, h, self.ROI_TAYIN_BAODI)
            baodi = False
            for item in self._ocr_lines(agent):
                text = (item.get("text") or "").strip()
                if text not in ("3", "2", "1"):
                    continue
                cx, cy = item["center"]
                if x <= cx <= x + rw and y <= cy <= y + rh:
                    baodi = True
                    break
            if baodi:
                logger.info("窗口=%s 拓印触发保底机制，关闭拓印界面", agent.hwnd)
                self._close_tayin(agent)
                return True
            # 拓印完成 = And(OCR 完成, ColorMatch) -> 点击
            wc_roi = self._fraction_region(w, h, self.ROI_TAYIN_WANCHENG)
            pos = self._find_text_in(self._ocr_lines(agent), ("完成",), wc_roi)
            if pos and self._colormatch(img, wc_roi, self.CM_TAYIN_LOWER,
                                        self.CM_TAYIN_UPPER, self.CM_TAYIN_COUNT):
                logger.info("窗口=%s 拓印完成，点击 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(0.5)
                self._ocr_cache = None
                return True
            # [JumpBack]拓印滑动（描摹, max_hit 20）
            if traces >= self.tayin_trace_max:
                logger.warning("窗口=%s 拓印描摹达上限仍未完成，关闭拓印界面", agent.hwnd)
                self._close_tayin(agent)
                return True
            if not self._tayin_trace(agent):
                # 描摹不可用（缺 skimage/未提取到笔画）：拓印界面已不在就直接退出
                if not self._check_tayin(agent):
                    return True
                logger.warning("窗口=%s 拓印描摹失败，尝试关闭拓印界面", agent.hwnd)
                self._close_tayin(agent)
                return True
            traces += 1
            time.sleep(1.0)
            self._ocr_cache = None

    def _check_tayin(self, agent) -> bool:
        """Maa「识别拓印」= Or(OCR"拓印", tayin 模板 x2)。"""
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

    def _tayin_trace(self, agent) -> bool:
        """Maa custom action「tayin」拓印描摹的 win32 移植（折线连续滑动）。"""
        try:
            import cv2
            import numpy as np
        except Exception:
            return False
        try:
            from skimage.morphology import skeletonize
        except Exception:
            if not self._tayin_warned:
                logger.warning("窗口=%s 未安装 scikit-image，拓印描摹不可用",
                               getattr(agent, "hwnd", None))
                self._tayin_warned = True
            return False

        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_TAYIN_DRAW)
        roi_img = cv2.cvtColor(img[y:y + rh, x:x + rw], cv2.COLOR_BGR2RGB)

        lower = np.array(self.TAYIN_INK_LOWER, dtype=np.uint8)
        upper = np.array(self.TAYIN_INK_UPPER, dtype=np.uint8)
        mask = cv2.inRange(roi_img, lower, upper)
        if cv2.countNonZero(mask) < 100:
            logger.info("窗口=%s 拓印笔画像素过少", agent.hwnd)
            return False
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        skeleton = (skeletonize(closed > 0) * 255).astype(np.uint8)
        ys, xs = np.where(skeleton > 0)
        if len(xs) == 0:
            return False
        points = np.stack([xs, ys], axis=-1)

        groups = self._tayin_sort_strokes(points)
        strokes = self._tayin_simplify(groups, max_strokes=10)
        if not strokes:
            return False
        logger.info("窗口=%s 拓印描摹 %d 个笔画", agent.hwnd, len(strokes))

        # 还原为截图(客户区)坐标并逐笔画拖拽
        for idx, stroke in enumerate(strokes):
            if idx > 0:
                time.sleep(random.uniform(0.1, 0.3))
            pts = [(px + x, py + y) for px, py in stroke]
            self._drag_polyline(agent, pts, duration_ms=random.randint(600, 1000))
        return True

    @staticmethod
    def _tayin_sort_strokes(points) -> list:
        """8邻域连通分量拆笔画 + 端点DFS排序 + 质心排序（与 tayin.py 一致）。"""
        points_list = points.tolist()
        points_set = set(map(tuple, points_list))
        neighbors = {}
        for p in points_list:
            nbs = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    q = (p[0] + dx, p[1] + dy)
                    if q in points_set:
                        nbs.append(q)
            neighbors[(p[0], p[1])] = nbs
        visited = set()
        components = []
        for p in points_list:
            key = (p[0], p[1])
            if key in visited:
                continue
            comp, stack = [], [key]
            visited.add(key)
            while stack:
                node = stack.pop()
                comp.append(node)
                for nb in neighbors[node]:
                    if nb not in visited:
                        visited.add(nb)
                        stack.append(nb)
            components.append(comp)
        ordered = []
        for comp in components:
            endpoints = [pt for pt in comp if len(neighbors[pt]) == 1]
            start = endpoints[0] if endpoints else comp[0]
            seen, out, stack = set(), [], [start]
            while stack:
                node = stack.pop()
                if node in seen:
                    continue
                seen.add(node)
                out.append(node)
                for nb in reversed(neighbors[node]):
                    if nb not in seen:
                        stack.append(nb)
            ordered.append(out)

        def centroid(comp):
            arr = [(p[0], p[1]) for p in comp]
            my = sum(p[1] for p in arr) / len(arr)
            mx = sum(p[0] for p in arr) / len(arr)
            return (my, mx)

        ordered.sort(key=centroid)
        return ordered

    @staticmethod
    def _tayin_simplify(stroke_groups, max_strokes: int = 10) -> list:
        """Douglas-Peucker 简化每笔画为折线关键点（与 tayin.py 一致）。"""
        import cv2
        import numpy as np
        max_points, min_points = 12, 3
        result = []
        for stroke in stroke_groups:
            if len(stroke) < min_points:
                continue
            pts = np.array(stroke, dtype=np.float32)
            if len(pts) <= max_points + 1:
                sampled = pts.tolist()
            else:
                epsilon = 2.0
                while True:
                    approx = cv2.approxPolyDP(
                        pts.reshape(-1, 1, 2).astype(np.int32), epsilon, False)
                    simplified = approx.reshape(-1, 2).tolist()
                    if len(simplified) <= max_points:
                        sampled = simplified
                        break
                    epsilon *= 1.5
                    if epsilon > 50:
                        idx = np.linspace(0, len(pts) - 1, max_points, dtype=int)
                        sampled = pts[idx].tolist()
                        break
            result.append([(int(p[0]), int(p[1])) for p in sampled])

        def stroke_len(s):
            return sum(math.hypot(s[i][0] - s[i - 1][0], s[i][1] - s[i - 1][1])
                       for i in range(1, len(s)))

        result.sort(key=stroke_len, reverse=True)
        return result[:max_strokes]

    def _drag_polyline(self, agent, points, duration_ms: int = 800) -> None:
        """按截图(客户区)坐标做一条连续折线拖拽（笔画内不抬手）。"""
        try:
            import win32api
            import win32con
            import win32gui
        except Exception:
            return
        if len(points) < 2:
            return
        try:
            hwnd = agent.hwnd
            self._ensure_foreground(hwnd)
            time.sleep(0.2)
            screen_pts = [win32gui.ClientToScreen(hwnd, (px, py)) for px, py in points]
            segs = [math.hypot(screen_pts[i][0] - screen_pts[i - 1][0],
                               screen_pts[i][1] - screen_pts[i - 1][1])
                    for i in range(1, len(screen_pts))]
            total = sum(segs) or 1.0
            sx, sy = screen_pts[0]
            win32api.SetCursorPos((sx, sy))
            time.sleep(0.08)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, sx, sy, 0, 0)
            try:
                for i in range(1, len(screen_pts)):
                    time.sleep(duration_ms * (segs[i - 1] / total) / 1000.0)
                    win32api.SetCursorPos(screen_pts[i])
            finally:
                ex, ey = screen_pts[-1]
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, ex, ey, 0, 0)
        except Exception:
            logger.exception("窗口=%s 拓印描摹拖拽失败", getattr(agent, "hwnd", None))

    # ------------------------------------------------------------------
    # 弹窗遮挡（两种模式共用）
    # ------------------------------------------------------------------
    def _dismiss_popups(self, agent) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        # Maa「师门完成-九转天阶遮挡」: OCR 九转天阶 -> ESC
        if self._find_text_in(self._ocr_lines(agent), ("九转天阶",),
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
            logger.info("窗口=%s 关闭战斗平衡弹窗 %s", agent.hwnd, m[:2])
            agent.click(m[0], m[1])
            time.sleep(0.6)
            return True
        # Maa「关闭X9联赛弹窗」
        m = self._match_any(agent, self.T_X9,
                            self._fraction_region(w, h, self.ROI_X9), self.TH_X9)
        if m:
            logger.info("窗口=%s 关闭X9联赛弹窗 %s", agent.hwnd, m[:2])
            agent.click(m[0], m[1])
            time.sleep(1.0)
            return True
        # Maa「跳过剧情动画-快进键」
        m = self._match_any(agent, self.T_KUAIJIN,
                            self._fraction_region(w, h, self.ROI_KUAIJIN), self.TH_KUAIJIN)
        if m:
            logger.info("窗口=%s 跳过剧情动画 %s", agent.hwnd, m[:2])
            agent.click(m[0], m[1])
            time.sleep(1.0)
            return True
        # Maa「关闭三界热点」
        x, y, rw, rh = self._fraction_region(w, h, self.ROI_SANJIE)
        for item in self._ocr_lines(agent):
            text = (item.get("text") or "").strip()
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

    # ==================================================================
    # 打造子链路（dazao.json 移植）
    # ==================================================================
    def _run_dazao(self, agent, level: str, category: str, equip_name: str) -> bool:
        """对应 Maa 的 run_task("dazao") + override 选等级/选品类/装备名判定。"""
        logger.info("窗口=%s 进入打造子链路: %s级 %s %s", agent.hwnd, level, category, equip_name)
        started = time.monotonic()

        def timeout() -> bool:
            return time.monotonic() - started > self.dazao_timeout

        # ---- 打造-在长安主界面（不在则 panduan_ks / 打开大地图传送）----
        while not timeout():
            self._check_stop(agent)
            if self._in_changan_main(agent):
                break
            if not self._open_map_and_teleport(agent):
                agent.press_key("esc")  # panduan_zhujiemian_ks 兜底
                time.sleep(0.8)
        if timeout():
            logger.warning("窗口=%s 打造：回长安超时", agent.hwnd)
            return False

        # ---- 打造-展开菜单-加号 -> 点击打造入口 ----
        time.sleep(1.0)
        if not self._dazao_open_panel(agent):
            logger.warning("窗口=%s 打造：打开打造面板失败", agent.hwnd)
            return False

        # ---- 打造-打造装备-收集材料 已在目标装备页？否则 切换等级 -> 切换装备 ----
        if not self._ocr_equip_visible(agent, equip_name):
            if not self._dazao_select_level(agent, level):
                logger.warning("窗口=%s 打造：选择等级 %s 失败", agent.hwnd, level)
                return False
            if not self._dazao_select_category(agent, category):
                logger.warning("窗口=%s 打造：选择品类 %s 失败", agent.hwnd, category)
                return False

        # ---- 打造-打造装备-收集材料：买材料 -> 普通打造 ----
        return self._dazao_collect_and_build(agent, equip_name)

    def _in_changan_main(self, agent) -> bool:
        """Maa「打造-在长安主界面」= And(OCR 长安城, jiahao)。"""
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        if not self._find_text_in(self._ocr_lines(agent), ("长安城",),
                                  self._fraction_region(w, h, self.ROI_CHANGAN_OCR)):
            return False
        return self._match_any(agent, self.T_JIAHAO,
                               self._fraction_region(w, h, self.ROI_JIAHAO_BR),
                               self.TH_MAIN_INDICATOR) is not None

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
            # [JumpBack]关闭整点活动弹窗
            m = self._match_any(agent, self.T_RENWU_TANCHUANG,
                                self._fraction_region(w, h, self.ROI_RENWU_TANCHUANG),
                                self.TH_RENWU_TANCHUANG)
            if m:
                logger.info("窗口=%s 关闭整点活动弹窗 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(0.5)
                continue
            # 打开大地图成功 -> 传送长安城
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
                mm_roi = self._fraction_region(w, h, self.ROI_MINIMAP)
                m = self._match_any(agent, self.T_MINIMAP, mm_roi, self.TH_MINIMAP)
                hit = m is not None or self._colormatch(
                    img, mm_roi, self.CM_MINIMAP_LOWER, self.CM_MINIMAP_UPPER,
                    self.CM_MINIMAP_COUNT)
                if hit:
                    fx, fy = int(w * self.POS_MINIMAP[0]), int(h * self.POS_MINIMAP[1])
                    logger.info("窗口=%s 点击小地图图标 (%d,%d)", agent.hwnd, fx, fy)
                    agent.click(fx, fy)
                    clicked_icon = True
                    time.sleep(1.0)
                    continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 打开大地图/传送长安城超时", agent.hwnd)
        return False

    def _dazao_open_panel(self, agent) -> bool:
        """Maa「打造-展开菜单-加号」->「打造-点击打造入口」->「打造-打开成功」。"""
        deadline = time.monotonic() + self.node_timeout
        clicked_plus = False
        clicked_entry = False
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            # [JumpBack]关闭整点活动弹窗
            m = self._match_any(agent, self.T_RENWU_TANCHUANG,
                                self._fraction_region(w, h, self.ROI_RENWU_TANCHUANG),
                                self.TH_RENWU_TANCHUANG)
            if m:
                agent.click(m[0], m[1])
                time.sleep(0.5)
                continue
            # 打造-打开成功：dazao_active/inactive 页签 -> 点击
            tab_roi = self._fraction_region(w, h, self.ROI_DAZAO_TAB)
            m = self._match_any(agent, self.T_DAZAO_TAB, tab_roi, self.TH_DAZAO_TAB)
            if m:
                logger.info("窗口=%s 打造面板已打开，点击打造页签 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(1.0)
                self._ocr_cache = None
                return True
            if not clicked_plus:
                # 打造-展开菜单-加号
                m = self._match_any(agent, self.T_JIAHAO,
                                    self._fraction_region(w, h, self.ROI_JIAHAO_BR),
                                    self.TH_MAIN_INDICATOR)
                if m:
                    logger.info("窗口=%s 打造：点击右下角加号 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    clicked_plus = True
                    time.sleep(1.0)
                    continue
            elif not clicked_entry:
                # 打造-点击打造入口
                m = self._match_any(agent, self.T_DAZAO_RUKOU,
                                    self._fraction_region(w, h, self.ROI_DAZAO_RUKOU),
                                    self.TH_DAZAO_RUKOU)
                if m:
                    logger.info("窗口=%s 打造：点击打造入口 %s", agent.hwnd, m[:2])
                    agent.click(m[0], m[1])
                    clicked_entry = True
                    time.sleep(1.5)
                    continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        return False

    def _ocr_equip_visible(self, agent, equip_name: str) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        return self._find_text_in(self._ocr_lines(agent), (equip_name,),
                                  self._fraction_region(w, h, self.ROI_EQUIP_NAME)) is not None

    def _dazao_select_level(self, agent, level: str) -> bool:
        """Maa「打造-切换等级」：展开等级界面 -> 点全部 -> 上滑x3 -> 选目标等级(下滑 max 10)。"""
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            # 打造-切换等级-已展开等级界面：OCR 全部 -> 点击
            pos = self._find_text_in(self._ocr_lines(agent), ("全部",),
                                     self._fraction_region(w, h, self.ROI_QUANBU))
            if pos:
                logger.info("窗口=%s 打造：点击全部等级 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(0.8)
                self._ocr_cache = None
                break
            # [JumpBack]打造-切换等级-点击展开等级界面
            m = self._match_any(agent, self.T_ZHANKAI,
                                self._fraction_region(w, h, self.ROI_ZHANKAI),
                                self.TH_ZHANKAI)
            if m:
                logger.info("窗口=%s 打造：展开等级界面 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(0.8)
                continue
            if self._sleep(self.poll_interval):
                raise _Aborted()
        else:
            return False

        # 打造-切换等级-向上滑动三次
        for _ in range(3):
            self._swipe_vertical(agent, self.SWIPE_LEVEL_X,
                                 self.SWIPE_LEVEL_UP_FROM, self.SWIPE_LEVEL_UP_TO)
            time.sleep(0.3)
        # 打造-切换等级-选择目标等级（OCR level）+ [JumpBack]向下滑动 max 10
        for swipe in range(11):
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            pos = self._find_text_in(self._ocr_lines(agent), (level,),
                                     self._fraction_region(w, h, self.ROI_LEVEL_LIST),
                                     exact=True)
            if pos:
                logger.info("窗口=%s 打造：选择等级 %s %s", agent.hwnd, level, pos)
                agent.click(pos[0], pos[1])
                time.sleep(0.8)
                self._ocr_cache = None
                # 打造-切换等级-结束过渡
                fx = int(w * self.POS_GUODU_CLICK[0])
                fy = int(h * self.POS_GUODU_CLICK[1])
                agent.click(fx, fy)
                time.sleep(0.8)
                return True
            if swipe < 10:
                self._swipe_vertical(agent, self.SWIPE_LEVEL_X,
                                     self.SWIPE_LEVEL_DOWN_FROM, self.SWIPE_LEVEL_DOWN_TO)
                self._ocr_cache = None
                time.sleep(0.5)
        return False

    def _dazao_select_category(self, agent, category: str) -> bool:
        """Maa「打造-切换装备」：下滑x3 -> 选目标品类(上滑 max 30)。"""
        for _ in range(3):
            self._swipe_vertical(agent, self.SWIPE_EQUIP_X,
                                 self.SWIPE_EQUIP_DOWN_FROM, self.SWIPE_EQUIP_DOWN_TO)
            time.sleep(0.3)
        for swipe in range(31):
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            pos = self._find_text_in(self._ocr_lines(agent), (category,),
                                     self._fraction_region(w, h, self.ROI_CATEGORY_LIST),
                                     exact=True)
            if pos:
                logger.info("窗口=%s 打造：选择品类 %s %s", agent.hwnd, category, pos)
                agent.click(pos[0], pos[1])
                time.sleep(0.8)
                self._ocr_cache = None
                return True
            if swipe < 30:
                self._swipe_vertical(agent, self.SWIPE_EQUIP_X,
                                     self.SWIPE_EQUIP_UP_FROM, self.SWIPE_EQUIP_UP_TO)
                self._ocr_cache = None
                time.sleep(0.4)
        return False

    def _dazao_collect_and_build(self, agent, equip_name: str) -> bool:
        """Maa「打造-打造装备-收集材料」的 next 列表循环。"""
        deadline = time.monotonic() + self.dazao_timeout
        while time.monotonic() < deadline:
            self._check_stop(agent)
            img = self._image(agent)
            if img is None:
                return False
            h, w = img.shape[:2]
            # 装备名判定（Maa 节点 recognition；被 override 为命中装备名）
            if not self._ocr_equip_visible(agent, equip_name):
                if self._sleep(self.poll_interval):
                    raise _Aborted()
                continue
            # [JumpBack]打造-购买材料-购买制造书
            if self._dazao_buy_material(agent, img, self.CM_ROI_BOOK, stall=False):
                continue
            # [JumpBack]打造-购买材料-购买精铁
            if self._dazao_buy_material(agent, img, self.CM_ROI_TIE, stall=False):
                continue
            # [JumpBack]打造-购买材料-购买打造符
            if self._dazao_buy_material(agent, img, self.CM_ROI_FU, stall=True):
                continue
            # [JumpBack]打造-购买材料-取消石头
            m = self._match_any(agent, self.T_SHITOU,
                                self._fraction_region(w, h, self.ROI_SHITOU),
                                self.TH_SHITOU)
            if m:
                logger.info("窗口=%s 打造：取消已选石头 %s", agent.hwnd, m[:2])
                agent.click(m[0], m[1])
                time.sleep(0.8)
                continue
            # 打造-购买材料-点击打造（OCR 普通打造）
            pos = self._find_text_in(self._ocr_lines(agent), ("普通打造",),
                                     self._fraction_region(w, h, self.ROI_PUTONG_DAZAO))
            if pos:
                logger.info("窗口=%s 打造：点击普通打造 %s", agent.hwnd, pos)
                agent.click(pos[0], pos[1])
                time.sleep(2.0)
                self._ocr_cache = None
                # [JumpBack]打造-购买材料-点击打造-确认
                self._click_queding_in(agent, self.ROI_QUEDING_DAZAO, timeout=10.0)
                self._run_node(agent, self._node_panduan_zhujiemian, 30.0, "打造后回主界面")
                logger.info("窗口=%s 打造子链路完成: %s", agent.hwnd, equip_name)
                return True
            if self._sleep(self.poll_interval):
                raise _Aborted()
        logger.warning("窗口=%s 打造：收集材料超时", agent.hwnd)
        return False

    def _dazao_buy_material(self, agent, img, cm_roi_frac, stall: bool) -> bool:
        """Maa 购买材料 JumpBack：ColorMatch 缺料 -> 商会/摆摊 -> 购买 -> 确定 -> 返回。"""
        h, w = img.shape[:2]
        cm_roi = self._fraction_region(w, h, cm_roi_frac)
        if not self._colormatch(img, cm_roi, self.CM_MATERIAL_LOWER,
                                self.CM_MATERIAL_UPPER, self.CM_MATERIAL_COUNT):
            return False
        cx, cy = cm_roi[0] + cm_roi[2] // 2, cm_roi[1] + cm_roi[3] // 2
        logger.info("窗口=%s 打造：材料缺失，点击 (%d,%d) (%s)",
                    agent.hwnd, cx, cy, "摆摊" if stall else "商会")
        agent.click(cx, cy)
        time.sleep(0.8)
        self._ocr_cache = None
        # 点击商会 / 点击摆摊（OCR + target_offset 上移 50px）
        lines_roi = self.ROI_BAITAN_LIST if stall else self.ROI_SHANGHUI
        keyword = "摆摊" if stall else "商会"
        img2 = self._image(agent)
        if img2 is not None:
            pos = self._find_text_in(self._ocr_lines(agent), (keyword,),
                                     self._fraction_region(w, h, lines_roi))
            if pos:
                off = int(h * (50.0 / 720.0))
                agent.click(pos[0], pos[1] - off)
                logger.info("窗口=%s 打造：点击%s %s", agent.hwnd, keyword, (pos[0], pos[1] - off))
                time.sleep(1.0)
                self._ocr_cache = None
        if stall:
            # [JumpBack]打造-购买材料-点击摆摊-选中物品（ColorMatch）
            img3 = self._image(agent)
            if img3 is not None:
                sel_roi = self._fraction_region(w, h, self.CM_ROI_SELECT)
                if self._colormatch(img3, sel_roi, self.CM_SELECT_LOWER,
                                    self.CM_SELECT_UPPER, self.CM_SELECT_COUNT):
                    sx, sy = sel_roi[0] + sel_roi[2] // 2, sel_roi[1] + sel_roi[3] // 2
                    agent.click(sx, sy)
                    time.sleep(0.8)
        # 打造-购买材料-点击购买
        self._click_text_once(agent, ("购买",), self.ROI_GOUMAI, wait=1.0)
        # [JumpBack]打造-购买材料-点击购买-确认
        self._click_queding_in(agent, self.ROI_QUEDING_BUY, timeout=5.0)
        # 打造-购买材料-点击返回
        agent.press_key("esc")
        time.sleep(1.0)
        self._ocr_cache = None
        return True

    def _click_text_once(self, agent, keywords, roi_frac, wait: float = 1.0) -> bool:
        img = self._image(agent)
        if img is None:
            return False
        h, w = img.shape[:2]
        pos = self._find_text_in(self._ocr_lines(agent), keywords,
                                 self._fraction_region(w, h, roi_frac))
        if not pos:
            return False
        agent.click(pos[0], pos[1])
        logger.info("窗口=%s 点击 %s %s", agent.hwnd, "/".join(keywords), pos)
        time.sleep(wait)
        self._ocr_cache = None
        return True

    def _click_queding_in(self, agent, roi_frac, timeout: float = 10.0) -> bool:
        """在指定 ROI 内等 OCR"确定"并点击。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._check_stop(agent)
            if self._click_text_once(agent, ("确定",), roi_frac, wait=1.0):
                return True
            if self._sleep(self.poll_interval):
                raise _Aborted()
        return False

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

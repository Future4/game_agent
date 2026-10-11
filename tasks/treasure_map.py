"""宝图任务第一阶段：活动界面参加宝图并选择“听听无妨”。"""
import logging
import os
import time
from typing import Callable, Optional

from domain.tasks import TaskContext, TaskDefinition, TaskSnapshot, TaskStatus
from tasks.base import AutomationTask

logger = logging.getLogger(__name__)


def _save_click_debug(agent, match, click_pos) -> None:
    """Save the current frame with match/click markers for coordinate QA."""
    try:
        import cv2
        import numpy as np
        image = agent.capture()
        if image is None:
            return
        os.makedirs("debug", exist_ok=True)
        annotated = image.copy()
        cv2.drawMarker(annotated, (int(match[0]), int(match[1])), (0, 0, 255), cv2.MARKER_CROSS, 24, 3)
        cv2.circle(annotated, (int(click_pos[0]), int(click_pos[1])), 12, (255, 0, 0), 3)
        cv2.putText(annotated, f"match={match[0]},{match[1]}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(annotated, f"click={click_pos[0]},{click_pos[1]}", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
        path = os.path.abspath(os.path.join("debug", f"treasure_map_changan_{agent.hwnd}.png"))
        cv2.imwrite(path, annotated)
        logger.info("窗口=%s 已保存长安城点击调试截图：%s", agent.hwnd, path)
    except Exception:
        logger.exception("保存长安城点击调试截图失败")


class TreasureMapBanditTask(AutomationTask):
    """Run the confirmed navigation/dialogue part of the treasure-map task.

    The first and third controls are stable client-layout anchors from the
    supplied screenshots. Text and button recognition gates every subsequent
    click, so a changed screen is waited on instead of clicked blindly.
    """

    definition = TaskDefinition("treasure_map", "宝图任务", "打强盗获取藏宝图")
    poll_interval = 0.5
    # Ten automatic fights can take several minutes; the completion template
    # is the authoritative stop condition rather than a fixed sleep/count.
    timeout_seconds = 900.0

    def run(self, context: TaskContext, on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        agent = context.agent
        self._on_update = on_update
        logger.info("宝图任务启动，窗口句柄=%s", getattr(agent, "hwnd", None))
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.total_steps = 7
        self._completion_scroll_attempts = 0
        self._treasure_count = 0
        self._reward_visible = False
        self._already_completed = False
        self._report(on_update, "等待游戏画面")
        stages = (
            self._open_activity,
            self._select_daily_activity,
            self._join_treasure,
            self._wait_for_dialogue,
            self._choose_listen,
            self._wait_for_treasure_rewards,
            self._wait_for_all_treasure_completed,
        )
        started = time.monotonic()
        for index, stage in enumerate(stages, 1):
            self.snapshot.completed_steps = index - 1
            self._report(on_update, f"步骤 {index}/{len(stages)}：{stage.__name__}")
            logger.info("窗口=%s 开始步骤 %d/%d：%s", agent.hwnd, index, len(stages), stage.__name__)
            while not self._stop_event.is_set():
                if time.monotonic() - started > self.timeout_seconds:
                    self.snapshot.status = TaskStatus.FAILED
                    self._report(on_update, "任务超时，请检查游戏窗口和识别模板")
                    return
                if stage(agent):
                    logger.info("窗口=%s 步骤完成：%s", agent.hwnd, stage.__name__)
                    break
                if self._stop_event.wait(self.poll_interval):
                    return
        self.snapshot.completed_steps = len(stages)
        self.snapshot.status = TaskStatus.COMPLETED
        logger.info("窗口=%s 宝图第一阶段完成", agent.hwnd)
        self._report(on_update, "检测到宝图任务 10/10 完成，第一阶段结束")

    def _wait_for_treasure_rewards(self, agent) -> bool:
        """Count one reward toast per fight, using an appearance edge."""
        if self._already_completed:
            return True
        match = agent.detect_template_multiscale("treasure_obtained", threshold=0.68)
        visible = bool(match)
        logger.info("窗口 %s 藏宝图获得提示=%s，当前数量=%s/10", agent.hwnd, match, self._treasure_count)
        if visible and not self._reward_visible:
            self._treasure_count = min(10, self._treasure_count + 1)
            self.snapshot.message = f"已获得藏宝图 {self._treasure_count}/10"
            self._reward_visible = True
            if self._on_update:
                self._on_update(self.snapshot)
        elif not visible:
            self._reward_visible = False
        # The game may briefly show the completion row before the tenth toast
        # is sampled; completion detection remains the final authoritative gate.
        return self._treasure_count >= 10

    def _wait_for_all_treasure_completed(self, agent) -> bool:
        """Wait until the activity row shows 次数10/10、活跃10/10、完成."""
        if self._already_completed:
            return True
        match = agent.detect_template_multiscale("treasure_completed", threshold=0.88)
        logger.info("窗口=%s 宝图完成状态匹配结果=%s", agent.hwnd, match)
        if match:
            self.snapshot.message = "已检测到宝图任务完成（10/10）"
            return True
        # The activity list is scrollable. The unfinished row is near the top,
        # while the completed row can move below the viewport after the state
        # changes. Scroll only after a failed scan, and cap attempts to avoid
        # endlessly cycling the list.
        if self._completion_scroll_attempts < 8:
            self._completion_scroll_attempts += 1
            image = agent.capture()
            if image is not None:
                height, width = image.shape[:2]
                scroll_pos = (int(width * 0.60), int(height * 0.52))
            else:
                scroll_pos = (500, 330)
            result = agent.scroll(-3, x=scroll_pos[0], y=scroll_pos[1])
            logger.info("窗口=%s 未找到完成状态，滚动第%s次，行数=-3，位置=%s，结果=%s",
                        agent.hwnd, self._completion_scroll_attempts, scroll_pos, result)
            time.sleep(0.8)
        else:
            logger.info("窗口=%s 已达到完成状态最大滚动次数", agent.hwnd)
        return False

    def _match_and_click_center(self, agent, template_name: str, region=None, threshold: float = 0.65, label: str = "") -> bool:
        image = agent.capture()
        if image is None:
            return False
        if region is None:
            match = agent.detect_template_multiscale(template_name, threshold)
        else:
            match = agent.detect_template_multiscale_region(template_name, region, threshold)
        logger.info("窗口=%s %s，模板=%s，结果=%s，截图尺寸=%sx%s", agent.hwnd, label, template_name, match, image.shape[1], image.shape[0])
        if not match:
            raw = (agent.detect_template_multiscale_region(template_name, region, 0.0)
                   if region is not None else agent.detect_template_multiscale(template_name, 0.0))
            os.makedirs("debug", exist_ok=True)
            path = os.path.abspath(os.path.join("debug", f"{template_name}_not_matched_{agent.hwnd}.png"))
            try:
                import cv2
                cv2.imwrite(path, image)
            except Exception:
                logger.exception("保存模板匹配失败截图失败")
            logger.warning("窗口=%s %s，最佳原始匹配=%s，诊断截图=%s", agent.hwnd, label, raw, path)
            return False
        # All matcher APIs return the center of the matched template.
        result = bool(agent.click(match[0], match[1]))
        logger.info("窗口=%s %s，中心点击=%s，结果=%s", agent.hwnd, label, match[:2], result)
        time.sleep(1.0)
        return result

    def _open_activity(self, agent) -> bool:
        image = agent.capture()
        if image is None:
            return False
        h, w = image.shape[:2]
        return self._match_and_click_center(agent, "activity_button", (0, 0, min(w, 400), min(h, 180)), 0.35, "活动按钮")

    def _select_daily_activity(self, agent) -> bool:
        image = agent.capture()
        if image is None:
            return False
        h, w = image.shape[:2]
        return self._match_and_click_center(agent, "daily_activity", (0, 0, min(w, 260), min(h, 260)), 0.60, "日常活动")

    def _join_treasure(self, agent) -> bool:
        if self._find_completed_treasure(agent):
            self._already_completed = True
            self.snapshot.message = "检测到宝图任务已经完成（10/10）"
            logger.info("窗口=%s 已完成宝图任务，跳过参加按钮", agent.hwnd)
            return True
        image = agent.capture()
        if image is None:
            return False
        h, w = image.shape[:2]
        # treasure_row contains the whole 宝图任务 row; its right-side
        # 参加 button center is (252,38) in the 294x76 reference template.
        match = agent.detect_template_multiscale_region("treasure_row", (0, 0, w, h), 0.82)
        logger.info("窗口=%s 宝图任务行匹配结果=%s", agent.hwnd, match)
        if not match:
            return False
        click_pos = (match[0] + 105, match[1])
        result = bool(agent.click(*click_pos))
        logger.info("窗口=%s 宝图参加按钮：任务行中心=%s，参加按钮中心=(252,38)，点击=%s，结果=%s", agent.hwnd, match, click_pos, result)
        time.sleep(1.0)
        return result

    def _find_completed_treasure(self, agent) -> bool:
        for attempt in range(9):
            image = agent.capture()
            if image is None:
                return False
            height, width = image.shape[:2]
            # Only inspect the scrollable activity list, excluding the fixed
            # activity header, left navigation and bottom reward strip.
            list_region = (int(width * 0.18), int(height * 0.14),
                           int(width * 0.78), int(height * 0.66))
            # A low threshold falsely matches neighboring task rows. The
            # supplied completed-row crop should be a near-exact match.
            match = agent.detect_template_multiscale_region(
                "treasure_completed", list_region, threshold=0.88
            )
            logger.info("窗口=%s 已完成宝图扫描第%s次，结果=%s", agent.hwnd, attempt + 1, match)
            if match:
                return True
            if attempt < 8:
                position = (int(width * 0.60), int(height * 0.42))
                result = agent.scroll(-5, x=position[0], y=position[1])
                logger.info("窗口=%s 活动列表向下滚动，次数=%s，行数=-5，位置=%s，结果=%s", agent.hwnd, attempt + 1, position, result)
                time.sleep(0.8)
        return False

    def _wait_for_dialogue(self, agent) -> bool:
        if self._already_completed:
            return True
        match = agent.detect_template_multiscale("baotu_dialogue", threshold=0.65)
        logger.info("窗口=%s 等待宝图对话，匹配结果=%s", agent.hwnd, match)
        return bool(match)

    def _open_world_map(self, agent) -> bool:
        # Match the complete supplied upper-left anchor (map button + coords),
        # then click the center of the map-button portion of that template.
        image = agent.capture()
        match = None
        if image is not None:
            h, w = image.shape[:2]
            match = agent.detect_template_region("map_anchor", (0, 0, min(w, 220), min(h, 150)), threshold=0.55)
        if match:
            # detect_template_region returns the *full template center*.
            # map_anchor is 155x64; the world-map button is its left 50x64
            # portion, whose center is (25,32). Convert that sub-region center
            # from template-relative coordinates to the live image.
            click_pos = (match[0] - 52, match[1])
            result = bool(agent.click(*click_pos))
            logger.info("hwnd=%s map anchor full-center=%s subcenter=(25,32) click=%s result=%s", agent.hwnd, match, click_pos, result)
        else:
            result = bool(agent.click_fixed(29, 31))
            logger.warning("hwnd=%s map anchor not found; fixed fallback=(29,31) result=%s", agent.hwnd, result)
        # The world-map panel animates in. Do not inspect/click its contents
        # during the opening transition; the game can drop those clicks.
        if result:
            time.sleep(1.0)
        return result

    def _select_changan(self, agent) -> bool:
        pos = agent.detect_text("长安城", threshold=0.55)
        logger.info("hwnd=%s changan OCR result=%s", agent.hwnd, pos)
        if pos:
            result = bool(agent.click(*pos))
            logger.info("hwnd=%s changan OCR click=%s result=%s", agent.hwnd, pos, result)
            return result
        # The world map has several visually similar buildings. Restrict the
        # match to the central Chang'an area to avoid a high-score false hit.
        image = agent.capture()
        match = None
        if image is not None:
            height, width = image.shape[:2]
            region = (int(width * 0.25), int(height * 0.25), int(width * 0.50), int(height * 0.55))
            match = agent.detect_template_multiscale_region("changan_city", region, threshold=0.70)
            logger.info("hwnd=%s changan image=%sx%s region=%s", agent.hwnd, width, height, region)
        logger.info("hwnd=%s changan template region result=%s", agent.hwnd, match)
        if match:
            # The requested behavior is to click the center of the supplied
            # Chang'an template itself.
            click_pos = (match[0], match[1])
            _save_click_debug(agent, match, click_pos)
            # Give the fully-rendered map a short settling period before the
            # navigation click, then allow the scene transition to begin.
            time.sleep(1.0)
            result = bool(agent.click(*click_pos))
            logger.info("hwnd=%s changan template match=%s click=%s result=%s", agent.hwnd, match, click_pos, result)
            time.sleep(1.5)
            # A successful PostMessage only means the message was queued. If
            # the world map is still visible, retry this stage instead of
            # opening the coordinate panel on the wrong screen.
            current = agent.capture()
            if current is not None:
                still_map = agent.vision.detect_template(current, "changan_city", threshold=0.90)
                logger.info("hwnd=%s post-click world-map check=%s", agent.hwnd, still_map)
                if still_map:
                    # Some Unity-rendered map layers ignore background
                    # PostMessage clicks. Retry once with a real foreground
                    # mouse event while preserving background operation for
                    # all other windows/steps.
                    logger.warning("hwnd=%s world map unchanged; retrying foreground click=%s", agent.hwnd, click_pos)
                    foreground_result = bool(agent.click_foreground(*click_pos))
                    logger.info("hwnd=%s changan foreground click result=%s", agent.hwnd, foreground_result)
                    time.sleep(1.5)
                    return foreground_result
            return result
        # Do not click a guessed point: at a different window size it can land
        # above the city icon. Keep polling until the scaled template matches.
        return False

    def _open_city_map(self, agent) -> bool:
        # After entering Chang'an, map_anchor appears again in the upper-left.
        # Its right 105x64 portion opens the city interior map. The matcher
        # returns the full 155x64 template center (~77,32), while the desired
        # sub-region center is (~102,32), hence the +25 x offset.
        pos = agent.detect_text("长安城", threshold=0.55)
        logger.info("hwnd=%s city map OCR result=%s", agent.hwnd, pos)
        if pos and pos[0] < 180 and pos[1] < 100:
            # OCR location text itself is not the action target; continue to
            # template matching so the right half of map_anchor is selected.
            logger.info("hwnd=%s city map OCR confirms upper-left anchor", agent.hwnd)

        image = agent.capture()
        match = None
        if image is not None:
            height, width = image.shape[:2]
            match = agent.detect_template_region(
                "map_anchor", (0, 0, min(width, 220), min(height, 150)), threshold=0.55
            )
        if match:
            click_pos = (match[0] + 25, match[1])
            result = bool(agent.click(*click_pos))
            logger.info("hwnd=%s city map anchor full-center=%s subcenter=(102,32) click=%s result=%s",
                        agent.hwnd, match, click_pos, result)
            time.sleep(1.2)
            return result

        # Safe fallback for older layouts where the complete anchor template
        # is temporarily obscured during the scene transition.
        time.sleep(1.0)
        result = bool(agent.click_fixed(100, 45))
        logger.warning("hwnd=%s city map anchor not found; fixed fallback=(100,45) result=%s",
                       agent.hwnd, result)
        time.sleep(1.2)
        return result

    def _select_shopkeeper(self, agent) -> bool:
        pos = agent.detect_text("店小二", threshold=0.55)
        logger.info("hwnd=%s shopkeeper OCR result=%s", agent.hwnd, pos)
        if pos:
            agent.click(*pos)
            return True
        match = agent.detect_template_multiscale("shopkeeper", threshold=0.62)
        logger.info("hwnd=%s shopkeeper multiscale template result=%s", agent.hwnd, match)
        if match:
            agent.click(match[0], match[1])
            return True
        return False

    def _choose_listen(self, agent) -> bool:
        pos = agent.detect_text("听听无妨", threshold=0.55)
        logger.info("hwnd=%s listen OCR result=%s", agent.hwnd, pos)
        if pos:
            agent.click(*pos)
            return True
        match = agent.detect_template("baotu_dialogue", threshold=0.82)
        logger.info("hwnd=%s listen template result=%s", agent.hwnd, match)
        if match:
            agent.click(match[0], match[1])
            return True
        return False

    def _report(self, callback, message: str) -> None:
        self.snapshot.message = message
        if callback:
            callback(self.snapshot)

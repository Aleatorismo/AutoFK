import time
import win32gui
import win32con
import win32api
from mss import mss
from paddleocr import PaddleOCR
import numpy as np
from PIL import Image
import ctypes  # For screen metrics, though not strictly used for clicking logic here

# --- 用户配置区域 --- #
# 请根据您的实际游戏窗口和界面调整以下常量

# 特定点击位置的比例 (相对于游戏窗口的宽和高)
# (X轴比例, Y轴比例)
SPECIFIC_POS_A_X_RATIO = 0.75
SPECIFIC_POS_A_Y_RATIO = 0.7
SPECIFIC_POS_B_X_RATIO = 0.45
SPECIFIC_POS_B_Y_RATIO = 0.7
SPECIFIC_POS_C_X_RATIO = 0.5
SPECIFIC_POS_C_Y_RATIO = 0.9

# 新增：“战斗”按钮的特定点击位置比例
SPECIFIC_POS_BATTLE_X_RATIO = 0.55
SPECIFIC_POS_BATTLE_Y_RATIO = 0.92

# Y轴偏移量的比例 (相对于游戏窗口的高度)
Y_OFFSET_GATE_RATIO = 0.35
Y_OFFSET_SHOP_ITEM_RATIO = 0.35
Y_OFFSET_BOSS_RATIO = 0.35

# OCR识别置信度阈值 (0.0 到 1.0)
CONFIDENCE_THRESHOLD = 0.6  # 低于此置信度的OCR结果将被忽略

# 游戏窗口标题 (需要精确匹配或包含此字符串)
# 示例: "BlueStacks App Player" 或您游戏的实际标题
GAME_WINDOW_TITLE = "BlueStacks App Player"

# --- 调试选项 ---
# 设置为整数可以直接从第几步开始，例如 DEBUG_START_STEP = 4 会从步骤4开始。
# 设置为 None 或 1 则从头开始。
DEBUG_START_STEP = None
# --- 用户配置区域结束 --- #


class AutoLabyrinth:
    def __init__(self, window_title):
        self.window_title = window_title
        self.hwnd = None
        print("正在初始化PaddleOCR引擎，可能需要一些时间...")
        # lang='ch' 表示中文识别。show_log=False 禁止打印PaddleOCR的日志
        self.ocr_engine = PaddleOCR(
            use_angle_cls=True, lang='ch', show_log=False)
        print("PaddleOCR引擎初始化完成。")
        self.sct = mss()
        self.window_rect = None

        # 初始化动态计算的坐标和偏移量 (像素值)
        # 这些将在 _update_dynamic_coords 中根据窗口大小实际计算
        self.specific_pos_a_px = (0, 0)
        self.specific_pos_b_px = (0, 0)
        self.specific_pos_c_px = (0, 0)
        self.specific_pos_battle_px = (0, 0)  # 初始化战斗按钮的像素坐标
        self.y_offset_gate_px = 0
        self.y_offset_shop_item_px = 0
        self.y_offset_boss_px = 0  # 虽然当前未使用，但进行初始化

    def _update_dynamic_coords(self):
        if self.window_rect and self.window_rect.get("width") and self.window_rect.get("height"):
            win_w = self.window_rect["width"]
            win_h = self.window_rect["height"]

            if win_w <= 0 or win_h <= 0:
                print("警告: _update_dynamic_coords 接收到无效的窗口尺寸，无法更新动态坐标。将使用默认值(0)。")
                self.specific_pos_a_px = (0, 0)
                self.specific_pos_b_px = (0, 0)
                self.specific_pos_c_px = (0, 0)
                self.specific_pos_battle_px = (0, 0)  # 重置战斗按钮的像素坐标
                self.y_offset_gate_px = 0
                self.y_offset_shop_item_px = 0
                self.y_offset_boss_px = 0
                return

            self.specific_pos_a_px = (
                int(SPECIFIC_POS_A_X_RATIO * win_w), int(SPECIFIC_POS_A_Y_RATIO * win_h))
            self.specific_pos_b_px = (
                int(SPECIFIC_POS_B_X_RATIO * win_w), int(SPECIFIC_POS_B_Y_RATIO * win_h))
            self.specific_pos_c_px = (
                int(SPECIFIC_POS_C_X_RATIO * win_w), int(SPECIFIC_POS_C_Y_RATIO * win_h))
            self.specific_pos_battle_px = (int(SPECIFIC_POS_BATTLE_X_RATIO * win_w), int(
                SPECIFIC_POS_BATTLE_Y_RATIO * win_h))  # 计算战斗按钮的像素坐标

            self.y_offset_gate_px = int(Y_OFFSET_GATE_RATIO * win_h)
            self.y_offset_shop_item_px = int(Y_OFFSET_SHOP_ITEM_RATIO * win_h)
            self.y_offset_boss_px = int(Y_OFFSET_BOSS_RATIO * win_h)

            # print(f"动态坐标已更新: A={self.specific_pos_a_px}, B={self.specific_pos_b_px}, C={self.specific_pos_c_px}")
            # print(f"动态Y偏移已更新: Gate={self.y_offset_gate_px}, Shop={self.y_offset_shop_item_px}, Boss={self.y_offset_boss_px}")
        else:
            # print("警告: _update_dynamic_coords 未找到有效窗口矩形或尺寸，无法更新动态坐标。将使用默认值(0)。")
            self.specific_pos_a_px = (0, 0)
            self.specific_pos_b_px = (0, 0)
            self.specific_pos_c_px = (0, 0)
            self.specific_pos_battle_px = (0, 0)  # 重置战斗按钮的像素坐标
            self.y_offset_gate_px = 0
            self.y_offset_shop_item_px = 0
            self.y_offset_boss_px = 0

    def find_window(self):
        self.hwnd = None  # Reset hwnd before search

        def enum_windows_proc(hwnd, lParam):
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                if window_text and self.window_title in window_text:
                    self.hwnd = hwnd
                    return False  # Stop enumeration once found
            return True

        win32gui.EnumWindows(enum_windows_proc, 0)
        if self.hwnd:
            print(f"窗口 '{self.window_title}' 已找到 (HWND: {self.hwnd}).")
            try:
                # 尝试将窗口置于前台并恢复（如果最小化）
                # win32gui.SetForegroundWindow(self.hwnd) # 慎用，可能会打断用户操作
                # win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)  # 短暂等待窗口状态稳定
            except Exception as e:
                print(f"设置窗口到前台或恢复时发生错误: {e}")
            return True
        else:
            print(f"错误: 未找到标题包含 '{self.window_title}' 的可见窗口。")
            print("请检查 GAME_WINDOW_TITLE 是否正确，以及游戏窗口是否已打开且可见。")
            return False

    def get_window_rect(self):
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            if not self.find_window():  # Attempt to re-find the window
                self.window_rect = None
                self._update_dynamic_coords()  # 确保在窗口无效时也更新/重置坐标
                return None
        try:
            rect = win32gui.GetWindowRect(self.hwnd)
            # 检查窗口尺寸是否有效
            if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
                print(
                    f"警告: 窗口 '{self.window_title}' (HWND: {self.hwnd}) 尺寸无效或已最小化。")
                # 尝试恢复窗口
                # win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                # time.sleep(0.5) # 等待恢复
                # rect = win32gui.GetWindowRect(self.hwnd) # 再次获取
                # if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
                #     print("错误: 恢复后窗口尺寸仍然无效。")
                self.window_rect = None
                self._update_dynamic_coords()  # 确保在窗口无效时也更新/重置坐标
                return None

            self.window_rect = {
                "left": rect[0], "top": rect[1],
                "width": rect[2] - rect[0], "height": rect[3] - rect[1]
            }
            self._update_dynamic_coords()  # 成功获取矩形后更新动态坐标
            # print(f"窗口区域: {self.window_rect}")
            return self.window_rect
        except win32gui.error as e:
            print(f"获取窗口矩形失败 (win32gui.error): {e} (HWND: {self.hwnd})")
            self.hwnd = None  # Invalidate hwnd as it might be closed or invalid
            self.window_rect = None
            self._update_dynamic_coords()  # 确保在窗口无效时也更新/重置坐标
            return None

    def capture_window(self):
        monitor = self.get_window_rect()
        if not monitor or monitor["width"] <= 0 or monitor["height"] <= 0:
            # print("错误: 无法获取有效的窗口区域进行截图。")
            return None

        try:
            sct_img = self.sct.grab(monitor)
            # 将 BGRA 转换为 RGB (Pillow 默认使用 RGB)
            img = Image.frombytes("RGB", sct_img.size,
                                  sct_img.rgb, "raw", "BGR")
            return np.array(img)
        except Exception as e:
            print(f"截图失败: {e}")
            # 常见问题：窗口句柄失效，窗口被遮挡，窗口最小化等
            if "DMABUF" in str(e) or "XGetImage" in str(e):  # Linux specific errors
                print("提示: 在某些Linux环境下，mss截图可能存在问题。请确保窗口可见且未被完全遮挡。")
            return None

    def perform_ocr(self, image_np):
        if image_np is None:
            return []
        try:
            # result 是一个列表，通常我们关心 result[0]
            # result[0] 是一个包含多个识别行的列表
            # 每个识别行是 [box, (text, confidence)]
            # box 是四个点的坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            result = self.ocr_engine.ocr(image_np, cls=True)
            filtered_result = []
            if result and result[0]:  # 确保 result[0] 不是 None
                for line_info in result[0]:
                    text_info = line_info[1]  # (text, confidence)
                    if text_info[1] >= CONFIDENCE_THRESHOLD:
                        filtered_result.append(line_info)
            # if filtered_result:
            #     print(f"OCR 结果 (置信度 >= {CONFIDENCE_THRESHOLD}): {[item[1][0] for item in filtered_result]}")
            return filtered_result
        except Exception as e:
            print(f"OCR 识别失败: {e}")
            return []

    def _get_text_center(self, box_coords):
        # box_coords: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        # 计算文本框的中心点
        x_coords = [p[0] for p in box_coords]
        y_coords = [p[1] for p in box_coords]
        center_x = int(sum(x_coords) / 4)
        center_y = int(sum(y_coords) / 4)
        return center_x, center_y

    def find_text_locations(self, ocr_data, target_text, partial_match=True):
        locations = []  # 存储 (center_x, center_y, text_content, confidence)
        if not ocr_data:
            return locations

        for item in ocr_data:  # item is [box, (text, confidence)]
            box = item[0]
            text_content = item[1][0]
            confidence = item[1][1]
            found = False
            if partial_match:
                if target_text in text_content:
                    found = True
            else:  # 完全匹配
                if target_text == text_content:
                    found = True

            if found:
                center_x, center_y = self._get_text_center(box)
                locations.append(
                    (center_x, center_y, text_content, confidence))

        # if locations:
        #     print(f"查找文本 '{target_text}': 找到 {len(locations)} 处 - {[(loc[0], loc[1], loc[2][:15], f'{loc[3]:.2f}') for loc in locations]}")
        # else:
        #     print(f"查找文本 '{target_text}': 未找到。")
        return locations

    def click_at_relative(self, rel_x, rel_y, y_offset=0):
        if not self.window_rect:
            if not self.get_window_rect():  # 尝试重新获取
                print("错误: 尝试重新获取窗口矩形失败，无法点击。")
                return False

        # 确保窗口是活动窗口（可选，但有时是必要的）
        # current_fg_hwnd = win32gui.GetForegroundWindow()
        # if self.hwnd != current_fg_hwnd:
        #     print(f"警告: 目标窗口 (HWND {self.hwnd}) 不是前景窗口 (当前前景 HWND {current_fg_hwnd}). 尝试激活...")
        #     try:
        #         win32gui.SetForegroundWindow(self.hwnd)
        #         time.sleep(0.2) # 给窗口一点时间响应
        #     except Exception as e:
        #         print(f"激活窗口失败: {e}. 点击可能无效。")
        #         # return False # 可以选择如果激活失败则不点击

        # 将窗口内的相对坐标转换为屏幕绝对坐标
        abs_x = self.window_rect["left"] + rel_x
        abs_y = self.window_rect["top"] + rel_y + y_offset

        print(
            f"点击操作: 相对坐标({rel_x},{rel_y}) + Y偏移({y_offset}) -> 屏幕绝对坐标({abs_x},{abs_y})")

        # 移动鼠标到目标位置
        win32api.SetCursorPos((abs_x, abs_y))
        time.sleep(0.05)  # 短暂等待鼠标移动到位
        # 执行鼠标左键按下和抬起
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, abs_x, abs_y, 0, 0)
        time.sleep(0.05)  # 按下和抬起之间的短暂延迟
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, abs_x, abs_y, 0, 0)
        time.sleep(0.25)  # 点击后等待UI响应
        return True

    def click_text(self, target_text, ocr_data=None, y_offset=0, partial_match=True, click_first_if_multiple=True, timeout_no_ocr=0.1):
        """查找并点击文本，如果未提供ocr_data，则会进行一次快速OCR"""
        if ocr_data is None:
            # print(f"click_text: 未提供OCR数据，为 '{target_text}' 进行快速扫描...")
            start_ocr_time = time.time()
            # 短暂尝试获取OCR数据
            while time.time() - start_ocr_time < timeout_no_ocr + 0.01:
                image = self.capture_window()
                if image is None:
                    return False  # 截图失败则无法继续
                ocr_data = self.perform_ocr(image)
                if ocr_data:
                    break  # 获取到OCR结果
                time.sleep(0.1)  # 避免过于频繁的截图
            if not ocr_data:
                # print(f"click_text: 快速扫描未能为 '{target_text}' 获取OCR数据。")
                return False

        locations = self.find_text_locations(
            ocr_data, target_text, partial_match)
        if locations:
            # 默认点击找到的第一个匹配项
            loc_to_click = locations[0]
            print(
                f"点击文本 '{target_text}' (识别为: '{loc_to_click[2]}') @相对({loc_to_click[0]},{loc_to_click[1]}), Y偏移:{y_offset}")
            return self.click_at_relative(loc_to_click[0], loc_to_click[1], y_offset)
        # print(f"click_text: 未在提供的OCR数据中找到文本 '{target_text}'。")
        return False

    def wait_for_text_and_click(self, target_text, timeout=5, interval=0.3, y_offset=0, partial_match=True, optional=False):
        print(f"等待并点击文本 '{target_text}' (超时: {timeout}s, 可选: {optional})...")
        start_time = time.time()
        last_ocr_data_summary = "无"  # 用于调试
        while time.time() - start_time < timeout:
            if not self.hwnd or not win32gui.IsWindow(self.hwnd):  # 检查窗口是否仍然存在
                print("错误: 目标窗口在等待期间关闭或失效。")
                return False if not optional else True

            image = self.capture_window()
            if image is None:
                print("等待时截图失败，稍后重试...")
                time.sleep(interval)
                continue

            ocr_data = self.perform_ocr(image)
            if ocr_data:
                last_ocr_data_summary = f"找到 {len(ocr_data)} 条 (首条: '{ocr_data[0][1][0][:20]}...')"

            if self.click_text(target_text, ocr_data=ocr_data, y_offset=y_offset, partial_match=partial_match):
                return True
            time.sleep(interval)

        print(
            f"超时: 未在 {timeout}s 内找到并点击 '{target_text}'. (最后OCR摘要: {last_ocr_data_summary})")
        return True if optional else False  # 如果是可选操作，超时也算成功（不阻塞流程）

    def wait_for_text_location(self, target_texts, timeout=5, interval=0.3, partial_match=True, find_all_occurrences=False):
        """等待指定的单个或多个文本出现，返回找到的第一个文本及其位置(们)"""
        if not isinstance(target_texts, list):
            target_texts = [target_texts]

        # print(f"等待文本列表 {target_texts} (超时: {timeout}s)...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not self.hwnd or not win32gui.IsWindow(self.hwnd):
                print("错误: 目标窗口在等待文本位置期间关闭或失效。")
                return None, []

            image = self.capture_window()
            if image is None:
                time.sleep(interval)
                continue
            ocr_data = self.perform_ocr(image)

            for text_to_find in target_texts:
                locations = self.find_text_locations(
                    ocr_data, text_to_find, partial_match)
                if locations:
                    print(
                        f"等待时找到文本 '{text_to_find}' @ {[(loc[0], loc[1]) for loc in locations]}")
                    if find_all_occurrences:
                        return text_to_find, locations  # 返回所有找到的位置
                    else:
                        return text_to_find, [locations[0]]  # 只返回第一个位置
            time.sleep(interval)

        # print(f"超时: 未在 {timeout}s 内找到任何文本来自列表 {target_texts}.")
        return None, []  # 未找到

    def run_main_loop(self):
        if not self.find_window():
            return
        if not self.get_window_rect():
            return  # 确保初始窗口矩形有效

        current_step = 1
        if DEBUG_START_STEP is not None and isinstance(DEBUG_START_STEP, int) and DEBUG_START_STEP > 1:
            # 简单的有效性检查，确保步骤号在合理范围内 (例如1到13)
            # 您可以根据实际步骤总数调整此处的上限
            if 1 <= DEBUG_START_STEP <= 13:  # 假设总共有13个步骤
                current_step = DEBUG_START_STEP
                print(f"--- 调试模式: 从步骤 {current_step} 开始 ---")
            else:
                print(
                    f"--- 警告: 无效的 DEBUG_START_STEP ({DEBUG_START_STEP})。将从步骤 1 开始。 ---")

        self.last_brand_clicked_in_step9 = None  # 新增：记录步骤9点击的烙印
        consecutive_step_failures = {
            step: 0 for step in range(1, 14)}  # 记录每个步骤连续失败的次数
        MAX_FAILURES_PER_STEP = 3  # 每个步骤允许的最大连续失败次数，超过则可能重置

        while True:
            print(
                f"\n--- 主循环 | 当前步骤: {current_step} ---")

            # 每次循环开始时检查窗口状态
            if not self.hwnd or not win32gui.IsWindow(self.hwnd) or not self.get_window_rect():
                print("错误: 游戏窗口丢失或无法获取其区域。尝试重新查找...")
                if not self.find_window() or not self.get_window_rect():
                    print("错误: 窗口彻底丢失，停止自动化。")
                    break
                else:
                    print("窗口已重新找到，继续操作。")

            step_executed_successfully = False  # 标记当前步骤是否成功执行

            # --- 步骤 1 ---
            if current_step == 1:
                print("步骤 1: 查找“进入”，点击。然后查找“7天内不在提醒”(2s超时)，若找到则点击特定位置A。")
                if self.wait_for_text_and_click("进入", timeout=10, interval=0.5, partial_match=True):
                    time.sleep(1.5)  # 等待可能的界面切换
                    # 查找“7天内不再提醒”，超时0.5秒，不找到就不点击
                    found_reminder_text, reminder_locs = self.wait_for_text_location(
                        "7天内不再提醒", timeout=0.5, interval=0.2, partial_match=True)
                    print(found_reminder_text)
                    if found_reminder_text:
                        print(
                            f"找到 '{found_reminder_text}', 点击特定位置 A ({self.specific_pos_a_px}).")
                        self.click_at_relative(
                            self.specific_pos_a_px[0], self.specific_pos_a_px[1])
                    else:
                        print("未在0.5秒内找到“7天内不再提醒”，跳过点击A。")
                    current_step = 2
                    step_executed_successfully = True
                else:
                    print("步骤1: 未找到“进入”。")

            # --- 步骤 2 ---
            elif current_step == 2:
                print("步骤 2: 查找“英雄”，如果识别到，就点击特定位置B。")
                # 这里是查找“英雄”作为触发条件，然后点击固定位置B
                found_hero_text, _ = self.wait_for_text_location(
                    "英雄", timeout=5, partial_match=True)
                if found_hero_text:
                    time.sleep(0.5)  # 等待界面稳定
                    print(f"找到“英雄”。点击特定位置 B ({self.specific_pos_b_px}).")
                    self.click_at_relative(
                        self.specific_pos_b_px[0], self.specific_pos_b_px[1])
                    current_step = 3
                    step_executed_successfully = True
                else:
                    print("步骤2: 未找到“英雄”。")

            # --- 步骤 3 ---
            elif current_step == 3:
                # print("步骤 3: 附加挑战(4.5s, 可选C点) -> 战斗 -> 跳过 -> 回放(可选C点)。")
                # found_challenge_text, _ = self.wait_for_text_location(
                #     "附加挑战", timeout=4.5, interval=0.2, partial_match=True)
                # if found_challenge_text:
                #     print(f"找到“附加挑战”，点击特定位置 C ({self.specific_pos_c_px}).")
                #     self.click_at_relative(
                #         self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                # else:
                #     print("步骤3: 4.5秒内未找到“附加挑战”，跳过点击C。")

                # “附加挑战” 总是识别不到，索性直接放弃识别，因为 5 秒后这个界面会自动消失

                time.sleep(4)  # 太快点击“战斗”可能会点不到
                # 修改：先定位“战斗”，再点击特定位置
                found_battle_text, _ = self.wait_for_text_location(
                    "战斗", timeout=10, partial_match=True)
                if found_battle_text:
                    print(f"找到“战斗”，点击特定位置 ({self.specific_pos_battle_px})。")
                    self.click_at_relative(
                        self.specific_pos_battle_px[0], self.specific_pos_battle_px[1])
                    time.sleep(0.5)
                    self.wait_for_text_and_click(
                        "跳过", timeout=10, optional=True, partial_match=True)  # 跳过是可选的
                    time.sleep(0.3)
                    found_replay_text, _ = self.wait_for_text_location(
                        "回放", timeout=10, interval=0.2, partial_match=True)
                    if found_replay_text:
                        time.sleep(0.5)  # 等待界面稳定
                        print(f"找到“回放”，点击特定位置 C ({self.specific_pos_c_px}).")
                        self.click_at_relative(
                            self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                    current_step = 5
                    step_executed_successfully = True
                else:
                    print("步骤3: 未找到“战斗”。")

            # --- 步骤 4 ---
            elif current_step == 4:
                print("步骤 4: 检查是否存在“13/15”文本。")
                time.sleep(1)  # 等待界面稳定，可以根据实际情况调整
                img_s4 = self.capture_window()
                ocr_s4 = self.perform_ocr(img_s4) if img_s4 is not None else []

                # 检查是否找到“13/15”
                # 使用 partial_match=False 进行精确匹配，如果需要部分匹配则改为True
                found_13_15_locations = self.find_text_locations(
                    ocr_s4, "13/15", partial_match=False)
                found_13_15 = bool(found_13_15_locations)

                if found_13_15:
                    print("找到“13/15”。进入步骤 8。")
                    current_step = 8
                else:
                    print("未找到“13/15”。进入步骤 5。")
                    current_step = 5
                step_executed_successfully = True  # 这是一个导航步骤，总是“成功”

            # --- 步骤 5 ---
            elif current_step == 5:
                print("步骤 5: 选择门 (优先级: 馈赠>晶粹>遗物>精英>道具)，点击相对Y偏移位置。")
                gate_priority = ["馈赠之门", "晶粹之门",
                                 "遗物之门", "精英", "道具之门"]  # 优先级从高到低
                time.sleep(0.5)
                img_s5 = self.capture_window()
                ocr_s5 = self.perform_ocr(img_s5) if img_s5 is not None else []

                clicked_this_step = False
                for gate_type in gate_priority:
                    # 对于门和精英，我们可能需要精确匹配，或者至少是包含这些核心词
                    # partial_match=False 意味着完全匹配 "馈赠之门" 等
                    # 如果希望更宽松，比如只匹配 "馈赠"，可以设为 True 并调整 target_text
                    locations = self.find_text_locations(
                        ocr_s5, gate_type, partial_match=False)
                    if locations:
                        # 如果有多个同优先级的，点击找到的第一个
                        loc_to_click = locations[0]
                        print(
                            f"最高优先级选择: '{gate_type}'。点击其下方 {self.y_offset_gate_px} 像素。")
                        self.click_at_relative(
                            loc_to_click[0], loc_to_click[1], y_offset=self.y_offset_gate_px)
                        clicked_this_step = True
                        break  # 找到最高优先级的就执行并跳出循环

                if clicked_this_step:
                    current_step = 6
                    step_executed_successfully = True
                else:
                    print("步骤5: 未找到任何指定的门或精英选项。可能需要检查OCR或游戏界面。")
                    # 如果这里卡住，可能需要一个回退机制，比如返回步骤4或等待

            # --- 步骤 6 --- (与步骤3逻辑类似)
            elif current_step == 6:
                # print("步骤 6: 附加挑战(4.5s, 可选C点) -> 战斗 -> 跳过 -> 回放(可选C点)。")
                # found_challenge_s6, _ = self.wait_for_text_location(
                #     "附加挑战", timeout=4.5, interval=0.2, partial_match=True)
                # if found_challenge_s6:
                #     print(f"找到“附加挑战”，点击特定位置 C ({self.specific_pos_c_px}).")
                #     self.click_at_relative(
                #         self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                # else:
                #     print("步骤6: 4.5秒内未找到“附加挑战”。")

                # “附加挑战” 总是识别不到，索性直接放弃识别，因为 5 秒后这个界面会自动消失

                time.sleep(5)  # 太快点击“战斗”可能会点不到
                # 修改: 获取所有“战斗”出现的位置
                found_battle_s6_text, battle_s6_locations = self.wait_for_text_location(
                    "战斗", timeout=10, partial_match=True, find_all_occurrences=True)  # 获取所有匹配项

                action_after_battle_check_s6 = False  # 标记是否执行战斗后的操作

                if found_battle_s6_text and battle_s6_locations:  # 确保找到了文本且有位置信息
                    if self.window_rect and self.window_rect.get("height") and self.window_rect["height"] > 0:
                        window_height = self.window_rect["height"]
                        lower_third_threshold = window_height * 2 / 3

                        for loc in battle_s6_locations:  # 遍历所有找到的“战斗”位置
                            battle_y_coord = loc[1]  # 获取当前“战斗”的Y坐标
                            if battle_y_coord > lower_third_threshold:
                                print(
                                    f"步骤6: 找到“战斗”于Y={battle_y_coord} (窗口下方1/3区域，阈值 > {lower_third_threshold:.0f})。点击特定位置 ({self.specific_pos_battle_px})。")
                                self.click_at_relative(
                                    self.specific_pos_battle_px[0], self.specific_pos_battle_px[1])
                                action_after_battle_check_s6 = True
                                break  # 只要有一个符合条件就点击并跳出循环

                        if not action_after_battle_check_s6:  # 如果循环结束都没有点击
                            print(
                                f"步骤6: 找到 {len(battle_s6_locations)} 处“战斗”，但均不在窗口下方1/3区域 (阈值 > {lower_third_threshold:.0f})。不点击。")
                    else:
                        print("步骤6: 无法获取有效窗口高度以验证“战斗”位置。不点击。")

                if action_after_battle_check_s6:
                    time.sleep(0.5)
                    # 新的“跳过”逻辑
                    print("步骤6: 第一次尝试点击“跳过”(4秒超时)...")
                    clicked_skip_attempt1 = self.wait_for_text_and_click(
                        "跳过", timeout=4, optional=False, partial_match=True)

                    if not clicked_skip_attempt1:
                        print("步骤6: 第一次尝试点击“跳过”失败或超时。将再次点击战斗按钮并重试“跳过”。")
                        self.click_at_relative(
                            self.specific_pos_battle_px[0], self.specific_pos_battle_px[1])
                        time.sleep(0.5)  # 点击战斗按钮后稍作等待

                        print("步骤6: 第二次尝试点击“跳过”(4秒超时, 可选)...")
                        # 第二次尝试可以是可选的，如果仍然找不到，就继续
                        if self.wait_for_text_and_click("跳过", timeout=4, optional=True, partial_match=True):
                            print("步骤6: 第二次尝试点击“跳过”成功。")
                        else:
                            print("步骤6: 第二次尝试点击“跳过”也失败或超时。")
                    else:
                        print("步骤6: 第一次尝试点击“跳过”成功。")

                    time.sleep(0.3)  # 在检查“回放”之前等待
                    found_replay_s6, _ = self.wait_for_text_location(
                        "回放", timeout=10, interval=0.2, partial_match=True)
                    if found_replay_s6:
                        time.sleep(0.5)  # 等待界面稳定
                        print(f"找到“回放”，点击特定位置 C ({self.specific_pos_c_px}).")
                        self.click_at_relative(
                            self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                    found_success_s6, _ = self.wait_for_text_location(
                        "挑战成功", timeout=1, interval=0.2, partial_match=True)
                    if found_success_s6:
                        print("找到“挑战成功”，点击特定位置 C ({self.specific_pos_c_px}).")
                        self.click_at_relative(
                            self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                    current_step = 7
                    step_executed_successfully = True
                else:
                    print("步骤6: 未找到“战斗”或未满足点击条件。")
                    # step_executed_successfully 保持 False

            # --- 步骤 7 ---
            elif current_step == 7:
                # step_executed_successfully 将在此块的末尾设置

                # 新增：检查是否意外返回到了英雄选择界面
                print("步骤7: 检查是否出现“英雄”文本 (2.5s超时)...")
                found_hero_early, _ = self.wait_for_text_location(
                    "英雄", timeout=2.5, interval=0.2, partial_match=True)
                if found_hero_early:
                    print("步骤7: 检测到“英雄”，返回步骤4。")
                    current_step = 4
                    step_executed_successfully = True
                else:
                    # 2. 进入遗物选择循环
                    time.sleep(2)  # 等待界面稳定
                    print("步骤7: 找到“选择烙印”。开始遗物选择循环...")
                    max_relic_selection_attempts = 3  # 最多尝试3次选择遗物
                    relic_selection_attempts = 0
                    # 这个标志用于判断在循环结束后，是否是因为“选择烙印”仍然存在而退出的
                    select_sigil_still_present_after_loop = False

                    while relic_selection_attempts < max_relic_selection_attempts:
                        relic_selection_attempts += 1
                        print(
                            f"步骤7: 遗物选择尝试 #{relic_selection_attempts}/{max_relic_selection_attempts}")
                        select_sigil_still_present_after_loop = False  # 重置标志

                        # 每次循环开始时，重新捕获屏幕以获取最新的遗物选项
                        print("步骤7: 正在捕获当前遗物选项...")
                        time.sleep(0.5)  # 给UI一点时间刷新（如果“选择烙印”刚重新出现）
                        img_relic_options = self.capture_window()
                        if img_relic_options is None:
                            print("步骤7: 捕获遗物选项截图失败。结束遗物选择循环。")
                            break  # 退出 while 循环

                        ocr_relic_options = self.perform_ocr(
                            img_relic_options)
                        if not ocr_relic_options:  # 检查OCR结果是否为空
                            print("步骤7: OCR未能从遗物选项截图中识别任何文本。结束遗物选择循环。")
                            break  # 退出 while 循环

                        # 4. 选择遗物 ("史诗" > "精英" > "稀有")
                        print("步骤7: 选择遗物 (优先级: 史诗 > 精英 > 稀有)...")
                        relic_priority = ["史诗", "精英", "稀有"]
                        clicked_relic_this_attempt = False

                        for quality in relic_priority:
                            # 使用 partial_match=False 进行精确品质匹配
                            if self.click_text(quality, ocr_data=ocr_relic_options, partial_match=False):
                                print(f"步骤7: 已点击遗物品质: '{quality}'.")
                                clicked_relic_this_attempt = True
                                break  # 跳出遗物品质选择 for 循环

                        if not clicked_relic_this_attempt:
                            print("步骤7: 本轮尝试未能选择任何优先级的遗物。结束遗物选择循环。")
                            break  # 退出 while 循环

                        # 点击 "确认"
                        time.sleep(0.5)  # 等待遗物点击生效
                        if self.wait_for_text_and_click("确认", timeout=5, partial_match=True):
                            print("步骤7: 已点击“确认”(在选择遗物之后)。")
                            time.sleep(1.0)  # 等待UI更新，例如“选择烙印”文本可能消失或重新出现

                            # 5. 检查“选择烙印”是否再次出现 (1s超时)
                            print("步骤7: 检查“选择烙印”是否再次出现 (1s超时)...")
                            found_select_sigil_again, _ = self.wait_for_text_location(
                                "选择烙印", timeout=3.0, interval=0.2, partial_match=True)

                            if found_select_sigil_again:
                                print("步骤7: 检测到“选择烙印”再次出现。将继续下一轮遗物选择。")
                                select_sigil_still_present_after_loop = True  # 标记以便在循环结束时检查
                                # 继续 while 循环的下一次迭代
                            else:
                                print("步骤7: 未再检测到“选择烙印”。认为遗物选择已完成。")
                                break  # 退出 while 循环
                        else:
                            print("步骤7: 点击遗物后未能找到或点击“确认”。结束遗物选择循环。")
                            break  # 退出 while 循环

                    # while 循环结束后 (无论是正常结束、break跳出还是达到max_attempts)
                    if relic_selection_attempts == max_relic_selection_attempts and select_sigil_still_present_after_loop:
                        print(
                            f"步骤7: 遗物选择达到最大尝试次数 ({max_relic_selection_attempts})，但“选择烙印”在最后一次检查时仍存在。")

                    print("步骤7: 遗物选择流程结束。前往步骤4。")
                    current_step = 4
                    step_executed_successfully = True

            # --- 步骤 8 ---
            elif current_step == 8:
                print("步骤 8: 点击相对于“烙印晶球”的坐标一定Y轴距离的位置，然后等待5秒。")
                # partial_match=True 确保能找到 "烙印晶球" 即使周围有其他文字
                if self.wait_for_text_and_click("烙印晶球", timeout=7, y_offset=self.y_offset_shop_item_px, partial_match=True):
                    print("已点击“烙印晶球”下方。等待商店界面或后续操作...")
                    time.sleep(5)  # 等待商店反应或动画
                    current_step = 9  # 或其他逻辑，例如检查购买成功
                else:
                    print("步骤8: 未找到“烙印晶球”进行点击。可能不在商店界面。返回步骤4。")
                    current_step = 4  # 如果找不到，可能流程出错了，返回步骤4重新判断

            # --- 步骤 9 ---
            elif current_step == 9:
                print("步骤 9: 尝试替换烙印 (精英>稀有)。若“晶粹不足”->步骤11，否则->步骤10。")
                brand_priority_replace = ["精英", "稀有"]
                clicked_brand_s9 = False
                self.last_brand_clicked_in_step9 = None  # 重置

                time.sleep(0.5)  # 等待界面
                img_s9_brand = self.capture_window()
                ocr_s9_brand = self.perform_ocr(
                    img_s9_brand) if img_s9_brand is not None else []

                for quality in brand_priority_replace:
                    if self.click_text(quality, ocr_data=ocr_s9_brand, partial_match=False):
                        print(f"步骤9: 已点击烙印品质: '{quality}' 用于替换。")
                        self.last_brand_clicked_in_step9 = quality  # 记录点击的品质
                        clicked_brand_s9 = True
                        break

                if clicked_brand_s9:
                    time.sleep(0.5)  # 等待点击生效
                    if self.wait_for_text_and_click("确认替换", timeout=5, partial_match=True):
                        print("步骤9: 已点击“确认替换”。")
                        time.sleep(0.5)  # 等待UI响应
                        found_insufficient, _ = self.wait_for_text_location(
                            "晶粹不足", timeout=1, interval=0.2, partial_match=True)

                        if found_insufficient:
                            print("步骤9: 检测到“晶粹不足”。进入步骤 11。")
                            current_step = 11
                        else:
                            print("步骤9: 未检测到“晶粹不足”。进入步骤 10 (基于已替换的烙印进行后续操作)。")
                            current_step = 10
                        step_executed_successfully = True
                    else:
                        print("步骤9: 点击烙印后未找到“确认替换”。进入步骤 10 (尝试保留或选择新烙印)。")
                        self.last_brand_clicked_in_step9 = None  # 替换未确认，重置状态
                        current_step = 10
                        step_executed_successfully = True
                else:
                    print("步骤9: 未找到“精英”或“稀有”烙印可点击替换。进入步骤 11。")
                    self.last_brand_clicked_in_step9 = None  # 没有点击，重置状态
                    current_step = 11
                    step_executed_successfully = True

            # --- 步骤 10 ---
            elif current_step == 10:
                print(
                    f"步骤 10: 处理烙印选择。上次在步骤9尝试点击的品质: {self.last_brand_clicked_in_step9}")
                time.sleep(0.5)
                img_s10 = self.capture_window()
                ocr_s10 = self.perform_ocr(
                    img_s10) if img_s10 is not None else []
                initial_ocr_s10 = ocr_s10  # 保存初始OCR结果，用于后续“保留烙印”等

                action_taken_s10 = False

                if self.last_brand_clicked_in_step9 == "精英":
                    print("步骤10: 逻辑分支 - 步骤9点击了“精英”进行替换。现在查找“史诗”。")
                    if self.click_text("史诗", ocr_data=ocr_s10, partial_match=False):
                        print("步骤10: 已点击“史诗”。")
                        if self.wait_for_text_and_click("确认选择", timeout=5, partial_match=True):
                            print("步骤10: 已点击“确认选择”(史诗)。点击特定位置 C。")
                            self.click_at_relative(
                                self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                            action_taken_s10 = True
                        else:
                            print("步骤10: 点击“史诗”后未找到“确认选择”。")
                            action_taken_s10 = True  # 标记为已尝试操作，避免默认选择史诗或保留
                    # 如果未找到史诗，则 action_taken_s10 保持 False，会尝试保留烙印

                elif self.last_brand_clicked_in_step9 == "稀有":
                    print("步骤10: 逻辑分支 - 步骤9点击了“稀有”进行替换。现在查找“史诗”或“精英”。")
                    sigil_priority_s10_rare_case = ["史诗", "精英"]
                    for quality_rare in sigil_priority_s10_rare_case:
                        if self.click_text(quality_rare, ocr_data=ocr_s10, partial_match=False):
                            print(f"步骤10: 已点击“{quality_rare}”。")
                            if self.wait_for_text_and_click("确认选择", timeout=5, partial_match=True):
                                print(
                                    f"步骤10: 已点击“确认选择”({quality_rare})。点击特定位置 C。")
                                self.click_at_relative(
                                    self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                                action_taken_s10 = True
                                break
                            else:
                                print(f"步骤10: 点击“{quality_rare}”后未找到“确认选择”。")
                                action_taken_s10 = True  # 标记为已尝试操作
                                break
                    # 如果未找到史诗或精英，则 action_taken_s10 保持 False，会尝试保留烙印

                # 默认/回退逻辑: 如果步骤9未点击任何烙印，或者上述特定路径未执行或未成功完成烙印选择和确认
                if not action_taken_s10 and self.last_brand_clicked_in_step9 is None:
                    print("步骤10: 逻辑分支 - 默认 (步骤9未指定替换或替换未确认)。查找“史诗”或“精英”。")
                    sigil_priority_s10_default = ["史诗", "精英"]
                    for quality_default in sigil_priority_s10_default:
                        if self.click_text(quality_default, ocr_data=initial_ocr_s10, partial_match=False):
                            print(f"步骤10 (默认): 已点击烙印品质: '{quality_default}'.")
                            time.sleep(0.5)
                            if self.wait_for_text_and_click("确认选择", timeout=5, partial_match=True):
                                print(f"步骤10 (默认): 已点击“确认选择”。点击特定位置 C。")
                                self.click_at_relative(
                                    self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                                action_taken_s10 = True
                                break
                            else:
                                print(
                                    f"步骤10 (默认): 点击 '{quality_default}' 后未找到“确认选择”。")
                                action_taken_s10 = True  # 标记为已尝试操作
                                break

                # 最后尝试: 如果以上所有操作都未导致选择烙印并确认
                if not action_taken_s10:
                    print("步骤10: 所有特定及默认选择均未成功或未执行。尝试点击“保留烙印”。")
                    if self.click_text("保留烙印", ocr_data=initial_ocr_s10, partial_match=True):
                        print("步骤10: 已点击“保留烙印”。")
                    else:
                        print("步骤10: 未找到“保留烙印”可点击。")

                current_step = 9  # 无论如何都返回步骤9
                step_executed_successfully = True
                time.sleep(0.5)  # 返回前稍作等待

            # --- 步骤 11 ---
            elif current_step == 11:
                time.sleep(0.5)  # 等待界面稳定
                print("步骤 11: 点击“继续前进”。查“首领”，点击其相对Y偏移位置。")
                if self.wait_for_text_and_click("继续前进", timeout=10, partial_match=True):
                    time.sleep(1.5)  # 等待地图或首领界面加载
                    # 查找“首领”，精确匹配
                    found_boss_text, boss_locations = self.wait_for_text_location(
                        "首领", timeout=10, interval=0.5, partial_match=False)
                    if found_boss_text and boss_locations:
                        # 取第一个找到的“首领”
                        boss_rel_x, boss_rel_y, _, _ = boss_locations[0]
                        print(f"找到“首领”。点击其下方 {self.y_offset_boss_px} 位置。")
                        self.click_at_relative(
                            boss_rel_x, boss_rel_y, y_offset=self.y_offset_boss_px)
                        current_step = 12
                        step_executed_successfully = True
                    else:
                        print("步骤11: 点击继续前进后未找到“首领”。可能已在错误界面。返回步骤4。")
                        current_step = 4  # 回退到地图选择
                else:
                    print("步骤11: 未找到“继续前进”。可能已在错误界面。返回步骤4。")
                    current_step = 4  # 回退

            # --- 步骤 12 --- (与步骤3/6类似，但可能是首领战)
            elif current_step == 12:
                print("步骤 12: 战斗 -> 跳过 -> 回放(可选C点)。(首领战)")
                # 修改：先定位“战斗”，再点击特定位置
                found_battle_s12, _ = self.wait_for_text_location(
                    "战斗", timeout=15, partial_match=True)  # 首领战可能加载慢一些
                if found_battle_s12:
                    print(
                        f"找到“战斗”(首领战)，点击特定位置 ({self.specific_pos_battle_px})。")
                    self.click_at_relative(
                        self.specific_pos_battle_px[0], self.specific_pos_battle_px[1])
                    time.sleep(1.0)
                    self.wait_for_text_and_click(
                        "跳过", timeout=15, optional=True, partial_match=True)
                    time.sleep(0.5)
                    found_replay_s12, _ = self.wait_for_text_location(
                        "回放", timeout=5, interval=0.2, partial_match=True)
                    if found_replay_s12:
                        time.sleep(0.5)  # 等待界面稳定
                        print(
                            f"找到“回放”，点击特定位置 C ({self.specific_pos_c_px}) (首领战后)。")
                        self.click_at_relative(
                            self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                    current_step = 13
                    step_executed_successfully = True
                else:
                    print("步骤12: 未找到“战斗”(首领战)。可能流程出错。返回步骤4。")
                    current_step = 4  # 回退

            # --- 步骤 13 ---
            elif current_step == 13:
                print(
                    "步骤 13: 等5秒。查“结束探索”->点->回步骤1。否则选烙印(史诗>精英>稀有)->“选择烙印”->“结束探索”->回步骤1。")
                print("等待5秒以观察界面...")
                time.sleep(5)

                # 第一次扫描，查找“结束探索”
                img_s13_initial = self.capture_window()
                ocr_s13_initial = self.perform_ocr(
                    img_s13_initial) if img_s13_initial is not None else []

                if self.click_text("结束探索", ocr_data=ocr_s13_initial, partial_match=True):
                    print("已点击“结束探索”。返回步骤1。")
                    current_step = 1
                    step_executed_successfully = True
                else:
                    print("未直接找到“结束探索”。尝试选择烙印流程...")

                    # 循环选择烙印，可能会多次
                    max_sigil_selection_attempts = 4  # 防止无限循环
                    sigil_selection_attempts = 0
                    # 如果步骤通过成功跳转到步骤1或步骤4来完成，则此标志为true。
                    # 用于确定是否需要max_attempts回退。
                    # step_executed_successfully 已在外部定义，我们将使用它。

                    while sigil_selection_attempts < max_sigil_selection_attempts and not step_executed_successfully:
                        sigil_selection_attempts += 1
                        print(
                            f"步骤13: 烙印选择尝试 #{sigil_selection_attempts} / {max_sigil_selection_attempts}")

                        # 每次尝试选择烙印时获取新的屏幕截图
                        img_s13_brand_select = self.capture_window()
                        ocr_s13_brand_select = self.perform_ocr(
                            img_s13_brand_select) if img_s13_brand_select is not None else []
                        brand_priority_s13 = ["史诗", "精英", "稀有"]  # 优先级
                        clicked_brand_in_this_attempt = False
                        for quality in brand_priority_s13:
                            if self.click_text(quality, ocr_data=ocr_s13_brand_select, partial_match=False):
                                print(f"步骤13: 已点击烙印品质: '{quality}'.")
                                clicked_brand_in_this_attempt = True
                                break

                        if clicked_brand_in_this_attempt:
                            time.sleep(0.5)  # 等待点击生效
                            # 点击烙印后，查找“确认”
                            if self.wait_for_text_and_click("确认", timeout=5, partial_match=True):
                                print("步骤13: 已点击“确认”(烙印选择后)。")
                                # 等待“确认”后UI更新
                                time.sleep(1.0)

                                # 检查“选择烙印”是否再次出现
                                # 根据要求，对此检查使用较短的超时时间
                                found_select_sigil_again, _ = self.wait_for_text_location(
                                    "选择烙印", timeout=1.0, interval=0.2)

                                if found_select_sigil_again:
                                    print("步骤13: 检测到“选择烙印”再次出现，将重新进行烙印选择。")
                                    # `while sigil_selection_attempts < max_sigil_selection_attempts:` 循环将继续
                                    # step_executed_successfully 尚未更改，因为我们正在步骤13内循环。
                                    continue  # 进入烙印选择循环的下一次迭代
                                else:
                                    # 未找到“选择烙印”，因此假定选择已完成。尝试“结束探索”。
                                    print("步骤13: 未再检测到“选择烙印”，尝试结束探索。")
                                    if self.wait_for_text_and_click("结束探索", timeout=5, partial_match=True):
                                        print("步骤13: 确认选择烙印后，已点击“结束探索”。返回步骤1。")
                                        current_step = 1
                                        step_executed_successfully = True
                                    else:
                                        print("步骤13: 确认选择烙印后，未能点击“结束探索”。返回步骤4。")
                                        current_step = 4  # 回退
                                        step_executed_successfully = True  # 标记为已由回退处理
                                    break  # 退出烙印选择循环，因为我们已完成或遇到回退
                            else:  # 未能点击“确认”
                                print("步骤13: 点击烙印品质后，未找到“确认”。尝试直接结束探索。")
                                if self.wait_for_text_and_click("结束探索", timeout=3, partial_match=True):
                                    print("步骤13: 无法确认烙印，但成功点击“结束探索”。返回步骤1。")
                                    current_step = 1
                                    step_executed_successfully = True
                                else:
                                    print("步骤13: 无法确认烙印，也无法结束探索。返回步骤4。")
                                    current_step = 4
                                    step_executed_successfully = True  # 标记为已由回退处理
                                break  # 退出烙印选择循环
                        else:  # 在此尝试中未找到并点击指定质量的烙印
                            print("步骤13: 本轮未找到任何优先级的烙印可点击。尝试结束探索。")
                            # 使用当前的OCR数据
                            if self.wait_for_text_and_click("结束探索", timeout=5, ocr_data=ocr_s13_brand_select, partial_match=True):
                                print("步骤13: 未选择新烙印，已点击“结束探索”。返回步骤1。")
                                current_step = 1
                                step_executed_successfully = True
                            else:
                                print("步骤13: 未选择新烙印，也未能点击“结束探索”。尝试点击C点后结束。")
                                self.click_at_relative(
                                    self.specific_pos_c_px[0], self.specific_pos_c_px[1])
                                time.sleep(0.3)
                                if self.wait_for_text_and_click("结束探索", timeout=3, partial_match=True):
                                    print("步骤13: 点击C点后，已点击“结束探索”。返回步骤1。")
                                    current_step = 1
                                    step_executed_successfully = True
                                else:
                                    print("步骤13: 所有尝试失败（无烙印可选，结束探索也失败）。返回步骤4。")
                                    current_step = 4  # 最终回退
                                    step_executed_successfully = True  # 标记为已由回退处理
                            break  # 退出烙印选择循环

                    # 烙印选择循环之后（如果中断或达到最大尝试次数）
                    if not step_executed_successfully:
                        # 这意味着循环由于达到max_attempts而结束，但未成功设置current_step和step_executed_successfully
                        print(
                            f"步骤13: 烙印选择达到最大尝试次数 ({max_sigil_selection_attempts}) 仍未成功结束探索。返回步骤4。")
                        current_step = 4
                        step_executed_successfully = True  # 标记为已由回退处理

            # --- 步骤失败处理和重置 ---
            # 为了防止某些步骤卡住，增加失败计数和重置机制
            if not step_executed_successfully:
                consecutive_step_failures[current_step] += 1
                print(
                    f"步骤 {current_step} 执行失败，连续失败 {consecutive_step_failures[current_step]} 次。")

                # 如果某个步骤连续失败超过阈值，尝试重置或返回上一步
                if consecutive_step_failures[current_step] > MAX_FAILURES_PER_STEP:
                    print(
                        f"错误: 步骤 {current_step} 连续失败超过 {MAX_FAILURES_PER_STEP} 次。尝试重置或返回上一步。")
                    # 可以选择返回上一步，或者直接重置到某个安全步骤
                    if current_step > 1:
                        print(f"返回到步骤 {current_step - 1}。")
                        current_step -= 1
                    else:
                        print("已在第一个步骤，无法回退。尝试重新查找窗口。")
                        self.find_window()
                        self.get_window_rect()
                        current_step = 1  # 强制回到第一个步骤
            else:
                # 如果成功执行，重置该步骤的失败计数
                consecutive_step_failures[current_step] = 0

            # 为了避免过于频繁的循环，添加全局间隔
            time.sleep(0.1)  # 可以根据需要调整


def main():
    print("自动迷宫脚本启动...")
    print(f"将尝试控制窗口标题包含: '{GAME_WINDOW_TITLE}'")
    print(f"  CONFIDENCE_THRESHOLD = {CONFIDENCE_THRESHOLD}")
    print("脚本即将开始。请切换到游戏窗口。")
    print("按 Ctrl+C 在终端中停止脚本。")
    print("-" * 70)

    automation_instance = AutoLabyrinth(GAME_WINDOW_TITLE)

    try:
        automation_instance.run_main_loop()
    except KeyboardInterrupt:
        print("\n脚本被用户中断 (Ctrl+C)。")
    except Exception as e:
        print(f"\n发生未处理的严重错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("脚本执行结束。")


if __name__ == "__main__":
    main()

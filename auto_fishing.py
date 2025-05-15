import time
import win32api
import win32con
import win32gui
import mss
import numpy as np
from PIL import Image
from ultralytics import YOLO
import os
import cv2  # 新增导入

# --- 配置参数 ---
TARGET_WINDOW_NAME = "BlueStacks App Player"  # 目标窗口名称
YOLO_MODEL_PATH = "yolo/models/best.pt"  # YOLOv8 模型路径
CONFIDENCE_THRESHOLD = 0.8  # 置信度阈值
STATE_IDLE = 0
STATE_FISHING_START = 1
STATE_WAITING_FOR_WEIGHT_MARK = 2
STATE_PULLING_ROD = 3
STATE_CHECK_RESULT = 4

# --- 全局变量 ---
current_state = STATE_WAITING_FOR_WEIGHT_MARK  # 直接进入第二阶段
yolo_model = None
REFRESH_RATE = 0  # 帧间隔时间（秒），控制检测频率
# last_weight_mark_check_time = 0  # 用于第二阶段的计时器 (旧逻辑)
# CLICK_POSITION_STAGE2_X_RATIO = 0.45  # 第二阶段点击位置的X轴比例 (旧逻辑)
# CLICK_POSITION_STAGE2_Y_RATIO = 0.75  # 第二阶段点击位置的Y轴比例 (旧逻辑)
# WEIGHT_MARK_TIMEOUT = 6.0  # weight mark 检测超时时间（秒）(旧逻辑)
PULL_CONFIRM_TIMEOUT_STAGE2 = 0.5  # 第二阶段检测到 'pull' 后等待 'weight mark' 的超时时间
pull_detected_timestamp_stage2 = 0  # 第二阶段首次检测到 'pull' 的时间戳
pull_item_info_stage2 = None  # 第二阶段存储 'pull' item bbox 和 label

STATE_TRANSITION_TIME = 1.5  # 第二阶段和第三阶段之间的等待时间（秒）
BOUND_ABSENCE_TIMEOUT = 1.0  # 第三阶段'bound'或'bound blue'持续消失多久后转换状态（秒）
CLICK_POSITION_STAGE3_X_RATIO = 0.45  # 第三阶段按住/松开位置的X轴比例
CLICK_POSITION_STAGE3_Y_RATIO = 0.75  # 第三阶段按住/松开位置的Y轴比例
is_mouse_pressed_stage3 = False  # 第三阶段鼠标是否已按下
last_known_should_press_stage3 = False  # 第三阶段上一次有效的按住/松开状态
bound_absence_start_time = None  # 第三阶段'bound'/'bound blue'开始消失的时间戳
last_hook_out_x_stage3 = None  # 第三阶段上一次 'hook_out' 的X坐标
last_hook_out_x_timestamp_stage3 = 0  # 第三阶段上一次 'hook_out' X坐标的时间戳
HOOK_OUT_STUCK_TIMEOUT = 0.5  # 'hook_out' 卡住的超时时间 (秒)
HOOK_OUT_X_STUCK_THRESHOLD = 1.5  # 'hook_out' X坐标卡住的像素阈值
CLICK_POSITION_STAGE4_STOP_X_RATIO = 0.1  # 第四阶段点击 'stop' 后特定位置的X轴比例
CLICK_POSITION_STAGE4_STOP_Y_RATIO = 0.9  # 第四阶段点击 'stop' 后特定位置1的Y轴比例
# 新增：'stop' 后的额外点击和拖拽位置比例 (占位符，需要用户测试确定)
CLICK_POS2_X_RATIO_AFTER_STOP = 0.8
CLICK_POS2_Y_RATIO_AFTER_STOP = 0.1
DRAG_START_POS3_X_RATIO_AFTER_STOP = 0.88
DRAG_START_POS3_Y_RATIO_AFTER_STOP = 0.47
DRAG_END_POS4_X_RATIO_AFTER_STOP = 0.88
DRAG_END_POS4_Y_RATIO_AFTER_STOP = 0.62
DRAG_DURATION_AFTER_STOP = 0.5  # 拖拽持续时间（秒）

initial_wait_done_stage4 = False  # 第四阶段初始等待是否已完成
DEBUG_SHOW_DETECTIONS = True  # 是否显示YOLO检测结果的调试窗口

# --- 窗口和截图相关函数 ---


def get_window_rect(window_name):
    """获取指定窗口的位置和大小"""
    hwnd = win32gui.FindWindow(None, window_name)
    if hwnd == 0:
        print(f"找不到窗口: {window_name}")
        return None, None, None
    # 置顶窗口，防止被其他窗口遮挡，但注意这可能会打扰用户
    # win32gui.SetForegroundWindow(hwnd)
    # time.sleep(0.1) # 等待窗口激活

    rect = win32gui.GetWindowRect(hwnd)
    client_rect = win32gui.GetClientRect(hwnd)  # 获取客户区大小

    # 计算边框和标题栏的厚度
    border_thickness = (rect[2] - rect[0] - client_rect[2]) // 2
    title_bar_height = (rect[3] - rect[1] - client_rect[3]) - border_thickness

    # 客户区的屏幕坐标
    client_x = rect[0] + border_thickness
    client_y = rect[1] + title_bar_height
    client_width = client_rect[2]
    client_height = client_rect[3]

    # print(f"窗口原始位置: {rect}")
    # print(f"窗口客户区大小: {client_rect}")
    # print(f"边框厚度: {border_thickness}, 标题栏高度: {title_bar_height}")
    # print(f"客户区屏幕坐标: x={client_x}, y={client_y}, width={client_width}, height={client_height}")

    if client_width <= 0 or client_height <= 0:
        print(f"窗口客户区大小异常: width={client_width}, height={client_height}")
        return None, None, None

    return (client_x, client_y, client_width, client_height), hwnd, (border_thickness, title_bar_height)


def capture_window_client_area(window_name):
    """捕获指定窗口客户区的截图"""
    rect_data, hwnd, _ = get_window_rect(window_name)
    if not rect_data or hwnd == 0:  # Ensure hwnd is valid
        return None, None, None

    x, y, width, height = rect_data

    try:
        with mss.mss() as sct:
            monitor = {"top": y, "left": x, "width": width, "height": height}
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size,
                                  sct_img.bgra, "raw", "BGRX")
            return img, (x, y), hwnd  # 返回图像、客户区左上角坐标和窗口句柄
    except Exception as e:
        print(f"使用mss截图失败: {e}")
        return None, None, None

# --- 鼠标点击函数 ---


def click_at_screen_coords(x, y):
    """在屏幕指定坐标执行鼠标左键单击"""
    win32api.SetCursorPos((x, y))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
    print(f"点击屏幕坐标: ({x}, {y})")


def click_item_center(item_bbox, window_screen_origin):
    """点击识别到的项目的中心点"""
    x1, y1, x2, y2 = item_bbox
    center_x_relative = (x1 + x2) / 2
    center_y_relative = (y1 + y2) / 2

    # 将相对坐标转换为屏幕绝对坐标
    screen_x = int(window_screen_origin[0] + center_x_relative)
    screen_y = int(window_screen_origin[1] + center_y_relative)

    click_at_screen_coords(screen_x, screen_y)


def mouse_drag(x1, y1, x2, y2, move_duration=0.3, steps=20):
    """模拟鼠标从(x1, y1)平滑拖拽到(x2, y2)并释放（左键）"""
    win32api.SetCursorPos((x1, y1))
    time.sleep(0.05)  # 确保光标在起始点
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x1, y1, 0, 0)
    print(f"鼠标按下于: ({x1}, {y1})")
    time.sleep(0.1)  # 按下后短暂延时，确保游戏响应

    if steps <= 0:  # 防止除以零或无效步数
        steps = 1

    dx = (x2 - x1) / steps
    dy = (y2 - y1) / steps
    delay_per_step = move_duration / steps

    print(
        f"开始拖拽: 从 ({x1},{y1}) 到 ({x2},{y2})，分 {steps} 步，每步延时 {delay_per_step:.4f}s")

    for i in range(steps):
        current_x = x1 + (i * dx)
        current_y = y1 + (i * dy)
        win32api.SetCursorPos((int(current_x), int(current_y)))
        time.sleep(delay_per_step)

    # 确保最终位置精确
    win32api.SetCursorPos((x2, y2))
    print(f"鼠标拖拽完成，当前位置: ({x2}, {y2})")
    time.sleep(0.05)  # 在目标点短暂停留后松开

    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x2, y2, 0, 0)
    print(f"鼠标松开于: ({x2}, {y2})")


def find_and_click_item_in_stage4(label_to_find, model, confidence_thresh, window_name, max_attempts=3, delay_between_attempts=0.2):
    """在第四阶段尝试查找并点击特定标签的第一个匹配项"""
    print(f"尝试查找并点击 '{label_to_find}'...")
    for attempt in range(max_attempts):
        img, origin, _ = capture_window_client_area(window_name)
        if img is None or origin is None:
            print(
                f"查找 '{label_to_find}' 时无法捕获窗口，尝试 {attempt + 1}/{max_attempts}")
            time.sleep(delay_between_attempts)
            continue

        detections = detect_objects(model, img, confidence_thresh)
        found_item = next(
            (item for item in detections if item["label"] == label_to_find), None)

        if found_item:
            print(f"找到 '{label_to_find}' 于 {found_item['bbox']}，点击它。")
            click_item_center(found_item["bbox"], origin)
            return True  # 成功找到并点击

        print(f"未找到 '{label_to_find}'，尝试 {attempt + 1}/{max_attempts}")
        time.sleep(delay_between_attempts)

    print(f"查找 '{label_to_find}' {max_attempts} 次后仍未找到。")
    return False  # 未找到

# --- YOLOv8 相关函数 ---


def load_yolo_model(model_path):
    """加载YOLOv8模型"""
    if not os.path.exists(model_path):
        print(f"错误: YOLO模型文件不存在于 {model_path}")
        return None
    try:
        model = YOLO(model_path)
        print(f"YOLO模型加载成功: {model_path}")
        return model
    except Exception as e:
        print(f"YOLO模型加载失败: {e}")
        return None


def detect_objects(model, image_pil, confidence_threshold=0.8):
    """使用YOLO模型检测图像中的对象"""
    if image_pil is None:
        return []
    results = model(image_pil, conf=confidence_threshold,
                    verbose=False)  # verbose=False 禁止打印详细日志
    detections = []
    for result in results:
        boxes = result.boxes
        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls = int(box.cls[0])
            label = model.names[cls]
            detections.append(
                {"label": label, "confidence": conf, "bbox": [x1, y1, x2, y2]})
    return detections

# --- 主逻辑 ---


def main_loop():
    global current_state
    global yolo_model
    # global last_weight_mark_check_time # 旧全局变量
    global pull_detected_timestamp_stage2  # 新增全局变量引用
    global pull_item_info_stage2  # 新增全局变量引用
    global is_mouse_pressed_stage3
    global bound_absence_start_time
    global last_known_should_press_stage3
    global last_hook_out_x_stage3
    global last_hook_out_x_timestamp_stage3
    global initial_wait_done_stage4  # 新增全局变量引用

    yolo_model = load_yolo_model(YOLO_MODEL_PATH)
    if yolo_model is None:
        print("无法加载YOLO模型，程序退出。")
        return

    print("程序启动，开始检测...")
    # current_state = STATE_IDLE  # 初始状态 - 已在全局变量处修改为 STATE_WAITING_FOR_WEIGHT_MARK
    # 初始化第二阶段变量，因为我们直接进入此状态
    # Ensure it's treated as global if accessed before assignment in loop
    global pull_detected_timestamp_stage2
    global pull_item_info_stage2
    pull_detected_timestamp_stage2 = 0
    pull_item_info_stage2 = None
    print(f"直接进入第二阶段 (STATE_WAITING_FOR_WEIGHT_MARK)，初始状态: {current_state}")

    if DEBUG_SHOW_DETECTIONS:
        cv2.namedWindow("YOLO Debug", cv2.WINDOW_NORMAL)

    try:  # 将while True包裹在try中，以便finally可以执行
        while True:
            # 获取窗口截图、客户区左上角坐标和窗口句柄
            img_pil, window_origin, hwnd = capture_window_client_area(
                TARGET_WINDOW_NAME)
            if img_pil is None or window_origin is None or hwnd == 0:
                print(f"无法捕获窗口 '{TARGET_WINDOW_NAME}' 或获取句柄，1秒后重试...")
                if DEBUG_SHOW_DETECTIONS:
                    if cv2.waitKey(1) & 0xFF == ord('q'):  # 允许在等待时退出
                        break
                time.sleep(1)
                continue

            # --- YOLO检测 ---
            # 为了获取原始results对象用于plot，我们在这里直接调用model
            # detect_objects 函数仍然用于提取我们逻辑需要的字典列表
            results_raw = yolo_model(
                img_pil, conf=CONFIDENCE_THRESHOLD, verbose=False)
            detections = []
            if results_raw and results_raw[0]:
                boxes = results_raw[0].boxes
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    label = yolo_model.names[cls]
                    detections.append(
                        {"label": label, "confidence": conf, "bbox": [x1, y1, x2, y2]})

            if DEBUG_SHOW_DETECTIONS:
                # 将PIL图像转换为OpenCV格式 (BGR)
                img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
                annotated_frame = results_raw[0].plot()  # 使用原始results对象进行绘制
                cv2.imshow("YOLO Debug", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("通过调试窗口的 'q' 键退出程序。")
                    break  # 退出主循环

            if detections:  # 新增: 打印当前帧所有检测到的标签
                print(
                    f"Debug (Frame Detections): {[d['label'] for d in detections]}")

            # print(f"当前状态: {current_state}, 检测到: {[d['label'] for d in detections]}") # 调试信息

            # STATE_IDLE 逻辑已移除，直接进入 STATE_WAITING_FOR_WEIGHT_MARK
            # if current_state == STATE_IDLE:
            #     print("状态: 空闲 - 正在查找 'start'...")
            #     for item in detections:
            #         if item["label"] == "start":
            #             print("检测到 'start'，点击进入钓鱼...")
            #             click_item_center(item["bbox"], window_origin)
            #             current_state = STATE_WAITING_FOR_WEIGHT_MARK  # 进入第二阶段
            #             # 重置第二阶段特定变量
            #             pull_detected_timestamp_stage2 = 0
            #             pull_item_info_stage2 = None
            #             print("进入第二阶段 (STATE_WAITING_FOR_WEIGHT_MARK)，已重置阶段变量。")
            #             # time.sleep(0.5) # 点击后稍作等待，确保状态转换
            #             break

            if current_state == STATE_WAITING_FOR_WEIGHT_MARK:  # 注意这里从 elif 改为 if，因为它是第一个活动状态检查
                print("状态: 等待 'pull' 和 'weight mark'...")

                current_pull_item = None  # 当前帧检测到的 'pull'
                weight_mark_in_center = False  # 当前帧 'weight mark' 是否在中心
                window_width = img_pil.width  # 获取当前窗口客户区宽度

                for item in detections:
                    if item["label"] == "pull":
                        current_pull_item = item
                    elif item["label"] == "weight mark":
                        x1, _, x2, _ = item["bbox"]
                        mark_center_x = (x1 + x2) / 2
                        if window_width * 0.475 < mark_center_x < window_width * 0.525:  # 假设中心区域为47.5%到52.5%
                            weight_mark_in_center = True

                if current_pull_item:
                    # 如果是首次检测到 'pull' (或 'pull' 重新出现)，则记录其信息和时间戳
                    if pull_item_info_stage2 is None or pull_item_info_stage2["label"] != "pull":
                        pull_item_info_stage2 = current_pull_item
                        pull_detected_timestamp_stage2 = time.time()
                        print(
                            f"首次检测到 'pull' (或重新出现)，目标: {pull_item_info_stage2['bbox']}。开始 {PULL_CONFIRM_TIMEOUT_STAGE2}s 计时。")
                    else:
                        # 如果 'pull' 持续可见，更新其位置信息，以防它移动
                        pull_item_info_stage2 = current_pull_item

                    # 条件1: 'pull' 可见且 'weight mark' 在中央
                    if weight_mark_in_center:
                        print(
                            f"'pull' ({pull_item_info_stage2['bbox']}) 可见且 'weight mark' 在中央。点击 'pull'。")
                        click_item_center(
                            pull_item_info_stage2["bbox"], window_origin)
                        print(f"等待 {STATE_TRANSITION_TIME}s 后进入拉杆状态...")
                        time.sleep(STATE_TRANSITION_TIME)
                        current_state = STATE_PULLING_ROD
                        # 重置Stage 2状态变量
                        pull_detected_timestamp_stage2 = 0
                        pull_item_info_stage2 = None
                        print("进入拉杆状态 (STATE_PULLING_ROD)")
                        continue  # 完成操作，跳到下一个主循环迭代

                    # 条件2: 'pull' 可见，但 'weight mark' 未在中央 (或未出现)，且已超时
                    elif pull_detected_timestamp_stage2 > 0 and \
                            (time.time() - pull_detected_timestamp_stage2) > PULL_CONFIRM_TIMEOUT_STAGE2:
                        print(
                            f"检测到 'pull' ({pull_item_info_stage2['bbox']}) 已超过 {PULL_CONFIRM_TIMEOUT_STAGE2}s，但 'weight mark' 未在中央。点击 'pull'。")
                        click_item_center(
                            pull_item_info_stage2["bbox"], window_origin)
                        print(f"等待 {STATE_TRANSITION_TIME}s 后进入拉杆状态...")
                        time.sleep(STATE_TRANSITION_TIME)
                        current_state = STATE_PULLING_ROD
                        # 重置Stage 2状态变量
                        pull_detected_timestamp_stage2 = 0
                        pull_item_info_stage2 = None
                        print("进入拉杆状态 (STATE_PULLING_ROD) - 'pull' 超时触发")
                        continue  # 完成操作，跳到下一个主循环迭代

                    # 'pull' 可见，但 'weight mark' 未在中央且未超时
                    elif pull_detected_timestamp_stage2 > 0:
                        time_since_pull_detected = time.time() - pull_detected_timestamp_stage2
                        print(
                            f"'pull' ({pull_item_info_stage2['bbox']}) 可见。等待 'weight mark' 出现在中央或 'pull' 超时 ({time_since_pull_detected:.2f}s / {PULL_CONFIRM_TIMEOUT_STAGE2}s)")

                else:  # 当前帧未检测到 'pull'
                    if pull_item_info_stage2 is not None:  # 如果上一帧有 'pull'，现在没了
                        print("'pull' 从视野中消失，重置 'pull' 相关计时和信息。")
                    # 重置 'pull' 相关状态，以便下次 'pull' 出现时重新计时
                    pull_detected_timestamp_stage2 = 0
                    pull_item_info_stage2 = None
                    # print("当前帧未检测到 'pull'。继续等待 'pull' 出现。")

            elif current_state == STATE_PULLING_ROD:
                global is_mouse_pressed_stage3
                print("状态: 拉杆中...")

                bound_x = None
                hook_out_x = None
                hook_in_x = None
                strong_pull_item = None
                bound_blue_visible = False

                # 收集所需项目的信息
                for item in detections:
                    if item["label"] == "bound":
                        bound_x = (item["bbox"][0] + item["bbox"][2]) / 2
                    elif item["label"] == "hook_out":  # Changed "hook out" to "hook_out"
                        hook_out_x = (item["bbox"][0] + item["bbox"][2]) / 2
                    elif item["label"] == "hook_in":   # Changed "hook in" to "hook_in"
                        hook_in_x = (item["bbox"][0] + item["bbox"][2]) / 2
                    elif item["label"] == "strong pull":
                        strong_pull_item = item  # 保存整个item以便点击
                    elif item["label"] == "bound blue":
                        bound_blue_visible = True

                # Uncommented and added Stage3 marker
                print(
                    f"Debug (Stage3): bound_x={bound_x}, hook_out_x={hook_out_x}, hook_in_x={hook_in_x}, strong_pull_item={'Yes' if strong_pull_item else 'No'}, bound_blue_visible={bound_blue_visible}")

                if bound_x is not None or bound_blue_visible:
                    # 'bound' 或 'bound blue' 可见，重置消失计时器
                    if bound_absence_start_time is not None:
                        print("'bound' 或 'bound blue' 已重新出现。")
                    bound_absence_start_time = None

                    # --- 开始处理 'strong pull', 'bound blue' 暂停, 和常规拉杆逻辑 ---
                    # 处理 'strong pull' (优先)
                    if strong_pull_item:
                        print("检测到 'strong pull'!")
                        if is_mouse_pressed_stage3:  # 如果之前按下了鼠标，松开它
                            click_x_screen_hold = int(
                                window_origin[0] + img_pil.width * CLICK_POSITION_STAGE3_X_RATIO)
                            click_y_screen_hold = int(
                                window_origin[1] + img_pil.height * CLICK_POSITION_STAGE3_Y_RATIO)
                            win32api.mouse_event(
                                win32con.MOUSEEVENTF_LEFTUP, click_x_screen_hold, click_y_screen_hold, 0, 0)
                            is_mouse_pressed_stage3 = False
                            print("松开鼠标 (因 strong pull)")

                        click_item_center(
                            strong_pull_item["bbox"], window_origin)
                        print("点击了 'strong pull'。等待 'bound blue' 消失...")
                        # 等待 'bound blue' 消失的逻辑
                        while True:
                            img_pil_sp, window_origin_sp, _ = capture_window_client_area(  # Adjusted to unpack 3 values
                                TARGET_WINDOW_NAME)
                            if img_pil_sp is None or window_origin_sp is None:  # Ensure both are valid
                                time.sleep(0.1)
                                continue
                            detections_sp = detect_objects(
                                yolo_model, img_pil_sp, CONFIDENCE_THRESHOLD)
                            current_bound_blue_visible_sp = any(  # Use a different variable name to avoid conflict
                                d["label"] == "bound blue" for d in detections_sp)
                            if not current_bound_blue_visible_sp:
                                print("'bound blue' 已消失。")
                                break
                            print("仍然检测到 'bound blue'，继续等待...")
                            time.sleep(0.1)  # 短暂等待后重新检测
                        # 'bound blue' 消失后，脚本应继续在 STATE_PULLING_ROD 状态下运行
                        print("'strong pull' 处理完毕，将继续在拉杆状态下评估。")
                        # current_state 保持为 STATE_PULLING_ROD
                        continue  # 继续主循环，重新评估 STATE_PULLING_ROD 的逻辑

                    # 如果 'bound blue' 可见 (且没有 strong pull)，则暂停常规拉杆操作
                    # 注意: strong pull 逻辑优先，如果 strong pull 发生，这里的 continue 会跳过此块
                    if bound_blue_visible:  # This bound_blue_visible is from the main detection at start of STATE_PULLING_ROD
                        print("'bound blue' 可见，暂停常规拉杆操作。")
                        if is_mouse_pressed_stage3:  # 如果之前按下了鼠标，松开它
                            click_x_screen = int(
                                window_origin[0] + img_pil.width * CLICK_POSITION_STAGE3_X_RATIO)
                            click_y_screen = int(
                                window_origin[1] + img_pil.height * CLICK_POSITION_STAGE3_Y_RATIO)
                            win32api.mouse_event(
                                win32con.MOUSEEVENTF_LEFTUP, click_x_screen, click_y_screen, 0, 0)
                            is_mouse_pressed_stage3 = False
                            print("松开鼠标 (因 bound blue)")
                        time.sleep(0.1)  # 等待 'bound blue' 消失
                        continue  # 继续主循环，下一帧重新评估

                    # --- 新增：检测 'hook_out' 是否卡住 ---
                    if hook_out_x is not None and bound_x is not None:  # 确保两者都可见才能判断卡住
                        if last_hook_out_x_stage3 is not None and \
                           abs(hook_out_x - last_hook_out_x_stage3) < HOOK_OUT_X_STUCK_THRESHOLD:
                            if (time.time() - last_hook_out_x_timestamp_stage3) > HOOK_OUT_STUCK_TIMEOUT:
                                print(
                                    f"'hook_out' 卡住 (x={hook_out_x:.2f} 持续超过 {HOOK_OUT_STUCK_TIMEOUT}s)，执行双击...")
                                # --- 执行双击操作 ---
                                click_x_double = int(
                                    window_origin[0] + img_pil.width * CLICK_POSITION_STAGE3_X_RATIO)
                                click_y_double = int(
                                    window_origin[1] + img_pil.height * CLICK_POSITION_STAGE3_Y_RATIO)

                                if is_mouse_pressed_stage3:  # 如果之前按下了鼠标，先松开
                                    win32api.mouse_event(
                                        win32con.MOUSEEVENTF_LEFTUP, click_x_double, click_y_double, 0, 0)
                                    print("松开鼠标 (因hook_out卡住，准备双击)")

                                # 双击
                                win32api.SetCursorPos(
                                    (click_x_double, click_y_double))
                                time.sleep(0.02)  # 短暂延时确保光标到位
                                win32api.mouse_event(
                                    win32con.MOUSEEVENTF_LEFTDOWN, click_x_double, click_y_double, 0, 0)
                                time.sleep(0.05)
                                win32api.mouse_event(
                                    win32con.MOUSEEVENTF_LEFTUP, click_x_double, click_y_double, 0, 0)
                                time.sleep(0.05)
                                win32api.mouse_event(
                                    win32con.MOUSEEVENTF_LEFTDOWN, click_x_double, click_y_double, 0, 0)
                                time.sleep(0.05)
                                win32api.mouse_event(
                                    win32con.MOUSEEVENTF_LEFTUP, click_x_double, click_y_double, 0, 0)
                                print(
                                    f"在 ({click_x_double}, {click_y_double}) 执行了双击")

                                is_mouse_pressed_stage3 = False  # 双击后鼠标是松开的
                                last_known_should_press_stage3 = False  # 重置期望状态
                                last_hook_out_x_stage3 = None  # 重置卡住检测，避免立即再次触发
                                last_hook_out_x_timestamp_stage3 = 0
                                continue  # 重新评估场景
                        else:  # hook_out_x 移动了或首次记录
                            last_hook_out_x_stage3 = hook_out_x
                            last_hook_out_x_timestamp_stage3 = time.time()
                    elif hook_out_x is None:  # 如果 hook_out 消失了，重置卡住检测
                        last_hook_out_x_stage3 = None
                        last_hook_out_x_timestamp_stage3 = 0

                    # --- 常规拉杆逻辑 ---
                    # (此逻辑在 "hook_out 卡住" 未触发 continue 时执行)
                    # bound_x is not None is already guaranteed by the outer 'if bound_x is not None or bound_blue_visible:'

                    current_decision_should_press = False  # 用于本帧基于可见元素的判断
                    hooks_are_currently_visible = (
                        hook_out_x is not None) or (hook_in_x is not None)

                    if hooks_are_currently_visible:
                        if hook_out_x is not None and hook_out_x < bound_x:
                            current_decision_should_press = True
                            print(
                                f"hook_out_x ({hook_out_x:.2f}) < bound_x ({bound_x:.2f}) -> 决定按住")
                        elif hook_in_x is not None and hook_in_x < bound_x:
                            current_decision_should_press = True
                            print(
                                f"hook_in_x ({hook_in_x:.2f}) < bound_x ({bound_x:.2f}) -> 决定按住")
                        else:  # Hooks visible but conditions not met to press
                            current_decision_should_press = False
                            print(
                                f"hook_out/in_x >= bound_x (hook_out={hook_out_x}, hook_in={hook_in_x}, bound={bound_x}) -> 决定松开")
                        last_known_should_press_stage3 = current_decision_should_press  # 更新记忆
                        final_action_should_press = current_decision_should_press
                    # Hooks not visible, but bound is. Maintain last known action.
                    elif bound_x is not None:
                        # This condition (bound_x is not None) is implicitly true if we are in this part of the code.
                        final_action_should_press = last_known_should_press_stage3
                        print(
                            f"未检测到 'hook_out'/'hook_in' (bound={bound_x})。维持上一状态: {'按住' if final_action_should_press else '松开'}")
                    else:
                        # This case should ideally not be reached if bound_x is None,
                        # as the outer 'if bound_x is not None or bound_blue_visible:' would be false,
                        # leading to the 'bound_absence_start_time' logic.
                        # However, as a fallback, maintain last known state or default to release.
                        final_action_should_press = last_known_should_press_stage3
                        print(
                            f"警告: hook 和 bound 均未明确检测到，维持上一状态: {'按住' if final_action_should_press else '松开'}")

                    click_x_screen = int(
                        window_origin[0] + img_pil.width * CLICK_POSITION_STAGE3_X_RATIO)
                    click_y_screen = int(
                        window_origin[1] + img_pil.height * CLICK_POSITION_STAGE3_Y_RATIO)

                    if final_action_should_press:
                        if not is_mouse_pressed_stage3:
                            try:
                                win32gui.SetForegroundWindow(hwnd)
                                win32gui.SetActiveWindow(hwnd)
                                time.sleep(0.05)  # 给窗口一点时间响应
                            except Exception as e_fg:
                                print(f"警告: 设置前景窗口失败: {e_fg}")
                            win32api.SetCursorPos(
                                (click_x_screen, click_y_screen))
                            win32api.mouse_event(
                                win32con.MOUSEEVENTF_LEFTDOWN, click_x_screen, click_y_screen, 0, 0)
                            is_mouse_pressed_stage3 = True
                            print(
                                f"按住鼠标于 ({click_x_screen}, {click_y_screen})")
                    else:
                        if is_mouse_pressed_stage3:
                            win32api.mouse_event(
                                win32con.MOUSEEVENTF_LEFTUP, click_x_screen, click_y_screen, 0, 0)
                            is_mouse_pressed_stage3 = False
                            print(
                                f"松开鼠标于 ({click_x_screen}, {click_y_screen})")

                else:  # 'bound' 和 'bound blue' 均未检测到
                    if bound_absence_start_time is None:
                        # 第一次检测到消失
                        print("未检测到 'bound' 或 'bound blue'，开始计时等待其彻底消失...")
                        bound_absence_start_time = time.time()
                        if is_mouse_pressed_stage3:  # 如果之前按下了鼠标，松开它
                            click_x_screen = int(
                                window_origin[0] + img_pil.width * CLICK_POSITION_STAGE3_X_RATIO)
                            click_y_screen = int(
                                window_origin[1] + img_pil.height * CLICK_POSITION_STAGE3_Y_RATIO)
                            win32api.mouse_event(
                                win32con.MOUSEEVENTF_LEFTUP, click_x_screen, click_y_screen, 0, 0)
                            is_mouse_pressed_stage3 = False
                            print("松开鼠标 (因 'bound'/'bound blue' 初次消失)")
                    else:
                        # 已经开始计时，检查是否超时
                        time_elapsed_since_bound_gone = time.time() - bound_absence_start_time
                        if time_elapsed_since_bound_gone > BOUND_ABSENCE_TIMEOUT:
                            print(
                                f"'bound' 或 'bound blue' 持续消失超过 {BOUND_ABSENCE_TIMEOUT:.1f}s，进入检查结果阶段。")
                            # 确保鼠标已松开 (理论上在计时开始时已松开)
                            if is_mouse_pressed_stage3:
                                click_x_screen = int(
                                    window_origin[0] + img_pil.width * CLICK_POSITION_STAGE3_X_RATIO)
                                click_y_screen = int(
                                    window_origin[1] + img_pil.height * CLICK_POSITION_STAGE3_Y_RATIO)
                                win32api.mouse_event(
                                    win32con.MOUSEEVENTF_LEFTUP, click_x_screen, click_y_screen, 0, 0)
                                is_mouse_pressed_stage3 = False
                                print("松开鼠标 (因 'bound'/'bound blue' 超时消失)")
                            current_state = STATE_CHECK_RESULT
                            bound_absence_start_time = None  # 重置计时器
                            initial_wait_done_stage4 = False  # 确保下次进入第四阶段时会等待
                            print("进入检查结果状态 (STATE_CHECK_RESULT)")
                            continue  # 跳过本轮后续逻辑
                        else:
                            print(
                                f"'bound'/'bound blue' 仍未出现，已等待 {time_elapsed_since_bound_gone:.2f}s...")
                            # 保持鼠标松开状态
                            if is_mouse_pressed_stage3:  # Should not happen if logic above is correct
                                click_x_screen = int(
                                    window_origin[0] + img_pil.width * CLICK_POSITION_STAGE3_X_RATIO)
                                click_y_screen = int(
                                    window_origin[1] + img_pil.height * CLICK_POSITION_STAGE3_Y_RATIO)
                                win32api.mouse_event(
                                    win32con.MOUSEEVENTF_LEFTUP, click_x_screen, click_y_screen, 0, 0)
                                is_mouse_pressed_stage3 = False
                                print("松开鼠标 (等待 'bound'/'bound blue' 重新出现或超时)")

            elif current_state == STATE_CHECK_RESULT:
                if not initial_wait_done_stage4:
                    print("状态: 检查结果 - 执行初始等待2秒...")
                    time.sleep(2)
                    initial_wait_done_stage4 = True

                print("状态: 检查结果 - 持续检测 'start', 'stop', 'click'...")
                # 在此阶段，我们需要持续捕获屏幕并检测
                img_pil_stage4, window_origin_stage4, _ = capture_window_client_area(
                    TARGET_WINDOW_NAME)

                if img_pil_stage4 is None or window_origin_stage4 is None:
                    print("第四阶段：无法捕获窗口，1秒后重试并可能返回空闲状态...")
                    time.sleep(1)  # 等待一下再尝试，或者可以决定直接退出到IDLE
                    # current_state = STATE_IDLE # 可选：如果捕获持续失败则返回IDLE
                    # initial_wait_done_stage4 = False
                    continue

                detections_stage4 = detect_objects(
                    yolo_model, img_pil_stage4, CONFIDENCE_THRESHOLD)

                # 检查 'start'
                start_item = next(
                    (item for item in detections_stage4 if item["label"] == "start"), None)
                if start_item:
                    print("第四阶段：检测到 'start' 项。")
                    click_item_center(start_item["bbox"], window_origin_stage4)
                    current_state = STATE_WAITING_FOR_WEIGHT_MARK
                    initial_wait_done_stage4 = False  # 重置等待标记
                    # 重置第二阶段特定变量
                    pull_detected_timestamp_stage2 = 0
                    pull_item_info_stage2 = None
                    print("点击 'start'，返回第二阶段 (STATE_WAITING_FOR_WEIGHT_MARK)。")
                    continue  # 状态已改变，重新开始主循环

                # 检查 'stop'
                stop_item = next(
                    (item for item in detections_stage4 if item["label"] == "stop"), None)
                if stop_item:
                    print("第四阶段：检测到 'stop' 项。执行复杂操作序列...")

                    # a. 点击 "特定位置1"
                    click_x_stop1 = int(
                        window_origin_stage4[0] + img_pil_stage4.width * CLICK_POSITION_STAGE4_STOP_X_RATIO)
                    click_y_stop1 = int(
                        window_origin_stage4[1] + img_pil_stage4.height * CLICK_POSITION_STAGE4_STOP_Y_RATIO)
                    click_at_screen_coords(click_x_stop1, click_y_stop1)
                    print(
                        f"点击了 'stop' 后的特定位置1 ({click_x_stop1}, {click_y_stop1})。")
                    time.sleep(2)  # 等待2秒，确保退出钓鱼界面

                    # b. 点击 "特定位置2"
                    click_x_pos2 = int(
                        window_origin_stage4[0] + img_pil_stage4.width * CLICK_POS2_X_RATIO_AFTER_STOP)
                    click_y_pos2 = int(
                        window_origin_stage4[1] + img_pil_stage4.height * CLICK_POS2_Y_RATIO_AFTER_STOP)
                    click_at_screen_coords(click_x_pos2, click_y_pos2)
                    print(f"点击了特定位置2 ({click_x_pos2}, {click_y_pos2})。")
                    time.sleep(1)

                    # c. & d. 从 "特定位置3" 拖拽到 "特定位置4"
                    drag_x1 = int(
                        window_origin_stage4[0] + img_pil_stage4.width * DRAG_START_POS3_X_RATIO_AFTER_STOP)
                    drag_y1 = int(
                        window_origin_stage4[1] + img_pil_stage4.height * DRAG_START_POS3_Y_RATIO_AFTER_STOP)
                    drag_x2 = int(
                        window_origin_stage4[0] + img_pil_stage4.width * DRAG_END_POS4_X_RATIO_AFTER_STOP)
                    drag_y2 = int(
                        window_origin_stage4[1] + img_pil_stage4.height * DRAG_END_POS4_Y_RATIO_AFTER_STOP)
                    print(
                        f"准备从 ({drag_x1},{drag_y1}) 拖拽到 ({drag_x2},{drag_y2})")
                    mouse_drag(drag_x1, drag_y1, drag_x2, drag_y2,
                               move_duration=DRAG_DURATION_AFTER_STOP, steps=30)  # 增加steps使拖拽更平滑
                    print("拖拽操作完成。")
                    time.sleep(0.5)

                    # e. 查找并点击 'fish pool'
                    if find_and_click_item_in_stage4("fish pool", yolo_model, CONFIDENCE_THRESHOLD, TARGET_WINDOW_NAME):
                        print("成功点击 'fish pool'。")
                        time.sleep(0.2)  # 点击后短暂延时

                        # f. 只有成功点击 'fish pool' 后才查找并点击 'pathfind'
                        if find_and_click_item_in_stage4("pathfind", yolo_model, CONFIDENCE_THRESHOLD, TARGET_WINDOW_NAME):
                            print("成功点击 'pathfind'。")
                        else:
                            print("未能找到或点击 'pathfind'。")
                        time.sleep(0.2)

                        # g. 完成 'fish pool' 和 'pathfind' (或其一) 后回到第二阶段待命
                        current_state = STATE_WAITING_FOR_WEIGHT_MARK
                        initial_wait_done_stage4 = False  # 重置等待标记
                        pull_detected_timestamp_stage2 = 0  # 重置第二阶段变量
                        pull_item_info_stage2 = None
                        print(
                            "完成 'stop' 后序列操作（包含fish pool/pathfind），返回第二阶段 (STATE_WAITING_FOR_WEIGHT_MARK)。")
                        continue  # 状态已改变，重新开始主循环
                    else:
                        # 未能找到或点击 'fish pool'，则直接返回第二阶段
                        print("未能找到或点击 'fish pool'。返回第二阶段待命。")
                        current_state = STATE_WAITING_FOR_WEIGHT_MARK
                        initial_wait_done_stage4 = False  # 重置等待标记
                        pull_detected_timestamp_stage2 = 0  # 重置第二阶段变量
                        pull_item_info_stage2 = None
                        print(
                            "返回第二阶段 (STATE_WAITING_FOR_WEIGHT_MARK) - 因未找到fish pool。")
                        continue  # 状态已改变，重新开始主循环

                # 检查 'click'
                click_item = next(
                    (item for item in detections_stage4 if item["label"] == "click"), None)
                if click_item:
                    print("第四阶段：检测到 'click' 项，点击它。")
                    click_item_center(click_item["bbox"], window_origin_stage4)
                    print("点击了 'click'。继续在第四阶段检测。")
                    time.sleep(0.3)  # 点击后短暂延时，避免快速重复检测相同项或让界面有时间反应
                    # 保持在 STATE_CHECK_RESULT，initial_wait_done_stage4 已为 True，不会重复2秒等待
                    continue  # 重新评估第四阶段

                # 如果以上都没有检测到，则保持在第四阶段继续检测
                # print("第四阶段：未检测到 'start', 'stop', 或 'click'。继续检测...")
                # 无需显式 continue，主循环会自动再次进入此状态块

            time.sleep(REFRESH_RATE)  # 控制检测频率

    except KeyboardInterrupt:  # 捕获Ctrl+C
        print("程序被用户中断 (Ctrl+C)")
    except Exception as e:
        print(f"主循环发生错误: {e}")
    finally:  # 确保窗口关闭
        if DEBUG_SHOW_DETECTIONS:
            cv2.destroyAllWindows()
            print("调试窗口已关闭。")
        print("程序退出。")


if __name__ == "__main__":
    print(f"将识别 '{TARGET_WINDOW_NAME}' 窗口")
    print(f"YOLO 模型: {YOLO_MODEL_PATH}")
    print(f"置信度阈值: {CONFIDENCE_THRESHOLD}")
    print("按 Ctrl+C 退出程序")
    main_loop()

"""
测试对指定窗口的识别
"""

from ultralytics import YOLO
import cv2
import numpy as np
import time
import win32gui
import win32ui
from ctypes import windll

# 加载YOLO模型
model = YOLO("./models/best.pt")  # 使用已有的预训练模型

# 捕获窗口设置
window_name = "BlueStacks App Player"  # 替换为你想要捕获的窗口标题


def get_window_rect(window_name):
    """获取指定窗口的位置和尺寸"""
    hwnd = win32gui.FindWindow(None, window_name)
    if hwnd == 0:
        print(f"找不到窗口: {window_name}")
        return None

    # 获取窗口位置和尺寸
    rect = win32gui.GetWindowRect(hwnd)
    x, y, x1, y1 = rect
    width = x1 - x
    height = y1 - y

    return hwnd, x, y, width, height


def capture_window(window_name):
    """捕获指定窗口的图像"""
    result = get_window_rect(window_name)
    if result is None:
        return None

    hwnd, x, y, width, height = result

    # 创建设备上下文
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    # 创建位图对象
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
    saveDC.SelectObject(saveBitMap)

    # 尝试使用不同标志的PrintWindow
    # 0x2 = PW_RENDERFULLCONTENT 标志可以捕获更多类型的内容包括D3D
    result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0x2)

    # 如果使用0x2标志失败，尝试使用标准模式
    if not result:
        result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)

    # 转换为numpy数组
    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)
    img = np.frombuffer(bmpstr, dtype=np.uint8).reshape(
        bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4)

    # 只保留RGB通道，BGR格式用于OpenCV
    img = img[:, :, :3]

    # 垂直翻转图像 (PrintWindow可能会上下颠倒)
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # 释放资源
    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    # 检查图像是否为黑屏
    if np.mean(img) < 5:  # 平均像素值非常低，可能是黑屏
        print("检测不到窗口，可能最小化或已关闭，将在1秒后重试")
        time.sleep(1)

    return img


def main():
    prev_time = 0

    # 创建窗口
    cv2.namedWindow("YOLOv8 Real-time Detection", cv2.WINDOW_NORMAL)

    # 获取目标窗口的尺寸
    window_info = get_window_rect(window_name)
    if window_info is None:
        print(f"无法找到窗口: {window_name}")
        return

    _, _, _, width, height = window_info
    cv2.resizeWindow("YOLOv8 Real-time Detection", width, height)

    try:
        while True:
            # 捕获窗口
            img = capture_window(window_name)

            if img is None:
                print("无法捕获窗口")
                time.sleep(1)
                continue

            # 使用YOLO进行检测
            results = model(img, verbose=True)

            # 在图像上绘制检测结果
            annotated_img = results[0].plot()

            # 计算FPS
            current_time = time.time()
            fps = 1 / (current_time - prev_time)
            prev_time = current_time

            # 在图像上显示FPS
            cv2.putText(annotated_img, f"FPS: {fps:.1f}", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # 显示图像
            cv2.imshow("YOLOv8 Real-time Detection", annotated_img)

            # 按'q'退出
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("检测已停止")
    finally:
        cv2.destroyAllWindows()
        print("程序已退出")


if __name__ == "__main__":
    main()

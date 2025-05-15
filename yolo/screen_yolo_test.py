"""
测试对屏幕指定区域的识别，使用 pywin32 而不是 pyautogui
"""

from ultralytics import YOLO
import cv2
import numpy as np
import time
import os
import win32gui
import win32ui
import win32con
from ctypes import windll
from PIL import Image

# 加载YOLO模型
model = YOLO("./models/best.pt")  # 使用已有的预训练模型

# 设置捕获区域(这里可以根据需要修改坐标和大小)
# 格式为 (left, top, width, height)
capture_region = (694, 87, 525, 935)  # 默认值，你可以根据需要调整


def capture_screen(region=None):
    """使用pywin32从屏幕捕获图像"""
    if region:
        left, top, width, height = region
    else:
        left = 0
        top = 0
        width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

    # 创建设备上下文
    hdc = win32gui.GetDC(0)
    hdc_dc = win32ui.CreateDCFromHandle(hdc)
    compatible_dc = hdc_dc.CreateCompatibleDC()

    # 创建位图对象
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(hdc_dc, width, height)
    compatible_dc.SelectObject(bitmap)

    # 将屏幕内容复制到位图中
    compatible_dc.BitBlt((0, 0), (width, height), hdc_dc,
                         (left, top), win32con.SRCCOPY)

    # 将位图转换为numpy数组
    bmp_info = bitmap.GetInfo()
    bmp_bits = bitmap.GetBitmapBits(True)
    img = np.frombuffer(bmp_bits, dtype=np.uint8).reshape(height, width, 4)

    # 只保留RGB通道（去掉Alpha通道），Windows位图顺序是BGRA
    img = img[:, :, :3]  # 此时是BGR格式

    # 释放资源
    win32gui.DeleteObject(bitmap.GetHandle())
    compatible_dc.DeleteDC()
    hdc_dc.DeleteDC()
    win32gui.ReleaseDC(0, hdc)

    # 直接返回BGR格式图像，无需转换，因为OpenCV默认使用BGR
    return img


def main():
    prev_time = 0

    # 创建窗口
    cv2.namedWindow("YOLOv8 Real-time Detection", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("YOLOv8 Real-time Detection",
                     capture_region[2], capture_region[3])

    try:
        while True:
            # 捕获屏幕
            img = capture_screen(region=capture_region)

            # 使用YOLO进行检测
            results = model(img, conf=0.8, verbose=False)

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
    # 导入win32api只在main中使用，避免可能的循环导入
    import win32api
    main()

"""
捕获游戏窗口截图
"""

import keyboard
import win32gui
import win32ui  # 添加导入
import win32con  # 添加导入
import datetime
import os
from PIL import Image
import time
import mss
import numpy as np

# 配置参数
SAVE_DIR = r"D:\My_Scripts\git\AutoFK\yolo\screenshots"  # 保存截图的文件夹
TARGET_WINDOW_NAME = "BlueStacks App Player"  # 要截图的窗口名称，请修改为你需要截图的窗口名称

# 确保保存目录存在
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)


def get_window_rect(window_name):
    """获取指定窗口的位置和大小"""
    hwnd = win32gui.FindWindow(None, window_name)
    if hwnd == 0:
        print(f"找不到窗口: {window_name}")
        return None, None

    # 获取窗口位置
    rect = win32gui.GetWindowRect(hwnd)
    x = rect[0]
    y = rect[1]
    width = rect[2] - x
    height = rect[3] - y
    return (x, y, width, height), hwnd


def get_next_filename(save_dir):
    """获取下一个截图文件名"""
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    existing_files = os.listdir(save_dir)
    max_num = 0
    for f_name in existing_files:
        if f_name.endswith(".png"):
            try:
                num = int(os.path.splitext(f_name)[0])
                if num > max_num:
                    max_num = num
            except ValueError:
                # 文件名不是纯数字，忽略
                pass
    return os.path.join(save_dir, f"{max_num + 1}.png")


def capture_window(window_name):
    """对指定窗口进行截图并保存"""
    rect, hwnd = get_window_rect(window_name)
    if not rect:
        return

    x, y, width, height = rect
    # timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # filename = f"{SAVE_DIR}/screenshot_{timestamp}.png"
    filename = get_next_filename(SAVE_DIR)

    try:
        # 使用mss库进行截图，更好地支持多显示器
        with mss.mss() as sct:
            # 定义截图区域
            monitor = {"top": y, "left": x, "width": width, "height": height}

            # 捕获屏幕
            sct_img = sct.grab(monitor)

            # 转换为PIL图像
            img = Image.frombytes("RGB", sct_img.size,
                                  sct_img.bgra, "raw", "BGRX")

            # 保存图像
            img.save(filename)
            print(f"截图已保存: {filename}")

    except Exception as e:
        print(f"截图失败: {e}")
        try:
            # 尝试使用传统的win32gui方法
            # 使窗口处于前台
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.2)  # 等待窗口激活

            # 使用win32gui和win32ui截图
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()

            # 创建位图对象
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)

            # 复制窗口内容到位图对象
            saveDC.BitBlt((0, 0), (width, height), mfcDC,
                          (0, 0), win32con.SRCCOPY)

            # 转换为PIL Image并保存
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1)

            img.save(filename)
            print(f"使用备用方法保存截图: {filename}")

            # 清理资源
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)
            win32gui.DeleteObject(saveBitMap.GetHandle())
        except Exception as e2:
            print(f"所有截图方法都失败: {e2}")


def on_key_press(event):
    """键盘按键事件处理函数"""
    if event.name == 'z':
        print("检测到Z键被按下，开始截图...")
        capture_window(TARGET_WINDOW_NAME)


def main():
    """主函数"""
    print(f"截图工具已启动。按下Z键对窗口 '{TARGET_WINDOW_NAME}' 进行截图")
    print(f"截图将保存到 '{SAVE_DIR}' 文件夹")
    print("按下 Ctrl+C 退出程序")

    # 注册键盘事件
    keyboard.on_press(on_key_press)

    # 保持程序运行
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("程序已退出")


if __name__ == "__main__":
    main()

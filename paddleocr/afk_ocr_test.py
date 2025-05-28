import time
import win32gui
import win32con
from mss import mss
from paddleocr import PaddleOCR
import numpy as np
from PIL import Image


class WindowOCR:
    def __init__(self, window_title):
        self.window_title = window_title
        self.hwnd = None
        self.ocr = PaddleOCR(use_angle_cls=True, lang='ch')  # 初始化OCR，支持中文
        self.sct = mss()

    def find_window(self):
        """查找指定标题的窗口"""
        def enum_windows_proc(hwnd, lParam):
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                if self.window_title in window_text:
                    self.hwnd = hwnd
                    return False
            return True

        win32gui.EnumWindows(enum_windows_proc, 0)
        return self.hwnd is not None

    def get_window_rect(self):
        """获取窗口坐标"""
        if not self.hwnd:
            return None

        try:
            rect = win32gui.GetWindowRect(self.hwnd)
            return {
                "top": rect[1],
                "left": rect[0],
                "width": rect[2] - rect[0],
                "height": rect[3] - rect[1]
            }
        except:
            return None

    def capture_window(self):
        """截取窗口画面"""
        rect = self.get_window_rect()
        if not rect:
            return None

        try:
            screenshot = self.sct.grab(rect)
            # 转换为PIL Image
            img = Image.frombytes("RGB", screenshot.size,
                                  screenshot.bgra, "raw", "BGRX")
            return np.array(img)
        except Exception as e:
            print(f"截图失败: {e}")
            return None

    def perform_ocr(self, image):
        """执行OCR识别"""
        if image is None:
            return []

        try:
            result = self.ocr.ocr(image, cls=True)
            return result
        except Exception as e:
            print(f"OCR识别失败: {e}")
            return []

    def extract_text(self, ocr_result):
        """提取识别到的文字"""
        texts = []
        if ocr_result and len(ocr_result) > 0:
            for line in ocr_result[0]:
                if line:
                    # 获取文字框坐标
                    box = line[0]
                    text = line[1][0]
                    confidence = line[1][1]

                    # 计算文字框的左上角和右下角坐标
                    x1, y1 = int(box[0][0]), int(box[0][1])
                    x2, y2 = int(box[2][0]), int(box[2][1])

                    texts.append(
                        f"{text} [坐标: ({x1},{y1})-({x2},{y2})] (置信度: {confidence:.2f})")
        return texts

    def start_monitoring(self, interval=0.5):
        """开始监控窗口"""
        if not self.find_window():
            print(f"未找到窗口: {self.window_title}")
            return

        print(f"开始监控窗口: {self.window_title}")
        print(f"识别间隔: {interval}秒")
        print("按 Ctrl+C 停止监控")
        print("-" * 50)

        try:
            while True:
                # 重新查找窗口（防止窗口被关闭或移动）
                if not win32gui.IsWindow(self.hwnd):
                    print("窗口已关闭，重新查找...")
                    if not self.find_window():
                        print("窗口不存在，停止监控")
                        break

                # 截取窗口
                image = self.capture_window()
                if image is not None:
                    # 执行OCR
                    ocr_result = self.perform_ocr(image)
                    texts = self.extract_text(ocr_result)

                    # 打印结果
                    current_time = time.strftime("%H:%M:%S")
                    print(f"[{current_time}] 识别结果:")
                    if texts:
                        for text in texts:
                            print(f"  {text}")
                    else:
                        print("  未识别到文字")
                    print("-" * 30)

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n监控已停止")
        except Exception as e:
            print(f"发生错误: {e}")


def main():
    # 修改这里的窗口标题为您要监控的窗口
    window_title = "BlueStacks App Player"  # 示例：监控记事本窗口

    # 创建OCR监控实例
    ocr_monitor = WindowOCR(window_title)

    # 开始监控
    ocr_monitor.start_monitoring(1)


if __name__ == "__main__":
    main()

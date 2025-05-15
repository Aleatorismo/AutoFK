import sys
import time
import win32gui
import win32api
import win32con

TARGET_WINDOW_NAME = "BlueStacks App Player"


def get_window_client_rect_by_name(window_name):
    """获取指定窗口客户区的屏幕坐标和大小 (x, y, width, height) 及窗口句柄 hwnd."""
    hwnd = win32gui.FindWindow(None, window_name)
    if hwnd == 0:
        print(f"错误: 找不到窗口 '{window_name}'。请确保目标窗口已打开并且名称正确。")
        return None, None

    try:
        # 获取窗口的完整矩形（包括边框和标题栏）
        rect = win32gui.GetWindowRect(hwnd)
        # 获取窗口客户区的矩形（相对于窗口左上角）
        client_rect = win32gui.GetClientRect(hwnd)

        # 将客户区坐标转换为屏幕坐标
        client_x_screen, client_y_screen = win32gui.ClientToScreen(
            hwnd, (client_rect[0], client_rect[1]))

        client_width = client_rect[2] - client_rect[0]
        client_height = client_rect[3] - client_rect[1]

        if client_width <= 0 or client_height <= 0:
            print(
                f"错误: 窗口 '{window_name}' 的客户区大小无效 (width={client_width}, height={client_height})。")
            return None, None

        # print(f"原始窗口矩形: {rect}")
        # print(f"客户区矩形 (相对): {client_rect}")
        # print(f"客户区左上角屏幕坐标: ({client_x_screen}, {client_y_screen})")
        # print(f"客户区计算后大小: width={client_width}, height={client_height}")

        return (client_x_screen, client_y_screen, client_width, client_height), hwnd
    except Exception as e:
        print(f"获取窗口 '{window_name}' 客户区时发生错误: {e}")
        return None, None


# click_at_screen_coords 函数不再需要，因为我们只移动鼠标
# def click_at_screen_coords(x, y):
#     """在屏幕指定坐标执行鼠标左键单击"""
#     try:
#         win32api.SetCursorPos((x, y))
#         time.sleep(0.05)  # 短暂延时确保光标到位
#         win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
#         time.sleep(0.05)  # 模拟按键时长
#         win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
#         print(f"已在屏幕坐标 ({x}, {y}) 执行点击。")
#     except Exception as e:
#         print(f"点击屏幕坐标 ({x}, {y}) 时发生错误: {e}")


if __name__ == "__main__":
    print(f"--- 窗口相对坐标点击测试脚本 ---")
    print(f"目标窗口名称: '{TARGET_WINDOW_NAME}'")
    print("按 Ctrl+C 退出脚本。")

    client_area_rect, hwnd = None, None  # Initialize to ensure they are defined

    try:
        while True:
            print("\n请输入X轴和Y轴的比例值 (0.0 到 1.0)。")
            try:
                ratio_x_str = input("请输入X轴比例 (例如 0.5): ")
                ratio_x = float(ratio_x_str)
                if not (0.0 <= ratio_x <= 1.0):
                    print("错误: X轴比例必须在 0.0 和 1.0 之间。请重新输入。")
                    continue

                ratio_y_str = input("请输入Y轴比例 (例如 0.5): ")
                ratio_y = float(ratio_y_str)
                if not (0.0 <= ratio_y <= 1.0):
                    print("错误: Y轴比例必须在 0.0 和 1.0 之间。请重新输入。")
                    continue

            except ValueError:
                print("错误: 输入的比例值无效，请输入数字。请重新输入。")
                continue
            except EOFError:  # Handle Ctrl+D or similar that might close input stream
                print("\n输入流结束，脚本退出。")
                break

            # 尝试在每次循环时获取窗口句柄，以防窗口被关闭后重新打开
            print(f"\n正在查找窗口 '{TARGET_WINDOW_NAME}'...")
            client_area_rect, hwnd = get_window_client_rect_by_name(
                TARGET_WINDOW_NAME)

            if client_area_rect and hwnd:
                win_x, win_y, win_width, win_height = client_area_rect
                print(f"成功找到窗口 '{TARGET_WINDOW_NAME}'。")
                print(f"  客户区左上角屏幕坐标: ({win_x}, {win_y})")
                print(f"  客户区尺寸: Width={win_width}, Height={win_height}")

                abs_click_x = int(win_x + (win_width * ratio_x))
                abs_click_y = int(win_y + (win_height * ratio_y))

                print(f"\n输入比例: X={ratio_x:.3f}, Y={ratio_y:.3f}")
                print(f"计算得到的绝对屏幕坐标: ({abs_click_x}, {abs_click_y})")

                try:
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.1)
                except Exception as e_fg:
                    print(f"警告: 尝试置顶窗口失败: {e_fg} (鼠标仍会移动)")

                try:
                    win32api.SetCursorPos((abs_click_x, abs_click_y))
                    print(f"鼠标已移动到屏幕坐标 ({abs_click_x}, {abs_click_y})。")
                except Exception as e_setpos:
                    print(
                        f"移动鼠标到 ({abs_click_x}, {abs_click_y}) 时发生错误: {e_setpos}")

                print("准备下一次输入...")

            else:
                print(
                    f"未能处理窗口 '{TARGET_WINDOW_NAME}'。请检查窗口是否已打开且名称无误。将等待后重试输入。")
                time.sleep(2)  # 如果窗口找不到，稍等一下再提示输入，避免刷屏

    except KeyboardInterrupt:
        print("\n脚本被用户中断 (Ctrl+C)。正在退出...")
    finally:
        print("脚本执行完毕。")

"""
批量重命名 game_capture.py 获取的截图
"""

import os
import re
from pathlib import Path


def rename_images(directory):
    """
    将指定目录下的所有图片按照"1.png", "2.png"这样的格式重命名，并按照自然数的顺序

    Args:
        directory (str): 图片所在的目录路径
    """
    # 支持的图片格式
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp',
                        '.gif', '.tiff', '.webp')

    # 获取目录下所有图片文件
    image_files = []
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path) and filename.lower().endswith(image_extensions):
            image_files.append(file_path)

    # 如果没有找到图片文件，则返回
    if not image_files:
        print(f"在目录 {directory} 中没有找到图片文件")
        return

    print(f"找到 {len(image_files)} 个图片文件")

    # 创建临时文件夹用于重命名，避免重命名冲突
    temp_dir = os.path.join(directory, "temp_rename")
    os.makedirs(temp_dir, exist_ok=True)

    # 先将所有文件移动到临时文件夹并添加前缀，避免重命名时的冲突
    temp_files = []
    for i, old_path in enumerate(image_files):
        file_ext = os.path.splitext(old_path)[1]
        temp_path = os.path.join(temp_dir, f"temp_{i+1}{file_ext}")
        os.rename(old_path, temp_path)
        temp_files.append((temp_path, i+1, file_ext))

    # 将临时文件移回原目录并按照序号重命名
    for temp_path, number, file_ext in temp_files:
        new_path = os.path.join(directory, f"{number}{file_ext}")
        os.rename(temp_path, new_path)
        print(f"重命名: {os.path.basename(temp_path)} -> {number}{file_ext}")

    # 删除临时文件夹
    os.rmdir(temp_dir)
    print(f"重命名完成，共处理 {len(image_files)} 个图片文件")


if __name__ == "__main__":
    # 获取用户输入的目录路径
    directory = input("请输入图片所在的目录路径: ")

    # 检查目录是否存在
    if not os.path.isdir(directory):
        print(f"错误: 目录 '{directory}' 不存在")
    else:
        rename_images(directory)

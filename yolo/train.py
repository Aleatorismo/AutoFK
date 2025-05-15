"""
训练模型
"""

from ultralytics import YOLO

if __name__ == "__main__":
    # 加载预训练模型（推荐用于训练）
    model = YOLO('yolov8n.pt')

    model.train(
        data='data.yaml',   # 数据集文件路径
        epochs=500,         # 训练轮次（默认：300）
        imgsz=640,          # 推理尺寸（默认：640）
        batch=32,           # 批处理大小（默认：16）
        device=0,           # 用于训练的设备（默认：0，GPU = 0，CPU = 'cpu'）
    )

    print("Training completed successfully!")

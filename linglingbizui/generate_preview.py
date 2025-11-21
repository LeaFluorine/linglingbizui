# -*- coding: utf-8 -*-
"""
Generate a preview image for the Bot Status plugin.
"""
from image_generator import ImageGenerator


def main():
    """
    Generates and saves a preview image using mock data.
    """
    mock_data = {
        "os_type": "Windows",
        "os_version": "11",
        "cpu_percent": 42.5,
        "ram_percent": 60.2,
        "ram_total_gb": 31.9,
        "ram_used_gb": 19.2,
        "disks": [
            {"mountpoint": "C:", "percent": 75.8, "total_gb": 465.2, "used_gb": 352.8},
            {"mountpoint": "D:", "percent": 40.1, "total_gb": 1863.0, "used_gb": 747.1},
        ],
        "boot_time": "10天 2小时 15分钟",
        "plugin_count": 25,
        "python_version": "3.11.4",
        "total_messages_24h": 12345,
        "bot_messages_24h": 5432,
    }

    generator = ImageGenerator()
    image_bytes = generator.generate(mock_data)

    with open("./preview.png", "wb") as f:
        f.write(image_bytes)

    print("✅ 预览图片 'preview.png' 已成功生成。")


if __name__ == "__main__":
    main()
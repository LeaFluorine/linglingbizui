# -*- coding: utf-8 -*-
"""
Bot Status Image Generator
"""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


class ImageGenerator:
    """生成状态图片"""

    def __init__(self):
        self.width = 1000
        self.height = 650  # 增加高度以容纳更多硬盘信息
        self.bg_color = (255, 255, 255)
        self.title_color = (0, 0, 0)
        self.text_color = (50, 50, 50)
        self.bar_bg_color = (230, 230, 230)
        self.brand_color = (54, 123, 240)  # #367BF0

        try:
            self.font_bold = ImageFont.truetype("msyh.ttc", 32)
            self.font_main = ImageFont.truetype("msyh.ttc", 18)
            self.font_small = ImageFont.truetype("msyh.ttc", 15)
        except OSError:
            # Fallback to default font if msyh.ttc is not found
            self.font_bold = ImageFont.load_default()
            self.font_main = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

    def generate(self, data: dict) -> bytes:
        """生成图片并返回字节"""
        image = Image.new("RGB", (self.width, self.height), self.bg_color)
        draw = ImageDraw.Draw(image)

        # 绘制标题
        self._draw_text(draw, "墨狐-Bot 状态", (50, 40), self.font_bold, self.title_color)

        # 绘制系统信息
        y_pos = 100
        self._draw_info_line(draw, "操作系统", f"{data['os_type']} {data['os_version']}", 50, y_pos)
        y_pos += 45
        self._draw_progress_bar(draw, "CPU", data["cpu_percent"], 50, y_pos)
        y_pos += 45
        self._draw_progress_bar(
            draw, "内存", data["ram_percent"], 50, y_pos, f"{data['ram_used_gb']:.2f}GB / {data['ram_total_gb']:.2f}GB"
        )
        y_pos += 45

        # 绘制硬盘信息 (支持多分区)
        for disk in data["disks"]:
            disk_label = f"硬盘 ({disk['mountpoint'].replace('/', '')})"
            disk_text_right = f"{disk['used_gb']:.2f}GB / {disk['total_gb']:.2f}GB"
            self._draw_progress_bar(draw, disk_label, disk["percent"], 50, y_pos, disk_text_right)
            y_pos += 45

        self._draw_info_line(draw, "在线时间", data["boot_time"], 50, y_pos)
        y_pos += 15

        # 绘制分割线
        y_pos += 40
        draw.line([(50, y_pos), (self.width - 50, y_pos)], fill=self.bar_bg_color, width=2)
        y_pos += 30

        # 绘制机器人信息
        self._draw_info_line(draw, "Python 版本", data["python_version"], 50, y_pos)
        y_pos += 40
        self._draw_info_line(draw, "已加载插件", str(data["plugin_count"]), 50, y_pos)
        y_pos += 40
        self._draw_info_line(draw, "总消息数 (24h)", str(data["total_messages_24h"]), 50, y_pos)
        y_pos += 40
        self._draw_info_line(draw, "机器人消息 (24h)", str(data["bot_messages_24h"]), 50, y_pos)

        # 绘制页脚
        self._draw_text(draw, "由 墨狐工作室 提供支持", (50, self.height - 40), self.font_small, self.text_color)

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _draw_text(self, draw, text, position, font, color):
        draw.text(position, text, font=font, fill=color)

    def _draw_info_line(self, draw, label, value, x, y):
        self._draw_text(draw, f"{label}:", (x, y), self.font_main, self.text_color)
        self._draw_text(draw, value, (x + 200, y), self.font_main, self.title_color)

    def _draw_progress_bar(self, draw, label, percentage, x, y, text_right=""):
        bar_width = 400
        bar_height = 22
        label_x_offset = 200

        # 绘制背景条
        draw.rectangle([x + label_x_offset, y, x + label_x_offset + bar_width, y + bar_height], fill=self.bar_bg_color)

        # 绘制前景条
        fill_width = bar_width * (percentage / 100)
        draw.rectangle([x + label_x_offset, y, x + label_x_offset + fill_width, y + bar_height], fill=self.brand_color)

        # 绘制标签
        self._draw_text(draw, f"{label}:", (x, y + 2), self.font_main, self.text_color)

        # 绘制百分比 (垂直居中)
        percentage_text = f"{percentage:.1f}%"
        text_bbox = draw.textbbox((0, 0), percentage_text, font=self.font_main)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        text_x = x + label_x_offset + (fill_width - text_width) / 2
        text_y = y + (bar_height - text_height) / 2 - 2  # 微调

        # 确保文本在蓝色条内部
        if text_width < fill_width - 10:
            self._draw_text(
                draw, percentage_text, (text_x, text_y), self.font_main, (255, 255, 255)
            )

        if text_right:
            self._draw_text(draw, text_right, (x + label_x_offset + bar_width + 15, y + 2), self.font_main, self.text_color)
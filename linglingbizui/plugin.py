"""
Bot Status Plugin
"""

import base64
import platform
import sys
from datetime import datetime, timedelta
from typing import ClassVar, Type

import psutil

from src.config.config import global_config
from src.plugin_system.apis import (
    message_api,
    plugin_manage_api,
)
from src.plugin_system import register_plugin
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.command_args import CommandArgs
from src.plugin_system.base.component_types import ChatType, PlusCommandInfo
from src.plugin_system.base.plus_command import PlusCommand
from src.plugin_system.utils.permission_decorators import require_permission

from .image_generator import ImageGenerator


class StatusCommand(PlusCommand):
    """显示系统和机器人状态"""

    command_name: str = "status"
    command_description: str = "显示机器人和系统的状态信息"
    command_aliases: ClassVar[list[str]] = ["状态", "zt"]
    chat_type_allow: ChatType = ChatType.ALL
    priority: int = 20

    @require_permission("access", deny_message="❌ 你没有权限使用此命令")
    async def execute(self, args: CommandArgs) -> tuple[bool, str | None, bool]:
        """执行命令"""
        try:
            await self.send_text("📊 正在收集状态信息并生成图片...")
            stats = await self._get_status_data()

            generator = ImageGenerator()
            image_bytes = generator.generate(stats)
            image_base64 = base64.b64encode(image_bytes).decode()

            await self.send_image(image_base64)

            return True, "状态图片已发送", True
        except Exception as e:
            await self.send_text(f"❌ 生成状态图时出错: {e}")
            return True, f"生成状态图失败: {e}", False

    async def _get_status_data(self) -> dict:
        """获取系统和机器人状态数据"""
        # 系统信息
        cpu_percent = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        # 硬盘信息 (支持多分区)
        disks_info = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks_info.append(
                    {
                        "mountpoint": part.mountpoint,
                        "percent": usage.percent,
                        "total_gb": usage.total / (1024**3),
                        "used_gb": usage.used / (1024**3),
                    }
                )
            except (PermissionError, FileNotFoundError):
                # 某些分区 (如光驱、未就绪的驱动器) 可能无法访问
                continue
        boot_time = datetime.fromtimestamp(psutil.boot_time())

        # 机器人信息
        plugin_count = len(plugin_manage_api.list_loaded_plugins())
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        # 聊天信息统计 (过去24小时)
        time_24_hours_ago = datetime.now() - timedelta(hours=24)

        # 注意：由于API限制，我们无法直接统计所有聊天的总消息。
        # 这里暂时使用一个变通的方法：获取所有聊天记录再计数，这可能会有性能问题。
        # 更优的方案是未来在数据库层面直接支持聚合查询。
        all_messages = await message_api.get_messages_by_time(
            start_time=time_24_hours_ago.timestamp(), end_time=datetime.now().timestamp()
        )
        total_messages_24h = len(all_messages)

        # 筛选出机器人的消息
        bot_user_id = str(global_config.bot.qq_account)
        bot_messages_24h = sum(1 for msg in all_messages if msg.get("user_id") == bot_user_id)

        return {
            "os_type": platform.system(),
            "os_version": platform.release(),
            "cpu_percent": cpu_percent,
            "ram_percent": ram.percent,
            "ram_total_gb": ram.total / (1024**3),
            "ram_used_gb": ram.used / (1024**3),
            "disks": disks_info,
            "boot_time": str(datetime.now() - boot_time).split(".")[0],
            "plugin_count": plugin_count,
            "python_version": python_version,
            "total_messages_24h": total_messages_24h,
            "bot_messages_24h": bot_messages_24h,
        }


from src.plugin_system.base.component_types import PermissionNodeField
@register_plugin
class BotStatusPlugin(BasePlugin):
    plugin_name: str = "bot_status"
    enable_plugin: bool = True
    config_file_name: str = "config.toml"  # 配置文件名

    def get_plugin_components(self) -> list[tuple[PlusCommandInfo, Type[PlusCommand]]]:
        """返回插件的PlusCommand组件"""
        return [(StatusCommand.get_plus_command_info(), StatusCommand)]

    permission_nodes: ClassVar[list[PermissionNodeField]] = [
        PermissionNodeField(
            node_name="access",
            description="可以使用/status命令查看机器人状态",
        )
    ]

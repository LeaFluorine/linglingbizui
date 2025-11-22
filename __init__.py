from src.plugin_system.base.plugin_metadata import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="mute_and_unmute", # <--- 修改：更贴切的名字 ---
    description="一个允许Master控制Bot在当前聊天流中静音和取消静音的插件。支持命令、别名、@唤醒和配置。", # <--- 修改：更准确的描述 ---
    usage="/mute_mai, /unmute_mai", # <--- 修改：实际的命令 ---
    version="1.0.0",
    author="LeaFluorine",
    license="GPL-v3.0-or-later",
    repository_url="https://github.com/minecraft1024a",
    keywords=["mute", "unmute", "silence", "control"], # <--- 修改：更相关的关键词 ---
    extra={
        "plugin_type": "info", # <--- 如果这不是一个信息查询类插件，可能需要修改 plugin_type ---
    },
    python_dependencies=["psutil", "Pillow"] # <--- 如果插件本身不需要 psutil 或 Pillow，应该移除 ---
)
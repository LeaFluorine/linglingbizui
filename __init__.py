from src.plugin_system.base.plugin_metadata import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="linglingbizui",
    description="一条指令让bot闭嘴闭眼",
    usage="/status",
    version="1.0.0",
    author="LeaFluorine",
    license="GPL-v3.0-or-later",
    repository_url="https://github.com/minecraft1024a",
    keywords=["status", "statistics", "management"],
    extra={
        "plugin_type": "info",
    },
    python_dependencies=["psutil", "Pillow"]
)

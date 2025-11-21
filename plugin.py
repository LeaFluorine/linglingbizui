import asyncio
import time
import re
from datetime import datetime, timedelta
from typing import List, Tuple, Type, Optional, Dict, Any

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    PlusCommand,
    ComponentInfo,
    ChatType,
    Handler,
    Message,
    HandlerReturn,
    send_api,
    storage_api,
    generator_api,
    ChatStream,
    ConfigField # 导入 ConfigField 用于定义配置
)

# --- 常量定义 ---
PLUGIN_NAME = "mute_and_unmute_plugin"
STORAGE_KEY_MUTED_STREAMS = "muted_streams" # 用于存储被禁言的聊天流ID及其解除时间
COMMAND_MUTE_NAME = "mute_mai"
COMMAND_UNMUTE_NAME = "unmute_mai"

class MuteMaiCommand(PlusCommand):
    """Master 用来让 Bot 在当前聊天流静音的命令。"""
    command_name = COMMAND_MUTE_NAME
    command_description = "让Bot在当前聊天流静音，可指定时长（默认从配置读取）"
    # command_aliases = [] # 不再使用 PlusCommand 的 aliases，由 Handler 处理
    chat_type_allow = ChatType.ALL # 允许在群聊和私聊中使用

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # 获取当前聊天流ID
        chat_stream: ChatStream = context.get('chat_stream')
        if not chat_stream:
            return {"success": False, "message": "无法获取当前聊天流信息。"}

        stream_id = chat_stream.stream_id

        # 获取存储实例
        plugin_storage = storage_api.get(PLUGIN_NAME)

        # 获取插件配置
        # 检查插件主功能是否启用
        plugin_enabled = self.get_config("plugin.enabled", True)
        if not plugin_enabled:
            await send_api.text_to_stream("❌ 插件已被禁用。", stream_id)
            return {"success": False, "message": "插件已禁用"}

        # 检查静音功能是否启用
        mute_enabled = self.get_config("features.mute_enabled", True)
        if not mute_enabled:
            await send_api.text_to_stream("❌ 静音功能已被禁用。", stream_id)
            return {"success": False, "message": "静音功能已禁用"}

        # 从 context 中获取参数 (通过 CommandArgs)
        args = context.get('args') # 假设 context 中包含 CommandArgs
        if args and not args.is_empty():
            duration_str = args.get_raw().strip()
            duration_minutes = self._parse_duration(duration_str)
            if duration_minutes is None:
                await send_api.text_to_stream("❌ 无法解析指定的时长，请使用如 '10min', '30分钟', '1小时' 等格式。", stream_id)
                return {"success": False, "message": "无法解析时长"}
        else:
            # 如果没有参数，从配置中获取默认时长
            duration_minutes = self.get_config("defaults.default_mute_minutes", 10)

        # 计算解除禁言的时间
        unmute_time = datetime.now() + timedelta(minutes=duration_minutes)

        # 更新存储中的禁言列表
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
        current_muted_streams[stream_id] = unmute_time.timestamp() # 存储时间戳
        plugin_storage[STORAGE_KEY_MUTED_STREAMS] = current_muted_streams

        # 从配置中获取提示词
        mute_message_template = self.get_config("messages.mute_start", "好的，我将在当前聊天中保持安静，直到 {unmute_time_str}。")
        unmute_time_str = unmute_time.strftime('%H:%M')
        mute_message = mute_message_template.format(unmute_time_str=unmute_time_str)

        # 发送确认消息
        await send_api.text_to_stream(mute_message, stream_id)

        print(f"[MuteAndUnmutePlugin] Muted stream {stream_id} for {duration_minutes} minutes until {unmute_time}")
        return {"success": True, "message": f"已设置在 {stream_id} 禁言 {duration_minutes} 分钟至 {unmute_time}"}

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """
        尝试从字符串中解析出分钟数。
        支持格式如: "10min", "30分钟", "1小时", "2h", "45m" 等。
        """
        duration_str = duration_str.lower()
        # 使用正则表达式匹配数字和单位
        # 匹配分钟: x分钟, xmin, xm
        min_match = re.search(r'(\d+)\s*(?:分钟|min|m)', duration_str)
        if min_match:
            return int(min_match.group(1))

        # 匹配小时: x小时, xh
        hour_match = re.search(r'(\d+)\s*(?:小时|h)', duration_str)
        if hour_match:
            return int(hour_match.group(1)) * 60 # 转换为分钟

        # 匹配天: x天
        day_match = re.search(r'(\d+)\s*天', duration_str)
        if day_match:
            return int(day_match.group(1)) * 24 * 60 # 转换为分钟

        # 如果没有匹配到任何单位，返回 None
        return None


class UnmuteMaiCommand(PlusCommand):
    """Master 用来让 Bot 在当前聊天流取消静音的命令。"""
    command_name = COMMAND_UNMUTE_NAME
    command_description = "让Bot在当前聊天流取消静音并开始思考"
    # command_aliases = [] # 不再使用 PlusCommand 的 aliases，由 Handler 处理
    chat_type_allow = ChatType.ALL # 允许在群聊和私聊中使用

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # 获取当前聊天流ID
        chat_stream: ChatStream = context.get('chat_stream')
        if not chat_stream:
            return {"success": False, "message": "无法获取当前聊天流信息。"}

        stream_id = chat_stream.stream_id

        # 获取插件配置
        # 检查插件主功能是否启用
        plugin_enabled = self.get_config("plugin.enabled", True)
        if not plugin_enabled:
            await send_api.text_to_stream("❌ 插件已被禁用。", stream_id)
            return {"success": False, "message": "插件已禁用"}

        # 检查静音功能是否启用
        mute_enabled = self.get_config("features.mute_enabled", True)
        if not mute_enabled:
            await send_api.text_to_stream("❌ 静音功能已被禁用。", stream_id)
            return {"success": False, "message": "静音功能已禁用"}

        # 获取存储实例
        plugin_storage = storage_api.get(PLUGIN_NAME)

        # 从存储中移除该聊天流的禁言记录
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
        if stream_id in current_muted_streams:
            del current_muted_streams[stream_id]
            plugin_storage[STORAGE_KEY_MUTED_STREAMS] = current_muted_streams
            print(f"[MuteAndUnmutePlugin] Unmuted stream {stream_id} via command.")
        else:
            print(f"[MuteAndUnmutePlugin] Attempted to unmute stream {stream_id} via command, but it was not muted.")
            # 即使未被禁言，也可能需要发送消息，但这里我们只在解除时发送
            # 可以选择发送一个提示，说明当前并未禁言
            # await send_api.text_to_stream("我当前并未被禁言哦。", stream_id)
            # 为了与原逻辑一致，我们只在成功解除时发送消息
            return {"success": True, "message": f"尝试取消 {stream_id} 的禁言，但该聊天流未被禁言。"}

        # 从配置中获取提示词
        unmute_message = self.get_config("messages.unmute_start", "好的，我恢复发言了！")

        # 发送确认消息
        await send_api.text_to_stream(unmute_message, stream_id)

        # 尝试触发一次主动思考
        try:
            replyer = generator_api.get_replyer(chat_stream=chat_stream)
            if replyer:
                success, reply_set, prompt = await generator_api.generate_reply(
                    chat_stream=chat_stream,
                    action_data={"type": "unmute_trigger", "message": "Master has unmuted me."}, # 模拟动作数据
                    reply_to="", # 不回复特定消息
                    available_actions=[], # 不提供具体动作，让模型决定
                    enable_tool=False, # 暂时禁用工具调用
                    return_prompt=False
                )
                if success:
                    print(f"[MuteAndUnmutePlugin] Attempted to trigger thinking after unmute in {stream_id}.")
                else:
                    print(f"[MuteAndUnmutePlugin] Failed to generate reply/trigger thinking after unmute in {stream_id}.")
            else:
                print(f"[MuteAndUnmutePlugin] Could not get replyer for stream {stream_id} to trigger thinking.")
        except Exception as e:
            print(f"[MuteAndUnmutePlugin] Error trying to trigger thinking after unmute: {e}")

        return {"success": True, "message": f"已取消 {stream_id} 的禁言，并尝试触发思考。"}


class AliasHandler(Handler):
    """
    消息处理器，用于检查消息内容是否匹配配置文件中的指令别名。
    如果匹配，则调用相应的命令逻辑，并尝试解析参数（如时长）。
    """
    handler_name = "alias_handler"
    handler_description = "处理配置文件中定义的指令别名及其参数"

    async def handle(self, args: Dict[str, Any]) -> HandlerReturn:
        message: Message = args.get('message')
        if not message:
            return HandlerReturn(intercepted=False)

        # 获取插件配置
        # 检查插件主功能是否启用
        plugin_enabled = self.get_config("plugin.enabled", True)
        if not plugin_enabled:
            return HandlerReturn(intercepted=False)

        # 检查静音功能是否启用
        mute_enabled = self.get_config("features.mute_enabled", True)
        if not mute_enabled:
            return HandlerReturn(intercepted=False)

        mute_aliases = self.get_config("aliases.mute", ["绫绫闭嘴"]) # 默认值
        # unmute_aliases = self.get_config("aliases.unmute", ["绫绫张嘴"]) # unmute 别名也可以有参数，但当前 unmute 逻辑不需要

        message_content = message.content.strip()

        # 检查是否匹配 mute 别名
        for alias in mute_aliases:
            if message_content.startswith(alias):
                # 提取别名后的部分作为参数
                param_str = message_content[len(alias):].strip()
                # 构造 context，包含原始 message 和参数
                class SimpleCommandArgs:
                    def __init__(self, raw_str: str):
                        self.raw_str = raw_str
                        self.args_list = raw_str.split() if raw_str else []

                    def is_empty(self):
                        return not self.raw_str.strip()

                    def get_raw(self):
                        return self.raw_str

                    def get_args(self):
                        return self.args_list

                    def count(self):
                        return len(self.args_list)

                    def get_first(self):
                        return self.args_list[0] if self.args_list else None

                    def get_remaining(self):
                        return " ".join(self.args_list[1:]) if len(self.args_list) > 1 else ""

                    def has_flag(self, flag: str):
                        return flag in self.args_list

                    def get_flag_value(self, flag: str, default=None):
                        try:
                            idx = self.args_list.index(flag)
                            if idx + 1 < len(self.args_list):
                                return self.args_list[idx + 1]
                            else:
                                return default
                        except ValueError:
                            return default

                command_args = SimpleCommandArgs(param_str) if param_str else None
                context_with_args = {
                    'chat_stream': message.chat_stream,
                    'message': message,
                    'args': command_args
                }

                result = await MuteMaiCommand().execute(context_with_args)
                print(f"[MuteAndUnmutePlugin] Executed mute command via alias '{alias}' with param '{param_str}' in {message.stream_id}. Result: {result}")
                return HandlerReturn(intercepted=False) # 不拦截

        # 检查是否匹配 unmute 别名 (同样处理参数，虽然当前 unmute 不需要)
        unmute_aliases = self.get_config("aliases.unmute", ["绫绫张嘴"])
        for alias in unmute_aliases:
            if message_content.startswith(alias):
                param_str = message_content[len(alias):].strip()
                class SimpleCommandArgs:
                    def __init__(self, raw_str: str):
                        self.raw_str = raw_str
                        self.args_list = raw_str.split() if raw_str else []

                    def is_empty(self):
                        return not self.raw_str.strip()

                    def get_raw(self):
                        return self.raw_str

                    def get_args(self):
                        return self.args_list

                    def count(self):
                        return len(self.args_list)

                    def get_first(self):
                        return self.args_list[0] if self.args_list else None

                    def get_remaining(self):
                        return " ".join(self.args_list[1:]) if len(self.args_list) > 1 else ""

                    def has_flag(self, flag: str):
                        return flag in self.args_list

                    def get_flag_value(self, flag: str, default=None):
                        try:
                            idx = self.args_list.index(flag)
                            if idx + 1 < len(self.args_list):
                                return self.args_list[idx + 1]
                            else:
                                return default
                        except ValueError:
                            return default

                command_args = SimpleCommandArgs(param_str) if param_str else None
                context_with_args = {
                    'chat_stream': message.chat_stream,
                    'message': message,
                    'args': command_args
                }
                result = await UnmuteMaiCommand().execute(context_with_args)
                print(f"[MuteAndUnmutePlugin] Executed unmute command via alias '{alias}' with param '{param_str}' in {message.stream_id}. Result: {result}")
                return HandlerReturn(intercepted=False) # 不拦截

        # 如果不匹配任何别名，则不处理，继续后续流程
        return HandlerReturn(intercepted=False)


class AtUnmuteHandler(Handler):
    """
    消息处理器，用于检查消息是否是 @ 了 Bot。
    如果 Bot 正在被禁言，且收到 @ 消息，则自动解除禁言。
    """
    handler_name = "at_unmute_handler"
    handler_description = "处理 @Bot 唤醒被禁言的 Bot"

    async def handle(self, args: Dict[str, Any]) -> HandlerReturn:
        message: Message = args.get('message')
        if not message:
            return HandlerReturn(intercepted=False)

        # 获取插件配置
        # 检查插件主功能是否启用
        plugin_enabled = self.get_config("plugin.enabled", True)
        if not plugin_enabled:
            return HandlerReturn(intercepted=False)

        # 检查静音功能是否启用
        mute_enabled = self.get_config("features.mute_enabled", True)
        if not mute_enabled:
            return HandlerReturn(intercepted=False)

        # 检查 @ 唤醒功能是否启用
        at_unmute_enabled = self.get_config("features.at_unmute_enabled", True)
        if not at_unmute_enabled:
            return HandlerReturn(intercepted=False)

        stream_id = message.stream_id
        plugin_storage = storage_api.get(PLUGIN_NAME)

        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})

        # 检查当前聊天流是否被禁言
        if stream_id in current_muted_streams:
            mute_until_timestamp = current_muted_streams[stream_id]
            current_time = time.time()

            if current_time < mute_until_timestamp:
                # Bot 确实处于禁言状态
                # 检查消息是否 @ 了 Bot
                try:
                    from src.config.config import global_config
                    bot_id = str(global_config.bot.qq_account)
                except ImportError:
                    print("[MuteAndUnmutePlugin] Error: Could not import global_config to get bot_id for @ check.")
                    return HandlerReturn(intercepted=False)

                # 检查消息是否 @ 了 Bot
                if hasattr(message, 'mentioned_user_ids') and bot_id in message.mentioned_user_ids:
                    # Bot 被 @ 了，且正处于禁言状态，自动解除禁言
                    del current_muted_streams[stream_id]
                    plugin_storage[STORAGE_KEY_MUTED_STREAMS] = current_muted_streams
                    print(f"[MuteAndUnmutePlugin] Unmuted stream {stream_id} because Bot was mentioned (@).")

                    # 从配置中获取提示词
                    at_unmute_message = self.get_config("messages.at_unmute", "我被 @ 了，所以恢复发言啦！")

                    # 发送解除禁言的消息
                    await send_api.text_to_stream(at_unmute_message, stream_id)

                    # 尝试触发一次主动思考
                    try:
                        replyer = generator_api.get_replyer(chat_stream=message.chat_stream)
                        if replyer:
                            success, reply_set, prompt = await generator_api.generate_reply(
                                chat_stream=message.chat_stream,
                                action_data={"type": "at_unmute_trigger", "message": f"Bot was mentioned (@) by {message.user_info.user_nickname}."}, # 模拟动作数据
                                reply_to="", # 不回复特定消息
                                available_actions=[], # 不提供具体动作，让模型决定
                                enable_tool=False, # 暂时禁用工具调用
                                return_prompt=False
                            )
                            if success:
                                print(f"[MuteAndUnmutePlugin] Attempted to trigger thinking after @ unmute in {stream_id}.")
                            else:
                                print(f"[MuteAndUnmutePlugin] Failed to generate reply/trigger thinking after @ unmute in {stream_id}.")
                        else:
                            print(f"[MuteAndUnmutePlugin] Could not get replyer for stream {stream_id} to trigger thinking after @ unmute.")
                    except Exception as e:
                        print(f"[MuteAndUnmutePlugin] Error trying to trigger thinking after @ unmute: {e}")

                    return HandlerReturn(intercepted=False)
            # 如果禁言已过期，也直接返回不拦截，让 MuteHandler 去清理过期记录

        # 如果当前聊天流未被禁言，或 Bot 未被 @，或 @ 唤醒功能被禁用，则不处理
        return HandlerReturn(intercepted=False)


class MuteHandler(Handler):
    """
    消息处理器，用于检查当前聊天流是否被禁言。
    如果被禁言且未过期，则拦截消息，阻止Bot回复。
    这个处理器应该在 AtUnmuteHandler 之后执行，以确保 @ 检查优先。
    """
    handler_name = "mute_status_handler"
    handler_description = "检查并拦截被禁言聊天流的消息"

    async def handle(self, args: Dict[str, Any]) -> HandlerReturn:
        message: Message = args.get('message')
        if not message:
            return HandlerReturn(intercepted=False)

        # 获取插件配置
        # 检查插件主功能是否启用
        plugin_enabled = self.get_config("plugin.enabled", True)
        if not plugin_enabled:
            return HandlerReturn(intercepted=False)

        # 检查静音功能是否启用
        mute_enabled = self.get_config("features.mute_enabled", True)
        if not mute_enabled:
            return HandlerReturn(intercepted=False)

        stream_id = message.stream_id
        plugin_storage = storage_api.get(PLUGIN_NAME)

        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})

        if stream_id in current_muted_streams:
            mute_until_timestamp = current_muted_streams[stream_id]
            current_time = time.time()

            if current_time < mute_until_timestamp:
                # 当前时间仍在禁言时间内
                print(f"[MuteAndUnmutePlugin] Message intercepted in muted stream {stream_id}. Time remaining: {timedelta(seconds=int(mute_until_timestamp - current_time))}")
                # 从配置中获取禁言期间的提示词（如果有的话）
                mute_reply_message = self.get_config("messages.muted_reply", "") # 默认为空，不回复
                if mute_reply_message:
                    # 可以选择是否回复一条消息告知用户处于禁言状态
                    # 但通常禁言就是不回复，所以这里可以选择不发送
                    # await send_api.text_to_stream(mute_reply_message, stream_id)
                    pass
                # 返回 HandlerReturn 表示拦截此消息，不进行后续处理
                return HandlerReturn(intercepted=True, message="Message intercepted due to mute.")
            else:
                # 禁言时间已过，移除记录
                del current_muted_streams[stream_id]
                plugin_storage[STORAGE_KEY_MUTED_STREAMS] = current_muted_streams
                print(f"[MuteAndUnmutePlugin] Mute expired for stream {stream_id}. Removed from muted list.")

        # 如果未被禁言或禁言已过期，则不拦截，继续处理
        return HandlerReturn(intercepted=False) # 表示不拦截


@register_plugin
class MuteAndUnmutePlugin(BasePlugin):
    """主插件类，注册命令、处理器，并定义配置结构。"""

    plugin_name = PLUGIN_NAME
    plugin_description = "一个允许Master控制Bot在当前聊天流中静音和取消静音的插件。支持配置别名、提示词、功能开关和默认值。"

    # --- 配置相关 ---
    config_file_name = "config.toml"

    # 定义插件配置结构
    config_schema = {
        "plugin": {
            "enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用整个插件。如果为 false，所有功能（静音、@唤醒等）都将被禁用。",
                example=True
            )
        },
        "features": {
            "mute_enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用静音/取消静音功能。如果为 false，/mute_mai, /unmute_mai 及其别名将无效。",
                example=True
            ),
            "at_unmute_enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用 @Bot 唤醒功能。如果为 false，@Bot 将不会解除禁言。",
                example=True
            )
        },
        "defaults": {
            "default_mute_minutes": ConfigField(
                type=int,
                default=10,
                description="当指令中未指定时长时，静音的默认时长（单位：分钟）。",
                example=30
            )
        },
        "aliases": {
            "mute": ConfigField(
                type=list,
                default=["绫绫闭嘴"],
                description="触发静音命令的别名列表，例如 ['绫绫闭嘴', '星尘闭嘴', '阿绫闭嘴', '乐正绫闭嘴']",
                example=["绫绫闭嘴", "星尘闭嘴", "阿绫闭嘴", "乐正绫闭嘴"]
            ),
            "unmute": ConfigField(
                type=list,
                default=["绫绫张嘴"],
                description="触发取消静音命令的别名列表，例如 ['绫绫张嘴', '星尘张嘴']",
                example=["绫绫张嘴", "星尘张嘴"]
            ),
        },
        "messages": {
            "mute_start": ConfigField(
                type=str,
                default="好的，我将在当前聊天中保持安静，直到 {unmute_time_str}。",
                description="Bot 开始静音时发送的提示消息模板。{unmute_time_str} 会被替换为解除静音的时间。",
                example="好的，我将在当前聊天中保持安静，直到 {unmute_time_str}。"
            ),
            "unmute_start": ConfigField(
                type=str,
                default="好的，我恢复发言了！",
                description="Bot 取消静音时发送的提示消息。",
                example="好的，我恢复发言了！"
            ),
            "muted_reply": ConfigField(
                type=str,
                default="",
                description="Bot 在被禁言期间，如果有人说话（非@），Bot 可能会回复的提示消息。留空则不回复。",
                example="我正在闭嘴，暂时不能说话哦~"
            ),
            "at_unmute": ConfigField(
                type=str,
                default="我被 @ 了，所以恢复发言啦！",
                description="Bot 被 @ 时自动解除禁言后发送的提示消息。",
                example="我被 @ 了，所以恢复发言啦！"
            )
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        components = []

        # 注册主命令 (用于 /mute_mai 和 /unmute_mai)
        components.append((MuteMaiCommand.get_plus_command_info(), MuteMaiCommand))
        components.append((UnmuteMaiCommand.get_plus_command_info(), UnmuteMaiCommand))

        # 注册别名处理器 (处理配置文件中的别名及其参数)
        components.append((AliasHandler.get_handler_info(), AliasHandler))

        # 注册 @ 唤醒处理器 (检查并解除因 @ 而被禁言的 Bot)
        components.append((AtUnmuteHandler.get_handler_info(), AtUnmuteHandler))

        # 注册禁言状态处理器 (检查并拦截消息)
        components.append((MuteHandler.get_handler_info(), MuteHandler))

        return components

    async def on_plugin_loaded(self):
        """
        插件加载时的钩子函数。
        清空存储中所有已保存的禁言列表，确保插件状态与程序状态一致。
        """
        # 获取存储实例
        plugin_storage = storage_api.get(PLUGIN_NAME)

        # 获取当前存储的禁言列表
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})

        if current_muted_streams:
            # 如果列表不为空，则清空它
            plugin_storage[STORAGE_KEY_MUTED_STREAMS] = {}
            print(f"[MuteAndUnmutePlugin] 在插件加载时清空了 {len(current_muted_streams)} 条旧的禁言记录。")
        else:
            print(f"[MuteAndUnmutePlugin] 插件加载时，禁言列表为空，无需清空。")

        # 可选：如果需要，可以在此处发送一条系统日志或通知给 Master
        # 例如：await send_api.text_to_master("MuteAndUnmutePlugin 已加载，并清空了旧的禁言记录。")
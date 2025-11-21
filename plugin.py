import asyncio
import time
import re
from datetime import datetime, timedelta
from typing import List, Tuple, Type, Optional, Dict, Any # 导入 Any 用于类型注解

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    PlusCommand,
    ComponentInfo,
    ChatType,
    # Handler,  # --- 移除 ---
    # HandlerReturn, # --- 移除 ---
    BaseEventHandler, # --- 添加 ---
    # HandlerResult, # --- 移除 ---
    # ChatStream, # --- 移除 ---
    ConfigField, # 导入 ConfigField 用于定义配置
    EventType, # --- 添加：导入 EventType ---
    CommandArgs # --- 添加：导入 CommandArgs ---
)
# from src.plugin_system.base.base_event import Message, HandlerResult # --- 移除 Message ---
from src.plugin_system.base.base_event import HandlerResult # --- 仅保留 HandlerResult ---
# from src.chat.chat_stream import ChatStream # --- 移除 ---
# 尝试从可能的路径导入 ChatStream
# 根据知识库和原理剖析，ChatStream 位于 src.chat.message_receive.chat_stream
try:
    from src.chat.message_receive.chat_stream import ChatStream
except ImportError:
    # 如果从预期路径导入失败，定义一个占位符或使用 Any
    ChatStream: Any = Any # type: ignore

# 尝试从可能的路径导入 Message (根据原理剖析，可能是 MessageRecv)
# 根据知识库和原理剖析，MessageRecv 位于 src.chat.message_receive.message
try:
    from src.chat.message_receive.message import MessageRecv as Message
except ImportError:
    # 如果从预期路径导入失败，定义一个占位符或使用 Any
    Message: Any = Any # type: ignore

from src.plugin_system.apis import chat_api

# --- 添加：导入 Chatter 相关 ---
from src.plugin_system.base.base_chatter import BaseChatter
from src.common.data_models.message_manager_data_model import StreamContext
from src.plugin_system.base.component_types import ChatType as ChatterChatType # 重命名以避免与 PlusCommand 的 ChatType 冲突
from src.chat.planner_actions.action_manager import ChatterActionManager # TYPE_CHECKING 模拟
from src.plugin_system.apis import send_api, generator_api, storage_api

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

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]: # --- 修改：方法签名 ---
        # 获取当前聊天流ID (通过 self.chat_stream)
        chat_stream: ChatStream = self.chat_stream # --- 修改：使用 self.chat_stream ---
        if not chat_stream:
            # self.send_text 可能需要在有 chat_stream 的情况下才能工作
            # 如果没有 chat_stream，无法发送消息
            return (False, "无法获取当前聊天流信息。", False)

        stream_id = chat_stream.stream_id

        # --- 修改：获取存储实例 ---
        # plugin_storage = storage_api.get(PLUGIN_NAME) # --- 移除 ---
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME) # --- 添加 ---

        # 获取插件配置
        # 检查插件主功能是否启用
        plugin_enabled = self.get_config("plugin.enabled", True)
        if not plugin_enabled:
            await send_api.text_to_stream("❌ 插件已被禁用。", stream_id)
            return (False, "插件已禁用", False) # --- 修改：返回元组 ---

        # 检查静音功能是否启用
        mute_enabled = self.get_config("features.mute_enabled", True)
        if not mute_enabled:
            await send_api.text_to_stream("❌ 静音功能已被禁用。", stream_id)
            return (False, "静音功能已禁用", False) # --- 修改：返回元组 ---

        # 从 args 中获取参数 # --- 修改：添加类型和属性检查 ---
        duration_str = ""
        if isinstance(args, CommandArgs): # 确认 args 是 CommandArgs 实例
            if hasattr(args, 'is_empty') and callable(getattr(args, 'is_empty')): # 检查 is_empty 是否为方法
                if not args.is_empty():
                    duration_str = args.get_raw().strip()
            else:
                print(f"[MuteMaiCommand] WARNING: 'args' does not have a callable 'is_empty' method or 'is_empty' is not a method. Got type: {type(getattr(args, 'is_empty', None))}, value: {getattr(args, 'is_empty', 'NOT_FOUND')}")
                # 如果 is_empty 不是方法，我们假设它本身就是布尔值，表示是否为空
                # 但这与 CommandArgs 的预期行为不符，需要谨慎处理
                # 这里我们暂时跳过参数解析，或者记录错误
                is_empty_attr = getattr(args, 'is_empty', None)
                if isinstance(is_empty_attr, bool): # 如果 is_empty 属性恰好是布尔值
                     print(f"[MuteMaiCommand] WARNING: 'args.is_empty' seems to be a boolean value ({is_empty_attr}), not a method. This is unexpected.")
                     # 如果 is_empty 是 True，表示为空
                     # if is_empty_attr: # args is empty
                     #    duration_str = ""
                     # else: # args is not empty, but we cannot get the raw value
                     #    # This case is problematic, as we don't know how to get the raw value
                     #    # For now, let's assume we cannot parse the argument and treat it as empty
                     #    duration_str = ""
                else:
                    # 如果 is_empty 不是布尔值也不是方法，可能是其他属性或 None
                    # 我们尝试直接获取 raw_value 或类似属性
                    # 但这依赖于 CommandArgs 的具体实现
                    duration_str = getattr(args, 'raw_value', '') or getattr(args, 'raw', '') or ''
        else:
            print(f"[MuteMaiCommand] ERROR: 'args' is not an instance of CommandArgs. Got type: {type(args)}, value: {args}")
            # 如果 args 不是预期的类型，直接返回错误
            return (False, f"'args' is not a CommandArgs instance. Got type: {type(args)}.", False)

        if duration_str:
            duration_minutes = self._parse_duration(duration_str)
            if duration_minutes is None:
                await send_api.text_to_stream("❌ 无法解析指定的时长，请使用如 '10min', '30分钟', '1小时' 等格式。", stream_id)
                return (False, "无法解析时长", False) # --- 修改：返回元组 ---
        else:
            # 如果没有参数，从配置中获取默认时长
            duration_minutes = self.get_config("defaults.default_mute_minutes", 10)

        # 计算解除禁言的时间
        unmute_time = datetime.now() + timedelta(minutes=duration_minutes)

        # 更新存储中的禁言列表
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
        current_muted_streams[stream_id] = unmute_time.timestamp() # 存储时间戳
        plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams) # --- 修改：使用 plugin_storage.set ---

        # 从配置中获取提示词
        mute_message_template = self.get_config("messages.mute_start", "好的，我将在当前聊天中保持安静，直到 {unmute_time_str}。")
        unmute_time_str = unmute_time.strftime('%H:%M')
        mute_message = mute_message_template.format(unmute_time_str=unmute_time_str)

        # 发送确认消息 (使用 self.send_text 或 send_api)
        # self.send_text 是 PlusCommand 内置方法，应该更可靠
        await self.send_text(mute_message) # --- 修改：使用 self.send_text ---

        print(f"[MuteAndUnmutePlugin] Muted stream {stream_id} for {duration_minutes} minutes until {unmute_time}")
        return (True, f"已设置在 {stream_id} 禁言 {duration_minutes} 分钟至 {unmute_time}", True) # --- 修改：返回元组 ---

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

    async def execute(self, args: CommandArgs) -> Tuple[bool, Optional[str], bool]: # --- 修改：方法签名 ---
        # 获取当前聊天流ID (通过 self.chat_stream)
        chat_stream: ChatStream = self.chat_stream # --- 修改：使用 self.chat_stream ---
        if not chat_stream:
            return (False, "无法获取当前聊天流信息。", False)

        stream_id = chat_stream.stream_id

        # --- 修改：获取存储实例 ---
        # plugin_storage = storage_api.get(PLUGIN_NAME) # --- 移除 ---
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME) # --- 添加 ---

        # 获取插件配置
        # 检查插件主功能是否启用
        plugin_enabled = self.get_config("plugin.enabled", True)
        if not plugin_enabled:
            await send_api.text_to_stream("❌ 插件已被禁用。", stream_id)
            return (False, "插件已禁用", False) # --- 修改：返回元组 ---

        # 检查静音功能是否启用
        mute_enabled = self.get_config("features.mute_enabled", True)
        if not mute_enabled:
            await send_api.text_to_stream("❌ 静音功能已被禁用。", stream_id)
            return (False, "静音功能已禁用", False) # --- 修改：返回元组 ---

        # 从存储中移除该聊天流的禁言记录
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
        if stream_id in current_muted_streams:
            del current_muted_streams[stream_id]
            plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams) # --- 修改：使用 plugin_storage.set ---
            print(f"[MuteAndUnmutePlugin] Unmuted stream {stream_id} via command.")
        else:
            print(f"[MuteAndUnmutePlugin] Attempted to unmute stream {stream_id} via command, but it was not muted.")
            # 即使未被禁言，也可能需要发送消息，但这里我们只在解除时发送
            # 可以选择发送一个提示，说明当前并未禁言
            # await send_api.text_to_stream("我当前并未被禁言哦。", stream_id)
            # 为了与原逻辑一致，我们只在成功解除时发送消息
            await self.send_text("我当前并未被禁言哦。") # --- 修改：使用 self.send_text ---
            return (False, f"尝试取消 {stream_id} 的禁言，但该聊天流未被禁言。", False) # --- 修改：返回元组 ---

        # 从配置中获取提示词
        unmute_message = self.get_config("messages.unmute_start", "好的，我恢复发言了！")

        # 发送确认消息 (使用 self.send_text)
        await self.send_text(unmute_message) # --- 修改：使用 self.send_text ---

        # 尝试触发一次主动思考
        # 这里需要判断是否需要思考，根据 PlusCommand 的返回值约定，第三个 bool 表示是否需要思考
        # 通常，执行了明确的命令后，可以触发一次思考
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

        return (True, f"已取消 {stream_id} 的禁言，并尝试触发思考。", True) # --- 修改：返回元组 ---


# --- 修改：Chatter 组件来处理别名、@唤醒和禁言检查 ---
class MuteControlChatter(BaseChatter):
    """
    Chatter 组件，用于处理别名、@唤醒和禁言检查。
    """
    chatter_name = "mute_control_chatter"
    chatter_description = "处理禁言相关的别名、@唤醒和禁言状态检查。"
    chat_types = [ChatterChatType.PRIVATE, ChatterChatType.GROUP] # 允许在私聊和群聊中运行

    def __init__(self, stream_id: str, action_manager: ChatterActionManager):
        super().__init__(stream_id, action_manager)
        # 从配置中加载别名
        self.mute_aliases = self.get_config("aliases.mute", ["绫绫闭嘴"])
        self.unmute_aliases = self.get_config("aliases.unmute", ["绫绫张嘴"])

    async def execute(self, context: StreamContext) -> dict:
        """
        执行 Chatter 的核心逻辑。
        检查最新消息是否为别名、@唤醒，并检查禁言状态。
        """
        # 从 context 获取最新的消息
        last_message = context.get_last_message()
        if not last_message:
            return {"success": True, "stream_id": self.stream_id, "message": "No last message in context."}

        # 获取消息内容和发送者信息
        message_content = getattr(last_message, 'text', None) # 假设消息对象有 text 属性
        if not message_content:
             # 或者尝试其他可能的属性名，例如 raw_content, content 等
            message_content = getattr(last_message, 'raw_content', None) or getattr(last_message, 'content', None)
        if not message_content:
            return {"success": True, "stream_id": self.stream_id, "message": "No text content in last message."}

        # --- 1. 检查是否为别名 ---
        # 检查 Mute 别名
        for alias in self.mute_aliases:
            if message_content.strip().startswith(alias):
                print(f"[MuteControlChatter] Mute alias '{alias}' detected in stream {self.stream_id}.")
                # 提取参数（如果有的话）
                param_str = message_content[len(alias):].strip()
                # 调用内部方法执行 mute 逻辑
                success, message_result = await self._execute_mute_logic_direct(context, param_str)
                if success:
                    # 如果成功执行 mute，可以返回成功，但这不一定意味着要阻止后续流程
                    # 通常，执行 mute 命令本身会发送消息，然后消息处理流程可以继续或被拦截
                    # 这里我们只执行逻辑，不直接干预流程，除非是禁言状态检查
                    print(f"[MuteControlChatter] Processed mute alias '{alias}'. Result: {message_result}")
                else:
                    print(f"[MuteControlChatter] Failed to process mute alias '{alias}'. Error: {message_result}")
                break # 找到一个别名后就跳出循环

        # 检查 Unmute 别名
        for alias in self.unmute_aliases:
            if message_content.strip().startswith(alias):
                print(f"[MuteControlChatter] Unmute alias '{alias}' detected in stream {self.stream_id}.")
                param_str = message_content[len(alias):].strip()
                success, message_result = await self._execute_unmute_logic_direct(context, param_str)
                if success:
                    print(f"[MuteControlChatter] Processed unmute alias '{alias}'. Result: {message_result}")
                else:
                    print(f"[MuteControlChatter] Failed to process unmute alias '{alias}'. Error: {message_result}")
                break

        # --- 2. 检查是否为 @ 唤醒 ---
        # 获取被提及的用户列表 (假设 last_message 有 mentioned_user_ids 或类似属性)
        mentioned_user_ids = getattr(last_message, 'mentioned_user_ids', None)
        if not mentioned_user_ids:
            # 或者尝试其他可能的属性名
            mentioned_user_ids = getattr(last_message, 'at_user_ids', None) or getattr(last_message, 'mentions', None)

        if mentioned_user_ids:
            try:
                from src.config.config import global_config
                bot_id = str(global_config.bot.qq_account)
            except ImportError:
                print("[MuteControlChatter] Error: Could not import global_config to get bot_id for @ check.")
                return {"success": False, "stream_id": self.stream_id, "error_message": "Failed to get bot ID."}

            if bot_id in mentioned_user_ids:
                print(f"[MuteControlChatter] Bot @{bot_id} mentioned in stream {self.stream_id}. Checking mute status for auto-unmute.")
                # 检查是否处于禁言状态
                # --- 修改：获取存储实例 ---
                # plugin_storage = storage_api.get(PLUGIN_NAME) # --- 移除 ---
                plugin_storage = storage_api.get_local_storage(PLUGIN_NAME) # --- 添加 ---
                current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
                if self.stream_id in current_muted_streams:
                    mute_until_timestamp = current_muted_streams[self.stream_id]
                    current_time = time.time()
                    if current_time < mute_until_timestamp:
                        # Bot 被 @ 且正处于禁言状态，自动解除禁言
                        del current_muted_streams[self.stream_id]
                        plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams)
                        print(f"[MuteControlChatter] Unmuted stream {self.stream_id} because Bot was mentioned (@).")

                        # 从配置中获取提示词
                        at_unmute_message = self.get_config("messages.at_unmute", "我被 @ 了，所以恢复发言啦！")

                        # 发送解除禁言的消息
                        await send_api.text_to_stream(at_unmute_message, self.stream_id)

                        # 尝试触发一次主动思考
                        chat_stream_obj = chat_api.get_stream_by_id(self.stream_id) # 尝试获取 ChatStream 对象
                        if chat_stream_obj:
                            try:
                                replyer = generator_api.get_replyer(chat_stream=chat_stream_obj)
                                if replyer:
                                    success, reply_set, prompt = await generator_api.generate_reply(
                                        chat_stream=chat_stream_obj,
                                        action_data={"type": "at_unmute_trigger", "message": f"Bot was mentioned (@) by {getattr(last_message, 'user_info', {}).get('user_nickname', 'Someone')}."}, # 模拟动作数据
                                        reply_to="", # 不回复特定消息
                                        available_actions=[], # 不提供具体动作，让模型决定
                                        enable_tool=False, # 暂时禁用工具调用
                                        return_prompt=False
                                    )
                                    if success:
                                        print(f"[MuteControlChatter] Attempted to trigger thinking after @ unmute in {self.stream_id}.")
                                    else:
                                        print(f"[MuteControlChatter] Failed to generate reply/trigger thinking after @ unmute in {self.stream_id}.")
                                else:
                                    print(f"[MuteControlChatter] Could not get replyer for stream {self.stream_id} to trigger thinking after @ unmute.")
                            except Exception as e:
                                print(f"[MuteControlChatter] Error trying to trigger thinking after @ unmute: {e}")
                        else:
                            print(f"[MuteControlChatter] Warning: Could not get ChatStream object for {self.stream_id} to trigger thinking after @ unmute.")

                else:
                    print(f"[MuteControlChatter] Bot was mentioned (@) in stream {self.stream_id}, but it was not muted.")

        # --- 3. 检查当前聊天流是否被禁言，并决定是否阻止后续处理 ---
        # --- 修改：获取存储实例 ---
        # plugin_storage = storage_api.get(PLUGIN_NAME) # --- 移除 ---
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME) # --- 添加 ---
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})

        if self.stream_id in current_muted_streams:
            mute_until_timestamp = current_muted_streams[self.stream_id]
            current_time = time.time()

            if current_time < mute_until_timestamp:
                # 当前时间仍在禁言时间内
                print(f"[MuteControlChatter] Message in muted stream {self.stream_id} detected. Time remaining: {timedelta(seconds=int(mute_until_timestamp - current_time))}. Blocking further processing.")
                # 从配置中获取禁言期间的提示词（如果有的话）
                mute_reply_message = self.get_config("messages.muted_reply", "") # 默认为空，不回复
                if mute_reply_message:
                    # 可以选择是否回复一条消息告知用户处于禁言状态
                    # 但通常禁言就是不回复，所以这里可以选择不发送
                    # await send_api.text_to_stream(mute_reply_message, self.stream_id)
                    pass
                # 返回一个特殊标记，表示需要阻止后续处理
                # 这取决于 Chatter 和上层系统的交互方式
                # 一种方式是返回一个包含特殊键的字典
                # 另一种方式是尝试通过 action_manager 发送一个信号
                # 目前，我们返回一个标记，期望上层系统能理解
                return {
                    "success": True,
                    "stream_id": self.stream_id,
                    "plan_created": True, # 表示我们“计划”了阻止操作
                    "actions_count": 0, # 没有实际执行动作，只是判断
                    "block_follow_up_processing": True, # 关键：标记阻止后续处理
                    "message": "Message intercepted due to mute."
                }
            else:
                # 禁言时间已过，移除记录
                del current_muted_streams[self.stream_id]
                plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams)
                print(f"[MuteControlChatter] Mute expired for stream {self.stream_id}. Removed from muted list.")

        # 如果没有别名、@唤醒或禁言拦截，则不阻止后续处理
        return {
            "success": True,
            "stream_id": self.stream_id,
            "message": "Chatter executed, no blocking action taken."
        }

    async def _execute_mute_logic_direct(self, context: StreamContext, param_str: str):
        # --- 修改：获取存储实例 ---
        # plugin_storage = storage_api.get(PLUGIN_NAME) # --- 移除 ---
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME) # --- 添加 ---

        # 检查插件主功能是否启用
        plugin_enabled = self.get_config("plugin.enabled", True)
        if not plugin_enabled:
            await send_api.text_to_stream("❌ 插件已被禁用。", self.stream_id)
            return False, "Plugin is disabled"

        # 检查静音功能是否启用
        mute_enabled = self.get_config("features.mute_enabled", True)
        if not mute_enabled:
            await send_api.text_to_stream("❌ 静音功能已被禁用。", self.stream_id)
            return False, "Mute feature is disabled"

        # 解析参数
        duration_minutes = self._parse_duration(param_str) if param_str else None
        if duration_minutes is None:
            # 如果参数解析失败或为空，使用默认时长
            if param_str: # 如果有参数但解析失败
                await send_api.text_to_stream("❌ 无法解析指定的时长，请使用如 '10min', '30分钟', '1小时' 等格式。", self.stream_id)
                return False, "无法解析时长"
            else: # 如果没有参数
                duration_minutes = self.get_config("defaults.default_mute_minutes", 10)

        # 计算解除禁言的时间
        unmute_time = datetime.now() + timedelta(minutes=duration_minutes)

        # 更新存储中的禁言列表
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
        current_muted_streams[self.stream_id] = unmute_time.timestamp() # 存储时间戳
        plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams)

        # 从配置中获取提示词
        mute_message_template = self.get_config("messages.mute_start", "好的，我将在当前聊天中保持安静，直到 {unmute_time_str}。")
        unmute_time_str = unmute_time.strftime('%H:%M')
        mute_message = mute_message_template.format(unmute_time_str=unmute_time_str)

        # 发送确认消息
        await send_api.text_to_stream(mute_message, self.stream_id)

        print(f"[MuteControlChatter] Muted stream {self.stream_id} for {duration_minutes} minutes until {unmute_time}")
        return True, f"已设置在 {self.stream_id} 禁言 {duration_minutes} 分钟至 {unmute_time}"

    async def _execute_unmute_logic_direct(self, context: StreamContext, param_str: str):
        # --- 修改：获取存储实例 ---
        # plugin_storage = storage_api.get(PLUGIN_NAME) # --- 移除 ---
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME) # --- 添加 ---

        # 获取插件配置
        # 检查插件主功能是否启用
        plugin_enabled = self.get_config("plugin.enabled", True)
        if not plugin_enabled:
            await send_api.text_to_stream("❌ 插件已被禁用。", self.stream_id)
            return False, "Plugin is disabled."

        # 检查静音功能是否启用
        mute_enabled = self.get_config("features.mute_enabled", True)
        if not mute_enabled:
            await send_api.text_to_stream("❌ 静音功能已被禁用。", self.stream_id)
            return False, "Mute feature is disabled."

        # 从存储中移除该聊天流的禁言记录
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
        if self.stream_id in current_muted_streams:
            del current_muted_streams[self.stream_id]
            plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams)
            print(f"[MuteControlChatter] Unmuted stream {self.stream_id} via alias handler.")
        else:
            print(f"[MuteControlChatter] Attempted to unmute stream {self.stream_id} via alias handler, but it was not muted.")
            # 即使未被禁言，也可能需要发送消息
            await send_api.text_to_stream("我当前并未被禁言哦。", self.stream_id)
            return False, f"尝试取消 {self.stream_id} 的禁言，但该聊天流未被禁言。"

        # 从配置中获取提示词
        unmute_message = self.get_config("messages.unmute_start", "好的，我恢复发言了！")

        # 发送确认消息
        await send_api.text_to_stream(unmute_message, self.stream_id)

        # 尝试触发一次主动思考
        chat_stream_obj = chat_api.get_stream_by_id(self.stream_id) # 尝试获取 ChatStream 对象
        if chat_stream_obj:
            try:
                replyer = generator_api.get_replyer(chat_stream=chat_stream_obj)
                if replyer:
                    success, reply_set, prompt = await generator_api.generate_reply(
                        chat_stream=chat_stream_obj,
                        action_data={"type": "unmute_trigger", "message": "Bot was unmuted via alias."}, # 模拟动作数据
                        reply_to="", # 不回复特定消息
                        available_actions=[], # 不提供具体动作，让模型决定
                        enable_tool=False, # 暂时禁用工具调用
                        return_prompt=False
                    )
                    if success:
                        print(f"[MuteControlChatter] Attempted to trigger thinking after unmute alias in {self.stream_id}.")
                    else:
                        print(f"[MuteControlChatter] Failed to generate reply/trigger thinking after unmute alias in {self.stream_id}.")
                else:
                    print(f"[MuteControlChatter] Could not get replyer for stream {self.stream_id} to trigger thinking after unmute alias.")
            except Exception as e:
                print(f"[MuteControlChatter] Error trying to trigger thinking after unmute alias: {e}")
        else:
            print(f"[MuteControlChatter] Warning: Could not get ChatStream object for {self.stream_id} to trigger thinking after unmute alias.")

        return True, f"已取消 {self.stream_id} 的禁言，并尝试触发思考。"

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """
        尝试从字符串中解析出分钟数。
        支持格式如: "10min", "30分钟", "1小时", "2h", "45m" 等。
        """
        if not duration_str:
            return None
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
            "at_unmute_enabled": ConfigField( # 这个配置项在 Chatter 中可能用不上，因为 @ 检查总是进行
                type=bool,
                default=True,
                description="是否启用 @Bot 唤醒功能。如果为 false，@Bot 将不会解除禁言。", # 注意：此配置在 Chatter 实现中总是有效
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
        components.append((MuteMaiCommand.get_plus_command_info(), MuteMaiCommand)) # --- 修改：使用 get_plus_command_info ---
        components.append((UnmuteMaiCommand.get_plus_command_info(), UnmuteMaiCommand)) # --- 修改：使用 get_plus_command_info ---

        # 注册 Chatter 组件 (处理别名、@唤醒和禁言检查)
        components.append((MuteControlChatter.get_chatter_info(), MuteControlChatter))

        return components

    async def on_plugin_loaded(self):
        """
        插件加载时的钩子函数。
        清空存储中所有已保存的禁言列表，确保插件状态与程序状态一致。
        """
        # --- 修改：获取存储实例 ---
        # plugin_storage = storage_api.get(PLUGIN_NAME) # --- 移除 ---
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME) # --- 添加 ---

        # 获取当前存储的禁言列表
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {}) # --- 修改：使用 plugin_storage.get ---

        if current_muted_streams:
            # 如果列表不为空，则清空它
            plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, {}) # --- 修改：使用 plugin_storage.set ---
            print(f"[MuteAndUnmutePlugin] 在插件加载时清空了 {len(current_muted_streams)} 条旧的禁言记录。")
        else:
            print(f"[MuteAndUnmutePlugin] 插件加载时，禁言列表为空，无需清空。")

        # 可选：如果需要，可以在此处发送一条系统日志或通知给 Master
        # 例如：await send_api.text_to_master("MuteAndUnmutePlugin 已加载，并清空了旧的禁言记录。")
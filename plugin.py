import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Tuple, Type, Optional, Dict, Any # 导入 Any 用于类型注解

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    PlusCommand,
    ComponentInfo,
    ChatType,
    ConfigField, # 导入 ConfigField 用于定义配置
    CommandArgs # --- 添加：导入 CommandArgs ---
)

from src.chat.message_receive.chat_stream import ChatStream

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
    command_description = "让Bot在当前聊天流静音，使用配置中的默认时长"
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

        # 获取存储实例
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME) # --- 修改：使用 get_local_storage ---

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

        # 使用配置中的默认时长
        duration_minutes = self.get_config("defaults.default_mute_minutes", 10)

        # 计算解除禁言的时间
        unmute_time = datetime.now() + timedelta(minutes=duration_minutes)

        # 更新存储中的禁言列表
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
        current_muted_streams[stream_id] = unmute_time.timestamp() # 存储时间戳
        plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams) # --- 修改：使用 plugin_storage.set ---
        print(f"[MuteMaiCommand] DEBUG: Set mute for stream {stream_id} until {unmute_time} in storage. Current muted streams: {current_muted_streams}") # 添加调试日志

        # 从配置中获取提示词
        mute_message_template = self.get_config("messages.mute_start", "好的，我将在当前聊天中保持安静，直到 {unmute_time_str}。")
        unmute_time_str = unmute_time.strftime('%H:%M')
        mute_message = mute_message_template.format(unmute_time_str=unmute_time_str)

        # 发送确认消息 (使用 self.send_text 或 send_api)
        # self.send_text 是 PlusCommand 内置方法，应该更可靠
        await self.send_text(mute_message) # --- 修改：使用 self.send_text ---

        print(f"[MuteAndUnmutePlugin] Muted stream {stream_id} for {duration_minutes} minutes until {unmute_time}")
        return (True, f"已设置在 {stream_id} 禁言 {duration_minutes} 分钟至 {unmute_time}", True) # --- 修改：返回元组 ---


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

        # 获取存储实例
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME) # --- 修改：使用 get_local_storage ---

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
            print(f"[UnmuteMaiCommand] DEBUG: Removed mute for stream {stream_id} from storage. Current muted streams: {current_muted_streams}") # 添加调试日志
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
            replyer = await generator_api.get_replyer(chat_stream=chat_stream)
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

    def __init__(self, stream_id: str, action_manager: "ChatterActionManager"):
        super().__init__(stream_id, action_manager)
        # 初始化时只接收 stream_id 和 action_manager
        # 配置在 execute 方法中通过 self.get_config 获取
        # 初始化实例属性为 None 或默认值
        self.mute_aliases: List[str] = []
        self.unmute_aliases: List[str] = []
        self.plugin_enabled_val: bool = True
        self.mute_enabled_val: bool = True
        self.at_unmute_enabled_val: bool = True
        self.default_mute_minutes_val: int = 10
        self.messages_config_val: Dict[str, str] = {}
        print(f"[MuteControlChatter] Initialized instance for stream {self.stream_id}, waiting for config in execute.") # --- 添加：调试日志 ---

    async def execute(self, context: StreamContext) -> dict:
        """
        执行 Chatter 的核心逻辑。
        检查最新消息是否为别名、@唤醒，并检查禁言状态。
        """
        # 获取存储实例 (与 PlusCommand 一样的方式)
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME)
        print(f"[MuteControlChatter] DEBUG: Got storage instance for {PLUGIN_NAME}. Checking muted streams at start of execute...") # 添加调试日志
        initial_muted_streams = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
        print(f"[MuteControlChatter] DEBUG: Initial muted streams from storage in execute: {initial_muted_streams}") # 添加调试日志

        # --- 从 context 获取 stream_id ---
        # BaseChatter 实例本身有 self.stream_id，StreamContext 也有 stream_id
        # 两者应该是一致的，这里使用 self.stream_id 更直接，因为它在 __init__ 时就已确定
        stream_id = self.stream_id # --- 获取 stream_id ---

        # --- 从 context 获取最新的消息 ---
        last_message = context.get_last_message()
        if not last_message:
            print(f"[MuteControlChatter] No last message found in context for stream {stream_id}. Skipping checks.")
            return {"success": True, "stream_id": stream_id, "message": "No last message in context."}

                # --- 从 last_message 获取信息 ---
        # 尝试获取 content
        # 根据错误日志和 MoFox 架构，message 对象很可能是 DatabaseMessages 类型
        # 尝试常见的属性名，特别是根据 'message_storage' 日志，可能包含 processed_plain_text 或 plain_text
        # 也可能是 text, raw_content, content 等
        # 尝试从最可能的属性开始
        message_content = getattr(last_message, 'processed_plain_text', None)
        if not message_content:
            message_content = getattr(last_message, 'plain_text', None)
        if not message_content:
            message_content = getattr(last_message, 'text', None)
        if not message_content:
            message_content = getattr(last_message, 'content', None)
        if not message_content:
            message_content = getattr(last_message, 'raw_content', None)
        if not message_content:
            # 如果以上都失败，尝试获取原始消息段并手动拼接文本
            # 这需要了解 DatabaseMessages 的具体结构，例如是否有 segments 属性
            # 假设 DatabaseMessages 有 segments 属性，包含消息段列表
            # 每个段可能有 type 和 data 属性
            # 这里只处理 text 类型的段
            segments = getattr(last_message, 'segments', [])
            text_parts = []
            for seg in segments:
                if seg.get('type') == 'text':
                    text_parts.append(seg.get('data', {}).get('text', ''))
            message_content = ''.join(text_parts)

        if not message_content:
            print(f"[MuteControlChatter] No text content found in last message for stream {stream_id}. Skipping checks.")
            return {"success": True, "stream_id": stream_id, "message": "No text content in last message."}

        # --- 在 execute 中首次获取配置并缓存到实例属性 ---
        # 尝试调用 self.get_config
        try:
            # 检查插件主功能是否启用
            plugin_enabled = self.get_config("plugin.enabled", True) # <--- 尝试调用 ---
            mute_enabled = self.get_config("features.mute_enabled", True) # <--- 尝试调用 ---
            # at_unmute_enabled = self.get_config("features.at_unmute_enabled", True) # Chatter 中可能用不到这个开关，但仍可获取
            mute_aliases = self.get_config("aliases.mute", ["绫绫闭嘴"]) # <--- 尝试调用 ---
            unmute_aliases = self.get_config("aliases.unmute", ["绫绫张嘴"]) # <--- 尝试调用 ---
            default_mute_minutes = self.get_config("defaults.default_mute_minutes", 10) # <--- 尝试调用 ---
            messages_config = self.get_config("messages", {}) # <--- 尝试调用 ---

            # 将获取到的配置存储为实例属性，以供后续逻辑使用
            self.plugin_enabled_val = plugin_enabled
            self.mute_enabled_val = mute_enabled
            # self.at_unmute_enabled_val = at_unmute_enabled # 可选
            self.mute_aliases = mute_aliases
            self.unmute_aliases = unmute_aliases
            self.default_mute_minutes_val = default_mute_minutes
            self.messages_config_val = messages_config

            print(f"[MuteControlChatter] Loaded config from plugin in execute for stream {stream_id}. Aliases: mute={self.mute_aliases}, unmute={self.unmute_aliases}")

        except AttributeError:
            # 如果 self.get_config 不存在，则回退到使用默认值或从 storage_api 获取
            # 这意味着 BaseChatter 可能没有 get_config 方法
            print(f"[MuteControlChatter] WARNING: 'self' object has no attribute 'get_config'. Using defaults.")
            self.plugin_enabled_val = True
            self.mute_enabled_val = True
            # self.at_unmute_enabled_val = True # 可选
            self.mute_aliases = ["绫绫闭嘴"]
            self.unmute_aliases = ["绫绫张嘴"]
            self.default_mute_minutes_val = 10
            self.messages_config_val = {}
            # 如果需要从 storage_api 获取，可以在这里尝试
            # 但这需要在 execute 时进行，且可能性能较差
            # 或者，如果框架不支持，可以考虑在 on_plugin_loaded 时将配置存入 storage，然后在这里读取
            # 但这种方式不如工厂函数优雅，且可能存在延迟
            # 最坏的情况是，如果框架不提供获取配置的途径，那么这个 Chatter 就无法工作
            # 让我们先尝试 storage_api
            try:
                plugin_storage = storage_api.get_local_storage(PLUGIN_NAME)
                cached_config = plugin_storage.get("chatter_config", {}) # 使用一个特定的键
                if cached_config:
                    self.plugin_enabled_val = cached_config.get("plugin", {}).get("enabled", True)
                    self.mute_enabled_val = cached_config.get("features", {}).get("mute_enabled", True)
                    # self.at_unmute_enabled_val = cached_config.get("features", {}).get("at_unmute_enabled", True) # 可选
                    self.mute_aliases = cached_config.get("aliases", {}).get("mute", ["绫绫闭嘴"])
                    self.unmute_aliases = cached_config.get("aliases", {}).get("unmute", ["绫绫张嘴"])
                    self.default_mute_minutes_val = cached_config.get("defaults", {}).get("default_mute_minutes", 10)
                    self.messages_config_val = cached_config.get("messages", {})
                    print(f"[MuteControlChatter] Loaded config from storage in execute for stream {self.stream_id}. Aliases: mute={self.mute_aliases}, unmute={self.unmute_aliases}")
                else:
                    print(f"[MuteControlChatter] WARNING: Config not found in storage for stream {self.stream_id}. Using defaults.")
            except Exception as e:
                print(f"[MuteControlChatter] ERROR loading config from storage in execute for stream {self.stream_id}: {e}. Using defaults.")
        
        # --- 1. 检查是否为别名 ---
        # 检查 Mute 别名
        for alias in self.mute_aliases:
            if message_content.strip().startswith(alias):
                print(f"[MuteControlChatter] Mute alias '{alias}' detected in stream {stream_id} (via Chatter).")
                # 定义一个辅助函数来执行核心逻辑
                async def _execute_mute_logic_direct_from_chatter(context_stream_id):
                    # 获取存储实例
                    plugin_storage = storage_api.get_local_storage(PLUGIN_NAME)

                    # 检查插件主功能是否启用 # --- 修改：使用实例属性 ---
                    if not self.plugin_enabled_val:
                        await send_api.text_to_stream("❌ 插件已被禁用。", context_stream_id)
                        return False, "Plugin is disabled"

                    # 检查静音功能是否启用 # --- 修改：使用实例属性 ---
                    if not self.mute_enabled_val:
                        await send_api.text_to_stream("❌ 静音功能已被禁用。", context_stream_id)
                        return False, "Mute feature is disabled"

                    # 使用实例属性中的默认时长
                    duration_minutes = self.default_mute_minutes_val # --- 修改：使用实例属性 ---

                    # 计算解除禁言的时间
                    unmute_time = datetime.now() + timedelta(minutes=duration_minutes)

                    # 更新存储中的禁言列表
                    current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
                    current_muted_streams[context_stream_id] = unmute_time.timestamp() # 存储时间戳
                    plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams)

                    # 从配置中获取提示词
                    mute_message_template = self.messages_config_val.get("mute_start", "好的，我将在当前聊天中保持安静，直到 {unmute_time_str}。") # --- 修改：使用实例属性 ---
                    unmute_time_str = unmute_time.strftime('%H:%M')
                    mute_message = mute_message_template.format(unmute_time_str=unmute_time_str)

                    # 发送确认消息
                    await send_api.text_to_stream(mute_message, context_stream_id)

                    print(f"[MuteControlChatter] Muted stream {context_stream_id} for {duration_minutes} minutes until {unmute_time}")
                    return True, f"已设置在 {context_stream_id} 禁言 {duration_minutes} 分钟至 {unmute_time}"

                # 调用辅助函数
                success, message_result = await _execute_mute_logic_direct_from_chatter(stream_id)
                if success:
                    print(f"[MuteControlChatter] Processed mute alias '{alias}' in chatter. Result: {message_result}")
                    # Chatter 通常不直接拦截流程，它更多是做分析和决策
                    # 如果需要拦截，可能需要框架的其他机制
                    # 这里我们只执行逻辑
                else:
                    print(f"[MuteControlChatter] Failed to process mute alias '{alias}' in chatter. Error: {message_result}")
                break # 找到一个别名后就跳出循环

        # 检查 Unmute 别名
        for alias in self.unmute_aliases:
            if message_content.startswith(alias):
                # 定义一个辅助函数来执行 unmute 逻辑
                async def _execute_unmute_logic_direct_from_chatter(context_stream_id):
                    # 获取存储实例
                    plugin_storage = storage_api.get_local_storage(PLUGIN_NAME)

                    # 获取插件配置
                    # 检查插件主功能是否启用 # --- 修改：使用实例属性 ---
                    if not self.plugin_enabled_val:
                        await send_api.text_to_stream("❌ 插件已被禁用。", context_stream_id)
                        return False, "Plugin is disabled."

                    # 检查静音功能是否启用 # --- 修改：使用实例属性 ---
                    if not self.mute_enabled_val:
                        await send_api.text_to_stream("❌ 静音功能已被禁用。", context_stream_id)
                        return False, "Mute feature is disabled."

                    # 从存储中移除该聊天流的禁言记录
                    current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
                    if context_stream_id in current_muted_streams:
                        del current_muted_streams[context_stream_id]
                        plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams)
                        print(f"[MuteControlChatter] Unmuted stream {context_stream_id} via alias handler (from chatter).")
                    else:
                        print(f"[MuteControlChatter] Attempted to unmute stream {context_stream_id} via alias handler (from chatter), but it was not muted.")
                        # 即使未被禁言，也可能需要发送消息
                        await send_api.text_to_stream("我当前并未被禁言哦。", context_stream_id)
                        return False, f"尝试取消 {context_stream_id} 的禁言，但该聊天流未被禁言。"

                    # 从配置中获取提示词
                    unmute_message = self.messages_config_val.get("unmute_start", "好的，我恢复发言了！") # --- 修改：使用实例属性 ---

                    # 发送确认消息
                    await send_api.text_to_stream(unmute_message, context_stream_id)

                    # 尝试触发一次主动思考
                    # 需要 chat_stream 对象
                    # 通过 chat_api 获取 ChatManager，再获取 ChatStream
                    try:
                        from src.chat.message_receive.chat_stream import get_chat_manager # 获取 ChatManager 单例
                        chat_manager = get_chat_manager()
                        chat_stream_obj = await chat_manager.get_stream(context_stream_id) # 尝试从 ChatManager 获取 ChatStream 对象
                        if chat_stream_obj:
                            # 如果能获取到 ChatStream，再尝试触发思考
                            replyer =await generator_api.get_replyer(chat_stream=chat_stream_obj)
                            if replyer:
                                success, reply_set, prompt = await generator_api.generate_reply(
                                    chat_stream=chat_stream_obj,
                                    action_data={"type": "unmute_trigger", "message": "Bot was unmuted via alias (from chatter)."}, # 模拟动作数据
                                    reply_to="", # 不回复特定消息
                                    available_actions=[], # 不提供具体动作，让模型决定
                                    enable_tool=False, # 暂时禁用工具调用
                                    return_prompt=False
                                )
                                if success:
                                    print(f"[MuteControlChatter] Attempted to trigger thinking after unmute alias (from chatter) in {context_stream_id}.")
                                else:
                                    print(f"[MuteControlChatter] Failed to generate reply/trigger thinking after unmute alias (from chatter) in {context_stream_id}.")
                            else:
                                print(f"[MuteControlChatter] Could not get replyer for stream {context_stream_id} to trigger thinking after unmute alias (from chatter).")
                        else:
                            print(f"[MuteControlChatter] Warning: Could not get ChatStream object from ChatManager for {context_stream_id} to trigger thinking after unmute alias (from chatter).")
                    except Exception as e:
                        print(f"[MuteControlChatter] Error trying to get ChatStream from ChatManager or trigger thinking after unmute alias (from chatter): {e}")

                    return True, f"已取消 {context_stream_id} 的禁言，并尝试触发思考。"

                # 调用辅助函数
                success, message_result = await _execute_unmute_logic_direct_from_chatter(stream_id)
                if success:
                    print(f"[MuteControlChatter] Processed unmute alias '{alias}' in chatter. Result: {message_result}")
                else:
                    print(f"[MuteControlChatter] Failed to process unmute alias '{alias}' in chatter. Error: {message_result}")
                break # 找到一个别名后就跳出循环

        # --- 2. 检查是否为 @ 唤醒 ---
        # 先检查功能开关
        if not self.at_unmute_enabled_val:
            print(f"[MuteControlChatter] @ unmute feature is disabled, skipping @ check for stream {stream_id}.")
        else:
            print(f"[MuteControlChatter] @ unmute feature is enabled, checking for @ in stream {stream_id}.")
            # 尝试从 last_message 获取 mentioned_user_ids
            # last_message 应该是 Message 或其子类的实例
            # 根据 MoFox 消息结构，@ 信息在 message_segment 中
            mentioned_user_ids = []

            message_segment = getattr(last_message, 'message_segment', None)
            if message_segment:
                # message_segment 是 Seg 类型
                # 需要递归遍历 Seg 或 Seg.data (如果是 seglist)
                def extract_at_ids(segment):
                    ids = []
                    if segment.type == "at":
                        # seg.data 可能是 "昵称:QQ号", "QQ号", 或者 {"qq": "QQ号"}
                        at_data = segment.data
                        if isinstance(at_data, str):
                            # 尝试按冒号分割，取后半部分作为 QQ 号
                            parts = at_data.split(":", 1)
                            if len(parts) == 2:
                                ids.append(parts[1]) # 取 QQ 号部分
                            else:
                                ids.append(at_data) # 如果没有冒号，整个字符串可能是 QQ 号
                        elif isinstance(at_data, dict) and 'qq' in at_data:
                            # 处理 {'qq': 'QQ号'} 格式
                            ids.append(str(at_data['qq'])) # 确保 ID 是字符串
                    elif segment.type == "seglist" and isinstance(segment.data, list):
                        # 递归处理列表中的每个 segment
                        for sub_seg in segment.data:
                            ids.extend(extract_at_ids(sub_seg))
                    return ids

                mentioned_user_ids = extract_at_ids(message_segment)

            print(f"[MuteControlChatter] Extracted @ mentions from message_segment: {mentioned_user_ids}") # 添加调试日志

            if mentioned_user_ids:
                try:
                    from src.config.config import global_config
                    bot_id = str(global_config.bot.qq_account) # 确保 bot_id 也是字符串
                    print(f"[MuteControlChatter] Bot ID (from config): {bot_id}") # 添加调试日志
                except ImportError:
                    print("[MuteControlChatter] Error: Could not import global_config to get bot_id for @ check.")
                    return {"success": False, "stream_id": stream_id, "error_message": "Failed to get bot ID."}

                print(f"[MuteControlChatter] Checking if bot_id '{bot_id}' is in extracted mentioned_user_ids {mentioned_user_ids}")
                if bot_id in mentioned_user_ids:
                    print(f"[MuteControlChatter] Bot @{bot_id} mentioned in stream {stream_id} (via Chatter). Checking mute status for auto-unmute.")
                    # 检查是否处于禁言状态
                    plugin_storage = storage_api.get_local_storage(PLUGIN_NAME)
                    current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
                    if stream_id in current_muted_streams:
                        mute_until_timestamp = current_muted_streams[stream_id]
                        current_time = time.time()
                        if current_time < mute_until_timestamp:
                            # Bot 被 @ 且正处于禁言状态，自动解除禁言
                            del current_muted_streams[stream_id]
                            plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams)
                            print(f"[MuteControlChatter] Unmuted stream {stream_id} because Bot was mentioned (@) (from chatter).")

                            # 从配置中获取提示词
                            at_unmute_message = self.messages_config_val.get("at_unmute", "我被 @ 了，所以恢复发言啦！") # --- 修改：使用实例属性 ---

                            # 发送解除禁言的消息
                            await send_api.text_to_stream(at_unmute_message, stream_id)

                            # 尝试触发一次主动思考 (同样使用 ChatManager)
                            try:
                                from src.chat.message_receive.chat_stream import get_chat_manager # 获取 ChatManager 单例
                                chat_manager = get_chat_manager() 
                                chat_stream_obj = await chat_manager.get_stream(stream_id) # 尝试从 ChatManager 获取 ChatStream 对象
                                if chat_stream_obj:
                                    # 如果能获取到 ChatStream，再尝试触发思考
                                    replyer = await generator_api.get_replyer(chat_stream=chat_stream_obj) # <--- 加 await --->
                                    if replyer:
                                        success, reply_set, prompt = await generator_api.generate_reply(
                                            chat_stream=chat_stream_obj,
                                            action_data={"type": "at_unmute_trigger", "message": f"Bot was mentioned (@) by {getattr(last_message, 'user_info', {}).get('user_nickname', 'Someone')} (from chatter)."}, # 模拟动作数据
                                            reply_to="", # 不回复特定消息
                                            available_actions=[], # 不提供具体动作，让模型决定
                                            enable_tool=False, # 暂时禁用工具调用
                                            return_prompt=False
                                        )
                                        if success:
                                            print(f"[MuteControlChatter] Attempted to trigger thinking after @ unmute (from chatter) in {stream_id}.")
                                        else:
                                            print(f"[MuteControlChatter] Failed to generate reply/trigger thinking after @ unmute (from chatter) in {stream_id}.")
                                    else:
                                        print(f"[MuteControlChatter] Could not get replyer for stream {stream_id} to trigger thinking after @ unmute (from chatter).")
                                else:
                                    print(f"[MuteControlChatter] Warning: Could not get ChatStream object from ChatManager for {stream_id} to trigger thinking after @ unmute (from chatter).")
                            except Exception as e:
                                print(f"[MuteControlChatter] Error trying to get ChatStream from ChatManager or trigger thinking after @ unmute (from chatter): {e}")

                            # 这里不返回特殊标记，因为 Chatter 通常不直接阻断流程
                            # 但我们可以设置一个内部状态，或者依赖其他机制来确保 Bot 响应这次 @

                    else:
                        print(f"[MuteControlChatter] Bot was mentioned (@) in stream {stream_id} (via Chatter), but it was not muted.")

                else:
                    print(f"[MuteControlChatter] Bot ID '{bot_id}' was not found in the extracted mentioned_user_ids list {mentioned_user_ids} for stream {stream_id}.")
            else:
                print(f"[MuteControlChatter] No user IDs found in message_segment for @ mentions for stream {stream_id}.")
        # --- 3. 检查当前聊天流是否被禁言，并决定是否返回拦截标记 ---
        # 使用 self.stream_id (实例属性)
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})
        print(f"[MuteControlChatter] Checking mute status for stream {stream_id}. Current muted streams from storage: {current_muted_streams}") # 添加调试日志
        current_muted_streams = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {}) # 再次获取，确认是否有变化
        print(f"[MuteControlChatter] Final muted streams from storage in execute (for check): {current_muted_streams}") # 添加调试日志


        if stream_id in current_muted_streams:
            mute_until_timestamp = current_muted_streams[stream_id]
            current_time = time.time()
            print(f"[MuteControlChatter] Stream {stream_id} is muted until timestamp {mute_until_timestamp}. Current time is {current_time}.") # 添加调试日志

            if current_time < mute_until_timestamp:
                # 当前时间仍在禁言时间内
                print(f"[MuteControlChatter] New message in muted stream {stream_id} (via Chatter). Time remaining: {timedelta(seconds=int(mute_until_timestamp - current_time))}.")
                # 从配置中获取禁言期间的提示词（如果有的话）
                mute_reply_message = self.messages_config_val.get("muted_reply", "") # 默认为空，不回复 # --- 修改：使用实例属性 ---
                if mute_reply_message:
                    # 可以选择是否回复一条消息告知用户处于禁言状态
                    # 但通常禁言就是不回复，所以这里可以选择不发送
                    # await send_api.text_to_stream(mute_reply_message, stream_id)
                    pass
                # 返回 HandlerResult，设置 continue_process=False 以拦截消息
                return {
                    "success": True,
                    "stream_id": stream_id,
                    "plan_created": True, # 表示我们“计划”了拦截操作
                    "actions_count": 0, # 没有实际执行动作，只是判断
                    "block_follow_up_processing": True, # 关键：标记阻止后续处理
                    "message": "Message intercepted due to mute (from Chatter)."
                }
            else:
                # 禁言时间已过，移除记录
                print(f"[MuteControlChatter] Mute expired for stream {stream_id} (checked via Chatter). Removing from list.")
                del current_muted_streams[stream_id]
                plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, current_muted_streams)
                # print(f"[MuteControlChatter] Mute expired for stream {stream_id} (checked via Chatter). Removed from muted list.")
        else:
            print(f"[MuteControlChatter] Stream {stream_id} is NOT in the muted list at all.")

        # 如果没有别名、@唤醒或禁言拦截，则不阻止后续处理
        return {
            "success": True,
            "stream_id": stream_id,
            "message": "Chatter executed (from context), no blocking action taken."
        }


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
                description="Bot 静音的默认时长（单位：分钟）。",
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

    async def on_plugin_loaded(self):
        """
        插件加载时的钩子函数。
        清空存储中所有已保存的禁言列表，确保插件状态与程序状态一致。
        并将插件配置缓存到 storage，供 Chatter 使用。
        """
        # --- 修改：获取存储实例 ---
        plugin_storage = storage_api.get_local_storage(PLUGIN_NAME)

        # 获取当前存储的禁言列表
        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})

        if current_muted_streams:
            # 如果列表不为空，则清空它
            plugin_storage.set(STORAGE_KEY_MUTED_STREAMS, {})
            print(f"[MuteAndUnmutePlugin] 在插件加载时清空了 {len(current_muted_streams)} 条旧的禁言记录。")
        else:
            print(f"[MuteAndUnmutePlugin] 插件加载时，禁言列表为空，无需清空。")

        # 将当前加载的配置缓存到 storage，供 Chatter 使用
        # 将 self.config (加载后的配置) 存储起来
        config_to_cache = {
            "plugin": self.config.get("plugin", {}),
            "features": self.config.get("features", {}),
            "defaults": self.config.get("defaults", {}),
            "aliases": self.config.get("aliases", {}),
            "messages": self.config.get("messages", {}),
        }
        plugin_storage.set("chatter_config", config_to_cache)
        print(f"[MuteAndUnmutePlugin] 已将配置加载到 storage 中，供 Chatter 使用。")

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        components = []

        # 注册主命令 (用于 /mute_mai 和 /unmute_mai)
        components.append((MuteMaiCommand.get_plus_command_info(), MuteMaiCommand)) # --- 修改：使用 get_plus_command_info ---
        components.append((UnmuteMaiCommand.get_plus_command_info(), UnmuteMaiCommand)) # --- 修改：使用 get_plus_command_info ---

        # --- 修改：注册 Chatter 组件 (处理别名、@唤醒和禁言检查) ---
        # 直接传递 Chatter 类，框架负责实例化
        # 配置由 Chatter 在其 execute 方法中通过 self.get_config 或其他方式获取
        components.append((MuteControlChatter.get_chatter_info(), MuteControlChatter)) # --- 修改：直接传递类 ---        
        
        return components
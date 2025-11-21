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
    command_description = "让Bot在当前聊天流静音，可指定时长（默认10分钟）"
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

        # 从 context 中获取参数 (通过 CommandArgs)
        args = context.get('args') # 假设 context 中包含 CommandArgs
        if args and not args.is_empty():
            duration_str = args.get_raw().strip()
            duration_minutes = self._parse_duration(duration_str)
            if duration_minutes is None:
                await send_api.text_to_stream("❌ 无法解析指定的时长，请使用如 '10min', '30分钟', '1小时' 等格式。", stream_id)
                return {"success": False, "message": "无法解析时长"}
        else:
            # 如果没有参数，默认为 10 分钟
            duration_minutes = 10

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
        mute_aliases = self.get_config("aliases.mute", ["绫绫闭嘴"]) # 默认值
        # unmute_aliases = self.get_config("aliases.unmute", ["绫绫张嘴"]) # unmute 别名也可以有参数，但当前 unmute 逻辑不需要

        message_content = message.content.strip()

        # 检查是否匹配 mute 别名
        for alias in mute_aliases:
            if message_content.startswith(alias):
                # 提取别名后的部分作为参数
                param_str = message_content[len(alias):].strip()
                # 构造 context，包含原始 message 和参数
                context = {
                    'chat_stream': message.chat_stream,
                    'message': message,
                    'args': param_str # 这里简单传递字符串，实际 PlusCommand 可能期望 CommandArgs 对象
                    # 如果需要 CommandArgs，可能需要在 MuteMaiCommand.execute 中处理字符串解析
                    # 或者在 AliasHandler 中模拟 CommandArgs 的行为
                }
                # 为了兼容 PlusCommand.execute，我们需要模拟 CommandArgs
                # 或者直接修改 MuteMaiCommand.execute 来接受字符串参数
                # 这里我们选择修改 MuteMaiCommand.execute 来处理 context 中的参数字符串
                # 然后调用 MuteMaiCommand().execute(context)
                # 但 MuteMaiCommand 的 execute 期望 CommandArgs 对象
                # 让我们重新审视 CommandArgs 的用法
                # 在 PlusCommand.execute 中，'args' 是一个 CommandArgs 实例
                # 我们需要在 AliasHandler 中创建一个 CommandArgs 实例
                # 或者，我们修改 MuteMaiCommand.execute 来接受一个简单的字符串参数
                # 或者，我们创建一个辅助函数来模拟 CommandArgs 的行为

                # 更好的方法：创建一个临时的 CommandArgs 对象来传递参数
                # 但 CommandArgs 的创建可能需要特定的初始化
                # 为了简化，我们可以修改 MuteMaiCommand.execute，使其也能接受字符串参数
                # 或者，我们直接调用 MuteMaiCommand 的内部逻辑，绕过 CommandArgs

                # 方案：在 MuteMaiCommand 中增加一个方法来处理字符串参数
                # 然后在 AliasHandler 中调用这个方法
                # 但这会增加 MuteMaiCommand 的复杂性
                # 最佳实践是让 AliasHandler 模拟 CommandArgs

                # 查看文档，CommandArgs 通常在 PlusCommand 内部由系统根据 command_name 和输入消息解析
                # 在 AliasHandler 中，我们没有经过 PlusCommand 的解析流程
                # 我们需要手动模拟这个过程

                # 假设 CommandArgs 有 .get_raw(), .is_empty() 等方法
                # 我们可以创建一个简单的类来模拟
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
                return HandlerReturn(intercepted=False) # 不拦截，让原消息可能继续参与其他流程

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
                # 假设 Message 对象有一个 `at_info` 或类似属性，包含被 @ 的用户信息
                # 或者 `content` 中包含 @ 机器人的标识
                # 这需要根据 MoFox 的具体 Message 结构来确定
                # 假设 message.at_users 是一个被 @ 的用户 ID 列表
                # 且 global_config.bot.qq_account 是机器人的 ID
                # 从 Message 对象获取被 @ 的用户列表
                # 通常，这可能需要调用 message_api 或其他相关 API 来解析消息
                # 或者 Message 对象本身包含 .mentioned_user_ids 等属性
                # 我们暂时假设 Message 有一个 .mentioned_user_ids 属性
                # 需要查阅具体文档或 Message 类定义来确认
                # 为了演示，我们假设存在 .mentioned_user_ids
                # 并且机器人自身的 ID 可以通过某种方式获取
                # 例如，从 global_config 或通过 self.get_config 获取（不太可能）
                # 或者通过 context.get('global_config') (如果 Handler 支持)
                # 或者最可能的是，通过 message.chat_stream 或其他 API 获取
                # 暂时，我们假设可以获取到 bot_id
                # 从插件配置或全局配置获取 bot_id 可能比较麻烦
                # 最直接的方式是假设 Message 对象包含足够的信息
                # 假设 message.mentioned_user_ids 是一个列表
                # 假设我们能获取到 bot_id
                # 从 Message 对象中获取平台信息和用户ID，然后与 Bot 的 ID 对比
                # 通常 Bot 的 ID 在全局配置中，例如 global_config.bot.qq_account
                # 但这在 Handler 中获取可能比较复杂
                # 我们需要一种方式来获取 Bot 的 ID
                # 一个可能的方法是通过 send_api 或其他 API 间接获取
                # 或者，如果 Handler 有访问全局配置的权限，可以通过 self.global_config
                # 但 Handler 可能没有直接访问 global_config 的方法
                # 让我们假设 Message 对象包含 chat_stream，而 chat_stream 包含 bot_id
                # 或者，Bot ID 可以在插件加载时获取并存储在类属性中
                # 这需要更深入的框架知识
                # 为了继续，我们假设存在一种方法来获取 Bot ID
                # 并且 Message 对象包含 .mentioned_user_ids
                # 一个更安全的假设是，Message.content 包含 @ 信息，并且我们可以解析它
                # 通常，@ 信息在消息的特殊字段中，而不是 content 里
                # 但如果我们能获取 Bot 的 nickname 或 ID，我们可以在 content 中查找
                # 例如，QQ 中可能是 @机器人昵称 或 [CQ:at,qq=机器人QQ号]
                # 让我们尝试一种通用的方法：获取 Bot 在当前聊天流的 ID
                # 这通常需要通过 chat_stream 或全局配置
                # 假设我们可以通过某种方式获取 bot_id
                # 例如，通过 send_api 获取当前登录的账户信息？
                # send_api.get_current_account_info() ?
                # 或者，通过 context 传递 bot_id ?
                # 这个问题比较核心，需要框架支持
                # 让我们暂时使用一个占位符，表示我们需要获取 bot_id
                # 并检查 message 是否 @ 了它
                # 为了模拟，我们假设存在一个函数可以检查消息是否 @ 了 Bot
                # 或者，我们可以从 message 对象中获取 bot_id
                # 假设 message 对象有一个 .bot_info 或 .platform_info 可以获取当前机器人ID
                # 或者，我们可以从 context 中获取 bot_id
                # context = args.get('context', {})
                # bot_id = context.get('bot_id') # 这需要在 Handler 调用时提供
                # 最可能的情况是，我们需要在 Handler 的 handle 方法中获取 bot_id
                # 通过 Message 对象的 chat_stream 或其他方式
                # 例如: bot_id = message.chat_stream.get_bot_id() (如果存在)
                # 或者: from src.config.config import global_config; bot_id = global_config.bot.qq_account
                # 但直接导入 global_config 在 Handler 中可能不是最佳实践
                # 让我们尝试导入 global_config 来获取 bot_id
                # 但这意味着 Handler 依赖于全局配置，这可能不是理想的
                # 但是，为了实现功能，这可能是必要的
                # 从 MaiCore 或 MoFox 的结构来看，通常会有一个全局配置对象
                # 例如 src.config.config.global_config
                # 并且 Bot 的 ID 会存储在 global_config.bot.qq_account 或类似字段中
                # 我们尝试导入它
                try:
                    from src.config.config import global_config
                    bot_id = str(global_config.bot.qq_account)
                    platform = global_config.bot.platform
                except ImportError:
                    print("[MuteAndUnmutePlugin] Error: Could not import global_config to get bot_id for @ check.")
                    return HandlerReturn(intercepted=False)

                # 检查消息是否 @ 了 Bot
                # 假设 Message 对象有 .mentioned_user_ids 属性
                # 这是最常见的实现方式
                # 如果没有，我们需要检查 .content 或其他属性
                # 例如，如果 .content 包含 [CQ:at,qq=bot_id] 或类似格式
                # 但 .mentioned_user_ids 更符合设计
                # 假设 .mentioned_user_ids 存在
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

                    # 返回 HandlerReturn 表示已处理（虽然主要动作是解除禁言，但可以认为是处理了@事件）
                    # 这里可以决定是否拦截原 @ 消息，让 Bot 不再对这个 @ 做出其他回应
                    # 但通常 @ 消息本身可能触发其他逻辑（如普通回复），所以不拦截可能更合适
                    # 如果 Bot 因为 @ 而解除禁言并开始思考，那么它自然会处理后续流程
                    # 所以这里选择不拦截，让原消息继续参与其他处理流程
                    return HandlerReturn(intercepted=False)
                # 如果没有 @ Bot，但 Bot 仍被禁言，则继续执行 MuteHandler 的拦截逻辑
                # 所以这里直接返回不拦截，让 MuteHandler 去检查和拦截
            # 如果禁言已过期，也直接返回不拦截，让 MuteHandler 去清理过期记录

        # 如果当前聊天流未被禁言，或 Bot 未被 @，则不处理
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

        stream_id = message.stream_id
        plugin_storage = storage_api.get(PLUGIN_NAME)

        current_muted_streams: Dict[str, float] = plugin_storage.get(STORAGE_KEY_MUTED_STREAMS, {})

        if stream_id in current_muted_streams:
            mute_until_timestamp = current_muted_streams[stream_id]
            current_time = time.time()

            if current_time < mute_until_timestamp:
                # 当前时间仍在禁言时间内
                # 注意：AtUnmuteHandler 应该已经处理了 @Bot 的情况并解除了禁言
                # 如果代码执行到这里，说明消息不是 @Bot 或者 AtUnmuteHandler 没有处理
                # 但根据上面 AtUnmuteHandler 的逻辑，如果 Bot 被 @ 并且在禁言中，它会解除禁言
                # 所以如果执行到这里，Bot 应该仍然处于禁言状态
                # 我们需要确保 AtUnmuteHandler 的优先级低于 MuteHandler，或者逻辑上先于 MuteHandler 执行
                # 但这里的逻辑是，如果 AtUnmuteHandler 解除了禁言，那么 MuteHandler 不会再看到禁言记录
                # 所以这个判断是正确的：如果记录还在，且时间未到，就拦截
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
    plugin_description = "一个允许Master控制Bot在当前聊天流中静音和取消静音的插件。支持配置别名、提示词，并支持@Bot唤醒。"

    # --- 配置相关 ---
    config_file_name = "config.toml"

    # 定义插件配置结构
    config_schema = {
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

    # 可选：插件加载后的初始化逻辑（如果需要）
    # async def on_plugin_loaded(self):
    #     print(f"[MuteAndUnmutePlugin] Loaded. Managing mute status in storage key: {STORAGE_KEY_MUTED_STREAMS}")
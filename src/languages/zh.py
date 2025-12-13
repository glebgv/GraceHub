# src/languages/zh.py

from dataclasses import dataclass
from .base import Texts

TEXTS_ZH = Texts(
    language_menu_title="请选择机器人界面语言：",
    language_ru_label="🇷🇺Русский",
    language_en_label="🇬🇧English",
    language_es_label="🇪🇸Español",
    language_hi_label="🇮🇳हिन्दी",
    language_zh_label="🇨🇳中文",
    language_unknown_error="未知语言",
    language_updated_message="语言已更新",
    access_denied="❌ 访问被拒绝",
    you_are_admin_now="✅ 您已成为此机器人的管理员！",
    user_welcome="👋 欢迎！\n发送消息，我们将尽快回复。",
    support_not_configured="❌ 支持未配置。请联系管理员。",
    message_forwarded_to_support="✅ 您的消息已转发给支持团队。",
    you_are_blocked="❌ 您已被屏蔽，无法使用此机器人。",

    admin_panel_title="<b>🛠 管理员面板</b>",
    admin_panel_choose_section="选择一个部分：",
    menu_greeting="✏️ 欢迎语",
    menu_autoreply="🔄 自动回复",
    menu_export_users="📋 导出用户",
    menu_blacklist="🚫 黑名单",
    menu_privacy="🛡 隐私模式",
    menu_language="🌐 语言",
    greeting_edit_prompt=(
        "✏️ 发送新的欢迎语文本。\n"
        "要删除欢迎语，请发送 /clear_greeting"
    ),
    greeting_cleared="✅ 欢迎语已删除。",
    greeting_need_text="需要发送包含欢迎语的文本消息。",
    greeting_saved="✅ 新欢迎语已保存。",

    openchat_setup_hint=(
        "💬 要使用此机器人，请配置 OpenChat：\n"
        "1) 创建一个没有 @username 的私有超级群组\n"
        "2) 在群组中启用话题（论坛模式）\n"
        "3) 将此机器人添加为管理员\n"
        "4) 在该群组中运行命令：\n"
        "<code>/bind @{bot_username}</code>\n\n"
        "配置完成后，您将可以使用完整的管理员面板。"
    ),
    openchat_off_confirm="✅ OpenChat 已禁用。",
    openchat_bind_only_owner="❌ 只有机器人所有者可以绑定 OpenChat。",
    openchat_bind_usage_error=(
        "❌ 命令格式必须为：\n"
        "/bind @{bot_username}\n\n"
        "指定的机器人与当前机器人不匹配。"
    ),
    openchat_not_supergroup=(
        "❌ 此聊天不是超级群组。\n\n"
        "在聊天设置中将其转换为超级群组，然后再次调用 /bind。"
    ),
    openchat_has_username=(
        "❌ 此聊天有公开的 @username（@{chat_username}）。\n\n"
        "OpenChat 需要没有用户名 的私有超级群组。\n"
        "创建一个没有 @username 的独立私有聊天并添加机器人。"
    ),
    openchat_no_forum=(
        "❌ 此聊天未启用话题（论坛模式）。\n\n"
        "打开聊天设置 → '话题' / '论坛模式'，启用它然后重复 /bind。"
    ),
    openchat_bound_ok=(
        "✅ OpenChat 已成功绑定到此聊天：\n"
        "<b>{chat_title}</b>\n\n"
        "新用户请求将作为票据创建在此聊天中。"
    ),
    openchat_now_status=(
        "💬 OpenChat 当前状态：<b>{status}</b>\n"
        "当前聊天：{current}\n\n"
        "要绑定聊天：\n"
        "1) 创建一个没有 @username 的私有超级群组\n"
        "2) 在该群组中启用话题（论坛模式）\n"
        "3) 将此机器人添加为该群组的管理员\n"
        "4) 在该群组中运行命令：\n"
        "<code>/bind @{bot_username}</code>\n\n"
        "要关闭 OpenChat，请在此处发送命令 /openchat_off。"
    ),
    ticket_btn_not_spam="非垃圾信息",
    ticket_btn_reopen="重新打开",
    ticket_btn_self="给我",
    ticket_btn_assign="分配",
    ticket_btn_spam="垃圾信息",
    ticket_btn_close="关闭",
    ticket_btn_compact="⬅️ 折叠",
    ticket_not_found="未找到工单",
    ticket_taken_in_work="工单已被接手处理",
    ticket_assign_nobody="没有可分配的处理人",
    ticket_assign_cancel="已取消",
    ticket_assigned_to="已分配给 {username}",
    ticket_marked_spam="已标记为垃圾信息",
    ticket_restored_from_spam="工单已从垃圾信息中恢复",
    ticket_closed="工单已关闭",
    ticket_reopened="工单已重新打开",

    ticket_closed_rating_request="您的请求已关闭。请对专家进行评分：",
    rating_topic_message="用户评分：{emoji}",
    rating_thanks_edit="感谢您的评分！我们很乐意为您服务！",
    rating_thanks_alert="感谢您的评分！",

    back="◀️ 返回",
    cancel="取消",

    # Auto-reply: status labels
    autoreply_enabled_label="已启用",
    autoreply_disabled_label="已禁用",
    autoreply_state_on=(
        "🔄 自动回复当前<b>{state}</b>\n\n"
        "发送自动回复文本或 /autoreply_off 禁用"
    ),
    autoreply_off_cmd_hint="/autoreply_off",
    autoreply_turned_off="✅ 自动回复已禁用。",
    autoreply_need_text="发送自动回复文本或 /autoreply_off。",
    autoreply_saved_enabled="✅ 自动回复已保存并启用。",

    # OpenChat: statuses and labels for menu
    openchat_status_on="已启用",
    openchat_status_off="已禁用",
    openchat_current_chat_id="ID: <code>{chat_id}</code>",
    openchat_not_bound="未绑定",
    openchat_status_line_on="🔗 状态：🟢开启",
    openchat_status_line_off="🔗 状态：🔴关闭 – 在启用话题的超级群组中检查绑定！",
    openchat_setup_button="⚙️ 配置 OpenChat",
    menu_you_are_admin="🕹 您是管理员",

    # Privacy Mode: statuses and buttons
    privacy_state_on="已启用",
    privacy_state_off="已禁用",
    privacy_toggle_btn="🔁 切换",
    privacy_screen=(
        "🛡 隐私模式当前<b>{state}</b>\n\n"
        "启用时，转发和复制机器人消息将被 Telegram 限制。"
        "无法完全防止截屏。"
    ),
    privacy_toggled="隐私模式 {state}",

    # Blacklist: search
    blacklist_search_prompt=(
        "🔍 发送用户名的一部分来在黑名单中搜索。\n"
        "示例：<code>alex</code> 或 <code>@alex</code>"
    ),
    blacklist_title="<b>🚫 黑名单</b>\n\n选择操作。",
    blacklist_btn_add="➕ 添加",
    blacklist_btn_remove="➖ 删除",
    blacklist_btn_show="📄 显示列表",
    blacklist_btn_back="◀️ 返回",
    blacklist_search_button="🔍 按用户名搜索",
    blacklist_back_to_menu_button="◀️ 返回黑名单菜单",
    blacklist_prev_page_button="⬅️ 上一页",
    blacklist_next_page_button="下一页 ➡️",
    blacklist_page_suffix="\n\n第 {current} / {total} 页",
    blacklist_list_empty="列表为空。",
    blacklist_list_title="<b>当前黑名单：</b>\n",
    blacklist_list_truncated="\n\n显示 {count} 条记录中的前 50 条。",
    blacklist_add_need_text="发送用户 ID，可选用户名用空格分隔。",
    blacklist_add_bad_format="格式无效。请提供数字用户 ID。",
    blacklist_added="✅ 用户 <code>{user_id}</code> 已添加到黑名单。",
    blacklist_remove_need_text="发送要从黑名单中删除的用户 ID。",
    blacklist_remove_bad_format="格式无效。请提供数字用户 ID。",
    blacklist_user_not_found="用户 <code>{user_id}</code> 在黑名单中未找到。",
    blacklist_user_removed="✅ 用户 <code>{user_id}</code> 已从黑名单中删除。",
    blacklist_remove_prompt=(
        "✏️ 发送要从黑名单中移除的用户 ID。"
    ),
    blacklist_choose_action="请选择操作。",
    blacklist_add_prompt=(
        "✏️ 发送要加入黑名单的用户 ID。\n"
        "也可以在后面加上用户名，用空格分隔："
        "<code>123456789 @username</code>"
    ),
    require_text_message="需要文本消息。",
    auto_close_log="已自动关闭 {count} 个工单",
    export_preparing="正在准备导出…",
    export_no_users="暂无用户可导出。",
    export_users_caption="用户导出 (CSV)。",

    master_title="🤖 <b>GraceHub 平台 - 主控机器人</b>",
    master_start_howto_title="<b>如何开始：</b>",
    master_start_cmd_add_bot="/add_bot - 添加新机器人",
    master_start_cmd_list_bots="/list_bots - 查看你的机器人列表",
    master_start_cmd_remove_bot="/remove_bot - 删除机器人",
    master_add_bot_title="🔑 <b>添加新机器人</b>",
    master_add_bot_description="发送从 @BotFather 获得的机器人令牌",
    master_add_bot_example="示例：<code>123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>",
    master_add_bot_warning="❗️ 请确保令牌正确且未在其他地方使用。",
    master_menu_add_bot="➕ 添加机器人",
    master_menu_list_bots="📋 机器人列表",
    master_menu_help="❓ 帮助",
    master_start_hint="使用 /start 查看可用命令",
    master_help_text=(
        "GraceHub 平台允许你添加自己的机器人，通过它来管理客服并回复用户。\n\n"
        "你可以通过“添加机器人”菜单或 /add_bot 命令添加你的机器人。\n"
        "系统会向你询问机器人令牌，你可以从官方 Telegram 机器人 @BotFather 获取。\n"
        "添加令牌后，你会看到成功添加的提示。"
        "然后可以打开你自己的机器人，发送 /start 并按照指引操作。\n\n"
        "此界面仅用于添加和管理你的客服机器人。"
    ),
    master_unknown_command="未知命令",
    master_list_bots_empty=(
        "你还没有任何机器人。\n\n"
        "使用 /add_bot 来添加你的第一个机器人。"
    ),
    master_list_bots_title="🤖 <b>你的机器人：</b>",
    master_list_bots_status_label="状态",
    master_list_bots_add_button="➕ 添加机器人",
    master_list_bots_main_menu_button="🔙 主菜单",
    master_list_bots_panel_button="📟 控制面板",
    master_list_bots_settings_button_prefix="⚙️ ",
    master_instance_status_label="状态",
    master_instance_created_label="创建时间",
    master_instance_actions_label="操作：",
    master_instance_not_yours="❌ 这个机器人不属于你",
    master_instance_pause_button="⏸️ 暂停",
    master_instance_resume_button="▶️ 恢复",
    master_instance_delete_button="🗑️ 删除",
    master_instance_panel_button="📟 控制面板",
    master_instance_back_button="🔙 返回",
    master_instance_deleted_short="机器人已删除",
    master_instance_deleted_full="机器人已成功删除",
    master_token_format_invalid="❌ 令牌格式无效。请重试。",
    master_token_already_exists="❌ 该机器人已在系统中添加",
    master_token_generic_error="❌ 添加机器人时出错：{error}",
    master_bot_added_title="✅ <b>机器人已成功添加！</b>",
    master_bot_added_name_label="🤖 名称",
    master_bot_added_username_label="👤 用户名",
    master_bot_added_id_label="🆔 ID",
    master_bot_added_webhook_label="🔗 Webhook URL",
    master_bot_added_status_starting="状态：<b>正在启动...</b>",
    master_bot_added_panel_hint="📟 此机器人的控制面板可在 mini‑app 中访问：",
    master_bot_manage_button="📊 管理机器人",
    master_bot_main_menu_button="🔙 主菜单",
    master_bot_open_panel_button="📟 打开面板（Mini App）",
    master_remove_bot_no_bots="你没有可删除的机器人",
    master_remove_bot_title="🗑️ 请选择要删除的机器人：\n\n",
    master_remove_bot_cancel_button="🔙 取消",
    billing_user_limit_reached_message=(
        "⚠️ 目前这个机器人的客服系统已达到当前套餐的会话上限。"
        "如果可以，请尝试通过其他渠道联系机器人拥有者，并告知他们这个问题。"
    ),
    billing_user_demo_expired_message=(
        "⏳ 这个机器人的试用套餐已到期，因此暂时无法接收新的客服请求。"
        "如果方便，请通过其他方式联系机器人拥有者，并告诉他们这一情况。"
    ),
    billing_user_no_plan_message=(
        "⚠️ 这个机器人尚未配置有效的客服套餐，因此暂时无法接受新的请求。"
        "请尝试通过其他渠道联系机器人的拥有者。"
    ),

    # 给拥有者/运营人员的提示（发送到 General 主题）
    billing_owner_limit_reached_message=(
        "⚠️ 您当前套餐的工单数量已用尽。"
        "新的用户仍在向机器人发送消息，但他们的请求已经不会出现在客服面板中。"
        "请在小程序中升级套餐以继续处理新的请求。"
    ),
    billing_owner_demo_expired_message=(
        "⏳ 该机器人的试用期已结束。"
        "用户还在发送消息，但新的工单不会被创建。"
        "请在小程序中选择付费套餐，以重新开始接收请求。"
    ),
    billing_owner_no_plan_message=(
        "⚠️ 这个机器人没有配置任何有效的计费套餐。"
        "用户的请求无法进入客服系统。"
        "请在小程序中配置合适的套餐。"
    ),
    master_owner_only="主控机器人仅对所有者可用。",
    billing_owner_only="仅限拥有者访问",
    billing_plan_unavailable="该套餐不可用",
    billing_need_instance_first=(
        "请先添加至少一个机器人，然后再购买套餐。"
    ),
    billing_invoice_create_error="无法创建 Stars 账单",

    billing_confirm_title="账户套餐：<b>{plan_name}</b>",
    billing_confirm_periods="周期数：{periods}",
    billing_confirm_total="应付总额：<b>{total_amount} ⭐</b>",
    billing_confirm_pay_hint=(
        "点击下方按钮，通过 Telegram Stars 完成支付。"
    ),
    billing_confirm_after_pay=(
        "支付成功后，您的账户功能使用期限将延长。"
    ),

    billing_button_pay_stars="💳 使用 Stars 支付",
    billing_button_back_plans="⬅️ 返回套餐列表",
    master_remove_owner_only="仅限拥有者访问",
    master_remove_not_yours="❌ 该机器人不属于你",
    master_remove_confirm_title="🤖 <b>{bot_name}</b> (@{bot_username})",
    master_remove_confirm_question="你确定要删除这个机器人吗？",
    master_remove_confirm_irreversible="此操作无法撤销。",
    master_remove_confirm_yes="✅ 是的，删除",
    master_remove_confirm_cancel="❌ 取消",
    master_menu_billing="💳 套餐与支付",
)


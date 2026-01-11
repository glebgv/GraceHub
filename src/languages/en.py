# src/languages/en.py

from .base import Texts

TEXTS_EN = Texts(
    language_menu_title="Choose bot interface language:",
    language_ru_label="🇷🇺Русский",
    language_en_label="🇬🇧English",
    language_es_label="🇪🇸Español",
    language_hi_label="🇮🇳हिन्दी",
    language_zh_label="🇨🇳中文",
    language_unknown_error="Unknown language",
    language_updated_message="Language updated",
    access_denied="❌ Access denied",
    you_are_admin_now="✅ You have become the administrator of this bot!",
    user_welcome="👋 Welcome!\nSend a message and we will reply as soon as possible.",
    support_not_configured="❌ Support is not configured. Please contact the administrator.",
    message_forwarded_to_support="✅ Your message has been forwarded to support.",
    you_are_blocked="❌ You are blocked and cannot use this bot.",
    admin_panel_title="<b>🛠 Admin panel</b>",
    admin_panel_choose_section="Choose a section:",
    menu_greeting="✏️ Greeting",
    menu_autoreply="🔄 Auto replies",
    menu_export_users="📋 Export users",
    menu_blacklist="🚫 Blacklist",
    menu_privacy="🛡 Privacy Mode",
    menu_language="🌐 Language",
    greeting_edit_prompt=(
        "✏️ Send a new greeting text.\nTo remove the greeting, send /clear_greeting"
    ),
    greeting_cleared="✅ Greeting has been removed.",
    greeting_need_text="A text message with greeting is required.",
    greeting_saved="✅ New greeting has been saved.",
    openchat_setup_hint=(
        "💬 To use this bot, configure OpenChat:\n"
        "1) Create a private supergroup without @username\n"
        "2) Enable topics (forum mode) in it\n"
        "3) Add this bot as an administrator\n"
        "4) In that chat, run the command:\n"
        "<code>/bind @{bot_username}</code>\n\n"
        "After setup you will be able to use the full admin panel."
    ),
    openchat_off_confirm="✅ OpenChat is disabled.",
    openchat_bind_only_owner="❌ Only the bot owner can bind OpenChat.",
    openchat_bind_usage_error=(
        "❌ The command must look like:\n"
        "/bind @{bot_username}\n\n"
        "The specified bot does not match the current one."
    ),
    openchat_not_supergroup=(
        "❌ This chat is not a supergroup.\n\n"
        "Convert it to a supergroup in chat settings and then call /bind again."
    ),
    openchat_has_username=(
        "❌ This chat has a public @username (@{chat_username}).\n\n"
        "OpenChat requires a private supergroup WITHOUT username.\n"
        "Create a separate private chat without @username and add the bot there."
    ),
    openchat_no_forum=(
        "❌ Topics (forum mode) are not enabled in this chat.\n\n"
        "Open chat settings → 'Topics' / 'Forum mode', enable it and repeat /bind."
    ),
    openchat_bound_ok=(
        "✅ GraceHub has been successfully bound to this chat:\n"
        "<b>{chat_title}</b>\n\n"
        "New user requests will be created as tickets in this chat."
    ),
    openchat_now_status=(
        "💬 OpenChat is currently <b>{status}</b>\n"
        "Current chat: {current}\n\n"
        "To bind a chat:\n"
        "1) Create a private supergroup without @username\n"
        "2) Enable topics (forum mode) in it\n"
        "3) Add this bot as an administrator\n"
        "4) In that chat, run the command:\n"
        "<code>/bind @{bot_username}</code>\n\n"
        "To disable OpenChat, send /openchat_off here."
    ),
    ticket_btn_not_spam="Not spam",
    ticket_btn_reopen="Reopen",
    ticket_btn_self="To me",
    ticket_btn_assign="Assign",
    ticket_btn_spam="Spam",
    ticket_btn_close="Close",
    ticket_btn_compact="⬅️ Collapse",
    ticket_taken_in_work="Ticket has been taken in work",
    ticket_assign_nobody="There is no one to assign",
    ticket_assign_cancel="Cancelled",
    ticket_assigned_to="Assigned to {username}",
    ticket_marked_spam="Marked as spam",
    ticket_restored_from_spam="Ticket has been restored from spam",
    ticket_closed="Ticket has been closed",
    ticket_reopened="Ticket has been reopened",
    ticket_not_found="Ticket not found",
    ticket_closed_rating_request="Your request has been closed. Please rate the specialist:",
    ticket_unspammed="Removed from spam",
    spam_confirm_only_spam="🗑 Mark as spam only (don’t block)",
    spam_confirm_spam_and_block="⛔ Mark as spam + block user",
    spam_confirm_cancel="↩️ Cancel",
    rating_topic_message="User rating: {emoji}",
    rating_thanks_edit="Thank you for your rating! We are always happy to help!",
    rating_thanks_alert="Thank you for your rating!",
    back="◀️ Back",
    cancel="Cancel",
    # Auto-reply: status labels
    autoreply_enabled_label="enabled",
    autoreply_disabled_label="disabled",
    autoreply_state_on=(
        "🔄 Auto replies are currently <b>{state}</b>\n\n"
        "Send an auto reply text or /autoreply_off to disable"
    ),
    autoreply_off_cmd_hint="/autoreply_off",
    autoreply_turned_off="✅ Auto replies have been disabled.",
    autoreply_need_text="Send auto reply text or /autoreply_off.",
    autoreply_saved_enabled="✅ Auto reply saved and enabled.",
    # OpenChat: statuses and labels for menu
    openchat_status_on="enabled",
    openchat_status_off="disabled",
    openchat_current_chat_id="ID: <code>{chat_id}</code>",
    openchat_not_bound="not bound",
    openchat_status_line_on="🔗 Status: 🟢ON",
    openchat_status_line_off="🔗 Status: 🔴OFF – check binding in the supergroup with topics!",
    openchat_setup_button="⚙️ Configure OpenChat",
    menu_you_are_admin="🕹 You are an administrator",
    # Privacy Mode: statuses and buttons
    privacy_state_on="enabled",
    privacy_state_off="disabled",
    privacy_toggle_btn="🔁 Toggle",
    privacy_screen=(
        "🛡 Privacy Mode is currently <b>{state}</b>\n\n"
        "When enabled, forwarding and copying bot messages will be "
        "restricted by Telegram. It is not possible to fully prevent screenshots."
    ),
    privacy_toggled="Privacy Mode {state}",
    # Blacklist: search
    blacklist_search_prompt=(
        "🔍 Send a part of the username to search in the blacklist.\n"
        "Example: <code>alex</code> or <code>@alex</code>"
    ),
    blacklist_title="<b>🚫 Blacklist</b>\n\nChoose an action.",
    blacklist_btn_add="➕ Add",
    blacklist_btn_remove="➖ Remove",
    blacklist_btn_show="📄 Show list",
    blacklist_btn_back="◀️ Back",
    blacklist_search_button="🔍 Search by username",
    blacklist_back_to_menu_button="◀️ Back to blacklist menu",
    blacklist_prev_page_button="⬅️ Previous",
    blacklist_next_page_button="Next ➡️",
    blacklist_page_suffix="\n\nPage {current} / {total}",
    blacklist_list_empty="The list is empty.",
    blacklist_list_title="<b>Current blacklist:</b>\n",
    blacklist_list_truncated="\n\nShowing first 50 of {count} entries.",
    blacklist_add_need_text="Send user ID, optionally username separated by space.",
    blacklist_add_bad_format="Invalid format. Provide numeric user ID.",
    blacklist_added="✅ User <code>{user_id}</code> added to blacklist.",
    blacklist_remove_need_text="Send the user ID to remove from the blacklist.",
    blacklist_remove_bad_format="Invalid format. Provide numeric user ID.",
    blacklist_user_not_found="User <code>{user_id}</code> not found in blacklist.",
    blacklist_user_removed="✅ User <code>{user_id}</code> removed from blacklist.",
    blacklist_remove_prompt="✏️ Send the user ID to remove from the blacklist.",
    blacklist_choose_action="Choose an action.",
    blacklist_add_prompt=(
        "✏️ Send the user ID to add to the blacklist.\n"
        "You can also specify the username separated by space: "
        "<code>123456789 @username</code>"
    ),
    require_text_message="A text message is required.",
    auto_close_log="Auto-closed {count} tickets",
    # Users export
    export_preparing="Preparing export…",
    export_no_users="There are no users to export yet.",
    export_users_caption="Users export (CSV).",
    master_title="🤖 <b>GraceHub Platform - Master Bot</b>",
    master_start_howto_title="<b>How to start:</b>",
    master_start_cmd_add_bot="/add_bot - Add a new bot",
    master_start_cmd_list_bots="/list_bots - List your bots",
    master_start_cmd_remove_bot="/remove_bot - Remove a bot",
    master_add_bot_title="🔑 <b>Add a new bot</b>",
    master_add_bot_description="Send the token of your bot obtained from @BotFather",
    master_add_bot_example="Example: <code>123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>",
    master_add_bot_warning="❗️ Make sure the token is correct and not used anywhere else.",
    master_menu_add_bot="➕ Add bot",
    master_menu_list_bots="📋 List bots",
    master_menu_help="❓ Help",
    master_start_hint="Use /start to see available commands",
    master_help_text=(
        "GraceHub Platform allows you to add your own bot through which "
        "you can manage support and reply to users.\n\n"
        "You can add your bot using the “Add bot” menu or the /add_bot command.\n"
        "You will be asked for the bot token, which you can obtain from the official Telegram bot @BotFather.\n"
        "After adding the token you will see a successful addition message. "
        "Then you can open your own bot, press /start and follow the instructions.\n\n"
        "This interface is only for adding and managing your support bots."
    ),
    master_unknown_command="Unknown command",
    master_list_bots_empty=("You don't have any bots yet.\n\nUse /add_bot to add your first bot."),
    master_list_bots_title="🤖 <b>Your bots:</b>",
    master_list_bots_status_label="Status",
    master_list_bots_add_button="➕ Add bot",
    master_list_bots_main_menu_button="🔙 Main menu",
    master_list_bots_panel_button="📟 Control panel",
    master_list_bots_settings_button_prefix="⚙️ ",
    master_instance_status_label="Status",
    master_instance_created_label="Created at",
    master_instance_actions_label="Actions:",
    master_instance_not_yours="❌ This bot does not belong to you",
    master_instance_pause_button="⏸️ Pause",
    master_instance_resume_button="▶️ Resume",
    master_instance_delete_button="🗑️ Delete",
    master_instance_panel_button="📟 Control panel",
    master_instance_back_button="🔙 Back",
    master_instance_deleted_short="Bot deleted",
    master_instance_deleted_full="Bot has been successfully deleted",
    master_token_format_invalid="❌ Invalid token format. Please try again.",
    master_token_already_exists="❌ This bot is already added to the system",
    master_token_generic_error="❌ Error while adding the bot: {error}",
    master_bot_added_title="✅ <b>Bot has been added successfully!</b>",
    master_bot_added_name_label="🤖 Name",
    master_bot_added_username_label="👤 Username",
    master_bot_added_id_label="🆔 ID",
    master_bot_added_webhook_label="🔗 Webhook URL",
    master_bot_added_status_starting="Status: <b>Starting...</b>",
    master_bot_added_panel_hint="📟 The control panel for this bot is available in the mini app:",
    master_bot_manage_button="📊 Manage bot",
    master_bot_main_menu_button="🔙 Main menu",
    master_bot_open_panel_button="📟 Open panel (Mini App)",
    master_remove_bot_no_bots="You have no bots to remove",
    master_remove_bot_title="🗑️ Select a bot to remove:\n\n",
    master_remove_bot_cancel_button="🔙 Cancel",
    billing_user_limit_reached_message=(
        "⚠️ The owners of this bot have reached the support limit in their plan. "
        "If possible, please try to contact them through other channels and let them know about this issue."
    ),
    billing_user_demo_expired_message=(
        "⏳ The demo plan of this bot’s owners has expired, so they temporarily cannot receive new support requests. "
        "If you can, please contact them by other means and let them know."
    ),
    billing_user_no_plan_message=(
        "⚠️ This bot does not have an active support plan configured yet, so new requests are temporarily not accepted. "
        "Please try to reach the owners of the bot through other channels."
    ),
    # For owners/operators in the General topic
    billing_owner_limit_reached_message=(
        "⚠️ You have reached the ticket limit for your current plan. "
        "New users are writing to the bot, but their requests no longer appear in the support panel. "
        "Upgrade your plan in the mini app to continue working with new requests."
    ),
    billing_owner_demo_expired_message=(
        "⏳ The demo period for this bot has expired. "
        "Users keep sending messages, but new tickets are not being created. "
        "Choose a paid plan in the mini app to start receiving requests again."
    ),
    billing_owner_no_plan_message=(
        "⚠️ This bot has no active billing plan configured. "
        "User requests do not reach the helpdesk. "
        "Please configure a plan in the mini app."
    ),
    master_owner_only="The master bot is available only to the owner.",
    billing_owner_only="Access is restricted to the owner only",
    billing_plan_unavailable="The plan is not available",
    billing_need_instance_first=("Add at least one bot first, then you can purchase a plan."),
    billing_invoice_create_error="Failed to create Stars invoice",
    billing_confirm_title="Account plan: <b>{plan_name}</b>",
    billing_confirm_periods="Periods: {periods}",
    billing_confirm_total="Total to pay: <b>{total_amount} ⭐</b>",
    billing_confirm_pay_hint=("Tap the button below to pay via Telegram Stars."),
    billing_confirm_after_pay=("After successful payment, your account features will be extended."),
    billing_button_pay_stars="💳 Pay with Stars",
    billing_button_back_plans="⬅️ Back to plans",
    billing_expiring_title="🔔 <b>Plan reminder</b>\n\n",
    billing_expiring_body=(
        "Instance @{bot_username} has {days_left} days left before the billing period ends.\n"
        "Extend your plan to keep the bot running without limitations."
    ),
    master_remove_owner_only="Access is restricted to the owner only",
    master_remove_not_yours="❌ This bot does not belong to you",
    master_remove_confirm_title="🤖 <b>{bot_name}</b> (@{bot_username})",
    master_remove_confirm_question="Do you really want to delete this bot?",
    master_remove_confirm_irreversible="This action cannot be undone.",
    master_remove_confirm_yes="✅ Yes, delete",
    master_remove_confirm_cancel="❌ Cancel",
    master_menu_billing="💳 Plans & Billing",
    attachment_too_big="The file is too large. Please send a smaller file.",
    too_many_messages="⚠️ Too many messages. Please wait a bit and try again.",
    billing_plans_title="Choose a plan for your account:",
    billing_plan_line="• <b>{plan_name}</b>: {price_stars} ⭐ / {period_days} days, limit {tickets_limit} tickets",
    menu_rating="Rating on close",
    rating_state_on="Rating request: ENABLED",
    rating_state_off="Rating request: DISABLED",
    rating_screen=(
        "{state}\n\n"
        "When enabled, after a ticket is closed the user will receive "
        "a request to rate the support quality."
    ),
    rating_toggle_btn="Toggle rating request",
    rating_toggled="Rating request state has been changed.\n\n{state}",
    master_current_plan_with_expiry="Current plan: {plan_name} (until {date}), {days_left} days left.",
    master_current_plan_no_date="Current plan: {plan_name}, {days_left} days left.",
    master_current_plan_paused="Plan {plan_name} is paused (until {date}). Renew your subscription to continue.",
    billing_unknown_plan_name="Unknown plan",
    ticket_taken_self="✅ The ticket has been assigned to you",
    ticket_no_assignees="No available operators to assign",
    first_message_forwarded="✅ Message forwarded to support. We'll reply soon!",
    session_flood_message="⏳ Your messages have been delivered. Awaiting operator response!",
)

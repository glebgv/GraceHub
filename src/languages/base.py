# src/languages/base.py
from dataclasses import dataclass

@dataclass
class Texts:
    access_denied: str
    you_are_admin_now: str
    user_welcome: str
    support_not_configured: str
    message_forwarded_to_support: str
    you_are_blocked: str
    language_menu_title: str
    language_ru_label: str
    language_en_label: str
    language_es_label: str
    language_hi_label: str
    language_zh_label: str
    language_unknown_error: str
    language_updated_message: str

    admin_panel_title: str
    admin_panel_choose_section: str
    menu_greeting: str
    menu_autoreply: str
    menu_export_users: str
    menu_blacklist: str
    menu_privacy: str
    menu_language: str
    greeting_edit_prompt: str
    greeting_cleared: str
    greeting_need_text: str
    greeting_saved: str

    openchat_setup_hint: str
    openchat_off_confirm: str
    openchat_bind_only_owner: str
    openchat_bind_usage_error: str
    openchat_not_supergroup: str
    openchat_has_username: str
    openchat_no_forum: str
    openchat_bound_ok: str

    ticket_btn_not_spam: str
    ticket_btn_reopen: str
    ticket_btn_self: str
    ticket_btn_assign: str
    ticket_btn_spam: str
    ticket_btn_close: str
    ticket_btn_compact: str
    ticket_not_found: str
    ticket_taken_in_work: str
    ticket_assign_nobody: str
    ticket_assign_cancel: str
    ticket_assigned_to: str
    ticket_marked_spam: str
    ticket_restored_from_spam: str
    ticket_closed: str
    ticket_reopened: str

    ticket_closed_rating_request: str
    rating_topic_message: str
    rating_thanks_edit: str
    rating_thanks_alert: str

    # Auto-reply: status labels
    autoreply_enabled_label: str
    autoreply_disabled_label: str
    autoreply_state_on: str
    autoreply_off_cmd_hint: str
    autoreply_turned_off: str
    autoreply_need_text: str
    autoreply_saved_enabled: str

    # OpenChat: statuses and labels for menu
    openchat_status_on: str
    openchat_status_off: str
    openchat_current_chat_id: str
    openchat_not_bound: str
    openchat_status_line_on: str
    openchat_status_line_off: str
    openchat_setup_button: str
    menu_you_are_admin: str
    openchat_now_status: str

    # Privacy Mode: statuses and buttons
    privacy_state_on: str
    privacy_state_off: str
    privacy_toggle_btn: str

    privacy_screen: str
    privacy_toggled: str

    # Blacklist: search
    blacklist_search_prompt: str
    blacklist_title: str
    blacklist_btn_add: str
    blacklist_btn_remove: str
    blacklist_btn_show: str
    blacklist_btn_back: str
    blacklist_search_button: str
    blacklist_back_to_menu_button: str
    blacklist_prev_page_button: str
    blacklist_next_page_button: str
    blacklist_page_suffix: str
    blacklist_list_empty: str
    blacklist_list_title: str
    blacklist_list_truncated: str
    blacklist_add_need_text: str
    blacklist_add_bad_format: str
    blacklist_added: str
    blacklist_remove_need_text: str
    blacklist_remove_bad_format: str
    blacklist_user_not_found: str
    blacklist_user_removed: str
    blacklist_remove_prompt: str
    blacklist_choose_action: str
    blacklist_add_prompt: str

    require_text_message: str
    auto_close_log: str
    export_preparing: str
    export_no_users: str
    export_users_caption: str

    back: str
    cancel: str

    master_title: str
    master_start_howto_title: str
    master_start_cmd_add_bot: str
    master_start_cmd_list_bots: str
    master_start_cmd_remove_bot: str
    master_add_bot_title: str
    master_add_bot_description: str
    master_add_bot_example: str
    master_add_bot_warning: str
    master_menu_add_bot: str
    master_menu_list_bots: str
    master_menu_help: str
    master_start_hint: str
    master_help_text: str
    master_menu_billing: str
    master_unknown_command: str
    master_list_bots_empty: str
    master_list_bots_title: str
    master_list_bots_status_label: str
    master_list_bots_add_button: str
    master_list_bots_main_menu_button: str
    master_list_bots_panel_button: str
    master_list_bots_settings_button_prefix: str
    master_instance_status_label: str
    master_instance_created_label: str
    master_instance_actions_label: str
    master_instance_not_yours: str
    master_instance_pause_button: str
    master_instance_resume_button: str
    master_instance_delete_button: str
    master_instance_panel_button: str
    master_instance_back_button: str
    master_instance_deleted_short: str
    master_instance_deleted_full: str
    master_token_format_invalid: str
    master_token_already_exists: str
    master_token_generic_error: str
    master_bot_added_title: str
    master_bot_added_name_label: str
    master_bot_added_username_label: str
    master_bot_added_id_label: str
    master_bot_added_webhook_label: str
    master_bot_added_status_starting: str
    master_bot_added_panel_hint: str
    master_bot_manage_button: str
    master_bot_main_menu_button: str
    master_bot_open_panel_button: str
    master_remove_bot_no_bots: str
    master_remove_bot_title: str
    master_remove_bot_cancel_button: str

    # Billing: сообщения пользователю
    billing_user_limit_reached_message: str
    billing_user_demo_expired_message: str
    billing_user_no_plan_message: str

    # Billing: сообщения владельцам/операторам в General
    billing_owner_limit_reached_message: str
    billing_owner_demo_expired_message: str
    billing_owner_no_plan_message: str
    master_owner_only: str

    billing_owner_only: str
    billing_plan_unavailable: str
    billing_need_instance_first: str
    billing_invoice_create_error: str

    billing_confirm_title: str    
    billing_confirm_periods: str    
    billing_confirm_total: str         
    billing_confirm_pay_hint: str
    billing_confirm_after_pay: str

    billing_button_pay_stars: str
    billing_button_back_plans: str

    billing_plans_title: str
    billing_plan_line: str

    billing_expiring_title: str
    billing_expiring_body: str


    master_remove_owner_only: str
    master_remove_not_yours: str
    master_remove_confirm_title: str
    master_remove_confirm_question: str 
    master_remove_confirm_irreversible: str  
    master_remove_confirm_yes: str
    master_remove_confirm_cancel: str
    attachment_too_big: str
    too_many_messages: str


# src/languages/es.py

from dataclasses import dataclass
from .base import Texts

TEXTS_ES = Texts(
    language_menu_title="Elige el idioma de la interfaz del bot:",
    language_ru_label="🇷🇺Русский",
    language_en_label="🇬🇧English",
    language_es_label="🇪🇸Español",
    language_hi_label="🇮🇳हिन्दी",
    language_zh_label="🇨🇳中文",
    language_unknown_error="Idioma desconocido",
    language_updated_message="El idioma se ha actualizado",
    access_denied="❌ Acceso denegado",
    you_are_admin_now="✅ ¡Ahora eres administrador de este bot!",
    user_welcome="👋 ¡Bienvenido!\nEnvía un mensaje y te responderemos lo antes posible.",
    support_not_configured="❌ El soporte no está configurado. Ponte en contacto con el administrador.",
    message_forwarded_to_support="✅ Tu mensaje ha sido reenviado al soporte.",
    you_are_blocked="❌ Estás bloqueado y no puedes usar este bot.",

    admin_panel_title="<b>🛠 Panel de administración</b>",
    admin_panel_choose_section="Elige una sección:",
    menu_greeting="✏️ Mensaje de bienvenida",
    menu_autoreply="🔄 Respuestas automáticas",
    menu_export_users="📋 Exportar usuarios",
    menu_blacklist="🚫 Lista negra",
    menu_privacy="🛡 Modo de privacidad",
    menu_language="🌐 Idioma",
    greeting_edit_prompt=(
        "✏️ Envía un nuevo texto de bienvenida.\n"
        "Para eliminar el mensaje de bienvenida, envía /clear_greeting"
    ),
    greeting_cleared="✅ El mensaje de bienvenida ha sido eliminado.",
    greeting_need_text="Se necesita un mensaje de texto con el saludo.",
    greeting_saved="✅ El nuevo mensaje de bienvenida ha sido guardado.",

    openchat_setup_hint=(
        "💬 Para usar este bot, configura OpenChat:\n"
        "1) Crea un supergrupo privado sin @username\n"
        "2) Activa los temas (modo foro) en él\n"
        "3) Añade este bot como administrador\n"
        "4) En ese chat, ejecuta el comando:\n"
        "<code>/bind @{bot_username}</code>\n\n"
        "Después de la configuración podrás usar el panel de administración completo."
    ),
    openchat_off_confirm="✅ OpenChat está desactivado.",
    openchat_bind_only_owner="❌ Solo el propietario del bot puede vincular OpenChat.",
    openchat_bind_usage_error=(
        "❌ El comando debe tener el siguiente formato:\n"
        "/bind @{bot_username}\n\n"
        "El bot especificado no coincide con el actual."
    ),
    openchat_not_supergroup=(
        "❌ Este chat no es un supergrupo.\n\n"
        "Convierte el chat en supergrupo en los ajustes y luego ejecuta /bind de nuevo."
    ),
    openchat_has_username=(
        "❌ Este chat tiene un @username público (@{chat_username}).\n\n"
        "OpenChat requiere un supergrupo privado SIN nombre de usuario.\n"
        "Crea otro chat privado sin @username y añade allí el bot."
    ),
    openchat_no_forum=(
        "❌ Los temas (modo foro) no están activados en este chat.\n\n"
        "Abre los ajustes del chat → 'Temas' / 'Modo foro', actívalo y repite /bind."
    ),
    openchat_bound_ok=(
        "✅ OpenChat se ha vinculado correctamente a este chat:\n"
        "<b>{chat_title}</b>\n\n"
        "Las nuevas solicitudes de usuarios se crearán como tickets en este chat."
    ),

    ticket_btn_not_spam="No es spam",
    ticket_btn_reopen="Reabrir",
    ticket_btn_self="Para mí",
    ticket_btn_assign="Asignar",
    ticket_btn_spam="Spam",
    ticket_btn_close="Cerrar",
    ticket_btn_compact="⬅️ Contraer",
    ticket_not_found="El ticket no se ha encontrado",
    ticket_taken_in_work="El ticket ha sido tomado en trabajo",
    ticket_assign_nobody="No hay nadie a quien asignar",
    ticket_assign_cancel="Cancelado",
    ticket_assigned_to="Asignado a {username}",
    ticket_marked_spam="Marcado como spam",
    ticket_restored_from_spam="El ticket ha sido restaurado desde spam",
    ticket_closed="El ticket ha sido cerrado",
    ticket_reopened="El ticket ha sido reabierto",

    ticket_closed_rating_request="Tu solicitud ha sido cerrada. Valora al especialista:",
    rating_topic_message="Valoración del usuario: {emoji}",
    rating_thanks_edit="¡Gracias por tu valoración! ¡Siempre estamos encantados de ayudarte!",
    rating_thanks_alert="¡Gracias por tu valoración!",

    back="◀️ Atrás",
    cancel="Cancelar",

    # Auto-reply: status labels
    autoreply_enabled_label="activado",
    autoreply_disabled_label="desactivado",
    autoreply_state_on=(
        "🔄 Las respuestas automáticas están actualmente <b>{state}</b>\n\n"
        "Envía el texto de la respuesta automática o /autoreply_off para desactivarlas"
    ),
    autoreply_off_cmd_hint="/autoreply_off",
    autoreply_turned_off="✅ Las respuestas automáticas han sido desactivadas.",
    autoreply_need_text="Envía el texto de la respuesta automática o /autoreply_off.",
    autoreply_saved_enabled="✅ Respuesta automática guardada y activada.",

    # OpenChat: statuses and labels for menu
    openchat_status_on="activado",
    openchat_status_off="desactivado",
    openchat_current_chat_id="ID: <code>{chat_id}</code>",
    openchat_not_bound="no vinculado",
    openchat_status_line_on="🔗 Estado: 🟢ACTIVO",
    openchat_status_line_off="🔗 Estado: 🔴INACTIVO – ¡revisa la vinculación en el supergrupo con temas activados!",
    openchat_setup_button="⚙️ Configurar OpenChat",
    menu_you_are_admin="🕹 Eres administrador",
    openchat_now_status=(
        "💬 OpenChat está actualmente <b>{status}</b>\n"
        "Chat actual: {current}\n\n"
        "Para vincular un chat:\n"
        "1) Crea un supergrupo privado sin @username\n"
        "2) Activa los temas (modo foro) en él\n"
        "3) Añade este bot como administrador\n"
        "4) En ese chat ejecuta el comando:\n"
        "<code>/bind @{bot_username}</code>\n\n"
        "Para desactivar OpenChat, envía aquí el comando /openchat_off."
    ),

    # Privacy Mode: statuses and buttons
    privacy_state_on="activado",
    privacy_state_off="desactivado",
    privacy_toggle_btn="🔁 Cambiar",
    privacy_screen=(
        "🛡 El modo de privacidad está actualmente <b>{state}</b>\n\n"
        "Cuando está activado, reenviar y copiar los mensajes del bot "
        "estará limitado por Telegram. No es posible impedir completamente las capturas de pantalla."
    ),
    privacy_toggled="Modo de privacidad {state}",

    # Blacklist: search
    blacklist_search_prompt=(
        "🔍 Envía una parte del nombre de usuario para buscar en la lista negra.\n"
        "Ejemplo: <code>alex</code> o <code>@alex</code>"
    ),
    blacklist_title="<b>🚫 Lista negra</b>\n\nElige una acción.",
    blacklist_btn_add="➕ Añadir",
    blacklist_btn_remove="➖ Eliminar",
    blacklist_btn_show="📄 Mostrar lista",
    blacklist_btn_back="◀️ Atrás",
    blacklist_search_button="🔍 Buscar por nombre de usuario",
    blacklist_back_to_menu_button="◀️ Volver al menú de lista negra",
    blacklist_prev_page_button="⬅️ Anterior",
    blacklist_next_page_button="Siguiente ➡️",
    blacklist_page_suffix="\n\nPágina {current} / {total}",
    blacklist_list_empty="La lista está vacía.",
    blacklist_list_title="<b>Lista negra actual:</b>\n",
    blacklist_list_truncated="\n\nMostrando las primeras 50 de {count} entradas.",
    blacklist_add_need_text="Envía el ID de usuario, opcionalmente el nombre de usuario separado por un espacio.",
    blacklist_add_bad_format="Formato no válido. Proporciona un ID de usuario numérico.",
    blacklist_added="✅ El usuario <code>{user_id}</code> ha sido añadido a la lista negra.",
    blacklist_remove_need_text="Envía el ID de usuario que quieres eliminar de la lista negra.",
    blacklist_remove_bad_format="Formato no válido. Proporciona un ID de usuario numérico.",
    blacklist_user_not_found="El usuario <code>{user_id}</code> no se encuentra en la lista negra.",
    blacklist_user_removed="✅ El usuario <code>{user_id}</code> ha sido eliminado de la lista negra.",
    blacklist_remove_prompt=(
    "✏️ Envía el ID del usuario que quieres eliminar de la lista negra."
    ),
    blacklist_choose_action="Elige una acción.",
    blacklist_add_prompt=(
        "✏️ Envía el ID del usuario que quieres añadir a la lista negra.\n"
        "También puedes indicar el nombre de usuario separado por un espacio: "
        "<code>123456789 @username</code>"
    ),

    require_text_message="Se requiere un mensaje de texto.",
    auto_close_log="Se han cerrado automáticamente {count} tickets",
    export_preparing="Preparando la exportación…",
    export_no_users="Todavía no hay usuarios que exportar.",
    export_users_caption="Exportación de usuarios (CSV).",

    master_title="🤖 <b>GraceHub Platform - Bot Maestro</b>",
    master_start_howto_title="<b>Cómo empezar:</b>",
    master_start_cmd_add_bot="/add_bot - Añadir un nuevo bot",
    master_start_cmd_list_bots="/list_bots - Lista de tus bots",
    master_start_cmd_remove_bot="/remove_bot - Eliminar un bot",
    master_add_bot_title="🔑 <b>Añadir un nuevo bot</b>",
    master_add_bot_description="Envía el token de tu bot obtenido de @BotFather",
    master_add_bot_example="Ejemplo: <code>123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>",
    master_add_bot_warning="❗️ Asegúrate de que el token sea correcto y no se utilice en otro lugar.",
    master_menu_add_bot="➕ Añadir bot",
    master_menu_list_bots="📋 Lista de bots",
    master_menu_help="❓ Ayuda",
    master_start_hint="Usa /start para ver los comandos disponibles",
    master_help_text=(
        "GraceHub Platform te permite añadir tu propio bot con el que "
        "podrás gestionar el soporte y responder a los usuarios.\n\n"
        "Puedes añadir tu bot usando el menú «Añadir bot» o el comando /add_bot.\n"
        "Se te pedirá el token de tu bot, que puedes obtener del bot oficial de Telegram @BotFather.\n"
        "Después de añadir el token verás un mensaje de éxito. "
        "Luego podrás abrir tu bot, pulsar /start y seguir las instrucciones.\n\n"
        "Aquí solo se realiza la adición y gestión de tus bots de soporte."
    ),
    master_unknown_command="Comando desconocido",
    master_list_bots_empty=(
        "Todavía no tienes bots.\n\n"
        "Usa /add_bot para añadir tu primer bot."
    ),
    master_list_bots_title="🤖 <b>Tus bots:</b>",
    master_list_bots_status_label="Estado",
    master_list_bots_add_button="➕ Añadir bot",
    master_list_bots_main_menu_button="🔙 Menú principal",
    master_list_bots_panel_button="📟 Panel de control",
    master_list_bots_settings_button_prefix="⚙️ ",
    master_instance_status_label="Estado",
    master_instance_created_label="Creado",
    master_instance_actions_label="Acciones:",
    master_instance_not_yours="❌ Este bot no te pertenece",
    master_instance_pause_button="⏸️ Pausar",
    master_instance_resume_button="▶️ Reanudar",
    master_instance_delete_button="🗑️ Eliminar",
    master_instance_panel_button="📟 Panel de control",
    master_instance_back_button="🔙 Atrás",
    master_instance_deleted_short="Bot eliminado",
    master_instance_deleted_full="El bot se ha eliminado correctamente",
    master_token_format_invalid="❌ Formato de token no válido. Inténtalo de nuevo.",
    master_token_already_exists="❌ Este bot ya está añadido en el sistema",
    master_token_generic_error="❌ Error al añadir el bot: {error}",
    master_bot_added_title="✅ <b>¡Bot añadido correctamente!</b>",
    master_bot_added_name_label="🤖 Nombre",
    master_bot_added_username_label="👤 Usuario",
    master_bot_added_id_label="🆔 ID",
    master_bot_added_webhook_label="🔗 URL del webhook",
    master_bot_added_status_starting="Estado: <b>Iniciando...</b>",
    master_bot_added_panel_hint="📟 El panel de control de este bot está disponible en la mini‑app:",
    master_bot_manage_button="📊 Gestionar bot",
    master_bot_main_menu_button="🔙 Menú principal",
    master_bot_open_panel_button="📟 Abrir panel (Mini App)",
    master_remove_bot_no_bots="No tienes bots para eliminar",
    master_remove_bot_title="🗑️ Elige un bot para eliminar:\n\n",
    master_remove_bot_cancel_button="🔙 Cancelar",
    billing_user_limit_reached_message=(
        "⚠️ Los propietarios de este bot han alcanzado el límite de solicitudes de soporte en su plan. "
        "Si te es posible, intenta ponerte en contacto con ellos por otros canales y avísales de este problema."
    ),
    billing_user_demo_expired_message=(
        "⏳ Ha expirado el plan de demostración de los propietarios de este bot, por lo que temporalmente no pueden recibir nuevas solicitudes de soporte. "
        "Si puedes, contacta con ellos por otros medios y coméntales lo ocurrido."
    ),
    billing_user_no_plan_message=(
        "⚠️ Este bot aún no tiene configurado un plan de soporte activo, por lo que de momento no se aceptan nuevas solicitudes. "
        "Intenta ponerte en contacto con los propietarios del bot por otros canales."
    ),

    # Para los propietarios/operadores en el tema General
    billing_owner_limit_reached_message=(
        "⚠️ Se ha alcanzado el límite de tickets de vuestro plan actual. "
        "Los nuevos usuarios siguen escribiendo al bot, pero sus solicitudes ya no aparecen en el panel de soporte. "
        "Actualizad vuestro plan en la mini app para seguir trabajando con nuevas solicitudes."
    ),
    billing_owner_demo_expired_message=(
        "⏳ Ha terminado el periodo de demostración de este bot. "
        "Los usuarios siguen enviando mensajes, pero no se crean nuevos tickets. "
        "Elegid un plan de pago en la mini app para volver a recibir solicitudes."
    ),
    billing_owner_no_plan_message=(
        "⚠️ Este bot no tiene configurado ningún plan de facturación activo. "
        "Las solicitudes de los usuarios no llegan al sistema de soporte. "
        "Configurad un plan en la mini app."
    ),
    master_owner_only="El bot maestro está disponible solo para el propietario.",
    billing_owner_only="Acceso permitido solo al propietario",
    billing_plan_unavailable="El plan no está disponible",
    billing_need_instance_first=(
        "Primero añade al menos un bot y luego podrás contratar un plan."
    ),
    billing_invoice_create_error="No se pudo crear la factura de Stars",

    billing_confirm_title="Plan de la cuenta: <b>{plan_name}</b>",
    billing_confirm_periods="Periodos: {periods}",
    billing_confirm_total="Total a pagar: <b>{total_amount} ⭐</b>",
    billing_confirm_pay_hint=(
        "Pulsa el botón de abajo para pagar mediante Telegram Stars."
    ),
    billing_confirm_after_pay=(
        "Después del pago correcto, se ampliará el acceso a las funciones de la cuenta."
    ),

    billing_button_pay_stars="💳 Pagar con Stars",
    billing_button_back_plans="⬅️ Volver a los planes",
    master_remove_owner_only="Acceso permitido solo al propietario",
    master_remove_not_yours="❌ Este bot no es tuyo",
    master_remove_confirm_title="🤖 <b>{bot_name}</b> (@{bot_username})",
    master_remove_confirm_question="¿Realmente quieres eliminar este bot?",
    master_remove_confirm_irreversible="Esta acción no se puede deshacer.",
    master_remove_confirm_yes="✅ Sí, eliminar",
    master_remove_confirm_cancel="❌ Cancelar",
    master_menu_billing="💳 Planes y pago",
    attachment_too_big = "El archivo es demasiado grande. Por favor, envía un archivo más pequeño."

)


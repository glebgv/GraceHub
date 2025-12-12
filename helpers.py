
# Additional helper methods for GraceHub Worker
# Add these methods to the GraceHubWorker class in worker/main.py

    def clear_all_pending(self):
        """Clear all pending admin actions"""
        admin_id = int(self.get_setting("admin_user_id") or 0)
        if admin_id:
            self.db.execute("DELETE FROM adminactions WHERE adminid = ?", (admin_id,))
            self.db.execute("DELETE FROM greetingsetup WHERE adminid = ?", (admin_id,))
            self.db.commit()

    async def send_greeting(self, chat_id: int, reply_markup=None):
        """Send greeting message"""
        data = self.load_greeting()
        if not data:
            return

        gtype, file_id, text = data

        try:
            if gtype == "text":
                await self.bot.send_message(chat_id, text or "Добро пожаловать!", reply_markup=reply_markup)
            elif gtype == "photo":
                await self.bot.send_photo(chat_id, file_id, caption=text, reply_markup=reply_markup)
            elif gtype == "video":
                await self.bot.send_video(chat_id, file_id, caption=text, reply_markup=reply_markup)
            # Add other media types as needed
        except Exception as e:
            logger.error(f"Failed to send greeting: {e}")

    def load_greeting(self):
        """Load greeting from database"""
        row = self.db.execute("SELECT type, fileid, text FROM greetings WHERE id = 1").fetchone()
        if row:
            return (row[0], row[1], row[2])
        return None

    async def editor_answer_text(self, message, text: str, reply_markup=None):
        """Edit or send message text"""
        try:
            if message.content_type == "text":
                await message.edit_text(text, reply_markup=reply_markup)
            else:
                await message.edit_reply_markup(reply_markup=reply_markup) 
                await message.answer(text, reply_markup=reply_markup)
        except Exception:
            await message.answer(text, reply_markup=reply_markup)

    def set_openchat_enabled(self, enabled: bool):
        """Set OpenChat enabled status"""
        self.set_setting("openchat_enabled", str(enabled))

    def clear_openchat(self):
        """Clear OpenChat configuration"""
        self.set_setting("general_panel_chat_id", "")
        self.set_setting("openchat_username", "")
        self.set_setting("openchat_enabled", "False")

    async def ensure_general_panel(self):
        """Ensure general panel exists"""
        oc = self.get_openchat_settings()
        if not oc['chat_id']:
            return

        # Implementation would create/update the general panel message
        # This is a complex method from the original code
        pass

    async def update_general_panel_markup(self):
        """Update general panel markup"""
        # Implementation would update the panel keyboard
        pass

    async def ensure_ticket_for_user(self, chat_id: int, user_id: int, username: str) -> dict:
        """Ensure ticket exists for user"""
        # Check for existing ticket
        ticket = self.fetch_ticket_by_chat(chat_id, username, user_id)
        if ticket:
            return ticket

        # Create new ticket
        now = datetime.now(timezone.utc).isoformat()

        cur = self.db.execute("""
            INSERT INTO tickets (userid, username, chatid, status, createdat, updatedat) 
            VALUES (?, ?, ?, 'new', ?, ?)
        """, (user_id, username, chat_id, now, now))

        ticket_id = cur.lastrowid
        self.db.commit()

        # Create forum topic
        title = f"🎫 #{ticket_id} {username or f'user{user_id}'}"
        try:
            ft = await self.bot.create_forum_topic(chat_id, name=title)
            thread_id = ft.message_thread_id

            self.db.execute("UPDATE tickets SET threadid = ? WHERE id = ?", (thread_id, ticket_id))
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to create forum topic: {e}")
            thread_id = None

        return {
            'id': ticket_id,
            'userid': user_id,
            'username': username,
            'chatid': chat_id,
            'threadid': thread_id,
            'status': 'new'
        }

    def fetch_ticket_by_chat(self, chat_id: int, username: str, user_id: int):
        """Fetch existing ticket for user in chat"""
        if username:
            row = self.db.execute(
                "SELECT * FROM tickets WHERE chatid = ? AND username = ?",
                (chat_id, username)
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT * FROM tickets WHERE chatid = ? AND userid = ?", 
                (chat_id, user_id)
            ).fetchone()

        if row:
            cols = [c[0] for c in self.db.execute("PRAGMA table_info(tickets)").fetchall()]
            return dict(zip(cols, row))
        return None

    async def set_ticket_status(self, ticket_id: int, status: str, assigned_username: str = None, assigned_userid: int = None):
        """Set ticket status"""
        now = datetime.now(timezone.utc).isoformat()

        params = [status, now, ticket_id]
        sql = "UPDATE tickets SET status = ?, updatedat = ?"

        if assigned_username is not None:
            sql += ", assignedusername = ?"
            params.insert(-1, assigned_username)

        if assigned_userid is not None:
            sql += ", assigneduserid = ?"
            params.insert(-1, assigned_userid)

        sql += " WHERE id = ?"

        self.db.execute(sql, params)
        self.db.commit()

    async def put_ticket_keyboard(self, ticket_id: int, message_id: int, can_mark_solved: bool):
        """Add ticket management keyboard to message"""
        # Implementation would add inline keyboard with ticket actions
        # This is complex and depends on the specific ticket state
        pass

    def save_reply_mapping_v2(self, chat_id: int, message_id: int, target_user_id: int):
        """Save reply mapping for admin replies"""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("""
            INSERT OR REPLACE INTO adminreplymapv2 (chatid, adminmessageid, targetuserid, createdat) 
            VALUES (?, ?, ?, ?)
        """, (chat_id, message_id, target_user_id, now))
        self.db.commit()

    def save_reply_mapping_legacy(self, message_id: int, target_user_id: int):
        """Save legacy reply mapping"""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("""
            INSERT OR REPLACE INTO adminreplymap (adminmessageid, targetuserid, createdat) 
            VALUES (?, ?, ?)
        """, (message_id, target_user_id, now))
        self.db.commit()

    async def maybe_send_autoreply(self, user_id: int):
        """Send automatic reply if conditions are met"""
        # Check if auto-reply is enabled
        if self.get_setting("autoreply_enabled") != "True":
            return

        # Check if already replied today
        today = datetime.now(timezone.utc).date().isoformat()
        existing = self.db.execute(
            "SELECT 1 FROM autoreplylog WHERE userid = ? AND date = ?", 
            (user_id, today)
        ).fetchone()

        if existing:
            return

        # Check work hours and weekends (implement time checking)

        # Send auto-reply
        reply_text = self.get_setting("autoreply_text") or "Спасибо за обращение! Мы ответим в ближайшее время."

        try:
            await self.bot.send_message(user_id, reply_text)

            # Log the reply
            self.db.execute(
                "INSERT OR IGNORE INTO autoreplylog (userid, date) VALUES (?, ?)",
                (user_id, today)
            )
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to send auto-reply to {user_id}: {e}")

    async def handle_admin_text(self, message: Message):
        """Handle text from admin users"""
        # Implementation for admin commands and state handling
        # This would handle greeting setup, ban/unban flows, etc.
        pass

    async def handle_openchat_reply(self, message: Message, reply_msg: Message, oc: dict):
        """Handle replies in OpenChat mode"""
        # Implementation for OpenChat reply handling
        pass

    async def handle_admin_dm_reply(self, message: Message, reply_msg: Message):
        """Handle admin DM replies"""
        # Implementation for admin direct message replies
        pass

    async def forward_media_to_destination(self, user_id: int, username: str, message: Message):
        """Forward media message to destination"""
        oc = self.get_openchat_settings()
        header = f"👤 @{username}" if username else f"👤 userid:{user_id}"

        if oc['enabled'] and oc['chat_id']:
            # OpenChat mode
            ticket = await self.ensure_ticket_for_user(oc['chat_id'], user_id, username)

            # Forward media based on type
            if message.photo:
                sent = await self.bot.send_photo(
                    oc['chat_id'], 
                    message.photo[-1].file_id,
                    caption=header,
                    message_thread_id=ticket['threadid']
                )
            elif message.video:
                sent = await self.bot.send_video(
                    oc['chat_id'],
                    message.video.file_id, 
                    caption=header,
                    message_thread_id=ticket['threadid']
                )
            # Add other media types...

            self.save_reply_mapping_v2(oc['chat_id'], sent.message_id, user_id)
        else:
            # Direct admin mode
            admin_id = int(self.get_setting("admin_user_id") or 0)
            # Forward to admin...

    async def auto_close_tickets_loop(self):
        """Background task to auto-close inactive tickets"""
        while True:
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=12)  # AUTO_CLOSE_HOURS
                cutoff_iso = cutoff.isoformat()

                # Find tickets to close
                rows = self.db.execute("""
                    SELECT id FROM tickets 
                    WHERE status IN ('solved', 'inprogress') 
                    AND lastadminreplyat IS NOT NULL 
                    AND (lastusermsgat IS NULL OR lastusermsgat < ?)
                """, (cutoff_iso,)).fetchall()

                for (ticket_id,) in rows:
                    await self.set_ticket_status(ticket_id, 'closed')

                    # Update close timestamp
                    now = datetime.now(timezone.utc).isoformat()
                    self.db.execute(
                        "UPDATE tickets SET closedat = ? WHERE id = ?",
                        (now, ticket_id)
                    )
                    self.db.commit()

                if rows:
                    logger.info(f"Auto-closed {len(rows)} inactive tickets")

            except Exception as e:
                logger.error(f"Auto-close tickets error: {e}")

            await asyncio.sleep(300)  # Check every 5 minutes


# Additional callback implementations that were referenced
    async def cb_general_settings(self, c: CallbackQuery):
        """Handle general settings callback"""
        if not self.is_admin(c.from_user):
            return await c.answer("❌ Недостаточно прав", show_alert=True)

        await self.editor_answer_text(
            c.message, 
            "⚙️ Настройки панели",
            reply_markup=self.kb_panel_settings_root()
        )
        await c.answer()

    def kb_panel_settings_root(self):
        """Panel settings keyboard"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Авто-ответы", callback_data="gauto")],
            [InlineKeyboardButton(text="💬 OpenChat", callback_data="gopenchat")],
            [InlineKeyboardButton(text="🏠 Главная", callback_data="groot")]
        ])

    async def cb_goc_toggle(self, c: CallbackQuery):
        """Toggle OpenChat on/off"""
        if not self.is_admin(c.from_user):
            return await c.answer("❌ Недостаточно прав", show_alert=True)

        oc = self.get_openchat_settings()

        if not oc['chat_id'] and not oc['enabled']:
            return await c.answer("⚠️ Сначала настройте OpenChat", show_alert=True)

        if oc['chat_id']:
            # Check permissions before toggling
            ok, info = await self.openchat_check_permissions(oc['chat_id'])
            if not ok:
                self.set_openchat_enabled(False)
                await c.answer(info, show_alert=True)
                await self.update_general_panel_markup()
                return

        # Toggle status
        self.set_openchat_enabled(not oc['enabled'])
        await self.update_general_panel_markup()

        with contextlib.suppress(Exception):
            await c.message.edit_reply_markup(reply_markup=self.kb_openchat_quick_menu())

        await c.answer()

    async def cb_goc_bind_here(self, c: CallbackQuery):
        """Bind OpenChat to current chat"""
        if not self.is_admin(c.from_user):
            return await c.answer("❌ Недостаточно прав", show_alert=True)

        chat = c.message.chat

        if chat.type != ChatType.SUPERGROUP or not getattr(chat, 'is_forum', False):
            return await c.answer("❌ Это должна быть супергруппа с топиками", show_alert=True)

        self.set_openchat(chat.id, chat.username)
        await self.ensure_general_panel()

        ok, info = await self.openchat_check_permissions(chat.id)
        if not ok:
            await c.answer(info, show_alert=True)
        else:
            await c.answer("✅ OpenChat привязан к этому чату")

        with contextlib.suppress(Exception):
            await c.message.edit_reply_markup(reply_markup=self.kb_openchat_quick_menu())

    async def cb_goc_unbind(self, c: CallbackQuery):
        """Unbind OpenChat"""
        if not self.is_admin(c.from_user):
            return await c.answer("❌ Недостаточно прав", show_alert=True)

        self.clear_openchat()
        self.set_openchat_enabled(False)
        await self.update_general_panel_markup()

        with contextlib.suppress(Exception):
            await c.message.edit_reply_markup(reply_markup=self.kb_openchat_quick_menu())

        await c.answer("✅ OpenChat отключен")

# The rest of the callback implementations would follow similar patterns...


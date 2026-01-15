from telethon.tl.types import Message
from .. import loader, utils
import re
import time
import asyncio
from datetime import datetime


@loader.tds
class Digging(loader.Module):
    """Анти-копка и анти-кейсы с эскалацией наказаний, логами и лог-чатом"""

    strings = {"name": "Digging"}

    def __init__(self):
        self.resources = [
            "золото", "алмазы", "аметисты", "аквамарин",
            "изумруды", "материю", "плазму",
            "никель", "титан", "кобальт", "эктоплазму"
        ]

        self.case_regex = re.compile(
            r"^открыть кейс\s+(?:1|2|3|4|5)(?:\s+\d+)?",
            re.IGNORECASE
        )

        # минуты, None = бан
        self.punishments = [2, 30, 60, 120, 240, None]

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self.enabled_chats = set(db.get("Digging", "enabled_chats", []))
        self.violations = db.get("Digging", "violations", {})
        self.logs = db.get("Digging", "logs", {"warn": [], "mute": [], "ban": []})
        self.log_chat = db.get("Digging", "log_chat", None)

    def _save(self):
        self.db.set("Digging", "enabled_chats", list(self.enabled_chats))
        self.db.set("Digging", "violations", self.violations)
        self.db.set("Digging", "logs", self.logs)
        self.db.set("Digging", "log_chat", self.log_chat)

    @loader.command()
    async def digging(self, message: Message):
        """Включить или выключить Digging в текущем чате"""
        cid = message.chat_id
        if cid in self.enabled_chats:
            self.enabled_chats.remove(cid)
            await utils.answer(message, "⛔️ Digging **выключен** в этом чате.")
        else:
            self.enabled_chats.add(cid)
            await utils.answer(message, "✅ Digging **включён** в этом чате.")
        self._save()

    @loader.command()
    async def setlogcop(self, message: Message):
        """Установить чат для логов наказаний (.setlogcop <chat_id>)"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "❗ Укажи chat_id лог-чата")

        self.log_chat = int(args)
        self._save()
        await utils.answer(message, "✅ Лог-чат успешно установлен.")

    @loader.command()
    async def unsetlogcop(self, message: Message):
        """Отключить чат логов наказаний"""
        self.log_chat = None
        self._save()
        await utils.answer(message, "♻️ Лог-чат отключён.")

    async def watcher(self, message: Message):
        if not message.chat_id or message.chat_id not in self.enabled_chats:
            return
        if not message.raw_text or message.out:
            return

        text = message.raw_text.lower().strip()
        if self._starts_with_dig(text) or self.case_regex.match(text):
            await self._punish(message)

    def _starts_with_dig(self, text: str) -> bool:
        return any(text.startswith(f"копать {r}") for r in self.resources)

    async def _punish(self, message: Message):
        chat_id = str(message.chat_id)
        user_id = str(message.sender_id)
        key = f"{chat_id}:{user_id}"
        now = time.time()

        count, first_time = self.violations.get(key, (0, now))
        count += 1
        self.violations[key] = (count, first_time)

        punishment = self.punishments[min(count - 1, len(self.punishments) - 1)]

        user = await message.get_sender()
        uname = f"@{user.username}" if user.username else user.first_name or str(user.id)

        if punishment is None:
            text = "/ban\n\n№18. Копать, создавать зелья и открывать кейсы — в ЛС бота."
            log_type = "ban"
            duration = "перманент"
        else:
            text = f"/mute {punishment} минут\n\n№18. Используйте ЛС бота."
            log_type = "warn" if punishment == 2 else "mute"
            duration = f"{punishment} минут"

        reply = await message.reply(text)

        link = (
            f"https://t.me/{reply.chat.username}/{reply.id}"
            if reply.chat.username
            else f"https://t.me/c/{str(reply.chat_id)[4:]}/{reply.id}"
        )

        self.logs[log_type].append({
            "user": uname,
            "duration": duration,
            "link": link,
            "time": int(now),
        })

        self._save()
        await self._send_log_chat(user, message.chat, log_type, duration, link, now)

        await asyncio.sleep(5)
        try:
            await message.delete()
        except Exception:
            pass

    async def _send_log_chat(self, user, chat, ltype, duration, link, ts):
        if not self.log_chat:
            return

        tmap = {"warn": "Предупреждение", "mute": "Мут", "ban": "Бан"}
        time_str = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

        text = (
            "🚨 **Нарушение Digging**\n\n"
            f"👤 Пользователь: {('@' + user.username) if user.username else user.first_name}\n"
            f"📌 Тип: {tmap[ltype]}\n"
            f"⏱ Длительность: {duration}\n"
            f"🕒 Время: {time_str}\n"
            f"💬 Чат: {chat.title}\n"
            f"🔗 [Сообщение]({link})"
        )

        try:
            photo = await self.client.download_profile_photo(user, bytes)
            await self.client.send_file(
                self.log_chat,
                photo,
                caption=text,
                parse_mode="md",
            )
        except Exception:
            await self.client.send_message(self.log_chat, text, parse_mode="md")

    @loader.command()
    async def logcop(self, message: Message):
        """Показать логи предупреждений, мутов и банов"""
        await utils.answer(
            message,
            "📊 **Логи наказаний**",
            reply_markup=[
                [
                    {"text": "📄 Предупреждения", "callback": self._show_warn},
                    {"text": "🔇 Муты", "callback": self._show_mute},
                ],
                [
                    {"text": "⛔️ Баны", "callback": self._show_ban},
                ],
            ],
        )

    async def _show(self, call, t, title):
        logs = self.logs[t]
        if not logs:
            return await call.answer("Логи пусты", show_alert=True)

        text = f"**{title}**\n\n"
        for i, l in enumerate(logs, 1):
            text += f"{i}. {l['user']} | {l['duration']} | [ссылка]({l['link']})\n"

        await call.edit(text, disable_web_page_preview=True)

    async def _show_warn(self, call):
        await self._show(call, "warn", "📄 Логи предупреждений")

    async def _show_mute(self, call):
        await self._show(call, "mute", "🔇 Логи мутов")

    async def _show_ban(self, call):
        await self._show(call, "ban", "⛔️ Логи банов")

    @loader.command()
    async def uplogcop(self, message: Message):
        """Очистить все логи наказаний (предупреждения, муты, баны)"""
        self.logs = {"warn": [], "mute": [], "ban": []}
        self._save()
        await utils.answer(message, "♻️ Все логи наказаний очищены.")
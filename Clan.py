# -*- coding: utf-8 -*-

__version__ = (1, 1, 1)

# ======================================================================
# Название модуля: ClanAdvertMod
# Версия: 1.0.0
# Описание: Автоматическая рассылка клановой афиши в чатах
# Автор: Heroku_Guard
# ======================================================================

import asyncio
import logging
import inspect
import aiohttp

from datetime import datetime, timedelta, timezone
from telethon.tl.types import Message
from .. import loader, utils

logger = logging.getLogger(__name__)

UPDATE_URL = "https://raw.githubusercontent.com/vbhhhgfddhy/Clan-module/main/ClanAdvertMod.py"

MSK = timezone(timedelta(hours=3))


@loader.tds
class ClanAdvertMod(loader.Module):
    """Авторассылка афиши + автообновление"""

    strings = {
        "name": "Clan",
        "enabled": "✅ <b>Модуль Clan включён</b>\n\nЧат 1: {}\nЧат 2: {}",
        "disabled": "⛔ <b>Модуль Clan выключен</b>",
        "log_title": "📊 <b>Лог афиши (последние 20)</b>\n\n",
        "log_empty": "Лог пуст.",
        "logs_cleared": "🗑 <b>Логи очищены</b>",
        "all_cleared": "🗑 <b>Все данные сброшены</b>",
    }

    config = loader.ModuleConfig(
        loader.ConfigValue(
            "interval1", 15, "КД для чата 1 (мин)",
            validator=loader.validators.Integer(minimum=1)
        ),
        loader.ConfigValue(
            "interval2", 15, "КД для чата 2 (мин)",
            validator=loader.validators.Integer(minimum=1)
        ),
        loader.ConfigValue("chat1", "None", "Чат 1"),
        loader.ConfigValue("chat2", "None", "Чат 2"),
        loader.ConfigValue("text1", "идёт набор в клан", "Текст 1"),
        loader.ConfigValue("text2", "идёт набор в клан", "Текст 2"),
        loader.ConfigValue("photo1", "None", "Фото 1"),
        loader.ConfigValue("photo2", "None", "Фото 2"),
    )

    def __init__(self):
        self.enabled = False
        self.tasks = {}

    # ===================== INIT =====================

    async def client_ready(self, client, db):
        self.client = client
        self._db = db

        await self.check_update(silent=True)

        self.enabled = self._db.get(self.name, "enabled", False)
        if self.enabled:
            self.restore_tasks()

    # ===================== AUTO UPDATE =====================

    async def check_update(self, silent=False):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(UPDATE_URL) as r:
                    if r.status != 200:
                        return
                    text = await r.text()

            if "__version__" not in text:
                return

            remote_version = eval(
                text.split("__version__ =")[1].split("\n")[0].strip()
            )

            if remote_version <= __version__:
                if not silent:
                    await self.client.send_message("me", "✅ Модуль уже актуален")
                return

            path = inspect.getfile(self.__class__)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

            await self.client.send_message(
                "me",
                f"🔄 <b>Модуль Clan обновлён</b>\n"
                f"{__version__} → {remote_version}\n\n"
                f"♻️ Выполни <code>.restart</code>"
            )

        except Exception:
            logger.exception("Ошибка автообновления")

    async def updateclancmd(self, message: Message):
        """Обновить модуль"""
        await utils.answer(message, "🔎 Проверяю обновления...")
        await self.check_update()

    # ===================== CORE =====================

    def restore_tasks(self):
        for idx in (1, 2):
            self.tasks[idx] = asyncio.create_task(self.send_loop(idx))

    async def send_ad(self, chat, text, photo):
        if chat == "None":
            return
        if photo != "None":
            await self.client.send_message(chat, text, file=photo)
        else:
            await self.client.send_message(chat, text)

    def add_log(self, idx, interval):
        key = f"logs_{idx}"
        logs = self._db.get(self.name, key, [])

        now = datetime.now(MSK).strftime("%d.%m.%Y %H:%M:%S")
        logs.insert(0, f"{now} | КД {interval} мин")

        self._db.set(self.name, key, logs[:20])

    async def send_loop(self, idx):
        while self.enabled:
            try:
                await self.send_ad(
                    self.config[f"chat{idx}"],
                    self.config[f"text{idx}"],
                    self.config[f"photo{idx}"],
                )
                self.add_log(idx, self.config[f"interval{idx}"])
            except Exception:
                logger.exception("Ошибка рассылки")

            await asyncio.sleep(self.config[f"interval{idx}"] * 60)

    # ===================== COMMANDS =====================

    async def clancmd(self, message: Message):
        """Вкл / выкл модуль"""
        if not self.enabled:
            self.enabled = True
            self._db.set(self.name, "enabled", True)

            for idx in (1, 2):
                self.tasks[idx] = asyncio.create_task(self.send_loop(idx))

            await utils.answer(
                message,
                self.strings["enabled"].format(
                    self.config["chat1"],
                    self.config["chat2"],
                ),
            )
        else:
            self.enabled = False
            self._db.set(self.name, "enabled", False)

            for task in self.tasks.values():
                task.cancel()
            self.tasks.clear()

            await utils.answer(message, self.strings["disabled"])

    async def logclancmd(self, message: Message):
        """Показать лог"""
        logs1 = self._db.get(self.name, "logs_1", [])
        logs2 = self._db.get(self.name, "logs_2", [])

        if not logs1 and not logs2:
            await utils.answer(message, self.strings["log_empty"])
            return

        text = self.strings["log_title"]

        if logs1:
            text += "<b>Чат 1:</b>\n" + "\n".join(logs1) + "\n\n"
        if logs2:
            text += "<b>Чат 2:</b>\n" + "\n".join(logs2)

        await utils.answer(message, text)

    async def uplogscmd(self, message: Message):
        """Очистить лог"""
        self._db.set(self.name, "logs_1", [])
        self._db.set(self.name, "logs_2", [])
        await utils.answer(message, self.strings["logs_cleared"])

    async def nulliscmd(self, message: Message):
        """Полный сброс модуля"""
        self.enabled = False
        self._db.set(self.name, "enabled", False)

        self._db.set(self.name, "logs_1", [])
        self._db.set(self.name, "logs_2", [])
        self._db.set(self.name, "next_run_1", None)
        self._db.set(self.name, "next_run_2", None)

        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()

        await utils.answer(message, self.strings["all_cleared"])

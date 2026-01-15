__version__ = (1, 1, 3)

# ======================================================================
# Название модуля: [DailyReplyMod]
# Версия: [1.1.3]
# Описание: [Модуль для рассылки клановой афиши в бфг чатах.]
# Автор: Heroku_Guard
# Канал и контакты: @heroku_Guard, https://t.me/heroku_Guard
# Дата создания: [12.01.2026]
# ======================================================================
#
# Лицензия: MIT License
# Copyright (c) 2025 Heroku_Guard
# ======================================================================

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telethon.tl.types import Message
from .. import loader, utils

logger = logging.getLogger(__name__)

MSK = timezone(timedelta(hours=3))


@loader.tds
class ClanAdvertMod(loader.Module):
    """
    Автоматическая рассылка афиши в двух чатах
    (разные интервалы, автозапуск, лог, очистка логов)
    """

    strings = {
        "name": "Clan",
        "enabled": (
            "✅ <b>Модуль Clan включён</b>\n\n"
            "Чат 1: {}\n"
            "Чат 2: {}"
        ),
        "disabled": "⛔ <b>Модуль Clan выключен</b>",
        "log_title": "📊 <b>Лог афиши (последние 20)</b>\n\n",
        "log_empty": "Лог пуст.",
        "logs_cleared": "🗑 <b>Логи афиши очищены</b>",
        "all_cleared": "🗑 <b>Все данные сброшены (включая логи и таймеры)</b>"
    }

    config = loader.ModuleConfig(
        loader.ConfigValue(
            "interval1",
            15,
            "КД для 1 чата (в минутах)",
            validator=loader.validators.Integer(minimum=1),
        ),
        loader.ConfigValue(
            "interval2",
            15, 
            "КД для 2 чата (в минутах)",
            validator=loader.validators.Integer(minimum=1),
        ),
        loader.ConfigValue("chat1", "None", "Чат №1"),
        loader.ConfigValue("chat2", "None", "Чат №2"),
        loader.ConfigValue("text1", "идёт набор в клан", "Текст для чата №1"),
        loader.ConfigValue("text2", "идёт наоборот в клан", "Текст для чата №2"),
        loader.ConfigValue("photo1", "None", "Фото для чата №1"),
        loader.ConfigValue("photo2", "None", "Фото для чата №2"),
    )

    def __init__(self):
        self.enabled = False
        self.tasks = {}

    async def client_ready(self, client, db):
        self.client = client
        self._db = db

        self.enabled = self._db.get(self.name, "enabled", False)

        if self.enabled:
            self.restore_tasks()

    def restore_tasks(self):
        now = datetime.now(timezone.utc)

        for idx in (1, 2):
            # Отменяем старую задачу, если она есть и не завершена
            if idx in self.tasks and not self.tasks[idx].done():
                self.tasks[idx].cancel()

            next_run = self._db.get(self.name, f"next_run_{idx}")
            delay = 0
            if next_run:
                delay = max(
                    0,
                    (datetime.fromisoformat(next_run) - now).total_seconds(),
                )

            # Создаём новую задачу для отправки афиши
            self.tasks[idx] = asyncio.create_task(self.send_loop(idx, delay))

    async def send_ad(self, chat, text, photo):
        if photo != "None":
            await self.client.send_message(chat, text, file=photo)
        else:
            await self.client.send_message(chat, text)

    def add_log(self, idx):
        key = f"logs_{idx}"
        logs = self._db.get(self.name, key, [])

        now = datetime.now(MSK).strftime("%d.%m.%Y %H:%M:%S")
        logs.insert(
            0,
            f"Афиша отправлена в {now}"
        )

        self._db.set(self.name, key, logs[:20])

    async def send_loop(self, idx: int, delay: float = 0):
        await asyncio.sleep(delay)

        while self.enabled:
            try:
                chat = self.config[f"chat{idx}"]
                if chat != "None":
                    await self.send_ad(
                        chat,
                        self.config[f"text{idx}"],
                        self.config[f"photo{idx}"],
                    )
                    self.add_log(idx)

            except Exception:
                logger.exception(f"ClanAdvert error (chat {idx})")

            # Сохраняем время следующей отправки
            next_run = datetime.now(timezone.utc) + timedelta(
                minutes=self.config[f"interval{idx}"]
            )
            self._db.set(self.name, f"next_run_{idx}", next_run.isoformat())

            await asyncio.sleep(self.config[f"interval{idx}"] * 60)

    async def clancmd(self, message: Message):
        """
        Включить / выключить модуль
        """
        if not self.enabled:
            self.enabled = True
            self._db.set(self.name, "enabled", True)
            self.restore_tasks()

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
        """
        Показать лог афиши в новом дизайне с эмодзи-счётчиком
        """
        msg = await utils.answer(message, "⏳ Загрузка лога...")

        logs1 = self._db.get(self.name, "logs_1", [])
        logs2 = self._db.get(self.name, "logs_2", [])

        if not logs1 and not logs2:
            await msg.edit(self.strings["log_empty"])
            return

        text = self.strings["log_title"]

        # Функция для преобразования номера в эмодзи
        def number_emoji(n):
            numbers = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
            if 1 <= n <= 10:
                return numbers[n]
            return f"{n}⃣"

        if logs1:
            text += "<b>1 чат:</b>\n"
            for i, log in enumerate(logs1, 1):
                text += f"{number_emoji(i)}. {log}\n"
            text += "\n"

        if logs2:
            text += "<b>2 чат:</b>\n"
            for i, log in enumerate(logs2, 1):
                text += f"{number_emoji(i)}. {log}\n"

        await msg.edit(text)

    async def uplogscmd(self, message: Message):
        """
        Очистить лог афиши
        """
        self._db.set(self.name, "logs_1", [])
        self._db.set(self.name, "logs_2", [])

        await utils.answer(message, self.strings["logs_cleared"])

    async def nulliscmd(self, message: Message):
        """
        Сбросить все данные (включая логи и отправки)
        """
        self._db.set(self.name, "logs_1", [])
        self._db.set(self.name, "logs_2", [])
        self._db.set(self.name, "enabled", False)
        self._db.set(self.name, "next_run_1", None)
        self._db.set(self.name, "next_run_2", None)

        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()

        await utils.answer(message, self.strings["all_cleared"])

    async def claninfocmd(self, message: Message):
        """
        Показать полную информацию о модуле Clan
        """
        info_lines = [
            "<emoji document_id=5116275208906343429>‼️</emoji>",
            "<b><u>ОБЕЗАТЕЛЬНО ЧИТАЙТЕ ПОЛНОСТЬЮ</u></b>",
            "<emoji document_id=5116275208906343429>‼️</emoji>",
            "",
            "<emoji document_id=5118454879039259395>❤️</emoji> Сдесь содержится полная информация этого модуля <emoji document_id=5118454879039259395>❤️</emoji>",
            "",
            "<blockquote><emoji document_id=5141109049114232089>1️⃣</emoji> "
            "Если вы надумаете выгружать модуль сначала не забудьте его выключить, иначе реклама будет продолжать рассылаться.</blockquote>",
            "",
            "<blockquote><emoji document_id=5140871649091912628>2️⃣</emoji> "
            "Если у вас длинная афиша клана текст вставлять таким способом:\n"
            "<code>.fcfg Clan text1</code> &lt;пишите текст с афиши&gt;\n"
            "<code>.fcfg Clan text2</code> &lt;пишите текст с афишей&gt;\n\n"
            "Если же текст короткий то можно просто:\n"
            "<code>.cfg Clan text1</code>\n"
            "<code>.cfg Clan text2</code></blockquote>",
            "",
            "<blockquote><emoji document_id=5141399818400170896>3️⃣</emoji> "
            "Как поставить текст афиши (обязательно кодом если присутствует премиум эмодзи).\n"
            "Отправляете в любой чат афиши и в ответ на сообщение пишите <code>.e r.text</code></blockquote>",
            "",
            "<blockquote expandable> <emoji document_id=5138822752123225428>4️⃣</emoji> Все обозначения конфига.\n\n"
            "1. Interval1 - Устанавливает КД для 1 чата. (КД - промежуток времени между рассылками)\n"
            "2. Interval2 - Устанавливает КД для 2 чата.\n"
            "3. Chat1 - Установка первого чата (ID или ссылка)\n"
            "4. Chat2 - Установка второго чата (ID или ссылка)\n"
            "5. text1 - Текст рекламы для первого чата\n"
            "6. text2 - Текст рекламы для второго чата\n"
            "7. photo1 - Фото для первого чата (<a href=\"https://x0.at/\">ссылка на фото</a>)\n"
            "8. photo2 - Фото для второго чата (<a href=\"https://x0.at/\">ссылка на фото</a>)</blockquote>",
            "",
            "<emoji document_id=5116275208906343429>‼️</emoji> Прочтите все внимательно чтобы не было лишних вопросов <emoji document_id=5116275208906343429>‼️</emoji>"
        ]

        info_text = "\n".join(info_lines)
        await utils.answer(message, info_text)

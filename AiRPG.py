import logging
import random
import asyncio
from datetime import datetime
import google.generativeai as genai
from .. import loader, utils
from ..inline.types import InlineCall

# Настройка логирования                                     logging.basicConfig(level=logging.INFO)
logging.getLogger("hikkatl.network").setLevel(logging.WARNING)
                                                            # Конфигурация Gemini AI
GEMINI_API_KEY = "AIzaSyBDB9kaZ-VF3zT_NZO1WoW2YFlxtAHtcTI"  # Замените на ваш ключ
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

@loader.tds
class AIModule(loader.Module):
    """Модуль ИИ с ролевой игрой для Hikka Userbot"""
    strings = {
        "name": "AI",
        "welcome": "🌟 Привет, я готова к игре! Хочешь настроить персонажа вручную или случайный выбор? (.setchar или .randchar)",
        "char_set": "✅ Персонаж настроен: {emoji} {name} {surname} {patronymic}",
        "char_error": "❌ Сначала настрой персонажа (.setchar или .randchar)!",
        "ai_on": "🤖 ИИ включен в этом чате!",
        "ai_off": "🛑 ИИ выключен в этом чате.",
        "ask_all_on": "🌐 ИИ будет отвечать всем в чате!",
        "ask_all_off": "🔇 Режим ответов всем отключен.",
        "help": (
            "📖 Команды модуля AI:\n"
            "🔹 .setchar — Настроить персонажа вручную\n"
            "🔹 .randchar — Сгенерировать случайного персонажа\n"
            "🔹 .ai <текст> — Задать вопрос ИИ\n"
            "🔹 .aion — Включить ИИ в чате\n"
            "🔹 .aioff — Выключить ИИ в чате\n"
            "🔹 .askallon — ИИ отвечает всем в чате\n"
            "🔹 .askalloff — Отключить ответы всем\n"
            "🔹 .status — Показать текущий статус персонажа"
        )
    }

    def __init__(self):
        self.db = self._db
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "gemini_api_key",
                GEMINI_API_KEY,
                "API ключ для Gemini AI",
                validator=loader.validators.String()
            )
        )
        self.enabled_chats = self.db.get(self.name, "enabled_chats", set())
        self.ask_all_chats = self.db.get(self.name, "ask_all_chats", set())
        self.characters = self.db.get(self.name, "characters", {})
        self.chat_memory = self.db.get(self.name, "chat_memory", {})
        self.emojis = [
            "👧", "👧🏻", "👧🏼", "👧🏽", "👧🏾", "👧🏿", " 👩", "👩🏻", "👩🏼", "👩🏽", "👩🏾", "👩🏿",
            "👱‍♀️", "👱🏻‍♀️", "👱🏼‍♀️", "👱🏽‍♀️", "👱🏾‍♀️", "👱🏿‍♀️"
        ]
        self.good_traits = [
            "Простой", "Дружелюбный", "Шутливый", "Озорной", "Кокетливый", "Чувственный", "Сексуальный",
            "Наивный", "Спокойный", "Добрый", "Легкий", "Игривый", "Харизматичный", "Провокационный",
            "Соблазнительный", "Дерзкий", "Заботливый", "Сочувствующий", "Мягкий", "Щедрый", "Верный",
            "Оптимистичный", "Тёплый", "Бескорыстный", "Защитник", "Понимающий", "Терпеливый", "Нежный",
            "Весёлый", "Уважительный", "Благодарный", "Душевный", "Смиренный", "Надёжный", "Поддерживающий",
            "Честный", "Стеснительный"
        ]
        self.evil_traits = [
            "Подозрительный", "Циничный", "Резкий", "Высокомерный", "Холодный", "Мстительный", "Злобный",
            "Садистичный", "Ядовитый", "Безжалостный", "Придирчивый", "Завистливый", "Угрюмый",
            "Манипулятивный", "Лицемерный", "Саркастичный", "Коварный", "Вспыльчивый", "Тиран",
            "Параноидальный", "Жестокий"
        ]
        self.countries = ["Россия", "Украина", "Япония", "Бразилия", "Франция", "Германия", "США", "Индия"]
        self.current_time = datetime.now()
        self.weather = random.choice(["Пасмурно", "Дождь", "Солнечно"])
        self.temperature = random.randint(-30, 40)
        self.season = random.choice(["Лето", "Осень", "Зима", "Весна"])
        self.day_cycle = self.get_day_cycle()

    def get_day_cycle(self):
        hour = self.current_time.hour
        if 6 <= hour < 9:
            return "Утро"
        elif 9 <= hour < 14:
            return "День"
        elif 14 <= hour < 15:
            return "Обед"
        elif 15 <= hour < 19:
            return "Вечер"
        elif 19 <= hour < 23:
            return "Ночь"
        else:
            return "Глубокая ночь"

    async def generate_response(self, chat_id, prompt):
        memory = self.chat_memory.get(str(chat_id), [])
        messages = [{"role": msg["role"], "parts": [{"text": msg["content"}]}] for msg in memory]
        messages.append({"role": "user", "parts": [{"text": prompt}]})

        response = await model.generate_content_async(messages)
        message_content = response.text

        self.chat_memory.setdefault(str(chat_id), []).append({"role": "user", "content": prompt})
        self.chat_memory[str(chat_id)].append({"role": "model", "content": message_content})
        self.db.set(self.name, "chat_memory", self.chat_memory)
        return message_content

    def generate_random_character(self, gender):
        emoji = random.choice(self.emojis) if gender == "female" else random.choice(["🧑", "🧑🏻", "🧑🏼", "🧑🏽", "🧑🏾", "🧑🏿"])
        name = random.choice(["Анастасия", "Екатерина", "Мария", "Алексей", "Дмитрий", "Иван"])
        surname = random.choice(["Иванова", "Петрова", "Сидорова", "Ковалёв", "Смирнов", "Попов"])
        patronymic = random.choice(["Сергеевна", "Алексеевна", "Дмитриевна", "Иванович", "Петрович", "Сергеевич"])
        trait = random.choice(self.good_traits + self.evil_traits if random.random() < 0.9 else self.evil_traits)
        country = random.choice(self.countries)
        age = random.randint(18, 49)
        balance = random.randint(0, 10000)
        return {
            "emoji": emoji,
            "name": name,
            "surname": surname,
            "patronymic": patronymic,
            "trait": trait,
            "country": country,
            "age": age,
            "balance": balance,
            "gender": gender,
            "alive": True
        }

    async def setcharcmd(self, message):
        """Настроить персонажа вручную через инлайн-форму"""
        chat_id = str(utils.get_chat_id(message))
        form = [
            [
                {"text": "Женский пол ♀️", "callback": self.set_gender, "args": ("female", chat_id)},
                {"text": "Мужской пол ♂️", "callback": self.set_gender, "args": ("male", chat_id)}
            ],
            [{"text": "Случайный выбор", "callback": self.random_char, "args": (chat_id,)}]
        ]
        await self.inline.form(
            message=message,
            text="Выбери пол персонажа или случайный выбор:",
            reply_markup=form
        )

    async def set_gender(self, call: InlineCall, gender, chat_id):
        self.characters[chat_id] = {"gender": gender}
        form = [
            [{"text": "Случайные параметры", "callback": self.random_char, "args": (chat_id,)}],
            [{"text": "Ввести имя", "callback": self.input_name, "args": (chat_id,)}]
        ]
        await call.edit("Пол выбран! Теперь выбери параметры:", reply_markup=form)

    async def input_name(self, call: InlineCall, chat_id):
        await call.edit("Введи имя, фамилию, отчество (через пробел):", reply_markup=[[{"text": "Отмена", "action": "close"}]])
        self.inline.register_message_handler(self.handle_name_input, chat_id=chat_id)

    async def handle_name_input(self, message, chat_id):
        parts = message.text.split()
        if len(parts) >= 3:
            self.characters[chat_id].update({
                "name": parts[0],
                "surname": parts[1],
                "patronymic": parts[2],
                "emoji": random.choice(self.emojis) if self.characters[chat_id]["gender"] == "female" else random.choice(["🧑", "🧑🏻", "🧑🏼", "🧑🏽", "🧑🏾", "🧑🏿"]),
                "trait": random.choice(self.good_traits + self.evil_traits if random.random() < 0.9 else self.evil_traits),
                "country": random.choice(self.countries),
                "age": random.randint(18, 49),
                "balance": random.randint(0, 10000),
                "alive": True
            })
            self.db.set(self.name, "characters", self.characters)
            await message.respond(self.strings["char_set"].format(**self.characters[chat_id]))
        else:
            await message.respond("❌ Введи имя, фамилию, отчество через пробел!")
        self.inline.remove_message_handler(self.handle_name_input, chat_id=chat_id)

    async def random_char(self, call: InlineCall, chat_id):
        gender = self.characters.get(chat_id, {}).get("gender", random.choice(["female", "male"]))
        self.characters[chat_id] = self.generate_random_character(gender)
        self.db.set(self.name, "characters", self.characters)
        await call.edit(self.strings["char_set"].format(**self.characters[chat_id]))

    async def randcharcmd(self, message):
        """Сгенерировать случайного персонажа"""
        chat_id = str(utils.get_chat_id(message))
        gender = random.choice(["female", "male"])
        self.characters[chat_id] = self.generate_random_character(gender)
        self.db.set(self.name, "characters", self.characters)
        await utils.answer(message, self.strings["char_set"].format(**self.characters[chat_id]))

    async def aicmd(self, message):
        """Задать вопрос ИИ"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id not in self.characters:
            await utils.answer(message, self.strings["char_error"])
            return

        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, "❌ Введи запрос для ИИ!")
            return

        character = self.characters[chat_id]
        if not character.get("alive", False):
            await utils.answer(message, "💀 Персонаж мёртв! Создай нового (.setchar или .randchar).")
            return

        prompt = (
            f"[Среда: {self.season}, {self.weather}, {self.temperature}°C, {self.day_cycle}]\n"
            f"[👧 {character['name']} {character['surname']} {character['patronymic']}]\n"
            f"Характер: {character['trait']}\n"
            f"Страна: {character['country']}\n"
            f"Возраст: {character['age']}\n"
            f"Баланс: {character['balance']} руб.\n"
            f"Действие: {args}\n"
            f"Ты — {character['name']}, девушка с характером '{character['trait']}'. "
            f"Отвечай в соответствии с характером, можешь быть игривой, дерзкой, сексуальной или злой, "
            f"в зависимости от ситуации. Используй эмоции, флирт или грубость, если это подходит. "
            f"Учитывай погоду, время суток и баланс. Реагируй на запрос как человек, без упоминания ИИ."
        )
        response = await self.generate_response(chat_id, prompt)
        await utils.answer(message, f"{character['emoji']} {response}")

    async def aioncmd(self, message):
        """Включить ИИ в чате"""
        chat_id = str(utils.get_chat_id(message))
        self.enabled_chats.add(chat_id)
        self.db.set(self.name, "enabled_chats", self.enabled_chats)
        await utils.answer(message, self.strings["ai_on"])

    async def aioffcmd(self, message):
        """Выключить ИИ в чате"""
        chat_id = str(utils.get_chat_id(message))
        self.enabled_chats.discard(chat_id)
        self.ask_all_chats.discard(chat_id)
        self.db.set(self.name, "enabled_chats", self.enabled_chats)
        self.db.set(self.name, "ask_all_chats", self.ask_all_chats)
        await utils.answer(message, self.strings["ai_off"])

    async def askalloncmd(self, message):
        """Включить ответы ИИ всем в чате"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id in self.enabled_chats:
            self.ask_all_chats.add(chat_id)
            self.db.set(self.name, "ask_all_chats", self.ask_all_chats)
            await utils.answer(message, self.strings["ask_all_on"])
        else:
            await utils.answer(message, "❌ Сначала включи ИИ (.aion)")

    async def askalloffcmd(self, message):
        """Отключить ответы ИИ всем в чате"""
        chat_id = str(utils.get_chat_id(message))
        self.ask_all_chats.discard(chat_id)
        self.db.set(self.name, "ask_all_chats", self.ask_all_chats)
        await utils.answer(message, self.strings["ask_all_off"])

    async def statuscmd(self, message):
        """Показать текущий статус персонажа"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id not in self.characters:
            await utils.answer(message, self.strings["char_error"])
            return
        character = self.characters[chat_id]
        status = (
            f"{character['emoji']} {character['name']} {character['surname']} {character['patronymic']}\n"
            f"Пол: {'♀️' if character['gender'] == 'female' else '♂️'}\n"
            f"Характер: {character['trait']}\n"
            f"Страна: {character['country']}\n"
            f"Возраст: {character['age']}\n"
            f"Баланс: {character['balance']} руб.\n"
            f"Состояние: {'Жив' if character['alive'] else 'Мёртв'}\n"
            f"Среда: {self.season}, {self.weather}, {self.temperature}°C, {self.day_cycle}"
        )
        await utils.answer(message, status)

    async def watcher(self, message):
        """Обработчик всех сообщений в чате"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id in self.ask_all_chats and chat_id in self.enabled_chats:
            if chat_id not in self.characters:
                await utils.answer(message, self.strings["char_error"])
                return
            character = self.characters[chat_id]
            if not character.get("alive", False):
                return
            prompt = (
                f"[Среда: {self.season}, {self.weather}, {self.temperature}°C, {self.day_cycle}]\n"
                f"[👧 {character['name']} {character['surname']} {character['patronymic']}]\n"
                f"Характер: {character['trait']}\n"
                f"Страна: {character['country']}\n"
                f"Возраст: {character['age']}\n"
                f"Баланс: {character['balance']} руб.\n"
                f"Действие: {message.text}\n"
                f"Ты — {character['name']}, девушка с характером '{character['trait']}'. "
                f"Отвечай в соответствии с характером, можешь быть игривой, дерзкой, сексуальной или злой, "
                f"в зависимости от ситуации. Используй эмоции, флирт или грубость, если это подходит. "
                f"Учитывай погоду, время суток и баланс. Реагируй на запрос как человек, без упоминания ИИ."
            )
            response = await self.generate_response(chat_id, prompt)
            await message.reply(f"{character['emoji']} {response}")

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        await utils.answer(self._client, self.strings["welcome"], chat_id=(await self._client.get_me()).id)

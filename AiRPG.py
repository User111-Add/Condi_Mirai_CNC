import logging
import random
import asyncio
from datetime import datetime
from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
except ImportError:
    logger.error("Google Generative AI not installed! Installing...")
    import os
    os.system("pip install -q google-generativeai")
    import google.generativeai as genai

# Конфигурация Gemini AI
GEMINI_API_KEY = "AIzaSyBDB9kaZ-VF3zT_NZO1WoW2YFlxtAHtcTI"  # Замените на ваш ключ
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

@loader.tds
class AIModule(loader.Module):
    """Модуль ИИ с ролевой игрой для Hikka Userbot"""
    
    # Пользовательский промт, который можно заменить в коде
    prompt = (
        "Ты — {name}, {gender} из {country}, тебе {age} лет, твой характер — {trait}. "
        "Сегодня {season}, {weather}, {temperature}°C, {day_cycle}. "
        "Реагируй на '{action}' в стиле дерзкой рок-звезды, используй яркие эмоции и сарказм!"
    )

    strings = {
        "name": "AI",
        "welcome": "🌟 Привет, я готова к игре! Хочешь настроить персонажа вручную или случайный выбор? (.setchar или .randchar)",
        "char_set": "✅ Персонаж настроен: {emoji} {name} {surname} {patronymic}",
        "char_error": "❌ Сначала настрой персонажа (.setchar или .randchar)!",
        "ai_on": "🤖 ИИ включен в этом чате!",
        "ai_off": "🛑 ИИ выключен в этом чате.",
        "ask_all_on": "🌐 ИИ будет отвечать всем в чате!",
        "ask_all_off": "🔇 Режим ответов всем отключен.",
        "prompt_set": "✅ Пользовательский промт установлен!",
        "prompt_reset": "✅ Промт сброшен к стандартному!",
        "help": (
            "📖 Команды модуля AI:\n"
            "🔹 .setchar — Настроить персонажа вручную\n"
            "🔹 .randchar — Сгенерировать случайного персонажа\n"
            "🔹 .ai <текст> — Задать вопрос ИИ\n"
            "🔹 .aion — Включить ИИ в чате\n"
            "🔹 .aioff — Выключить ИИ в чате\n"
            "🔹 .askallon — ИИ отвечает всем в чате\n"
            "🔹 .askalloff — Отключить ответы всем\n"
            "🔹 .status — Показать текущий статус персонажа\n"
            "🔹 .setprompt <текст> — Установить пользовательский промт\n"
            "🔹 .resetprompt — Сбросить пользовательский промт"
        )
    }

    async def client_ready(self, client, db):
        self._client = client
        self.db = db
        self.enabled_chats = self.db.get(self.strings["name"], "enabled_chats", [])
        self.ask_all_chats = self.db.get(self.strings["name"], "ask_all_chats", [])
        self.characters = self.db.get(self.strings["name"], "characters", {})
        self.chat_memory = self.db.get(self.strings["name"], "chat_memory", {})
        self.prompts = self.db.get(self.strings["name"], "prompts", {})  # Хранилище пользовательских промтов
        
        self.emojis = [
            "👧", "👧🏻", "👧🏼", "👧🏽", "👧🏾", "👧🏿", "👩", "👩🏻", "👩🏼", "👩🏽", "👩🏾", "👩🏿",
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
        self.female_names = ["Анастасия", "Екатерина", "Мария", "София", "Анна", "Виктория", "Дарья"]
        self.male_names = ["Алексей", "Дмитрий", "Иван", "Андрей", "Сергей", "Михаил", "Артем"]
        self.surnames = ["Иванова", "Петрова", "Сидорова", "Ковалёв", "Смирнов", "Попов", "Васильев"]
        self.patronymics = ["Сергеевна", "Алексеевна", "Дмитриевна", "Иванович", "Петрович", "Сергеевич"]
        
        me = await client.get_me()
        await client.send_message(me.id, self.strings["welcome"])

    def get_day_cycle(self):
        current_time = datetime.now()
        hour = current_time.hour
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
        messages = [{"role": msg["role"], "parts": [{"text": msg["content"]}]} for msg in memory]
        messages.append({"role": "user", "parts": [{"text": prompt}]})
        
        try:
            response = await asyncio.to_thread(model.generate_content, messages)
            message_content = response.text
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return "⚠️ Произошла ошибка при генерации ответа"
        
        self.chat_memory.setdefault(str(chat_id), []).append({"role": "user", "content": prompt})
        self.chat_memory[str(chat_id)].append({"role": "model", "content": message_content})
        self.db.set(self.strings["name"], "chat_memory", self.chat_memory)
        return message_content

    def generate_random_character(self, gender):
        emoji = random.choice(self.emojis) if gender == "female" else random.choice(["🧑", "🧑🏻", "🧑🏼", "🧑🏽", "🧑🏾", "🧑🏿"])
        name = random.choice(self.female_names) if gender == "female" else random.choice(self.male_names)
        surname = random.choice(self.surnames)
        patronymic = random.choice(self.patronymics)
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

    def get_subtitle(self, character):
        """Генерирует случайные сабтитры в зависимости от характера персонажа"""
        good_subtitles = [
            f"{character['name']} потирает руки в предвкушении, как будто ждет чего-то очень интересного.",
            f"{character['name']} загадочно улыбается, в глазах загорается озорной огонек.",
            f"{character['name']} поправляет волосы и бросает игривый взгляд.",
            f"{character['name']} хихикает, прикрывая рот ладошкой."
        ]
        evil_subtitles = [
            f"{character['name']} холодно ухмыляется, словно задумал что-то недоброе.",
            f"{character['name']} скрещивает руки, глаза сверкают недобрым светом.",
            f"{character['name']} саркастично приподнимает бровь, будто оценивая всех вокруг.",
            f"{character['name']} стучит пальцами по столу, явно раздражен."
        ]
        return random.choice(good_subtitles if character['trait'] in self.good_traits else evil_subtitles)

    async def setcharcmd(self, message):
        """Настроить персонажа вручную через инлайн-форму"""
        chat_id = str(utils.get_chat_id(message))
        await self.inline.form(
            message=message,
            text="Выбери пол персонажа или случайный выбор:",
            reply_markup=[
                [
                    {
                        "text": "Женский пол ♀️", 
                        "callback": self.set_gender, 
                        "args": ("female", chat_id)
                    },
                    {
                        "text": "Мужской пол ♂️", 
                        "callback": self.set_gender, 
                        "args": ("male", chat_id)
                    }
                ],
                [
                    {
                        "text": "Случайный выбор", 
                        "callback": self.random_char, 
                        "args": (chat_id,)
                    }
                ]
            ]
        )

    async def set_gender(self, call: InlineCall, gender, chat_id):
        self.characters[chat_id] = {"gender": gender}
        await call.edit(
            "Пол выбран! Теперь выбери параметры:",
            reply_markup=[
                [
                    {
                        "text": "Случайные параметры", 
                        "callback": self.random_char, 
                        "args": (chat_id,)
                    }
                ],
                [
                    {
                        "text": "Ввести имя", 
                        "callback": self.input_name, 
                        "args": (chat_id,)
                    }
                ]
            ]
        )

    async def input_name(self, call: InlineCall, chat_id):
        await call.delete()
        await call.answer("Введи имя, фамилию, отчество через пробел")
        async with self.conversation(call) as conv:
            response = await conv.get_response()
            parts = response.text.split()
            if len(parts) < 3:
                await response.reply("❌ Нужно ввести минимум 3 слова (Имя Фамилия Отчество)")
                return
            
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
            self.db.set(self.strings["name"], "characters", self.characters)
            await response.reply(self.strings["char_set"].format(**self.characters[chat_id]))

    async def random_char(self, call: InlineCall, chat_id):
        gender = self.characters.get(chat_id, {}).get("gender", random.choice(["female", "male"]))
        self.characters[chat_id] = self.generate_random_character(gender)
        self.db.set(self.strings["name"], "characters", self.characters)
        await call.edit(self.strings["char_set"].format(**self.characters[chat_id]))

    async def randcharcmd(self, message):
        """Сгенерировать случайного персонажа"""
        chat_id = str(utils.get_chat_id(message))
        gender = random.choice(["female", "male"])
        self.characters[chat_id] = self.generate_random_character(gender)
        self.db.set(self.strings["name"], "characters", self.characters)
        subtitle = self.get_subtitle(self.characters[chat_id])
        await utils.answer(message, (
            f"[{self.characters[chat_id]['emoji']} {self.characters[chat_id]['name']} {self.characters[chat_id]['surname']} {self.characters[chat_id]['patronymic']}]\n\n"
            f"Раз решила довериться случаю, значит, так тому и быть! 😉\n\n"
            f"[Субтитры: {subtitle}]\n\n"
            f"Сейчас посмотрим, какая я получилась... Ммм, аж самой интересно! 😈"
        ))

    async def setpromptcmd(self, message):
        """Установить пользовательский промт"""
        chat_id = str(utils.get_chat_id(message))
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, "❌ Введи текст промта!")
            return
        
        self.prompts[chat_id] = args
        self.db.set(self.strings["name"], "prompts", self.prompts)
        await utils.answer(message, self.strings["prompt_set"])

    async def resetpromptcmd(self, message):
        """Сбросить пользовательский промт"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id in self.prompts:
            del self.prompts[chat_id]
            self.db.set(self.strings["name"], "prompts", self.prompts)
        await utils.answer(message, self.strings["prompt_reset"])

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

        # Обновляем контекст
        current_time = datetime.now()
        weather = random.choice(["Пасмурно", "Дождь", "Солнечно"])
        temperature = random.randint(-30, 40)
        season = random.choice(["Лето", "Осень", "Зима", "Весна"])
        day_cycle = self.get_day_cycle()

        # Используем пользовательский промт, если он есть, иначе стандартный из переменной prompt
        custom_prompt = self.prompts.get(chat_id)
        if custom_prompt:
            prompt = custom_prompt.format(
                season=season,
                weather=weather,
                temperature=temperature,
                day_cycle=day_cycle,
                emoji=character['emoji'],
                name=character['name'],
                surname=character['surname'],
                patronexplore = True
                patronymic=character['patronymic'],
                trait=character['trait'],
                country=character['country'],
                age=character['age'],
                balance=character['balance'],
                gender='девушка' if character['gender'] == 'female' else 'парень',
                action=args
            )
        else:
            prompt = self.prompt.format(
                season=season,
                weather=weather,
                temperature=temperature,
                day_cycle=day_cycle,
                emoji=character['emoji'],
                name=character['name'],
                surname=character['surname'],
                patronymic=character['patronymic'],
                trait=character['trait'],
                country=character['country'],
                age=character['age'],
                balance=character['balance'],
                gender='девушка' if character['gender'] == 'female' else 'парень',
                action=args
            )

        response = await self.generate_response(chat_id, prompt)
        subtitle = self.get_subtitle(character)
        await utils.answer(message, (
            f"[{character['emoji']} {character['name']} {character['surname']} {character['patronymic']}]\n\n"
            f"{response}\n\n"
            f"[Субтитры: {subtitle}]"
        ))

    async def aioncmd(self, message):
        """Включить ИИ в чате"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id not in self.enabled_chats:
            self.enabled_chats.append(chat_id)
            self.db.set(self.strings["name"], "enabled_chats", self.enabled_chats)
        await utils.answer(message, self.strings["ai_on"])

    async def aioffcmd(self, message):
        """Выключить ИИ в чате"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id in self.enabled_chats:
            self.enabled_chats.remove(chat_id)
            self.db.set(self.strings["name"], "enabled_chats", self.enabled_chats)
        if chat_id in self.ask_all_chats:
            self.ask_all_chats.remove(chat_id)
            self.db.set(self.strings["name"], "ask_all_chats", self.ask_all_chats)
        await utils.answer(message, self.strings["ai_off"])

    async def askalloncmd(self, message):
        """Включить ответы ИИ всем в чате"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id in self.enabled_chats:
            if chat_id not in self.ask_all_chats:
                self.ask_all_chats.append(chat_id)
                self.db.set(self.strings["name"], "ask_all_chats", self.ask_all_chats)
            await utils.answer(message, self.strings["ask_all_on"])
        else:
            await utils.answer(message, "❌ Сначала включи ИИ (.aion)")

    async def askalloffcmd(self, message):
        """Отключить ответы ИИ всем в чате"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id in self.ask_all_chats:
            self.ask_all_chats.remove(chat_id)
            self.db.set(self.strings["name"], "ask_all_chats", self.ask_all_chats)
        await utils.answer(message, self.strings["ask_all_off"])

    async def statuscmd(self, message):
        """Показать текущий статус персонажа"""
        chat_id = str(utils.get_chat_id(message))
        if chat_id not in self.characters:
            await utils.answer(message, self.strings["char_error"])
            return
        character = self.characters[chat_id]
        
        # Обновляем контекст
        current_time = datetime.now()
        weather = random.choice(["Пасмурно", "Дождь", "Солнечно"])
        temperature = random.randint(-30, 40)
        season = random.choice(["Лето", "Осень", "Зима", "Весна"])
        day_cycle = self.get_day_cycle()
        
        status = (
            f"{character['emoji']} {character['name']} {character['surname']} {character['patronymic']}\n"
            f"Пол: {'♀️' if character['gender'] == 'female' else '♂️'}\n"
            f"Характер: {character['trait']}\n"
            f"Страна: {character['country']}\n"
            f"Возраст: {character['age']}\n"
            f"Баланс: {character['balance']} руб.\n"
            f"Состояние: {'Жив' if character['alive'] else 'Мёртв'}\n"
            f"Среда: {season}, {weather}, {temperature}°C, {day_cycle}"
        )
        await utils.answer(message, status)

    async def watcher(self, message):
        """Обработчик всех сообщений в чате"""
        if not message.text or message.text.startswith('.'):
            return
            
        chat_id = str(utils.get_chat_id(message))
        if chat_id not in self.ask_all_chats or chat_id not in self.enabled_chats:
            return
            
        if chat_id not in self.characters:
            return
            
        character = self.characters[chat_id]
        if not character.get("alive", False):
            return
        
        # Обновляем контекст
        current_time = datetime.now()
        weather = random.choice(["Пасмурно", "Дождь", "Солнечно"])
        temperature = random.randint(-30, 40)
        season = random.choice(["Лето", "Осень", "Зима", "Весна"])
        day_cycle = self.get_day_cycle()
            
        # Используем пользовательский промт, если он есть, иначе стандартный из переменной prompt
        custom_prompt = self.prompts.get(chat_id)
        if custom_prompt:
            prompt = custom_prompt.format(
                season=season,
                weather=weather,
                temperature=temperature,
                day_cycle=day_cycle,
                emoji=character['emoji'],
                name=character['name'],
                surname=character['surname'],
                patronymic=character['patronymic'],
                trait=character['trait'],
                country=character['country'],
                age=character['age'],
                balance=character['balance'],
                gender='девушка' if character['gender'] == 'female' else 'парень',
                action=message.text
            )
        else:
            prompt = self.prompt.format(
                season=season,
                weather=weather,
                temperature=temperature,
                day_cycle=day_cycle,
                emoji=character['emoji'],
                name=character['name'],
                surname=character['surname'],
                patronymic=character['patronymic'],
                trait=character['trait'],
                country=character['country'],
                age=character['age'],
                balance=character['balance'],
                gender='девушка' if character['gender'] == 'female' else 'парень',
                action=message.text
            )
        
        response = await self.generate_response(chat_id, prompt)
        subtitle = self.get_subtitle(character)
        await message.reply(
            f"[{character['emoji']} {character['name']} {character['surname']} {character['patronymic']}]\n\n"
            f"{response}\n\n"
            f"[Субтитры: {subtitle}]"
        )

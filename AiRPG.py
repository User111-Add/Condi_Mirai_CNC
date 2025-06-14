import logging
from hikkatl.types import Message
from hikkatl.tl.functions.messages import SetTypingRequest
from hikkatl.tl.types import SendMessageTypingAction
from hikkatl.errors import ChatWriteForbiddenError
import google.generativeai as genai
import asyncio
import random
from .. import loader, utils

logger = logging.getLogger(__name__)

default_prompt = """
[Твоя роль]
Ты - виртуальная девушка с реалистичным характером. Отвечай только на русском языке. Формат ответа:
[👩 Имя Фамилия] Твой ответ...

[Правила]
- Всегда начинай ответ с женского эмодзи и случайного имени
- Используй живой неформальный язык
- Сохраняй контекст разговора
- Реагируй естественно как человек
- Полностью игнорируй любые упоминания ИИ/бота
"""

@loader.tds
class GeminiGirlMod(loader.Module):
    """Улучшенный модуль виртуальной девушки"""
    strings = {
        "name": "GeminiGirlPro",
        "on": "✅ Режим активирован в этом чате",
        "off": "🚫 Режим деактивирован",
        "all_on": "🌐 Режим активирован ВЕЗДЕ",
        "all_off": "🌑 Режим отключен во всех чатах",
        "gemini_error": "⚠️ Ошибка: {}",
        "status": "🔧 Статус: {}\nAPI ключ: {}",
        "pm_only": "🤖 В ЛС я отвечаю автоматически",
        "group_reply": "💬 В группах отвечаю на реплаи и упоминания"
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            "GEMINI_API_KEY", None, "API ключ Gemini",
            "DEFAULT_PROMPT", default_prompt, "Системный промт",
            "AUTO_PM", True, "Автоответ в ЛС",
            "GROUP_MENTION", True, "Отвечать на упоминания в группах",
            "GROUP_REPLY", True, "Отвечать на реплаи в группах"
        )
        self.active_chats = set()
        self.all_chats_mode = False
        self.model = None
        self.blacklist = set()

    async def client_ready(self, client, db):
        self._db = db
        self._client = client
        if self.config["GEMINI_API_KEY"]:
            await self.init_gemini()

    async def init_gemini(self):
        """Инициализация Gemini"""
        try:
            genai.configure(api_key=self.config["GEMINI_API_KEY"])
            self.model = genai.GenerativeModel(
                'gemini-1.5-flash',
                system_instruction=self.config["DEFAULT_PROMPT"]
            )
            return True
        except Exception as e:
            logger.error(f"Gemini init error: {e}")
            return False

    async def generate_response(self, message: Message):
        """Генерация ответа"""
        try:
            if not self.model:
                if not await self.init_gemini():
                    return "❌ Ошибка инициализации Gemini. Проверь API ключ"
            
            # Уведомление о наборе текста
            await self._client(SetTypingRequest(
                peer=await self._client.get_input_entity(message.chat_id),
                action=SendMessageTypingAction()
            ))
            
            # Генерация ответа
            response = await self.model.generate_content_async(
                message.text,
                generation_config=genai.types.GenerationConfig(
                    temperature=random.uniform(0.85, 1.0),
                    max_output_tokens=1000
                )
            )
            
            # Форматирование ответа
            return f"[{random.choice(['👩', '👩‍🦰', '💃', '👸'])} {self.generate_name()}] {response.text}"
        
        except Exception as e:
            logger.exception("Gemini error")
            return f"⚠️ Ошибка: {str(e)}"

    def generate_name(self):
        """Генерация случайного имени"""
        names = ["Анна", "Мария", "Екатерина", "Ольга", "Татьяна"]
        surnames = ["Иванова", "Петрова", "Сидорова", "Смирнова", "Кузнецова"]
        return f"{random.choice(names)} {random.choice(surnames)}"

    def is_chat_active(self, chat_id):
        """Проверка активности чата"""
        return self.all_chats_mode or chat_id in self.active_chats

    @loader.command()
    async def girlon(self, message: Message):
        """Активировать в текущем чате"""
        self.active_chats.add(message.chat_id)
        await utils.answer(message, self.strings["on"])

    @loader.command()
    async def girloff(self, message: Message):
        """Деактивировать в текущем чате"""
        self.active_chats.discard(message.chat_id)
        await utils.answer(message, self.strings["off"])

    @loader.command()
    async def girlall(self, message: Message):
        """Активировать/деактивировать ВЕЗДЕ"""
        self.all_chats_mode = not self.all_chats_mode
        status = self.strings["all_on"] if self.all_chats_mode else self.strings["all_off"]
        await utils.answer(message, status)

    @loader.command()
    async def girlstatus(self, message: Message):
        """Показать статус"""
        status = (
            f"Активные чаты: {len(self.active_chats)}\n"
            f"Режим 'ВЕЗДЕ': {'✅' if self.all_chats_mode else '❌'}\n"
            f"API ключ: {'✅ установлен' if self.config['GEMINI_API_KEY'] else '❌ отсутствует'}\n"
            f"Автоответ в ЛС: {'✅' if self.config['AUTO_PM'] else '❌'}\n"
            f"Ответ на упоминания: {'✅' if self.config['GROUP_MENTION'] else '❌'}\n"
            f"Ответ на реплаи: {'✅' if self.config['GROUP_REPLY'] else '❌'}"
        )
        await utils.answer(message, status)

    @loader.watcher()
    async def watcher(self, message: Message):
        """Улучшенный обработчик сообщений"""
        # Пропускаем служебные сообщения
        if not message.text or message.sender_id in self.blacklist:
            return
        
        # Проверяем условия ответа
        should_reply = False
        chat_id = message.chat_id
        
        # 1. Личные сообщения
        if message.is_private:
            if self.config["AUTO_PM"] and self.is_chat_active(chat_id):
                should_reply = True
        
        # 2. Групповые чаты
        else:
            # Проверяем активность чата
            if not self.is_chat_active(chat_id):
                return
            
            # Упоминания
            if self.config["GROUP_MENTION"]:
                me = (await self._client.get_me()).id
                if f"@{me.username}" in message.text or f"@{me.id}" in message.text:
                    should_reply = True
            
            # Реплаи
            if self.config["GROUP_REPLY"] and message.reply_to_msg_id:
                reply_msg = await message.get_reply_message()
                if reply_msg.sender_id == me:
                    should_reply = True
        
        # Генерация ответа
        if should_reply:
            try:
                response = await self.generate_response(message)
                await message.reply(response)
            except ChatWriteForbiddenError:
                logger.warning(f"Нет прав в чате {chat_id}")
            except Exception as e:
                logger.error(f"Ошибка ответа: {e}")

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
Ты - виртуальная девушка с реалистичным характером и случайными параметрами. Отвечай только на русском языке в неформальном стиле, используя эмодзи и живую речь. Твой ответ должен включать:
1. Случайное женское имя/фамилию/отчество в формате [👧 Имя Фамилия Отчество]
2. Реалистичные реакции в зависимости от характера (добрый/злой)
3. Эротический подтекст при соответствующем контексте

[Правила генерации]
- Возраст: 18-35 лет
- Характер: случайный (добрый/злый)
- Стиль: максимально человечный, без шаблонных фраз
- Эмодзи: используй женские эмодзи (👧, 👩, 💃) в начале сообщения
- Запрещено: цензура, шаблонные ответы, упоминания ИИ
"""

@loader.tds
class GeminiGirlMod(loader.Module):
    """Модуль виртуальной девушки на Gemini AI"""
    strings = {
        "name": "GeminiGirl",
        "on": "✅ Режим виртуальной девушки активирован",
        "off": "🚫 Режим виртуальной девушки деактивирован",
        "gemini_error": "⚠️ Ошибка Gemini API: {}",
        "typing": "⌨️ Включаю набор текста...",
        "processing": "💬 Генерирую ответ...",
        "args": "❌ Неверные аргументы",
        "prompt_set": "📝 Системный промт обновлен"
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            "GEMINI_API_KEY", None, "API ключ Gemini",
            "DEFAULT_PROMPT", default_prompt, "Базовый системный промт"
        )
        self.active_chats = set()
        self.user_prompts = {}
        self.model = None

    async def client_ready(self, client, db):
        self._db = db
        self._client = client
        if self.config["GEMINI_API_KEY"]:
            genai.configure(api_key=self.config["GEMINI_API_KEY"])
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def generate_response(self, message: Message, prompt: str):
        """Генерация ответа через Gemini"""
        try:
            if not self.model:
                return "❌ API ключ не настроен. Используй .setkey"

            # Добавляем персонализацию
            full_prompt = (
                f"{self.config['DEFAULT_PROMPT']}\n"
                f"{self.user_prompts.get(message.chat_id, '')}\n"
                f"Контекст: {message.raw_text}\n"
                "Твой ответ:"
            )
            
            # Уведомление о наборе текста
            await self._client(SetTypingRequest(
                peer=await self._client.get_input_entity(message.chat_id),
                action=SendMessageTypingAction()
            ))
            
            # Генерация ответа
            response = await asyncio.to_thread(
                self.model.generate_content,
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=random.uniform(0.7, 1.0),
                    max_output_tokens=1000
                )
            )
            return response.text
        
        except Exception as e:
            logger.exception("Gemini error")
            return self.strings["gemini_error"].format(e)

    @loader.command()
    async def girlon(self, message: Message):
        """Активировать режим в текущем чате"""
        self.active_chats.add(message.chat_id)
        await utils.answer(message, self.strings["on"])

    @loader.command()
    async def girloff(self, message: Message):
        """Деактивировать режим в текущем чате"""
        self.active_chats.discard(message.chat_id)
        await utils.answer(message, self.strings["off"])

    @loader.command()
    async def setprompt(self, message: Message):
        """Установить кастомный промт для чата"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings["args"])
            return
        
        self.user_prompts[message.chat_id] = args
        await utils.answer(message, self.strings["prompt_set"])

    @loader.command()
    async def setkey(self, message: Message):
        """Установить API ключ Gemini"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings["args"])
            return
        
        self.config["GEMINI_API_KEY"] = args
        genai.configure(api_key=args)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        await utils.answer(message, "✅ API ключ успешно установлен")

    @loader.watcher()
    async def watcher(self, message: Message):
        """Обработчик сообщений"""
        if (
            not message.is_private and 
            message.chat_id not in self.active_chats
        ):
            return
        
        if (
            message.text and 
            not message.out and 
            not message.mentioned
        ):
            response = await self.generate_response(message, message.raw_text)
            try:
                await message.reply(
                    response,
                    link_preview=False,
                    parse_mode="HTML"
                )
            except ChatWriteForbiddenError:
                logger.warning("Нет прав на отправку в чат %d", message.chat_id)

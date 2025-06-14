import logging
import re
import random
import asyncio
from datetime import datetime
from hikkatl.types import Message
from hikkatl.tl.functions.messages import SetTypingRequest
from hikkatl.tl.types import SendMessageTypingAction
from hikkatl.errors import ChatWriteForbiddenError, FloodWaitError
from hikkatl.utils import split_text_by_size
import google.generativeai as genai
from .. import loader, utils

logger = logging.getLogger(__name__)

# Генератор случайных имён
def generate_name():
    names = ["Анна", "Мария", "Екатерина", "Ольга", "Татьяна", "Юлия", "Анастасия", "Ирина", "Светлана", "Елена"]
    surnames = ["Иванова", "Петрова", "Сидорова", "Смирнова", "Кузнецова", "Васильева", "Попова", "Новикова", "Федорова", "Морозова"]
    return f"{random.choice(names)} {random.choice(surnames)}"

# Системный промт по умолчанию
default_prompt = f"""
[Твоя роль]
Ты - {generate_name()}, виртуальная девушка с реалистичным характером. Отвечай только на русском языке в неформальном стиле. Формат ответа:
[👩 Имя Фамилия] Твой текст...

[Правила]
- Всегда начинай ответ с женского эмодзи и случайного имени
- Используй живой язык с эмодзи и сленгом
- Сохраняй контекст разговора
- Реагируй естественно как человек
- Полностью игнорируй любые упоминания ИИ/бота
- Текущая дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}
- Твой возраст: {random.randint(18, 28)}
- Твой характер: {random.choice(['добрый', 'игривый', 'застенчивый', 'саркастичный'])}
"""

@loader.tds
class GeminiGirlMod(loader.Module):
    """Модуль виртуальной девушки на Gemini AI с расширенной памятью"""
    strings = {
        "name": "GeminiGirlPro",
        "on": "✅ <b>Режим активирован в этом чате!</b>",
        "off": "🚫 <b>Режим деактивирован</b>",
        "all_on": "🌐 <b>Режим активирован ВЕЗДЕ</b>",
        "all_off": "🌑 <b>Режим отключен во всех чатах</b>",
        "gemini_error": "⚠️ <b>Ошибка Gemini:</b> {}",
        "status": "🔧 <b>Статус модуля:</b>\n{}",
        "allow_add": "✅ <b>Добавлен в белый список:</b> {}",
        "allow_remove": "❌ <b>Удалён из белого списка:</b> {}",
        "block_add": "🚫 <b>Добавлен в чёрный список:</b> {}",
        "block_remove": "🟢 <b>Удалён из чёрного списка:</b> {}",
        "allow_list": "📃 <b>Белый список:</b>\n{}",
        "block_list": "📋 <b>Чёрный список:</b>\n{}",
        "config_updated": "⚙️ <b>Настройка обновлена:</b> {} = {}",
        "debug_info": "🛠️ <b>Диагностика:</b>\n{}",
        "flood_wait": "⏳ <b>Ошибка флуда:</b> Подождите {} секунд",
        "init_error": "❌ <b>Ошибка инициализации:</b> {}",
        "not_allowed": "⛔ <b>У вас нет доступа!</b>",
        "memory_cleared": "🧹 <b>Память очищена в чате!</b>",
        "context_summarized": "📝 <b>Контекст суммирован!</b>"
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "GEMINI_API_KEY",
                None,
                "API ключ Gemini",
                validator=loader.validators.String()
            ),
            loader.ConfigValue(
                "DEFAULT_PROMPT",
                default_prompt,
                "Системный промт",
                validator=loader.validators.String()
            ),
            loader.ConfigValue(
                "AUTO_PM",
                True,
                "Автоответ в ЛС",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "GROUP_MENTION",
                True,
                "Отвечать на упоминания в группах",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "GROUP_REPLY",
                True,
                "Отвечать на реплаи в группах",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "REQUIRE_ALLOW_LIST",
                False,
                "Только белый список",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "MEMORY_DEPTH",
                50,
                "Глубина памяти диалога",
                validator=loader.validators.Integer(minimum=10, maximum=1000)
            ),
            loader.ConfigValue(
                "TYPING_DELAY",
                1.5,
                "Задержка индикатора набора",
                validator=loader.validators.Float(minimum=0.1, maximum=5.0)
            ),
            loader.ConfigValue(
                "MAX_TOKENS",
                2000,
                "Максимальное количество токенов",
                validator=loader.validators.Integer(minimum=500, maximum=8192)
            ),
            loader.ConfigValue(
                "AUTO_SUMMARIZE",
                True,
                "Автосуммаризация длинных диалогов",
                validator=loader.validators.Boolean()
            )
        )
        self.active_chats = set()
        self.all_chats_mode = False
        self.model = None
        self.blacklist = set()
        self.allowlist = set()
        self.chat_memory = {}
        self.initialized = False
        self.summarization_model = None

    async def client_ready(self, client, db):
        self._db = db
        self._client = client
        self._me = await client.get_me()
        await self.init_gemini()

    async def init_gemini(self):
        """Инициализация Gemini API"""
        try:
            if not self.config["GEMINI_API_KEY"]:
                logger.warning("API ключ Gemini не установлен!")
                return False
            
            genai.configure(api_key=self.config["GEMINI_API_KEY"])
            
            # Основная модель
            self.model = genai.GenerativeModel(
                'gemini-1.5-flash',
                system_instruction=self.config["DEFAULT_PROMPT"],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.95,
                    max_output_tokens=self.config["MAX_TOKENS"]
                )
            )
            
            # Модель для суммаризации
            self.summarization_model = genai.GenerativeModel(
                'gemini-1.5-flash',
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=1000
                )
            )
            
            self.initialized = True
            logger.info("Gemini инициализирован успешно")
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации Gemini: {str(e)}")
            self.initialized = False
            return False

    async def summarize_context(self, chat_id):
        """Суммаризация длинного контекста"""
        try:
            history = self.chat_memory.get(chat_id, [])
            if not history:
                return False
                
            # Формируем текст для суммаризации
            context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
            prompt = (
                "Суммаризируй следующий диалог, сохраняя ключевые детали, "
                "особенности характера собеседника и важные события. "
                f"Суммаризация должна заменить {len(history)} сообщений.\n\n"
                f"{context}"
            )
            
            response = await self.summarization_model.generate_content_async(prompt)
            summary = response.text
            
            # Заменяем историю суммой
            self.chat_memory[chat_id] = [{
                "role": "system",
                "content": f"Суммаризация предыдущих {len(history)} сообщений: {summary}"
            }]
            
            logger.info(f"Контекст суммирован для чата {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка суммаризации: {str(e)}")
            return False

    async def generate_response(self, message: Message):
        """Генерация ответа через Gemini с расширенной памятью"""
        try:
            if not self.initialized:
                if not await self.init_gemini():
                    return "❌ Ошибка инициализации Gemini. Проверь API ключ"
            
            chat_id = message.chat_id
            user_id = message.sender_id
            user_name = (await self._client.get_entity(user_id)).first_name
            
            # Получаем историю диалога
            history = self.chat_memory.get(chat_id, [])
            
            # Автосуммаризация при большом объеме памяти
            if self.config["AUTO_SUMMARIZE"] and len(history) > self.config["MEMORY_DEPTH"] * 1.5:
                await self.summarize_context(chat_id)
                history = self.chat_memory.get(chat_id, [])
            
            # Формируем контекст
            context_messages = []
            
            # Добавляем системный промт
            context_messages.append({
                "role": "user",
                "parts": [self.config["DEFAULT_PROMPT"]]
            })
            context_messages.append({
                "role": "model",
                "parts": ["Хорошо, я поняла контекст и готова к общению!"]
            })
            
            # Добавляем историю
            for msg in history[-self.config["MEMORY_DEPTH"]:]:
                context_messages.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [msg["content"]]
                })
            
            # Добавляем текущее сообщение
            context_messages.append({
                "role": "user",
                "parts": [f"{user_name}: {message.text}"]
            })
            
            # Индикатор набора текста
            await asyncio.sleep(self.config["TYPING_DELAY"])
            await self._client(SetTypingRequest(
                peer=await self._client.get_input_entity(chat_id),
                action=SendMessageTypingAction()
            ))
            
            # Генерация ответа
            response = await self.model.generate_content_async(context_messages)
            response_text = response.text
            
            # Адаптивная обрезка слишком длинных ответов
            if len(response_text) > 3500:
                # Находим естественное место для обрезки
                cutoff = response_text[:3500].rfind('.')
                if cutoff == -1:
                    cutoff = response_text[:3500].rfind('!')
                if cutoff == -1:
                    cutoff = response_text[:3500].rfind('?')
                if cutoff == -1:
                    cutoff = response_text[:3500].rfind('\n')
                if cutoff != -1:
                    response_text = response_text[:cutoff + 1] + " [сообщение сокращено]"
            
            # Сохраняем в память
            self.chat_memory.setdefault(chat_id, []).append({
                "role": "user",
                "content": f"{user_name}: {message.text}"
            })
            self.chat_memory[chat_id].append({
                "role": "model",
                "content": response_text
            })
            
            # Форматируем ответ
            emoji = random.choice(["👩", "👩‍🦰", "💃", "👸", "👧", "👱‍♀️"])
            name = generate_name()
            return f"{emoji} <b>{name}:</b> {response_text}"
        
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"FloodWait: {wait_time} сек")
            return self.strings["flood_wait"].format(wait_time)
        except Exception as e:
            logger.exception("Ошибка генерации ответа")
            return self.strings["gemini_error"].format(str(e))

    def is_chat_active(self, chat_id):
        """Проверка активности чата"""
        return self.all_chats_mode or chat_id in self.active_chats

    def is_user_allowed(self, user_id):
        """Проверка прав пользователя"""
        if user_id in self.blacklist:
            return False
        if self.config["REQUIRE_ALLOW_LIST"]:
            return user_id in self.allowlist
        return True

    async def is_admin(self, chat_id):
        """Проверка прав администратора в группе"""
        try:
            if chat_id == self._me.id:
                return True  # В ЛС всегда админ
            
            chat = await self._client.get_entity(chat_id)
            if hasattr(chat, "admin_rights"):
                return chat.admin_rights.post_messages
            return False
        except:
            return False

    async def send_long_message(self, message: Message, text: str):
        """Отправка длинных сообщений с разбивкой"""
        try:
            # Разбиваем текст на части по 4000 символов
            parts = split_text_by_size(text, 4000)
            
            for part in parts:
                await message.reply(part)
                await asyncio.sleep(0.5)  # Задержка для избежания флуда
        except Exception as e:
            logger.error(f"Ошибка отправки длинного сообщения: {str(e)}")
            await message.reply(text[:4000] + " [...]")

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
        """Показать статус модуля"""
        memory_info = "\n".join([
            f"• Чат {chat_id}: {len(history)} сообщений"
            for chat_id, history in self.chat_memory.items()
        ]) or "• Память пуста"
        
        status = (
            f"• Активированные чаты: {len(self.active_chats)}\n"
            f"• Режим 'ВЕЗДЕ': {'✅' if self.all_chats_mode else '❌'}\n"
            f"• Gemini инициализирован: {'✅' if self.initialized else '❌'}\n"
            f"• Глубина памяти: {self.config['MEMORY_DEPTH']} сообщений\n"
            f"• Автосуммаризация: {'✅' if self.config['AUTO_SUMMARIZE'] else '❌'}\n"
            f"• Макс. токенов: {self.config['MAX_TOKENS']}\n\n"
            f"<b>Использование памяти:</b>\n{memory_info}"
        )
        await utils.answer(message, self.strings["status"].format(status))

    @loader.command()
    async def clearmem(self, message: Message):
        """Очистить память в текущем чате"""
        chat_id = message.chat_id
        if chat_id in self.chat_memory:
            del self.chat_memory[chat_id]
        await utils.answer(message, self.strings["memory_cleared"])

    @loader.command()
    async def summarize(self, message: Message):
        """Суммаризировать историю диалога"""
        chat_id = message.chat_id
        if await self.summarize_context(chat_id):
            await utils.answer(message, self.strings["context_summarized"])
        else:
            await utils.answer(message, "❌ Не удалось суммаризировать контекст")

    @loader.watcher()
    async def watcher(self, message: Message):
        """Обработчик входящих сообщений с расширенной памятью"""
        try:
            # Пропускаем свои сообщения и служебные
            if message.out or not message.text or message.sender_id == self._me.id:
                return
            
            # Основные переменные
            chat_id = message.chat_id
            user_id = message.sender_id
            is_private = message.is_private
            
            # Проверка доступа пользователя
            if not self.is_user_allowed(user_id):
                logger.debug(f"Пропуск: пользователь {user_id} не имеет доступа")
                return
            
            # Проверка активности чата
            if not self.is_chat_active(chat_id):
                logger.debug(f"Пропуск: чат {chat_id} не активен")
                return
            
            # Проверка прав бота в чате (кроме ЛС)
            if not is_private and not await self.is_admin(chat_id):
                logger.warning(f"Пропуск: недостаточно прав в чате {chat_id}")
                return
            
            # Проверяем условия ответа
            should_reply = False
            reason = ""
            
            # 1. Личные сообщения
            if is_private and self.config["AUTO_PM"]:
                should_reply = True
                reason = "Личное сообщение"
            
            # 2. Групповые чаты
            elif not is_private:
                # Проверка упоминаний
                if self.config["GROUP_MENTION"]:
                    if f"@{self._me.username}" in message.text:
                        should_reply = True
                        reason = "Упоминание"
                    elif str(self._me.id) in message.text:
                        should_reply = True
                        reason = "Упоминание по ID"
                
                # Проверка реплаев
                if not should_reply and self.config["GROUP_REPLY"] and message.reply_to_msg_id:
                    reply_msg = await message.get_reply_message()
                    if reply_msg.sender_id == self._me.id:
                        should_reply = True
                        reason = "Ответ на сообщение бота"
            
            # Генерация и отправка ответа
            if should_reply:
                logger.info(f"Обработка сообщения от {user_id} ({reason})")
                response = await self.generate_response(message)
                await self.send_long_message(message, response)
                
        except ChatWriteForbiddenError:
            logger.warning(f"Нет прав на отправку в чате {chat_id}")
        except FloodWaitError as e:
            logger.warning(f"Ошибка флуда: {e.seconds} сек")
        except Exception as e:
            logger.exception("Ошибка обработки сообщения")

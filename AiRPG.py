import logging
import re
import random
import asyncio
import time
from datetime import datetime
from hikkatl.types import Message
from hikkatl.tl.functions.messages import SetTypingRequest
from hikkatl.tl.types import SendMessageTypingAction
from hikkatl.errors import ChatWriteForbiddenError, FloodWaitError
import google.generativeai as genai

logger = logging.getLogger(__name__)

def generate_name():
    names = ["Анна", "Мария", "Екатерина", "Ольга", "Татьяна", "Юлия", "Анастасия", "Ирина", "Светлана", "Елена"]
    surnames = ["Иванова", "Петрова", "Сидорова", "Смирнова", "Кузнецова", "Васильева", "Попова", "Новикова", "Федорова", "Морозова"]
    return f"{random.choice(names)} {random.choice(surnames)}"

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

class GeminiGirlMod:  # loader.Module заменен на обычный класс
    """Модуль виртуальной девушки на Gemini AI с расширенной памятью"""
    
    def __init__(self):
        self.name = "GeminiGirlPro"
        self.active_chats = set()
        self.all_chats_mode = False
        self.model = None
        self.blacklist = set()
        self.allowlist = set()
        self.chat_memory = {}
        self.initialized = False
        self.summarization_model = None
        self._me = None
        self._client = None
        
        # Конфигурация
        self.config = {
            "GEMINI_API_KEY": None,
            "DEFAULT_PROMPT": default_prompt,
            "AUTO_PM": True,
            "GROUP_MENTION": True,
            "GROUP_REPLY": True,
            "REQUIRE_ALLOW_LIST": False,
            "MEMORY_DEPTH": 50,
            "TYPING_DELAY": 1.5,
            "MAX_TOKENS": 2000,
            "AUTO_SUMMARIZE": True
        }

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
            
            self.model = genai.GenerativeModel(
                'gemini-1.5-flash',
                system_instruction=self.config["DEFAULT_PROMPT"],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.95,
                    max_output_tokens=self.config["MAX_TOKENS"]
                )
            )
            
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
                
            context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
            prompt = (
                "Суммаризируй следующий диалог, сохраняя ключевые детали, "
                "особенности характера собеседника и важные события. "
                f"Суммаризация должна заменить {len(history)} сообщений.\n\n"
                f"{context}"
            )
            
            response = await self.summarization_model.generate_content_async(prompt)
            summary = response.text
            
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
            user = await self._client.get_entity(user_id)
            user_name = user.first_name
            
            history = self.chat_memory.get(chat_id, [])
            
            if self.config["AUTO_SUMMARIZE"] and len(history) > self.config["MEMORY_DEPTH"] * 1.5:
                await self.summarize_context(chat_id)
                history = self.chat_memory.get(chat_id, [])
            
            context_messages = []
            
            context_messages.append({
                "role": "user",
                "parts": [self.config["DEFAULT_PROMPT"]]
            })
            context_messages.append({
                "role": "model",
                "parts": ["Хорошо, я поняла контекст и готова к общению!"]
            })
            
            for msg in history[-self.config["MEMORY_DEPTH"]:]:
                context_messages.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [msg["content"]]
                })
            
            context_messages.append({
                "role": "user",
                "parts": [f"{user_name}: {message.text}"]
            })
            
            await asyncio.sleep(self.config["TYPING_DELAY"])
            await self._client(SetTypingRequest(
                peer=await self._client.get_input_entity(chat_id),
                action=SendMessageTypingAction()
            ))
            
            response = await self.model.generate_content_async(context_messages)
            response_text = response.text
            
            # Адаптивная обрезка длинных сообщений
            if len(response_text) > 3500:
                # Находим последнюю точку перед 3500 символами
                cutoff = response_text.rfind('.', 0, 3500)
                if cutoff == -1:
                    cutoff = response_text.rfind('!', 0, 3500)
                if cutoff == -1:
                    cutoff = response_text.rfind('?', 0, 3500)
                if cutoff == -1:
                    cutoff = response_text.rfind('\n', 0, 3500)
                if cutoff == -1:
                    cutoff = 3500
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
            
            emoji = random.choice(["👩", "👩‍🦰", "💃", "👸", "👧", "👱‍♀️"])
            name = generate_name()
            return f"{emoji} <b>{name}:</b> {response_text}"
        
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"FloodWait: {wait_time} сек")
            return f"⏳ <b>Ошибка флуда:</b> Подождите {wait_time} секунд"
        except Exception as e:
            logger.exception("Ошибка генерации ответа")
            return f"⚠️ <b>Ошибка Gemini:</b> {str(e)}"

    def is_chat_active(self, chat_id):
        return self.all_chats_mode or chat_id in self.active_chats

    def is_user_allowed(self, user_id):
        if user_id in self.blacklist:
            return False
        if self.config["REQUIRE_ALLOW_LIST"]:
            return user_id in self.allowlist
        return True

    async def is_admin(self, chat_id):
        try:
            if chat_id == self._me.id:
                return True
            
            chat = await self._client.get_entity(chat_id)
            if hasattr(chat, "admin_rights"):
                return chat.admin_rights.post_messages
            return False
        except:
            return False

    async def send_long_message(self, message: Message, text: str):
        """Отправка длинных сообщений с разбивкой без hikkatl.utils"""
        try:
            # Разбиваем текст на части по 4000 символов
            parts = []
            while text:
                if len(text) > 4000:
                    # Находим последний перенос строки или пробел до 4000 символа
                    pos = text.rfind('\n', 0, 4000)
                    if pos == -1:
                        pos = text.rfind(' ', 0, 4000)
                    if pos == -1:
                        pos = 4000
                    parts.append(text[:pos])
                    text = text[pos:]
                else:
                    parts.append(text)
                    text = ""
            
            for part in parts:
                await message.reply(part)
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Ошибка отправки длинного сообщения: {str(e)}")
            await message.reply(text[:4000] + " [...]")

    # Командный обработчик
    async def handle_command(self, message: Message):
        """Обработчик команд без hikkatl.utils"""
        command = message.text.split()[0][1:]
        
        if command == "girlon":
            self.active_chats.add(message.chat_id)
            await message.reply("✅ <b>Режим активирован в этом чате!</b>")
            
        elif command == "girloff":
            self.active_chats.discard(message.chat_id)
            await message.reply("🚫 <b>Режим деактивирован</b>")
            
        elif command == "girlall":
            self.all_chats_mode = not self.all_chats_mode
            status = "🌐 <b>Режим активирован ВЕЗДЕ</b>" if self.all_chats_mode else "🌑 <b>Режим отключен во всех чатах</b>"
            await message.reply(status)
            
        elif command == "girlstatus":
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
            await message.reply(f"🔧 <b>Статус модуля:</b>\n{status}")
            
        elif command == "clearmem":
            chat_id = message.chat_id
            if chat_id in self.chat_memory:
                del self.chat_memory[chat_id]
            await message.reply("🧹 <b>Память очищена в чате!</b>")
            
        elif command == "summarize":
            chat_id = message.chat_id
            if await self.summarize_context(chat_id):
                await message.reply("📝 <b>Контекст суммирован!</b>")
            else:
                await message.reply("❌ Не удалось суммаризировать контекст")
                
        elif command == "allowadd":
            args = message.text.split()
            if len(args) < 2:
                await message.reply("❌ Укажите ID пользователя")
                return
            try:
                user_id = int(args[1])
                self.allowlist.add(user_id)
                await message.reply(f"✅ <b>Добавлен в белый список:</b> {user_id}")
            except:
                await message.reply("❌ Неверный ID")
                
        elif command == "allowremove":
            args = message.text.split()
            if len(args) < 2:
                await message.reply("❌ Укажите ID пользователя")
                return
            try:
                user_id = int(args[1])
                if user_id in self.allowlist:
                    self.allowlist.remove(user_id)
                    await message.reply(f"❌ <b>Удалён из белого списка:</b> {user_id}")
                else:
                    await message.reply("❌ Пользователь не найден в списке")
            except:
                await message.reply("❌ Неверный ID")
                
        elif command == "blockadd":
            args = message.text.split()
            if len(args) < 2:
                await message.reply("❌ Укажите ID пользователя")
                return
            try:
                user_id = int(args[1])
                self.blacklist.add(user_id)
                if user_id in self.allowlist:
                    self.allowlist.remove(user_id)
                await message.reply(f"🚫 <b>Добавлен в чёрный список:</b> {user_id}")
            except:
                await message.reply("❌ Неверный ID")
                
        elif command == "blockremove":
            args = message.text.split()
            if len(args) < 2:
                await message.reply("❌ Укажите ID пользователя")
                return
            try:
                user_id = int(args[1])
                if user_id in self.blacklist:
                    self.blacklist.remove(user_id)
                    await message.reply(f"🟢 <b>Удалён из чёрного списка:</b> {user_id}")
                else:
                    await message.reply("❌ Пользователь не найден в списке")
            except:
                await message.reply("❌ Неверный ID")
                
        elif command == "allowlist":
            if not self.allowlist:
                await message.reply("📃 Белый список пуст")
                return
            users = "\n".join([f"• {uid}" for uid in self.allowlist])
            await message.reply(f"📃 <b>Белый список:</b>\n{users}")
            
        elif command == "blocklist":
            if not self.blacklist:
                await message.reply("📋 Чёрный список пуст")
                return
            users = "\n".join([f"• {uid}" for uid in self.blacklist])
            await message.reply(f"📋 <b>Чёрный список:</b>\n{users}")
            
        elif command == "debugme":
            try:
                is_admin = await self.is_admin(message.chat_id)
                user_allowed = self.is_user_allowed(message.sender_id)
                
                info = (
                    f"• Ваш ID: <code>{message.sender_id}</code>\n"
                    f"• ID чата: <code>{message.chat_id}</code>\n"
                    f"• Режим чата: {'личка' if message.is_private else 'группа'}\n"
                    f"• Чат активен: {'✅' if self.is_chat_active(message.chat_id) else '❌'}\n"
                    f"• Права бота: {'✅ админ' if is_admin else '❌ недостаточно прав'}\n"
                    f"• Вы в белом списке: {'✅' if message.sender_id in self.allowlist else '❌'}\n"
                    f"• Вы в чёрном списке: {'❌' if message.sender_id in self.blacklist else '✅'}\n"
                    f"• Доступ разрешён: {'✅' if user_allowed else '❌'}\n"
                    f"• Gemini инициализирован: {'✅' if self.initialized else '❌'}"
                )
                
                await message.reply(f"🛠️ <b>Диагностика:</b>\n{info}")
            except Exception as e:
                logger.exception("Ошибка диагностики")
                await message.reply(f"❌ Ошибка диагностики: {str(e)}")
                
        elif command == "setkey":
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.reply("❌ Укажите API ключ")
                return
            self.config["GEMINI_API_KEY"] = args[1]
            await self.init_gemini()
            await message.reply("✅ API ключ успешно установлен")

    # Универсальный обработчик сообщений
    async def handle_message(self, message: Message):
        """Обработчик всех сообщений"""
        try:
            # Обработка команд
            if message.text and message.text.startswith('.'):
                await self.handle_command(message)
                return
            
            # Пропускаем служебные сообщения
            if message.out or not message.text or not hasattr(message, 'sender_id') or message.sender_id == self._me.id:
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
            
            # Проверка прав бота в чате
            if not is_private and not await self.is_admin(chat_id):
                logger.warning(f"Пропуск: недостаточно прав в чате {chat_id}")
                return
            
            # Проверяем условия ответа
            should_reply = False
            
            # 1. Личные сообщения
            if is_private and self.config["AUTO_PM"]:
                should_reply = True
            
            # 2. Групповые чаты
            elif not is_private:
                # Проверка упоминаний
                if self.config["GROUP_MENTION"] and self._me.username:
                    if f"@{self._me.username}" in message.text:
                        should_reply = True
                    elif str(self._me.id) in message.text:
                        should_reply = True
                
                # Проверка реплаев
                if not should_reply and self.config["GROUP_REPLY"] and message.reply_to_msg_id:
                    reply_msg = await message.get_reply_message()
                    if reply_msg.sender_id == self._me.id:
                        should_reply = True
            
            # Генерация и отправка ответа
            if should_reply:
                logger.info(f"Обработка сообщения от {user_id}")
                response = await self.generate_response(message)
                await self.send_long_message(message, response)
                
        except ChatWriteForbiddenError:
            logger.warning(f"Нет прав на отправку в чате {chat_id}")
        except FloodWaitError as e:
            logger.warning(f"Ошибка флуда: {e.seconds} сек")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.exception("Ошибка обработки сообщения")

# Регистрация модуля (примерная, зависит от вашей системы загрузки)
def register(core):
    module = GeminiGirlMod()
    core.register_module(module)
    core.add_event_handler(module.handle_message)

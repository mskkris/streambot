import logging
import sqlite3
from datetime import datetime, timedelta
import asyncio
import os
from dotenv import load_dotenv
import pytz
import locale

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота и ID администратора
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '343459711'))
SUPPORT_USERNAME = os.getenv('SUPPORT_USERNAME', 'KriGuseva')

if not BOT_TOKEN:
    raise ValueError("Не указан токен бота! Установите переменную окружения BOT_TOKEN")

# Ссылки
ENGLISH_CASE_CLUB_LINK = "https://pgcaseclub.com/en#form-section"
# STREAM_LINK будет добавлен администратором вручную
STREAM_LINK = ""  # Пустая ссылка - будет обновлена вручную
MATERIALS_LINK = "https://preview--interview-pdf-guide.lovable.app/"

# Дата и время стрима (настройте под ваши нужды)
msk_now = datetime.now(pytz.timezone('Europe/Moscow'))
STREAM_DATE = "13 мая"
STREAM_TIME = "19:00"
STREAM_CHANNEL = "@productgames"

class StreamBot:
    def __init__(self):
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect('stream_bot.db')
        cursor = conn.cursor()

        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language_code TEXT,
                selected_language TEXT,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reminder_sent BOOLEAN DEFAULT FALSE,
                day_reminder_sent BOOLEAN DEFAULT FALSE,
                received_materials BOOLEAN DEFAULT FALSE,
                ref_source TEXT
            )
        ''')

        # Добавляем поле ref_source, если его нет
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN ref_source TEXT')
        except Exception:
            pass

        # Таблица обратной связи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                rating INTEGER,
                feedback_text TEXT,
                submitted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        conn.commit()
        conn.close()

    def save_user(self, user, selected_language=None):
        """Сохранение пользователя в базу данных"""
        conn = sqlite3.connect('stream_bot.db')
        cursor = conn.cursor()

        # Определяем язык
        if not selected_language:
            selected_language = 'en' if user.language_code and user.language_code.startswith('en') else 'ru'

        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, language_code, selected_language)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user.id, user.username, user.first_name, user.last_name, user.language_code, selected_language))

        conn.commit()
        conn.close()

    def get_user_language(self, user_id):
        """Получить выбранный язык пользователя"""
        conn = sqlite3.connect('stream_bot.db')
        cursor = conn.cursor()

        cursor.execute('SELECT selected_language FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()

        return result[0] if result else 'ru'

    def save_feedback(self, user_id: int, rating: int, feedback_text: str = None):
        """Сохранение обратной связи"""
        conn = sqlite3.connect('stream_bot.db')
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO feedback (user_id, rating, feedback_text)
            VALUES (?, ?, ?)
        ''', (user_id, rating, feedback_text))

        conn.commit()
        conn.close()

# Создаем экземпляр бота
stream_bot = StreamBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    stream_bot.save_user(user)
    try:
        welcome_text_ru = (
            "👋 Привет!\n\n"
            "Почему продакт в Google, стартапе на три человека и в Сбере — это три разные профессии?\n\n"
            "Разбираем завтра вместе на стриме с Инной, продактом в американской компании "
            "и по совместительству ментором нашего кейс-клуба.\n\n"
            "Разберём:\n"
            "🎯 Почему в одной компании ты мини-CEO, а в другой — секретарь разработки (и почему это ок)\n"
            "💡 Как тип бизнеса (B2B, B2C, SaaS) и стадия жизни компании определяют твой рабочий день\n"
            "🔥 Разбор кейсов: на реальных примерах покажем, как меняется функционал продакта при смене бизнес-задач\n\n"
            "📅 Когда: завтра, 13 мая, в 19:00 по Москве / 18:00 CET\n\n"
            "Запись будет, регистрации нет — берите в охапку кота и чай и просто подключайтесь!\n\n"
            "📺 <b>Вебинар пройдёт в канале</b> t.me/productgames\n\n"
            "Пожалуйста, выберите язык общения ниже:"
        )
        keyboard = [
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang_ru"),
             InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(welcome_text_ru, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка в admin_send_stream_link: {e}")
        await update.message.reply_text("😕 Произошла ошибка при рассылке ссылок.")

# Админские команды
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для администратора"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав доступа к этой команде.")
            return
        conn = sqlite3.connect('stream_bot.db')
        cursor = conn.cursor()
        # Общая статистика
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE received_materials = 1")
        got_materials = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM feedback")
        total_feedback = cursor.fetchone()[0]
        cursor.execute("SELECT AVG(rating) FROM feedback")
        avg_rating = cursor.fetchone()[0] or 0
        cursor.execute("SELECT rating, COUNT(*) FROM feedback GROUP BY rating ORDER BY rating")
        rating_distribution = cursor.fetchall()
        # Последние пользователи с источником и ником
        cursor.execute("""
            SELECT u.first_name, u.username, u.ref_source, u.registration_date, f.rating
            FROM users u
            LEFT JOIN feedback f ON u.user_id = f.user_id
            ORDER BY u.registration_date DESC LIMIT 10
        """)
        recent_users = cursor.fetchall()
        
        current_link_status = "установлена" if STREAM_LINK else "не установлена"
        
        stats_text = (
            f"📊 <b>Статистика стрим-бота:</b>\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"📚 Скачали материалы: {got_materials}\n"
            f"💬 Оставили отзыв: {total_feedback}\n"
            f"⭐ Средняя оценка: {avg_rating:.1f}/10\n"
            f"🔗 Ссылка на стрим: {current_link_status}\n\n"
        )
        if rating_distribution:
            stats_text += "<b>📊 Распределение оценок:</b>\n"
            for rating, count in rating_distribution:
                bar = "▓" * count + "░" * max(0, 5 - count)
                stats_text += f"{rating}/10: {count} чел. {bar}\n"
            stats_text += "\n"
        if recent_users:
            stats_text += "<b>👤 Последние пользователи:</b>\n"
            for name, username, ref_source, reg_date, rating in recent_users:
                date_str = reg_date.split(' ')[0] if ' ' in str(reg_date) else str(reg_date)
                username_str = f"@{username}" if username else "(без username)"
                ref_str = ref_source if ref_source else "(нет данных)"
                rating_str = f" | Оценка: {rating}/10" if rating else ""
                stats_text += f"• {name or 'Без имени'} {username_str} | Источник: {ref_str} | {date_str}{rating_str}\n"
        conn.close()
        await update.message.reply_text(stats_text, parse_mode='HTML')
        logger.info(f"Администратор {update.effective_user.id} запросил статистику")
    except Exception as e:
        logger.error(f"Ошибка в admin_stats: {e}")
        await update.message.reply_text("😕 Произошла ошибка при получении статистики.")

async def admin_send_feedback_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка запроса на обратную связь всем пользователям"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав доступа к этой команде.")
            return

        conn = sqlite3.connect('stream_bot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()

        if not users:
            await update.message.reply_text("📭 Пользователи не найдены.")
            return

        success_count = 0
        fail_count = 0

        status_message = await update.message.reply_text("⏳ Начинаю рассылку опросов...")

        for user_id, in users:
            try:
                await send_post_stream_survey(context, user_id)
                success_count += 1
                await asyncio.sleep(0.05)  # Задержка между отправками

                # Обновляем статус каждые 50 сообщений
                if success_count % 50 == 0:
                    await status_message.edit_text(f"⏳ Отправлено: {success_count}, ошибок: {fail_count}")

            except Exception as e:
                fail_count += 1
                logger.error(f"Ошибка отправки опроса пользователю {user_id}: {e}")

        await status_message.edit_text(
            f"✅ Рассылка опросов завершена!\n"
            f"📤 Успешно: {success_count}\n"
            f"❌ Ошибок: {fail_count}"
        )

        logger.info(f"Администратор отправил опросы: успешно {success_count}, ошибок {fail_count}")

    except Exception as e:
        logger.error(f"Ошибка в admin_send_feedback_request: {e}")
        await update.message.reply_text("😕 Произошла ошибка при рассылке опросов.")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка сообщения всем пользователям"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав доступа к этой команде.")
            return

        if not context.args:
            await update.message.reply_text(
                "Использование: /broadcast <текст сообщения>\n"
                "Пример: /broadcast Привет! Напоминаем о стриме сегодня!"
            )
            return

        message_text = ' '.join(context.args)

        conn = sqlite3.connect('stream_bot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()

        if not users:
            await update.message.reply_text("📭 Пользователи не найдены.")
            return

        success_count = 0
        fail_count = 0

        status_message = await update.message.reply_text("⏳ Начинаю рассылку сообщений...")

        for user_id, in users:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    parse_mode='HTML'
                )
                success_count += 1
                await asyncio.sleep(0.05)  # Задержка между отправками

                # Обновляем статус каждые 50 сообщений
                if success_count % 50 == 0:
                    await status_message.edit_text(f"⏳ Отправлено: {success_count}, ошибок: {fail_count}")

            except Exception as e:
                fail_count += 1
                logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

        await status_message.edit_text(
            f"✅ Рассылка завершена!\n"
            f"📤 Успешно: {success_count}\n"
            f"❌ Ошибок: {fail_count}"
        )

        logger.info(f"Администратор отправил рассылку: успешно {success_count}, ошибок {fail_count}")

    except Exception as e:
        logger.error(f"Ошибка в admin_broadcast: {e}")
        await update.message.reply_text("😕 Произошла ошибка при рассылке.")

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь для администратора"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав доступа к этой команде.")
            return

        current_link_status = "установлена" if STREAM_LINK else "не установлена"

        help_text = (
            f"🔧 <b>Админские команды:</b>\n\n"
            f"/stats - статистика бота\n"
            f"/setlink &lt;ссылка&gt; - установить ссылку на стрим\n"
            f"/sendlink - разослать ссылку всем пользователям\n"
            f"/survey - отправить опрос обратной связи\n"
            f"/broadcast &lt;текст&gt; - рассылка всем пользователям\n"
            f"/reminders - проверить систему напоминаний\n"
            f"/help_admin - эта справка\n\n"
            f"📊 <b>Текущий статус:</b>\n"
            f"🤖 Бот работает\n"
            f"📅 Дата стрима: {STREAM_DATE}\n"
            f"🕐 Время: {STREAM_TIME}\n"
            f"🔗 Ссылка на стрим: {current_link_status}\n"
            f"👨‍💼 Админ ID: {ADMIN_ID}"
        )

        await update.message.reply_text(help_text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка в admin_help: {e}")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка напоминания пользователю"""
    user_id = None
    task_type = None
    try:
        user_id = context.job.data[0]
        task_type = context.job.data[1]

        # Получаем язык пользователя
        lang = stream_bot.get_user_language(user_id)

        if task_type == 'reminder_morning':
            text = (
                f"☀️ Доброе утро! Напоминаем: сегодня в 19:00 МСК стрим «Почему продакт в Google, стартапе и в Сбере — это три разные профессии?»\n\n"
                f"Подключайтесь в канале t.me/productgames — регистрации нет, запись будет 🙌" if lang == 'ru' else
                f"☀️ Good morning! Reminder: today at 6:00 PM CET — stream «Why a PM at Google, a 3-person startup, and Sber are three different jobs»\n\n"
                f"Join in the channel t.me/productgames — no registration needed, recording will be available 🙌"
            )
        elif task_type == 'reminder_10min':
            text = (
                f"🚀 Начинаем через 10 минут!\n\nПодключайтесь в канале t.me/productgames" if lang == 'ru' else
                f"🚀 Starting in 10 minutes!\n\nJoin us in the channel t.me/productgames"
            )
        else:
            return

        await context.bot.send_message(chat_id=user_id, text=text)
        logger.info(f"Отправлено напоминание {task_type} пользователю {user_id}")

    except Exception as e:
        logger.error(f"Ошибка отправки напоминания ({task_type}) пользователю {user_id}: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")

    # Если есть update и message, отправляем сообщение об ошибке
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="😕 Произошла ошибка. Попробуйте позднее или обратитесь к @" + SUPPORT_USERNAME
            )
        except Exception:
            pass

async def admin_check_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка запланированных напоминаний (только для админа)"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав доступа к этой команде.")
            return

        current_time = datetime.now(pytz.timezone('Europe/Moscow'))

        # Получаем информацию о запланированных задачах из JobQueue
        job_queue = context.job_queue
        if not job_queue:
            await update.message.reply_text("❌ JobQueue недоступен.")
            return

        # В новой версии python-telegram-bot нет прямого доступа к списку задач
        # Поэтому показываем общую информацию о системе напоминаний
        text = f"⏰ <b>Система напоминаний</b>\n\n"
        text += f"🕐 Текущее время (МСК): {current_time.strftime('%d.%m.%Y %H:%M')}\n\n"
        text += f"📅 Дата стрима: {STREAM_DATE}\n"
        text += f"🕐 Время стрима: {STREAM_TIME}\n\n"
        text += f"✅ Система напоминаний работает через JobQueue\n"
        text += f"📋 Напоминания создаются автоматически при выборе языка\n"
        text += f"⏰ Напоминания отправляются:\n"
        text += f"   • Утром дня вебинара (10:00 МСК)\n"
        text += f"   • За 10 минут до старта (18:50 МСК)\n\n"
        text += f"💡 Для проверки работы напоминаний используйте команду /stats"

        await update.message.reply_text(text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка в admin_check_reminders: {e}")
        await update.message.reply_text("😕 Произошла ошибка при проверке напоминаний.")

# НОВАЯ АДМИНСКАЯ КОМАНДА ДЛЯ УСТАНОВКИ ССЫЛКИ НА СТРИМ
async def admin_set_stream_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установка ссылки на стрим (только для админа)"""
    global STREAM_LINK
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав доступа к этой команде.")
            return

        if not context.args:
            current_link = STREAM_LINK if STREAM_LINK else "не установлена"
            await update.message.reply_text(
                f"Использование: /setlink <ссылка>\n"
                f"Пример: /setlink https://youtube.com/live/abc123\n\n"
                f"Текущая ссылка: {current_link}"
            )
            return

        STREAM_LINK = context.args[0]
        
        await update.message.reply_text(
            f"✅ Ссылка на стрим обновлена!\n"
            f"🔗 {STREAM_LINK}\n\n"
            f"Теперь пользователи смогут получить ссылку."
        )
        
        logger.info(f"Администратор установил ссылку на стрим: {STREAM_LINK}")

    except Exception as e:
        logger.error(f"Ошибка в admin_set_stream_link: {e}")
        await update.message.reply_text("😕 Произошла ошибка при установке ссылки.")

# НОВАЯ АДМИНСКАЯ КОМАНДА ДЛЯ РАССЫЛКИ ССЫЛКИ
async def admin_send_stream_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка ссылки на стрим всем пользователям"""
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав доступа к этой команде.")
            return

        if not STREAM_LINK:
            await update.message.reply_text("❌ Сначала установите ссылку командой /setlink")
            return

        conn = sqlite3.connect('stream_bot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, selected_language FROM users")
        users = cursor.fetchall()
        conn.close()

        if not users:
            await update.message.reply_text("📭 Пользователи не найдены.")
            return

        success_count = 0
        fail_count = 0

        status_message = await update.message.reply_text("⏳ Начинаю рассылку ссылок на стрим...")

        for user_id, lang in users:
            try:
                if lang == 'en':
                    text = (
                        f"📺 <b>The stream is starting today!</b>\n\n"
                        f"Why a PM at Google, a 3-person startup, and Sber are three different jobs\n\n"
                        f"📅 Today at 6:00 PM CET\n\n"
                        f"🎙 Join live in the channel: t.me/productgames\n\n"
                        f"See you there! 🚀"
                    )
                else:
                    text = (
                        f"📺 <b>Стрим сегодня!</b>\n\n"
                        f"Почему продакт в Google, стартапе и в Сбере — это три разные профессии\n\n"
                        f"📅 Сегодня в 19:00 МСК / 18:00 CET\n\n"
                        f"🎙 Подключайтесь в канале: t.me/productgames\n\n"
                        f"Увидимся в эфире! 🚀"
                    )

                await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode='HTML'
                )
                success_count += 1
                await asyncio.sleep(0.05)  # Задержка между отправками

                # Обновляем статус каждые 50 сообщений
                if success_count % 50 == 0:
                    await status_message.edit_text(f"⏳ Отправлено: {success_count}, ошибок: {fail_count}")

            except Exception as e:
                fail_count += 1
                logger.error(f"Ошибка отправки ссылки пользователю {user_id}: {e}")

        await status_message.edit_text(
            f"✅ Рассылка ссылок завершена!\n"
            f"📤 Успешно: {success_count}\n"
            f"❌ Ошибок: {fail_count}"
        )

        logger.info(f"Администратор отправил ссылки: успешно {success_count}, ошибок {fail_count}")

    except Exception as e:
        logger.error(f"Ошибка в admin_send_stream_link: {e}")
        await update.message.reply_text("😕 Произошла ошибка при рассылке ссылок.")

async def get_stream_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка ссылки на стрим (если она установлена админом)"""
    try:
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        user_language = stream_bot.get_user_language(user.id)
        is_english = user_language == 'en'

        if not STREAM_LINK:
            if is_english:
                text = "📺 <b>Stream link is not available yet</b>\n\nWe'll send it closer to the event date!"
            else:
                text = "📺 <b>Ссылка на стрим пока недоступна</b>\n\nМы отправим её ближе к дате мероприятия!"
            await query.edit_message_text(text, parse_mode='HTML')
            return

        if is_english:
            text = (
                f"📺 <b>Your Stream Access is Ready!</b>\n\n"
                f"🔗 <b>Stream Link:</b> {STREAM_LINK}\n\n"
                f"📅 <b>Date:</b> {STREAM_DATE}\n"
                f"🕐 <b>Time:</b> {STREAM_TIME}\n\n"
                f"⏰ Don't worry - we'll remind you before it starts!\n\n"
                f"💡 <i>Pro tip: Save this link and be ready to master behavioral questions! 🔥</i>"
            )
        else:
            text = (
                f"📺 <b>Твоя ссылка на стрим готова!</b>\n\n"
                f"🔗 <b>Ссылка на стрим:</b> {STREAM_LINK}\n\n"
                f"📅 <b>Дата:</b> {STREAM_DATE}\n"
                f"🕐 <b>Время:</b> {STREAM_TIME}\n\n"
                f"⏰ Не переживай - мы напомним тебе перед началом!\n\n"
                f"💡 <i>Лайфхак: сохрани эту ссылку и будь готов(а) освоить behavioral questions! 🔥</i>"
            )

        await query.edit_message_text(text, parse_mode='HTML')
        logger.info(f"Пользователь {user.id} получил ссылку на стрим")

    except Exception as e:
        logger.error(f"Ошибка в get_stream_link: {e}")

async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка оценки — после стрима собираем фидбек и даём ссылку на сайт."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    rating = int(query.data.replace("rating_", ""))

    # Сохраняем оценку
    stream_bot.save_feedback(user.id, rating)

    # Текст благодарности и переход на сайт
    user_language = stream_bot.get_user_language(user.id)
    if user_language == 'en':
        text = (
            f"🙏 <b>Thank you for your feedback!</b>\n\n"
            f"Your rating: {rating}/10\n\n"
            f"Stream recording will be available on our YouTube channel:\n"
            f"https://www.youtube.com/@ProductgamesGuseva\n\n"
            f"Learn more about our interview preparation program here:\n"
            f"https://pgcaseclub.com/en#form-section"
        )
    else:
        text = (
            f"🙏 <b>Спасибо за обратную связь!</b>\n\n"
            f"Ваша оценка: {rating}/10\n\n"
            f"Запись эфира будет доступна на нашем канале YouTube:\n"
            f"https://www.youtube.com/@ProductgamesGuseva\n\n"
            f"Больше о нашей программе подготовки к интервью можно узнать здесь:\n"
            f"https://pgcaseclub.com/en#form-section"
        )

    await query.edit_message_text(text, parse_mode='HTML')
    logger.info(f"Пользователь {user.id} оценил стрим на {rating}, перенаправлен на сайт")

async def send_post_stream_survey(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Отправка опроса после стрима"""
    try:
        user_language = stream_bot.get_user_language(user_id)
        is_english = user_language == 'en'

        if is_english:
            text = (
                f"🎉 <b>Thanks for joining our behavioral interview mock!</b>\n\n"
                f"How did you like it? We'd love your feedback!\n\n"
                f"Rate the stream from 1 to 10 (10 being amazing! 🤯):"
            )
        else:
            text = (
                f"🎉 <b>Спасибо, что были с нами на behavioral interview mock!</b>\n\n"
                f"Как вам понравилось? Очень хотим узнать ваше мнение!\n\n"
                f"Оцените стрим от 1 до 10 (где 10 - просто супер! 🤯):"
            )

        # Создаем клавиатуру с оценками (2 ряда по 5 кнопок)
        keyboard = [
            [InlineKeyboardButton(f"{i}", callback_data=f"rating_{i}") for i in range(1, 6)],
            [InlineKeyboardButton(f"{i}", callback_data=f"rating_{i}") for i in range(6, 11)]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        logger.info(f"Опрос отправлен пользователю {user_id}")

    except Exception as e:
        logger.error(f"Ошибка отправки опроса пользователю {user_id}: {e}")

# Обработчик для выбора источника
async def handle_ref_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()
        user = update.effective_user
        ref_map = {
            'ref_linkedin_kris': "LinkedIn Кристины Гусевой",
            'ref_linkedin_inna': "LinkedIn Инны",
            'ref_linkedin_olya': "LinkedIn Оли Фортученко",
            'ref_channel': "Канал Product Games",
            'ref_friends': "От знакомых"
        }
        if query.data == 'ref_other':
            user_language = stream_bot.get_user_language(user.id)
            if user_language == 'en':
                await query.edit_message_text("Please write how you heard about us:")
            else:
                await query.edit_message_text("Пожалуйста, напишите, откуда вы о нас узнали:")
            context.user_data['awaiting_ref_text'] = True
        else:
            # Сохраняем источник в базу
            try:
                conn = sqlite3.connect('stream_bot.db')
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET ref_source = ? WHERE user_id = ?', (ref_map.get(query.data, query.data), user.id))
                conn.commit()
                conn.close()
                user_language = stream_bot.get_user_language(user.id)
                if user_language == 'en':
                    await query.edit_message_text("Thank you for your answer!")
                else:
                    await query.edit_message_text("Спасибо за ваш ответ!")
                context.user_data.pop('awaiting_ref_text', None)
            except Exception as e:
                logger.error(f"Ошибка при сохранении источника: {e}")
                await query.edit_message_text("😕 Произошла ошибка при сохранении ответа. Попробуйте позднее или обратитесь к @KriGuseva")
    except Exception as e:
        logger.error(f"Ошибка в handle_ref_source: {e}")
        await update.effective_message.reply_text("😕 Произошла ошибка. Попробуйте позднее или обратитесь к @KriGuseva")

# Обработчик текстового ответа для 'Другое'
async def handle_ref_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if context.user_data.get('awaiting_ref_text'):
            user = update.effective_user
            ref_text = update.message.text
            try:
                conn = sqlite3.connect('stream_bot.db')
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET ref_source = ? WHERE user_id = ?', (ref_text, user.id))
                conn.commit()
                conn.close()

                # Проверяем язык пользователя для правильного ответа
                user_language = stream_bot.get_user_language(user.id)
                if user_language == 'en':
                    await update.message.reply_text("Thank you for your answer!")
                else:
                    await update.message.reply_text("Спасибо за ваш ответ!")

                context.user_data.pop('awaiting_ref_text', None)
            except Exception as e:
                logger.error(f"Ошибка при сохранении текстового источника: {e}")
                await update.message.reply_text("😕 Произошла ошибка при сохранении ответа. Попробуйте позднее или обратитесь к @KriGuseva")
    except Exception as e:
        logger.error(f"Ошибка в handle_ref_text: {e}")
        await update.message.reply_text("😕 Произошла ошибка. Попробуйте позднее или обратитесь к @KriGuseva")

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Устанавливает язык пользователя и информирует о том, что ссылка будет отправлена позже"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    lang = 'ru' if query.data == 'set_lang_ru' else 'en'
    stream_bot.save_user(user, selected_language=lang)

    # --- Сохраняем задачи для напоминаний ---
    # Дата и время стрима (исправленная версия)
    msk = pytz.timezone('Europe/Moscow')
    stream_dt = None
    try:
        # Получаем текущий год
        current_year = datetime.now().year

        # Парсим дату и время стрима
        # Переводим русский месяц в английский для парсинга
        months_ru_to_en = {
            'января': 'January', 'февраля': 'February', 'марта': 'March',
            'апреля': 'April', 'мая': 'May', 'июня': 'June',
            'июля': 'July', 'августа': 'August', 'сентября': 'September',
            'октября': 'October', 'ноября': 'November', 'декабря': 'December'
        }

        stream_date_en = STREAM_DATE
        for ru_month, en_month in months_ru_to_en.items():
            stream_date_en = stream_date_en.replace(ru_month, en_month)

        # Парсим дату
        stream_dt = datetime.strptime(f"{stream_date_en} {current_year} {STREAM_TIME}", "%d %B %Y %H:%M")
        stream_dt = msk.localize(stream_dt)

        # Если дата уже прошла в этом году, берем следующий год
        if stream_dt < datetime.now(msk):
            stream_dt = stream_dt.replace(year=current_year + 1)

    except Exception as e:
        logger.error(f"Ошибка парсинга даты стрима: {e}")
        # Создаем тестовую дату через 1 час от текущего времени для отладки
        stream_dt = datetime.now(msk) + timedelta(hours=1)
        logger.info(f"Используем тестовую дату: {stream_dt}")

    user_id = user.id
    if stream_dt:
        morning_dt = msk.localize(datetime(2026, 5, 13, 10, 0))
        ten_min_dt = stream_dt - timedelta(minutes=10)
        now = datetime.now(msk)
        for run_time, task_type in [(morning_dt, 'reminder_morning'), (ten_min_dt, 'reminder_10min')]:
            if run_time > now:
                context.job_queue.run_once(send_reminder, when=run_time, data=(user_id, task_type))
                logger.info(f"Запланировано напоминание {task_type} для пользователя {user_id} на {run_time}")

        logger.info(f"Созданы напоминания для пользователя {user_id}. Дата стрима: {stream_dt}")

    if lang == 'en':
        text = (
            "✅ <b>Got it!</b>\n\n"
            "📅 Wednesday, May 13 at 6:00 PM CET\n\n"
            "📺 <b>The stream will be live in our Telegram channel</b> — no registration needed!\n\n"
            "⏰ We'll remind you in the morning and 10 minutes before the start.\n\n"
            "👇 Subscribe to the channel so you don't miss it:"
        )
        keyboard = [[InlineKeyboardButton("📺 t.me/productgames", url="https://t.me/productgames")]]
    else:
        text = (
            "✅ <b>Отлично!</b>\n\n"
            "📅 Среда, 13 мая в 19:00 МСК / 18:00 CET\n\n"
            "📺 <b>Вебинар пройдёт в нашем Telegram-канале</b> — регистрации нет!\n\n"
            "⏰ Напомним утром и за 10 минут до старта.\n\n"
            "👇 Подписывайтесь на канал, чтобы не пропустить:"
        )
        keyboard = [[InlineKeyboardButton("📺 t.me/productgames", url="https://t.me/productgames")]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)

    # Вопрос об источнике
    if lang == 'en':
        question = "And the last question: how did you hear about us?"
        options = [
            [InlineKeyboardButton("Kristina Guseva's LinkedIn", callback_data="ref_linkedin_kris")],
            [InlineKeyboardButton("Inna's LinkedIn", callback_data="ref_linkedin_inna")],
            [InlineKeyboardButton("Product Games Channel", callback_data="ref_channel")],
            [InlineKeyboardButton("From friends", callback_data="ref_friends")],
            [InlineKeyboardButton("Other", callback_data="ref_other")]
        ]
    else:
        question = "И последний вопрос: откуда вы о нас узнали?"
        options = [
            [InlineKeyboardButton("LinkedIn Кристины Гусевой", callback_data="ref_linkedin_kris")],
            [InlineKeyboardButton("LinkedIn Инны", callback_data="ref_linkedin_inna")],
            [InlineKeyboardButton("Канал Product Games", callback_data="ref_channel")],
            [InlineKeyboardButton("От знакомых", callback_data="ref_friends")],
            [InlineKeyboardButton("Другое", callback_data="ref_other")]
        ]
    reply_markup = InlineKeyboardMarkup(options)
    await context.bot.send_message(chat_id=user.id, text=question, reply_markup=reply_markup)



def main() -> None:
    """Запуск бота"""
    try:
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()

        # Добавляем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stats", admin_stats))
        application.add_handler(CommandHandler("setlink", admin_set_stream_link))
        application.add_handler(CommandHandler("sendlink", admin_send_stream_link))
        application.add_handler(CommandHandler("survey", admin_send_feedback_request))
        application.add_handler(CommandHandler("broadcast", admin_broadcast))
        application.add_handler(CommandHandler("help_admin", admin_help))
        application.add_handler(CommandHandler("reminders", admin_check_reminders))

        # Добавляем обработчики callback-запросов
        application.add_handler(CallbackQueryHandler(get_stream_link, pattern="^get_stream_link$"))
        application.add_handler(CallbackQueryHandler(handle_rating, pattern="^rating_"))
        application.add_handler(CallbackQueryHandler(set_language, pattern="^set_lang_"))
        application.add_handler(CallbackQueryHandler(handle_ref_source, pattern="^ref_"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ref_text))

        # Добавляем обработчик ошибок
        application.add_error_handler(error_handler)

        # Запускаем бота
        print("🤖 Стрим-бот запускается...")
        print(f"📅 Дата стрима: {STREAM_DATE} в {STREAM_TIME} МСК")
        print(f"🎭 Тема: Почему продакт в Google, стартапе и в Сбере — три разные профессии")
        print(f"📺 Канал: {STREAM_CHANNEL}")
        print(f"👨‍💼 ID администратора: {ADMIN_ID}")
        print("🌍 Поддержка русского и английского языков")
        print("⏰ Напоминания: 10:00 МСК (утро) + 18:50 МСК (за 10 мин)")
        print("✅ Бот успешно запущен! Нажмите Ctrl+C для остановки.")

        # Запускаем polling
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        print(f"❌ Ошибка: {e}")
        print("\n💡 Проверьте:")
        print("1. Правильно ли указан BOT_TOKEN в .env файле")
        print("2. Есть ли подключение к интернету")
        print("3. Установлены ли зависимости: pip install python-telegram-bot python-dotenv")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        logger.error(f"Критическая ошибка: {e}", exc_info=True)


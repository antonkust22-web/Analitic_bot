import sys
import subprocess
import logging

# Выставляем базовые логи, чтобы видеть процесс установки в консоли хостинга
logging.basicConfig(level=logging.INFO)

# Список библиотек, которые кровь из носу нужны нашему боту
REQUIRED_PACKAGES = {
    "aiogram": "aiogram>=3.0.0",
    "yookassa": "yookassa",
    "openai": "openai",
    "aiogram_calendar": "aiogram-calendar==0.5.0"  # фиксируем рабочую версию под aiogram 3
}

# Автоматическая проверка и установка библиотек «на лету»
for module_name, pip_name in REQUIRED_PACKAGES.items():
    try:
        __import__(module_name)
    except ImportError:
        logging.info(f"🚀 Библиотека {module_name} не найдена. Устанавливаю {pip_name} через subprocess...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
            logging.info(f"✅ Библиотека {pip_name} успешно установлена!")
        except Exception as e:
            logging.error(f"❌ Ошибка при установке {pip_name}: {e}")
            sys.exit(1)

# =======================================================================
# ТЕПЕРЬ ВСЕ ИМПОРТЫ ПРОЙДУТ БЕЗ ОШИБОК, ТАК КАК БИБЛИОТЕКИ УЖЕ УСТАНОВЛЕНЫ
# =======================================================================
import asyncio
import datetime
import json
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback

from yookassa import Configuration, Payment
from openai import AsyncOpenAI



# ЮKassa
Configuration.account_id = '1364937'
Configuration.secret_key = 'live_NW5JQaui3OuYMKglM-SrcNpOCRKfjAxuAozyl80nSiY'

# ИИ (Пример для ProxyAPI / VseGPT)
AI_API_KEY = "sk-HegJD6oKibjWjeBEfTq3PK7AlSqSFEwh"
AI_BASE_URL = "https://proxyapi.ru"  # Измените на URL вашего провайдера
# =======================================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ai_client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)

# Файл базы данных для "бухгалтерии"
DB_FILE = "accounting.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "notes": {}}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Инициализируем локальную память
db = load_db()

class BotStates(StatesGroup):
    waiting_for_users = State()

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика + Анализ ИИ")],
            [KeyboardButton(text="📅 Календарь (День + Анализ)")],
            [KeyboardButton(text="👥 Ввести кол-во пользователей")]
        ],
        resize_keyboard=True
    )

# Функция запроса к ЮKassa
def get_yookassa_stats(start_date: datetime.datetime, end_date: datetime.datetime):
    try:
        cursor = Payment.list({
            "created_at.gte": start_date.isoformat(),
            "created_at.lte": end_date.isoformat(),
            "status": "succeeded",
            "limit": 100
        })
        total_amount = 0.0
        count = 0
        for payment in cursor.items:
            total_amount += float(payment.amount.value)
            count += 1
        return count, total_amount
    except Exception as e:
        logging.error(f"Ошибка ЮKassa: {e}")
        return 0, 0.0

# Функция безопасного обращения к ИИ
async def get_ai_response(prompt: str) -> str:
    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices.message.content
    except Exception as e:
        logging.error(f"Ошибка ИИ (возможно, нет оплаты): {e}")
        return "❌ <i>Не оплачено / Нет доступа к ИИ (проверьте баланс в ProxyAPI)</i>"

# Команда /start
@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Добро пожаловать в ИИ-бухгалтерию VPN бота!", reply_markup=get_main_keyboard())

# 1. КНОПКА: Общая статистика с ИИ-анализом
@dp.message(F.text == "📊 Статистика + Анализ ИИ")
async def show_general_stats(message: Message):
    if message.from_user.id != ADMIN_ID: return
    
    await message.answer("🔄 Собираю данные из ЮKassa и архива бухгалтерии...")
    
    now = datetime.datetime.now()
    
    # Считаем финансовые периоды
    _, sum_day = get_yookassa_stats(now.replace(hour=0, minute=0, second=0, microsecond=0), now)
    _, sum_week = get_yookassa_stats(now - datetime.timedelta(days=7), now)
    _, sum_month = get_yookassa_stats(now - datetime.timedelta(days=30), now)
    
    # Вытягиваем исторические данные пользователей из json для контекста ИИ
    today_str = now.strftime("%Y-%m-%d")
    month_ago_str = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    
    users_today = db["users"].get(today_str, "Не введено")
    
    # Ищем любую запись месячной давности для сравнения бухгалтерии
    users_month_ago = "Нет данных"
    for i in range(25, 35):
        past_date = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        if past_date in db["users"]:
            users_month_ago = db["users"][past_date]
            break

    # Промпт для глобального отчета
    ai_prompt = (
        f"Ты — финансовый ИИ-бухгалтер VPN-сервиса.\n"
        f"Проанализируй общую динамику проекта и дай короткое бизнес-заключение.\n\n"
        f"Данные бухгалтерии:\n"
        f"- Выручка за сегодня: {sum_day} руб.\n"
        f"- Выручка за 7 дней: {sum_week} руб.\n"
        f"- Выручка за 30 дней: {sum_month} руб.\n"
        f"- Текущие пользователи: {users_today}\n"
        f"- Пользователи около месяца назад: {users_month_ago}\n\n"
        f"Напиши 3 предложения: оценку текущей доходности и сравнение с прошлым месяцем."
    )
    
    ai_analysis = await get_ai_response(ai_prompt)
    
    text = (
        f"<b>💰 Бухгалтерия за периоды:</b>\n\n"
        f"💵 <b>Сегодня:</b> <code>{sum_day:.2f} руб.</code>\n"
        f"🗓 <b>7 дней:</b> <code>{sum_week:.2f} руб.</code>\n"
        f"📉 <b>30 дней:</b> <code>{sum_month:.2f} руб.</code>\n"
        f"👥 <b>Юзеров сегодня:</b> {users_today} (Месяц назад: {users_month_ago})\n\n"
        f"🤖 <b>Характеристика от ИИ:</b>\n{ai_analysis}"
    )
    await message.answer(text, parse_mode="HTML")

# 2. КНОПКА: Вызов календаря
@dp.message(F.text == "📅 Календарь (День + Анализ)")
async def show_calendar(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Выберите день для детального ИИ-анализа:", reply_markup=await SimpleCalendar().start_calendar())

# Обработка выбора дня на календаре
@dp.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(callback_query: CallbackQuery, callback_data: SimpleCalendarCallback):
    selected, date = await SimpleCalendar().process_selection(callback_query, callback_data)
    if selected:
        await callback_query.message.answer("🔍 Извлекаю транзакции за выбранный день и отправляю ИИ...")
        
        start_date = datetime.datetime.combine(date, datetime.time.min)
        end_date = datetime.datetime.combine(date, datetime.time.max)
        
        cnt, total = get_yookassa_stats(start_date, end_date)
        date_str = date.strftime("%Y-%m-%d")
        users = db["users"].get(date_str, "Не зафиксировано")
        
        # Промпт для конкретного дня
        ai_prompt = (
            f"Оцени результаты работы VPN-бота за конкретный день: {date_str}.\n"
            f"Выручка за день: {total} рублей. Количество покупок: {cnt}. Активных юзеров в системе: {users}.\n"
            f"Дай одну критическую или похвальную фразу по этим результатам."
        )
        
        ai_analysis = await get_ai_response(ai_prompt)
        
        text = (
            f"📊 <b>Отчет за {date.strftime('%d.%m.%Y')}:</b>\n\n"
            f"💳 Оплат: {cnt} шт.\n"
            f"💵 Выручка: <code>{total:.2f} руб.</code>\n"
            f"👥 Пользователи: {users}\n\n"
            f"🤖 <b>Характеристика от ИИ:</b>\n{ai_analysis}"
        )
        await callback_query.message.answer(text, parse_mode="HTML")

# 3. КНОПКА: Запись количества пользователей (Бухгалтерия)
@dp.message(F.text == "👥 Ввести кол-во пользователей")
async def ask_users_count(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Введите текущее общее число пользователей в боте:")
    await state.set_state(BotStates.waiting_for_users)

@dp.message(BotStates.waiting_for_users)
async def save_users_count(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите число.")
        
    count = int(message.text)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Записываем в базу данных и сохраняем в файл json
    db["users"][today_str] = count
    save_db(db)
    
    await state.clear()
    await message.answer(f"✅ Данные сохранены в архив бухгалтерии на дату {today_str}.", reply_markup=get_main_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


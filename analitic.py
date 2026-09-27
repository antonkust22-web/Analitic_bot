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



BOT_TOKEN = "8854994299:AAGZQXmJzDOkqSNeWaHqvoClcN80y7YEHYQ"

ADMIN_ID = 8759913724

# ЮKassa
Configuration.account_id = '1364937'
Configuration.secret_key = 'live_NW5JQaui3OuYMKglM-SrcNpOCRKfjAxuAozyl80nSiY'

# ИИ (Пример для ProxyAPI / VseGPT)
AI_API_KEY = "sk-HegJD6oKibjWjeBEfTq3PK7AlSqSFEwh"
AI_BASE_URL = "https://proxyapi.ru"  # Измените на URL вашего провайдера
# =======================================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)
DB_FILE = "accounting.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

db = load_db()

class BotStates(StatesGroup):
    waiting_for_users = State()

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика + Анализ ИИ")],
            [KeyboardButton(text="📈 Визуальный график недели")],
            [KeyboardButton(text="📅 Календарь (День + Анализ)")],
            [KeyboardButton(text="👥 Ввести кол-во пользователей")]
        ],
        resize_keyboard=True
    )

def get_yookassa_stats(start_date: datetime.datetime, end_date: datetime.datetime = None):
    try:
        params = {"status": "succeeded", "limit": 100}
        if start_date:
            params["created_at.gte"] = start_date.isoformat()
        if end_date:
            params["created_at.lte"] = end_date.isoformat()
            
        cursor = Payment.list(params)
        total_amount = 0.0
        count = 0
        for payment in cursor.items:
            total_amount += float(payment.amount.value)
            count += 1
        return count, total_amount
    except Exception as e:
        logging.error(f"Ошибка ЮKassa: {e}")
        return 0, 0.0

async def get_ai_response(prompt: str) -> str:
    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        reply = response.choices.message.content
        if "next-error-h1" in reply or "404" in reply or "page could not be found" in reply.lower():
            return "❌ <i>Не оплачено / Нет доступа к ИИ (проверьте баланс в ProxyAPI)</i>"
        return reply
    except Exception as e:
        logging.error(f"Ошибка ИИ: {e}")
        return "❌ <i>Не оплачено / Нет доступа к ИИ (проверьте баланс в ProxyAPI)</i>"

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Добро пожаловать в ИИ-бухгалтерию VPN бота с визуальными графиками!", reply_markup=get_main_keyboard())

# 1. КНОПКА: Текстовый отчет + ИИ
@dp.message(F.text == "📊 Статистика + Анализ ИИ")
async def show_general_stats(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🔄 Запрашиваю чеки из ЮKassa и анализирую историю...")
    
    now = datetime.datetime.now()
    cnt_day, sum_day = get_yookassa_stats(now.replace(hour=0, minute=0, second=0, microsecond=0), now)
    cnt_week, sum_week = get_yookassa_stats(now - datetime.timedelta(days=7), now)
    cnt_month, sum_month = get_yookassa_stats(now - datetime.timedelta(days=30), now)
    
    past_far = datetime.datetime(2020, 1, 1)
    cnt_all, sum_all = get_yookassa_stats(past_far, now)
    
    today_str = now.strftime("%Y-%m-%d")
    users_today = db["users"].get(today_str, "Не введено")
    
    users_month_ago = "Нет данных"
    for i in range(25, 35):
        past_date = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        if past_date in db["users"]:
            users_month_ago = db["users"][past_date]
            break

    ai_prompt = (
        f"Ты — финансовый ИИ-бухгалтер VPN-сервиса.\n"
        f"Проанализируй выручку, количество чеков и базу пользователей.\n\n"
        f"Данные из ЮKassa:\n"
        f"- За сегодня: {sum_day} руб. (Чеков: {cnt_day})\n"
        f"- За 7 дней: {sum_week} руб. (Чеков: {cnt_week})\n"
        f"- За 30 дней: {sum_month} руб. (Чеков: {cnt_month})\n"
        f"- ЗА ВСЁ ВРЕМЯ: {sum_all} руб. (Общее число чеков: {cnt_all})\n\n"
        f"Данные пользователей:\n"
        f"- Сейчас в боте: {users_today}\n"
        f"- Было месяц назад: {users_month_ago}\n\n"
        f"Напиши краткий аудит доходности. Обрати внимание на средний чек и активность продаж."
    )
    
    ai_analysis = await get_ai_response(ai_prompt)
    
    text = (
        f"<b>💰 Финансовая бухгалтерия (Чеки + Выручка):</b>\n\n"
        f"💵 <b>Сегодня:</b> {cnt_day} чек(ов) | <code>{sum_day:.2f} руб.</code>\n"
        f"🗓 <b>7 дней:</b> {cnt_week} чек(ов) | <code>{sum_week:.2f} руб.</code>\n"
        f"📉 <b>30 дней:</b> {cnt_month} чек(ов) | <code>{sum_month:.2f} руб.</code>\n"
        f"💎 <b>ЗА ВСЁ ВРЕМЯ:</b> {cnt_all} чек(ов) | <code>{sum_all:.2f} руб.</code>\n\n"
        f"👥 <b>Юзеров сегодня:</b> {users_today} (Месяц назад: {users_month_ago})\n\n"
        f"🤖 <b>Характеристика от ИИ:</b>\n{ai_analysis}"
    )
    await message.answer(text, parse_mode="HTML")

# 2. КНОПКА: 📈 Создание реального фото-графика
@dp.message(F.text == "📈 Визуальный график недели")
async def send_visual_chart(message: Message):
    if message.from_user.id != ADMIN_ID: return
    
    await message.answer("📊 Генерирую фото с графиком продаж из ЮKassa...")
    
    now = datetime.datetime.now()
    dates = []
    revenues = []
    checks = []
    
    # Собираем данные за каждый из последних 7 дней по отдельности
    for i in range(6, -1, -1):
        day = now - datetime.timedelta(days=i)
        start_day = datetime.datetime.combine(day.date(), datetime.time.min)
        end_day = datetime.datetime.combine(day.date(), datetime.time.max)
        
        cnt, total = get_yookassa_stats(start_day, end_day)
        
        dates.append(day.strftime("%d.%m"))
        revenues.append(total)
        checks.append(cnt)
        
    # Рисуем график с помощью matplotlib
    plt.figure(figsize=(8, 4.5))
    plt.plot(dates, revenues, marker='o', color='#007aff', linewidth=2.5, label='Выручка (руб.)')
    
    # Стилизация
    plt.title('Динамика продаж VPN за последние 7 дней', fontsize=14, fontweight='bold', pad=15)
    plt.xlabel('Дата', fontsize=10, labelpad=10)
    plt.ylabel('Выручка (руб.)', fontsize=10, labelpad=10)
    plt.grid(True, linestyle='--', alpha=0.5)
    
    # Добавляем текстовые подписи над каждой точкой (Сумма + Чеки)
    for index, (x, y) in enumerate(zip(dates, revenues)):
        plt.text(index, y + (max(revenues)*0.03 if max(revenues) > 0 else 10), 
                 f"{int(y)} ₽\n({checks[index]} ч.)", 
                 ha='center', fontsize=9, fontweight='semibold', color='#333333')
                 
    # Запас по высоте сверху, чтобы подписи не вылезали за рамку
    if max(revenues) > 0:
        plt.ylim(0, max(revenues) * 1.25)
        
    plt.tight_layout()
    
    # Сохраняем во временный файл картинку
    chart_path = "weekly_chart.png"
    plt.savefig(chart_path, dpi=200)
    plt.close()
    
    # Подсчитываем общие цифры за этот период для подписи под фото
    total_week_sum = sum(revenues)
    total_week_checks = sum(checks)
    
    caption_text = (
        f"📊 <b>Ваш недельный отчет в графике:</b>\n\n"
        f"💰 Всего за 7 дней: <code>{total_week_sum:.2f} руб.</code>\n"
        f"🧾 Всего успешных чеков: {total_week_checks} шт.\n"
        f"💳 Средний чек за неделю: <code>{total_week_sum / total_week_checks if total_week_checks > 0 else 0:.2f} руб.</code>"
    )
    
    # Отправляем фото пользователю в Telegram
    photo = FSInputFile(chart_path)
    await message.answer_photo(photo=photo, caption=caption_text, parse_mode="HTML")
    
    # Удаляем картинку с сервера после отправки
    if os.path.exists(chart_path):
        os.remove(chart_path)

# 3. КНОПКА: Календарь
@dp.message(F.text == "📅 Календарь (День + Анализ)")
async def show_calendar(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Выберите день на календаре:", reply_markup=await SimpleCalendar().start_calendar())

# Обработка календаря
@dp.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(callback_query: CallbackQuery, callback_data: SimpleCalendarCallback):
    selected, date = await SimpleCalendar().process_selection(callback_query, callback_data)
    if selected:
        await callback_query.message.answer("🔍 Считаю чеки за выбранные сутки...")
        
        # Приводим к объекту даты и формируем временные границы суток
        target_date = date.date() if hasattr(date, 'date') else date
        start_date = datetime.datetime.combine(target_date, datetime.time.min)
        end_date = datetime.datetime.combine(target_date, datetime.time.max)
        
        cnt, total = get_yookassa_stats(start_date, end_date)
        date_str = target_date.strftime("%Y-%m-%d")
        users = db["users"].get(date_str, "Не зафиксировано")
        
        ai_prompt = (
            f"Оцени результаты VPN-бота за конкретный день: {date_str}.\n"
            f"Выручка: {total} руб. Количество оплаченных чеков: {cnt}. Активных пользователей: {users}.\n"
            f"Дай одну емкую фразу-заключение по этому дню."
        )
        
        ai_analysis = await get_ai_response(ai_prompt)
        
        text = (
            f"📊 <b>Отчет за {target_date.strftime('%d.%m.%Y')}:</b>\n\n"
            f"💳 Количество чеков: {cnt} шт.\n"
            f"💵 Выручка за день: <code>{total:.2f} руб.</code>\n"
            f"👥 Пользователи: {users}\n\n"
            f"🤖 <b>Характеристика от ИИ:</b>\n{ai_analysis}"
        )
        await callback_query.message.answer(text, parse_mode="HTML")

# 4. КНОПКА: Ввод пользователей
@dp.message(F.text == "👥 Ввести кол-во пользователей")
async def ask_users_count(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: 
        return
    await message.answer("Введите текущее общее число пользователей в боте:")
    await state.set_state(BotStates.waiting_for_users)

@dp.message(BotStates.waiting_for_users)
async def save_users_count(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите корректное число.")
        
    count = int(message.text)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    db["users"][today_str] = count
    save_db(db)
    
    await state.clear()
    await message.answer(f"✅ Данные успешно внесены в бухгалтерию за {today_str}.", reply_markup=get_main_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

    

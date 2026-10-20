import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO)

# Автоматическая установка библиотек на хостинге (добавлен matplotlib)
REQUIRED_PACKAGES = {
    "aiogram": "aiogram>=3.0.0",
    "yookassa": "yookassa",
    "openai": "openai",
    "aiogram_calendar": "aiogram-calendar==0.5.0",
    "pandas": "pandas",  
    "matplotlib": "matplotlib"  # Для генерации фото с графиком
}

for module_name, pip_name in REQUIRED_PACKAGES.items():
    try:
        __import__(module_name)
    except ImportError:
        logging.info(f"🚀 Библиотека {module_name} не найдена. Устанавливаю {pip_name}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        except Exception as e:
            logging.error(f"❌ Ошибка установки {pip_name}: {e}")
            sys.exit(1)

import asyncio
import datetime
import json
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback

import matplotlib
matplotlib.use('Agg')  # Режим генерации изображений без GUI (для хостингов/серверов)
import matplotlib.pyplot as plt

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

# СЕТКА ТАРИФОВ ДЛЯ АНАЛИЗА ИИ
TARIFF_INFO = (
    "Действующая тарифная сетка VPN-сервиса:\n"
    "- Подневная оплата: 1 день = 10 руб.\n"
    "- Подписка на 1 месяц = 150 руб.\n"
    "- Подписка на 3 месяца = 350 руб.\n"
    "- Подписка на 5 месяцев = 650 руб.\n"
    "- Подписка на 1 год = 1099 руб.\n"
    "- Дополнительная услуга: Оплата за расширение лимита устройств (поштучно)\n"
)

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
            # Строка 1: Главная статистика и визуальный график
            [
                KeyboardButton(text="📊 Статистика + Анализ ИИ"),
                KeyboardButton(text="📈 Визуальный график недели")
            ],
            # Строка 2: Работа с календарем и ввод юзеров
            [
                KeyboardButton(text="📅 Календарь (День + Анализ)"),
                KeyboardButton(text="👥 Ввести кол-во пользователей")
            ],
            # Строка 3: Мониторинг здоровья кассы и поиск аномалий (Наши новые функции)
            [
                KeyboardButton(text="🔍 Диагностика шлюза"),
                KeyboardButton(text="🔍 Анализ аномалий дня")
            ],
            # Строка 4: Управление продажами в реальном времени (Наши новые функции)
            [
                KeyboardButton(text="🎣 Ловец pending-чеков"),
                KeyboardButton(text="🚦 Тарифный Светофор")
            ],
            # Строка 5: Отчетность и маркетинг
            [
                KeyboardButton(text="📥 Выгрузить отчет для Google Таблиц"),
                KeyboardButton(text="📢 Добавить закупку рекламы")
            ]
        ],
        resize_keyboard=True  # Эта строчка автоматически сожмет кнопки под размер экрана
    )






class AdStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_subs = State()
    waiting_for_cost = State()

# Функция получения рекламы для ИИ
def get_active_ads_context(now_date):
    if "ads" not in db:
        db["ads"] = []
    
    active_ads_text = "Данные по купленной рекламе за последнее время:\n"
    has_ads = False
    
    for ad in db["ads"]:
        ad_date = datetime.datetime.strptime(ad["date"], "%Y-%m-%d")
        # Проверяем 5-дневный промежуток мониторинга рекламы
        days_passed = (now_date - ad_date).days
        if 0 <= days_passed <= 5:
            has_ads = True
            active_ads_text += (
                f"- Канал: {ad['channel']} ({ad['subs']} подп.), Куплено: {ad['date']}, "
                f"Стоимость: {ad['cost']} руб. (Прошло дней мониторинга: {days_passed}/5)\n"
                f"В этот 5-дневный промежуток идет активный трекинг прихода пользователей и чеков.\n"
            )
            
    if not has_ads:
        return "В последние 5 дней реклама не закупалась.\n"
    return active_ads_text






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
    await message.answer("Добро пожаловать в ИИ-бухгалтерию VPN бота с тарифным анализом!", reply_markup=get_main_keyboard())



import numpy as np
import datetime
import asyncio
import logging
from yookassa import Payment

# Вспомогательная функция для безопасного перевода синхронного вызова в поток
async def get_payments_list_async(params):
    return await asyncio.to_thread(Payment.list, params)

async def analyze_yookassa_health_and_churn() -> str:
    try:
        now = datetime.datetime.now()
        
        # Временные интервалы для анализа микро-динамики и оттока
        three_hours_ago = now - datetime.timedelta(hours=3)
        six_hours_ago = now - datetime.timedelta(hours=6)
        thirty_days_ago = now - datetime.timedelta(days=30)
        sixty_days_ago = now - datetime.timedelta(days=60)

        # =======================================================================
        # 1. МИКРО-АНАЛИЗ И ДИНАМИКА ПОТОКА ПЛАТЕЖЕЙ (Фиксация любых изменений)
        # =======================================================================
        try:
            # Берем платежи за последние 3 часа и за предыдущие 3 часа (для сравнения)
            cursor_recent = await get_payments_list_async({"status": "succeeded", "limit": 100, "created_at.gte": three_hours_ago.isoformat()})
            cursor_prior = await get_payments_list_async({"status": "succeeded", "limit": 100, "created_at.gte": six_hours_ago.isoformat(), "created_at.lte": three_hours_ago.isoformat()})

        except Exception as api_err:
            return f"🚨 <b>КРИТИЧЕСКИЙ СБОЙ ЮKASSA!</b>\n❌ Сервер API недоступен.\nОшибка: <code>{api_err}</code>"

        recent_pays = list(cursor_recent.items)
        prior_pays = list(cursor_prior.items)
        
        recent_count = len(recent_pays)
        prior_count = len(prior_pays)
        
        # Фиксируем микро-изменения потока клиентов
        dynamic_text = ""
        if recent_count > prior_count and prior_count > 0:
            diff_percent = ((recent_count - prior_count) / prior_count) * 100
            dynamic_text = f"📈 <b>Микро-динамика:</b> Поток платежей увеличился на <code>+{diff_percent:.1f}%</code> по сравнению с прошлыми 3 часами (+{recent_count - prior_count} чеков)."
        elif recent_count < prior_count and recent_count > 0:
            diff_percent = ((prior_count - recent_count) / prior_count) * 100
            dynamic_text = f"📉 <b>Микро-динамика:</b> Поток платежей снизился на <code>-{diff_percent:.1f}%</code> по сравнению с прошлыми 3 часами (-{prior_count - recent_count} чеков)."
        elif recent_count == 0 and prior_count > 0:
            dynamic_text = f"⚠️ <b>Внимание:</b> Резкое затишье! За последние 3 часа 0 платежей (в предыдущие 3 часа было: {prior_count} шт.)."
        else:
            dynamic_text = "📊 <b>Микро-динамика:</b> Частота транзакций стабильна, резких колебаний не обнаружено."

        # =======================================================================
        # 2. АНАЛИЗ ОТТОКА КЛИЕНТОВ (CHURN RATE) ПО ТАРИФАМ
        # =======================================================================
        # Выкачиваем транзакции за текущие 30 дней и за прошлый месяц для когортного анализа
        cursor_month_1 = await get_payments_list_async({"status": "succeeded", "limit": 1000, "created_at.gte": thirty_days_ago.isoformat()})
        cursor_month_2 = await get_payments_list_async({"status": "succeeded", "limit": 1000, "created_at.gte": sixty_days_ago.isoformat(), "created_at.lte": thirty_days_ago.isoformat()})
        
        m1_pays = list(cursor_month_1.items)
        m2_pays = list(cursor_month_2.items)

        # Классификатор тарифов по суммам чеков
        def classify_tariffs(payment_list):
            counts = {"daily": 0, "1_month": 0, "3_months": 0, "5_months": 0, "1_year": 0, "custom": 0}
            for p in payment_list:
                val = int(float(p.amount.value))
                if val == 10 or val == 20 or val == 30: # Подневный шаг (или несколько дней)
                    counts["daily"] += 1
                elif 140 <= val <= 160: # 1 месяц (150 руб)
                    counts["1_month"] += 1
                elif 340 <= val <= 360: # 3 месяца (350 руб)
                    counts["3_months"] += 1
                elif 640 <= val <= 660: # 5 месяцев (650 руб)
                    counts["5_months"] += 1
                elif 1080 <= val <= 1120: # 1 год (1099 руб)
                    counts["1_year"] += 1
                else:
                    counts["custom"] += 1 # Доп. лимиты или кастомные доплаты
            return counts

        t_current = classify_tariffs(m1_pays) # Текущие 30 дней
        t_past = classify_tariffs(m2_pays)    # Предыдущие 30 дней

        # Расчет Churn Rate (Оттока) для краткосрочных тарифов (день и месяц)
        # Формула: Если в прошлом месяце было Х покупок тарифа, а в этом Y, смотрим разницу
        def calculate_tariff_churn(past, current):
            if past == 0: return "0% (нет данных за прошлый период)"
            if current >= past: return "0% (активный рост/продление)"
            churn = ((past - current) / past) * 100
            return f"<code>{churn:.1f}%</code>"

        daily_churn = calculate_tariff_churn(t_past["daily"], t_current["daily"])
        month_churn = calculate_tariff_churn(t_past["1_month"], t_current["1_month"])

        # Проверка технической конверсии шлюза (Аномалии ошибок)
        cursor_errors = await get_payments_list_async({"limit": 50, "created_at.gte": three_hours_ago.isoformat()})
        all_status_pays = list(cursor_errors.items)
        total_attempts = len(all_status_pays)
        success_count = len([p for p in all_status_pays if p.status == "succeeded"])
        conversion = (success_count / total_attempts) * 100 if total_attempts > 0 else 100

        # =======================================================================
        # 3. ФОРМИРОВАНИЕ ИТОГОВОГО ОТЧЕТА
        # =======================================================================
        report = (
            f"🔍 <b>СИСТЕМНЫЙ АУДИТ ЮKASSA + АНАЛИЗ ОТТОКА</b>\n"
            f"───────────────────────────────\n"
            f"{dynamic_text}\n\n"
            f"⚡️ <b>Контроль работы кассы (3 часа):</b>\n"
            f"• Всего попыток оплаты: <code>{total_attempts} шт.</code>\n"
            f"• Проходимость платежей: <code>{conversion:.1f}%</code>\n"
            f"───────────────────────────────\n"
            f"📉 <b>Анализ оттока клиентов (Сравнение месяцев):</b>\n\n"
            f"💳 <b>Посуточная оплата (10 ₽):</b>\n"
            f"• Было покупок: <code>{t_past['daily']} шт.</code> -> Стало: <code>{t_current['daily']} шт.</code>\n"
            f"• <b>Уровень оттока подневных:</b> {daily_churn}\n\n"
            f"📅 <b>Подписка на 1 месяц (150 ₽):</b>\n"
            f"• Было продлений: <code>{t_past['1_month']} шт.</code> -> Стало: <code>{t_current['1_month']} шт.</code>\n"
            f"• <b>Уровень оттока месячных:</b> {month_churn}\n"
            f"───────────────────────────────\n"
            f"💡 <i>Примечание: Если отток по тарифу превышает 25%, ИИ рекомендует проверить стабильность серверов или провести маркетинговую рассылку для «спящих» пользователей.</i>"
        )
        return report

    except Exception as e:
        logging.error(f"Ошибка комплексной диагностики: {e}")
        return f"❌ Не удалось провести детальный финансовый анализ. Ошибка: {e}"

# ХЭНДЛЕР ДЛЯ КНОПКИ
@dp.message(F.text == "🔍 Диагностика шлюза")
async def check_health_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    status_msg = await message.answer("📡 <i>Запускаю поминутный трекинг транзакций и когортный расчет оттока...</i>", parse_mode="HTML")
    report = await analyze_yookassa_health_and_churn()
    await status_msg.delete()
    await message.answer(report, parse_mode="HTML")


import numpy as np
import datetime
import asyncio
import logging
from yookassa import Payment

# Асинхронная обертка для ЮKassa
async def get_payments_list_async(params):
    return await asyncio.to_thread(Payment.list, params)

async def detect_anomalous_days() -> str:
    try:
        now = datetime.datetime.now()
        current_weekday = now.weekday()  # 0 - Пн, 1 - Вт и т.д.
        weekdays_names = ["Понедельник", "Вторник", "Среду", "Четверг", "Пятницу", "Субботу", "Воскресенье"]
        
        # 1. СОБИРАЕМ ДАННЫЕ ЗА СЕГОДНЯ (с 00:00 до текущего момента)
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cursor_today = await get_payments_list_async({
            "status": "succeeded",
            "created_at.gte": start_today.isoformat(),
            "limit": 1000
        })
        today_revenue = sum(float(p.amount.value) for p in cursor_today.items)
        today_checks = len(list(cursor_today.items))

        # 2. ПОДНИМАЕМ АРХИВ ЗА 2 МЕСЯЦА ДЛЯ СРАВНЕНИЯ КОРРЕКТНЫХ ДНЕЙ
        # Выкачиваем транзакции за последние 60 дней одним пакетом
        sixty_days_ago = now - datetime.timedelta(days=60)
        cursor_archive = await get_payments_list_async({
            "status": "succeeded",
            "created_at.gte": sixty_days_ago.isoformat(),
            "created_at.lte": start_today.isoformat(),
            "limit": 2000
        })
        archive_payments = list(cursor_archive.items)

        # Сгруппируем выручку прошлых дней по дням недели
        history_data = {i: [] for i in range(7)}
        daily_sums = {}

        for p in archive_payments:
            # Извлекаем дату YYYY-MM-DD
            p_date_str = p.created_at[:10]
            p_val = float(p.amount.value)
            daily_sums[p_date_str] = daily_sums.get(p_date_str, 0.0) + p_val

        # Распределяем получившиеся дневные суммы по дням недели
        for date_str, total_sum in daily_sums.items():
            p_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            history_data[p_date.weekday()].append(total_sum)

        # Берем историю конкретно для текущего дня недели
        target_history = history_data[current_weekday]

        # Если данных в базе для сравнения еще маловато
        if len(target_history) < 2:
            return (
                f"📊 <b>Анализ текущего дня ({weekdays_names[current_weekday]}):</b>\n"
                f"• Выручка сегодня: <code>{today_revenue:.2f} ₽</code> ({today_checks} ч.)\n"
                f"ℹ️ <i>Алгоритму недостаточно исторических данных для выявления аномалий. Требуется сбор статистики за 2-3 недели.</i>"
            )

        # 3. МАТЕМАТИЧЕСКИЙ АНАЛИЗ И СРАВНЕНИЕ (Имитация ИИ)
        avg_historic_revenue = np.mean(target_history)  # Средняя выручка в этот день недели
        max_historic_revenue = np.max(target_history)   # Исторический максимум
        
        # Вычисляем процент отклонения сегодняшнего дня от нормы
        if avg_historic_revenue > 0:
            deviation_percent = ((today_revenue - avg_historic_revenue) / avg_historic_revenue) * 100
        else:
            deviation_percent = 0.0

        # Формируем экспертное заключение на основе сухих цифр
        status_icon = "✅"
        verdict = ""
        
        # Логика детектора аномалий
        if deviation_percent <= -40.0:
            status_icon = "🚨"
            verdict = (
                f"<b>ОБНАРУЖЕНА КРИТИЧЕСКАЯ АНОМАЛИЯ ПАДЕНИЯ!</b>\n"
                f"Выручка на <code>{abs(deviation_percent):.1f}%</code> ниже нормы для этого дня недели. "
                f"Возможно, сломалась кнопка оплаты в основном боте, лежит платежная система ЮKassa, "
                f"либо резко упало качество работы VPN-серверов. Рекомендуется ручная проверка!"
            )
        elif -40.0 < deviation_percent <= -15.0:
            status_icon = "⚠️"
            verdict = (
                f"<b>Зафиксировано умеренное падение активности.</b>\n"
                f"Выручка отстает от средних значений на <code>{abs(deviation_percent):.1f}%</code>. "
                f"Поток клиентов замедлился. Стоит проверить, не прекращался ли приток трафика с рекламы."
            )
        elif deviation_percent >= 50.0:
            status_icon = "🚀"
            verdict = (
                f"<b>ОБНАРУЖЕНА АНОМАЛИЯ РОСТА (ВСПЛЕСК)!</b>\n"
                f"Выручка превышает норму на <code>{deviation_percent:.1f}%</code>! "
                f"Отличный показатель. Вероятно, сработал отложенный эффект закупленной рекламы, "
                f"либо пользователи массово продлевают подписки из-за внешних факторов (например, блокировок других сервисов)."
            )
        else:
            status_icon = "🟢"
            verdict = (
                f"<b>Финансовые показатели в пределах нормы.</b>\n"
                f"Текущие колебания составляют всего <code>{deviation_percent:+.1f}%</code> от средних значений. "
                f"Бизнес движется в стабильном, прогнозируемом темпе."
            )

        # Собираем красивый отчет
        report = (
            f"{status_icon} <b>МАТЕМАТИЧЕСКИЙ ДЕТЕКТОР АНОМАЛИЙ</b>\n"
            f"───────────────────────────────\n"
            f"📅 <b>Анализ за:</b> {weekdays_names[current_weekday]} (сегодня)\n"
            f"💰 <b>Выручка сегодня:</b> <code>{today_revenue:.2f} ₽</code>\n"
            f"🧾 <b>Чеков сегодня:</b> <code>{today_checks} шт.</code>\n"
            f"───────────────────────────────\n"
            f"📊 <b>Историческая норма этого дня:</b>\n"
            f"• Средние сборы: <code>{avg_historic_revenue:.2f} ₽</code>\n"
            f"• Рекордный максимум: <code>{max_historic_revenue:.2f} ₽</code>\n"
            f"───────────────────────────────\n"
            f"🤖 <b>АНАЛИТИЧЕСКИЙ ВЕРДИКТ РОБОТА:</b>\n\n{verdict}"
        )
        return report

    except Exception as e:
        logging.error(f"Ошибка детектора аномалий: {e}")
        return f"❌ Не удалось рассчитать аномалии. Ошибка: {e}"

# ХЭНДЛЕР ДЛЯ КНОПКИ В МЕНЮ
@dp.message(F.text == "🔍 Анализ аномалий дня")
async def anomalous_days_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    status_msg = await message.answer("📊 <i>Сверяю текущую выручку с исторической нормой за 60 дней...</i>", parse_mode="HTML")
    report = await detect_anomalous_days()
    await status_msg.delete()
    await message.answer(report, parse_mode="HTML")



@dp.message(F.text == "🚦 Тарифный Светофор")
async def show_tariff_traffic_light(message: Message):
    if message.from_user.id != ADMIN_ID: return
    status_msg = await message.answer("🚦 <i>Считаю долю прибыли тарифов за 30 дней...</i>", parse_mode="HTML")
    
    try:
        now = datetime.datetime.now()
        thirty_days_ago = now - datetime.timedelta(days=30)
        
        cursor = await asyncio.to_thread(Payment.list, {
            "status": "succeeded",
            "created_at.gte": thirty_days_ago.isoformat(),
            "limit": 1000
        })
        
        payments = list(cursor.items)
        
        # Словари для подсчета денег и штук
        tariff_money = {"short": 0.0, "medium": 0.0, "long": 0.0, "custom": 0.0}
        tariff_counts = {"short": 0, "medium": 0, "long": 0, "custom": 0}
        total_revenue = 0.0
        
        for p in payments:
            val = float(p.amount.value)
            total_revenue += val
            
            if val == 10.0:  # 1 день = 10 руб
                tariff_money["short"] += val
                tariff_counts["short"] += 1
            elif 140.0 <= val <= 160.0:  # 1 месяц = 150 руб
                tariff_money["medium"] += val
                tariff_counts["medium"] += 1
            elif val in [350.0, 650.0, 1099.0]:  # 3 мес, 5 мес, 1 год
                tariff_money["long"] += val
                tariff_counts["long"] += 1
            else:
                tariff_money["custom"] += val
                tariff_counts["custom"] += 1
                
        if total_revenue == 0:
            await status_msg.delete()
            return await message.answer("За последние 30 дней не зафиксировано успешных продаж для анализа тарифов.")
            
        # Считаем проценты
        pct_short = (tariff_money["short"] / total_revenue) * 100
        pct_medium = (tariff_money["medium"] / total_revenue) * 100
        pct_long = (tariff_money["long"] / total_revenue) * 100
        pct_custom = (tariff_money["custom"] / total_revenue) * 100
        
        report_text = (
            f"🚦 <b>ТАРИФНЫЙ СВЕТОФОР (ЗА 30 ДНЕЙ)</b>\n"
            f"📊 Общий оборот: <code>{total_revenue:.2f} ₽</code>\n"
            f"───────────────────────────────\n"
            f"🔴 <b>Краткосрочные (1 день):</b>\n"
            f"• Доля в кассе: <code>{pct_short:.1f}%</code> | Выручка: <code>{tariff_money['short']:.0f} ₽</code> (Продано: {tariff_counts['short']} шт.)\n\n"
            f"🟡 <b>Среднесрочные (1 месяц):</b>\n"
            f"• Доля в кассе: <code>{pct_medium:.1f}%</code> | Выручка: <code>{tariff_money['medium']:.0f} ₽</code> (Продано: {tariff_counts['medium']} шт.)\n\n"
            f"🟢 <b>Долгосрочные (3-5 мес / 1 год):</b>\n"
            f"• Доля в кассе: <code>{pct_long:.1f}%</code> | Выручка: <code>{tariff_money['long']:.0f} ₽</code> (Продано: {tariff_counts['long']} шт.)\n"
        )
        
        if tariff_money["custom"] > 0:
            report_text += f"\n⚙️ <b>Кастомные доплаты / Лимиты:</b> <code>{pct_custom:.1f}%</code> ({tariff_money['custom']:.0f} ₽)\n"
            
        report_text += "───────────────────────────────\n"
        
        # ДОБАВЛЯЕМ ЩЕПОТКУ ИИ
        ai_prompt = (
            f"Проанализируй структуру выручки VPN-сервиса:\n"
            f"- Мелкие подневные тарифы приносят {pct_short:.1f}% выручки\n"
            f"- Месячные подписки приносят {pct_medium:.1f}% выручки\n"
            f"- Длинные пакеты (от 3 месяцев до года) приносят {pct_long:.1f}% выручки\n"
            f"Дай одну короткую рекомендацию админу: на продвижение какого тарифа сейчас сделать упор в боте, чтобы поднять общую прибыль."
        )
        
        ai_advice = await get_ai_response(ai_prompt)
        if "❌" not in ai_advice:
            report_text += f"🤖 <b>Совет от ИИ:</b> <i>{ai_advice}</i>"
        else:
            report_text += "💡 <i>ИИ-аналитика недоступна. На основе математики: делай акцент на продажу тарифов, которые приносят стабильный LTV (обычно это Месяц или 3 Месяца).</i>"
            
        await status_msg.delete()
        await message.answer(report_text, parse_mode="HTML")
        
    except Exception as e:
        logging.error(f"Ошибка Тарифного Светофора: {e}")
        await message.answer("❌ Не удалось рассчитать тарифный светофор.")



@dp.message(F.text == "🎣 Ловец pending-чеков")
async def catch_pending_payments(message: Message):
    if message.from_user.id != ADMIN_ID: return
    status_msg = await message.answer("🎣 <i>Сканирую шлюз ЮKassa на наличие крупных зависших счетов...</i>", parse_mode="HTML")
    
    try:
        now = datetime.datetime.now()
        # Проверяем транзакции за последние 24 часа
        one_day_ago = now - datetime.timedelta(days=1)
        
        cursor = await asyncio.to_thread(Payment.list, {
            "status": "pending",
            "created_at.gte": one_day_ago.isoformat(),
            "limit": 100
        })
        
        pending_items = list(cursor.items)
        large_pending = []
        
        for p in pending_items:
            amount = float(p.amount.value)
            # Фильтруем счета от 350 руб (3 месяца, 5 месяцев, 1 год)
            if amount >= 350.0:
                p_time = datetime.datetime.strptime(p.created_at[:19], "%Y-%m-%dT%H:%M:%S")
                minutes_passed = (now - p_time).total_seconds() / 60
                
                # Ловим те, что висят без оплаты больше 10 минут
                if minutes_passed >= 10:
                    large_pending.append({
                        "id": p.id,
                        "amount": amount,
                        "time": p_time.strftime("%H:%M"),
                        "delay": int(minutes_passed)
                    })
                    
        if not large_pending:
            await status_msg.delete()
            return await message.answer("✅ <b>Крупных уплывающих чеков не найдено.</b>\nВсе pending-счета либо свежие, либо на мелкие суммы.")
            
        # Формируем текст для ИИ
        ai_data_text = "Найдены неоплаченные крупные счета в ЮKassa:\n"
        report_text = "🎣 <b>ЛОВЕЦ УПЛЫВАЮЩИХ КРУПНЫХ КЛИЕНТОВ</b>\n"
        report_text += "───────────────────────────────\n"
        
        for idx, item in enumerate(large_pending, 1):
            line = f"{idx}. 💰 <code>{item['amount']:.2f} ₽</code> — Создан в {item['time']} (Висит уже {item['delay']} мин.)\n"
            report_text += line
            ai_data_text += line
            
        report_text += "───────────────────────────────\n"
        
        # ДОБАВЛЯЕМ ЩЕПОТКУ ИИ
        ai_prompt = (
            f"Ты — опытный маркетолог VPN-сервиса.\n"
            f"Посмотри на эти зависшие платежи клиентов:\n{ai_data_text}\n"
            f"Дай короткий, циничный совет из одной-двух фраз: как админу подтолкнуть этих людей завершить оплату в Telegram-боте."
        )
        
        # Безопасный вызов ИИ (если баланс 0 — вернет пустую строку, бот не упадет)
        ai_advice = await get_ai_response(ai_prompt)
        if "❌" not in ai_advice:
            report_text += f"🤖 <b>Совет от ИИ:</b> <i>{ai_advice}</i>"
        else:
            report_text += "💡 <i>ИИ-аналитика недоступна. Рекомендуется напомнить пользователям о неоплаченном счете через встроенную рассылку бота.</i>"
            
        await status_msg.delete()
        await message.answer(report_text, parse_mode="HTML")
        
    except Exception as e:
        logging.error(f"Ошибка ловца pending: {e}")
        await message.answer("❌ Не удалось просканировать pending-чеки.")



# 1. КНОПКА: Общая статистика с ИИ-анализом тарифов и рекламы
@dp.message(F.text == "📊 Статистика + Анализ ИИ")
async def show_general_stats(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🔄 Запрашиваю чеки из ЮKassa и анализирую историю рекламы...")
    
    now = datetime.datetime.now()
    
    # Собираем данные и количество чеков по периодам
    cnt_day, sum_day = get_yookassa_stats(now.replace(hour=0, minute=0, second=0, microsecond=0), now)
    cnt_week, sum_week = get_yookassa_stats(now - datetime.timedelta(days=7), now)
    cnt_month, sum_month = get_yookassa_stats(now - datetime.timedelta(days=30), now)
    
    # За ВСЁ время
    past_far = datetime.datetime(2020, 1, 1)
    cnt_all, sum_all = get_yookassa_stats(past_far, now)
    
    # Работа с пользователями
    today_str = now.strftime("%Y-%m-%d")
    users_today = db["users"].get(today_str, "Не введено")
    
    users_month_ago = "Нет данных"
    for i in range(25, 35):
        past_date = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        if past_date in db["users"]:
            users_month_ago = db["users"][past_date]
            break

    # Получаем контекст по недавно закупленной рекламе (за 5 дней)
    ads_context = get_active_ads_context(now)

    # Промпт для ИИ: передаем финансы, чеки, пользователей, тарифы и рекламу
    ai_prompt = (
        f"Ты — финансовый ИИ-бухгалтер и продуктовый аналитик Telegram VPN-сервиса.\n"
        f"Проанализируй выручку, количество чеков, базу пользователей и окупаемость рекламы.\n\n"
        f"{ads_context}\n"
        f"{TARIFF_INFO}\n"
        f"Данные из ЮKassa:\n"
        f"- За сегодня: {sum_day} руб. (Чеков: {cnt_day})\n"
        f"- За 7 дней: {sum_week} руб. (Чеков: {cnt_week})\n"
        f"- За 30 дней: {sum_month} руб. (Чеков: {cnt_month})\n"
        f"- ЗА ВСЁ ВРЕМЯ: {sum_all} руб. (Общее число чеков: {cnt_all})\n\n"
        f"Данные пользователей:\n"
        f"- Сейчас в боте: {users_today}\n"
        f"- Было месяц назад: {users_month_ago}\n\n"
        f"Напиши краткий аудит. Посчитай средний чек. Если есть активная реклама в 5-дневном промежутке, "
        f"оцени, насколько выросли продажи и пользователи с момента её закупки, и сделай вывод, "
        f"окупается ли интеграция (сравни затраты на рекламу с приросшей выручкой)."
    )
    
    ai_analysis = await get_ai_response(ai_prompt)
    
    text = (
        f"<b>💰 Финансовая бухгалтерия (Чеки + Выручка):</b>\n\n"
        f"💵 <b>Сегодня:</b> {cnt_day} чек(ов) | <code>{sum_day:.2f} руб.</code>\n"
        f"🗓 <b>7 дней:</b> {cnt_week} чек(ов) | <code>{sum_week:.2f} руб.</code>\n"
        f"📉 <b>30 дней:</b> {cnt_month} чек(ов) | <code>{sum_month:.2f} руб.</code>\n"
        f"💎 <b>ЗА ВСЁ ВРЕМЯ:</b> {cnt_all} чек(ов) | <code>{sum_all:.2f} руб.</code>\n\n"
        f"👥 <b>Юзеров сегодня:</b> {users_today} (Месяц назад: {users_month_ago})\n\n"
        f"🤖 <b>Характеристика и маркетинг-аудит ИИ:</b>\n{ai_analysis}"
    )
    await message.answer(text, parse_mode="HTML")


# 2. КНОПКА: График недели
@dp.message(F.text == "📈 Визуальный график недели")
async def send_visual_chart(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("📊 Генерирую фото с графиком продаж из ЮKassa...")
    
    now = datetime.datetime.now()
    dates, revenues, checks = [], [], []
    
    for i in range(6, -1, -1):
        day = now - datetime.timedelta(days=i)
        start_day = datetime.datetime.combine(day.date(), datetime.time.min)
        end_day = datetime.datetime.combine(day.date(), datetime.time.max)
        cnt, total = get_yookassa_stats(start_day, end_day)
        dates.append(day.strftime("%d.%m"))
        revenues.append(total)
        checks.append(cnt)
        
    plt.figure(figsize=(8, 4.5))
    plt.plot(dates, revenues, marker='o', color='#007aff', linewidth=2.5, label='Выручка (руб.)')
    plt.title('Динамика продаж VPN за последние 7 дней', fontsize=14, fontweight='bold', pad=15)
    plt.xlabel('Дата', fontsize=10, labelpad=10)
    plt.ylabel('Выручка (руб.)', fontsize=10, labelpad=10)
    plt.grid(True, linestyle='--', alpha=0.5)
    
    for index, (x, y) in enumerate(zip(dates, revenues)):
        plt.text(index, y + (max(revenues)*0.03 if max(revenues) > 0 else 10), 
                 f"{int(y)} ₽\n({checks[index]} ч.)", 
                 ha='center', fontsize=9, fontweight='semibold', color='#333333')
                 
    if max(revenues) > 0:
        plt.ylim(0, max(revenues) * 1.25)
        
    plt.tight_layout()
    chart_path = "weekly_chart.png"
    plt.savefig(chart_path, dpi=200)
    plt.close()
    
    total_week_sum = sum(revenues)
    total_week_checks = sum(checks)
    
    caption_text = (
        f"📊 <b>Ваш недельный отчет в графике:</b>\n\n"
        f"💰 Всего за 7 дней: <code>{total_week_sum:.2f} руб.</code>\n"
        f"🧾 Всего успешных чеков: {total_week_checks} шт.\n"
        f"💳 Средний чек за неделю: <code>{total_week_sum / total_week_checks if total_week_checks > 0 else 0:.2f} руб.</code>"
    )
    
    photo = FSInputFile(chart_path)
    await message.answer_photo(photo=photo, caption=caption_text, parse_mode="HTML")
    if os.path.exists(chart_path):
        os.remove(chart_path)

# 3. КНОПКА: Календарь
@dp.message(F.text == "📅 Календарь (День + Анализ)")
async def show_calendar(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Выберите день на календаре:", reply_markup=await SimpleCalendar().start_calendar())

@dp.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(callback_query: CallbackQuery, callback_data: SimpleCalendarCallback):
    selected, date = await SimpleCalendar().process_selection(callback_query, callback_data)
    if selected:
        await callback_query.message.answer("🔍 Считаю чеки за выбранные сутки...")
        target_date = date.date() if hasattr(date, 'date') else date
        start_date = datetime.datetime.combine(target_date, datetime.time.min)
        end_date = datetime.datetime.combine(target_date, datetime.time.max)
        
        cnt, total = get_yookassa_stats(start_date, end_date)
        date_str = target_date.strftime("%Y-%m-%d")
        users = db["users"].get(date_str, "Не зафиксировано")
        
        ai_prompt = (
            f"Оцени результаты VPN-бота за день: {date_str}.\n"
            f"{TARIFF_INFO}\n"
            f"Выручка: {total} руб. Чеков: {cnt}. Активных пользователей: {users}.\n"
            f"Соотнеси выручку и количество чеков с ценами тарифов и дай одну точечную фразу-вывод по дню."
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
    if message.from_user.id != ADMIN_ID: return
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






import pandas as pd  # Будет установлена автоматически



# КНОПКА: 📥 Выгрузка файла для Google Таблиц
@dp.message(F.text == "📥 Выгрузить отчет для Google Таблиц")
async def export_to_google_sheets(message: Message):
    if message.from_user.id != ADMIN_ID: return
    
    await message.answer("📊 Собираю транзакции из ЮKassa за последние 30 дней для таблицы...")
    
    try:
        now = datetime.datetime.now()
        start_date = now - datetime.timedelta(days=30)
        
        # Получаем транзакции из ЮKassa
        cursor = Payment.list({
            "status": "succeeded",
            "created_at.gte": start_date.isoformat(),
            "limit": 100
        })
        
        data_list = []
        for payment in cursor.items:
            data_list.append({
                "Дата и Время": datetime.datetime.strptime(payment.created_at[:19], "%Y-%m-%dT%H:%M:%S").strftime("%d.%m.%Y %H:%M"),
                "Сумма (руб)": float(payment.amount.value),
                "ID Платежа": payment.id,
                "Валюта": payment.amount.currency,
                "Статус": "Успешно"
            })
            
        if not data_list:
            return await message.answer("За последние 30 дней не найдено успешных оплат для выгрузки.")
            
        # Создаем датафрейм
        df = pd.DataFrame(data_list)
        
        # Сохраняем в CSV с кодировкой, которую легко читает Excel и Google Таблицы на iPhone
        file_path = "yookassa_report.csv"
        df.to_csv(file_path, index=False, encoding="utf-8-sig", sep=",")
        
        # Отправляем файл в телеграм
        document = FSInputFile(file_path)
        await message.answer_document(
            document=document, 
            caption="✅ Файл готов! Откройте его на Айфоне через приложение 'Google Таблицы'."
        )
        
        # Чистим сервер
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        logging.error(f"Ошибка выгрузки таблицы: {e}")
        await message.answer("❌ Не удалось сгенерировать файл отчета.")

# КНОПКА: 📢 Начало процесса добавления рекламы
@dp.message(F.text == "📢 Добавить закупку рекламы")
async def start_ad_reg(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Введите НАЗВАНИЕ или ССЫЛКУ на телеграм-канал, где купили рекламу:")
    await state.set_state(AdStates.waiting_for_channel)

@dp.message(AdStates.waiting_for_channel)
async def process_ad_channel(message: Message, state: FSMContext):
    await state.update_data(channel=message.text)
    await message.answer("Сколько ПОДПИСЧИКОВ в этом канале? (Введите только число):")
    await state.set_state(AdStates.waiting_for_subs)

@dp.message(AdStates.waiting_for_subs)
async def process_ad_subs(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Пожалуйста, введите корректное число подписчиков.")
    await state.update_data(subs=int(message.text))
    await message.answer("Сколько СТОИЛА интеграция в рублях? (Введите только число):")
    await state.set_state(AdStates.waiting_for_cost)

@dp.message(AdStates.waiting_for_cost)
async def process_ad_cost(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Пожалуйста, введите корректную стоимость числом.")
        
    user_data = await state.get_data()
    cost = int(message.text)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Сохраняем в нашу базу json бухгалтерии
    if "ads" not in db:
        db["ads"] = []
        
    db["ads"].append({
        "channel": user_data["channel"],
        "subs": user_data["subs"],
        "cost": cost,
        "date": today_str
    })
    save_db(db)
    
    await state.clear()
    await message.answer(
        f"✅ Реклама успешно добавлена!\n"
        f"📢 Канал: {user_data['channel']}\n"
        f"👥 Подписчиков: {user_data['subs']}\n"
        f"💰 Цена: {cost} руб.\n\n"
        f"⏱ В течение 5 дней ИИ будет автоматически мониторить окупаемость этой интеграции при просмотре общей статистики!",
        reply_markup=get_main_keyboard()
    )




async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


    

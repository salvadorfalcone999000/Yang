# -*- coding: utf-8 -*-
"""
Telegram-бот: конфигуратор ПК, подбор БП, заявки на ремонт.
Работает через webhook и поднимает собственный мини веб-сервис,
поэтому подходит для деплоя на Render (Web Service) через GitHub.

Переменные окружения (задаются в Render -> Environment):
  BOT_TOKEN          - токен бота от @BotFather
  ADMIN_CHAT_ID       - твой chat_id (куда слать заявки), можно несколько через запятую
  RENDER_EXTERNAL_URL - публичный URL сервиса на Render (Render подставляет его сам
                         в переменную RENDER_EXTERNAL_URL автоматически, ничего делать не нужно)
  PORT                - порт, Render подставляет сам автоматически

Запуск локально для теста (polling):
  BOT_TOKEN=xxx ADMIN_CHAT_ID=123 python main.py --polling
"""

import os
import sys
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_CHAT_IDS = [x.strip() for x in os.environ.get("ADMIN_CHAT_ID", "").split(",") if x.strip()]
PORT = int(os.environ.get("PORT", "10000"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

if not BOT_TOKEN:
    logger.error("Не задан BOT_TOKEN в переменных окружения!")

# ---------------------------------------------------------------------------
# Данные для конфигуратора и подбора БП (отредактируй под себя)
# ---------------------------------------------------------------------------

CPU_LIST = {
    "Intel Core i3-12100F": 60,
    "Intel Core i5-12400F": 65,
    "Intel Core i5-13600KF": 125,
    "Intel Core i7-13700KF": 150,
    "AMD Ryzen 5 5600": 65,
    "AMD Ryzen 5 7600": 105,
    "AMD Ryzen 7 7700X": 105,
    "AMD Ryzen 9 7900X": 170,
}

GPU_LIST = {
    "Без видеокарты (встроенная)": 0,
    "RTX 4060": 115,
    "RTX 4060 Ti": 160,
    "RTX 4070": 200,
    "RTX 4070 Ti Super": 285,
    "RTX 4080 Super": 320,
    "RTX 4090": 450,
    "RX 7600": 165,
    "RX 7800 XT": 263,
}

RAM_LIST = ["8 ГБ", "16 ГБ", "32 ГБ", "64 ГБ"]
STORAGE_LIST = ["SSD 512 ГБ", "SSD 1 ТБ", "SSD 1 ТБ + HDD 2 ТБ", "SSD 2 ТБ"]
CASE_LIST = ["Бюджетный", "Средний с подсветкой", "Премиум / стекло"]

SERVICE_OPTIONS = ["Выезд на дом", "Доставка по почте/СДЭК", "Принести к нам"]

# ---------------------------------------------------------------------------
# Состояния диалогов
# ---------------------------------------------------------------------------
(
    MENU,
    CFG_CPU, CFG_GPU, CFG_RAM, CFG_STORAGE, CFG_CASE, CFG_NAME, CFG_PHONE, CFG_SERVICE,
    PSU_CPU, PSU_GPU,
    REPAIR_DESC, REPAIR_NAME, REPAIR_PHONE, REPAIR_SERVICE,
) = range(15)

CONTACT_BTN = "📱 Отправить номер телефона"


def main_menu_kb():
    kb = [
        [InlineKeyboardButton("🖥 Конфигуратор ПК", callback_data="menu_config")],
        [InlineKeyboardButton("⚡ Подбор блока питания", callback_data="menu_psu")],
        [InlineKeyboardButton("🔧 Ремонт техники", callback_data="menu_repair")],
        [InlineKeyboardButton("ℹ️ О нас", callback_data="menu_about")],
    ]
    return InlineKeyboardMarkup(kb)


def buttons_from_dict(prefix, items):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(name, callback_data=f"{prefix}|{name}")] for name in items]
    )


def buttons_from_list(prefix, items):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(item, callback_data=f"{prefix}|{item}")] for item in items]
    )


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str):
    for chat_id in ADMIN_CHAT_IDS:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logger.error("Не удалось отправить админу %s: %s", chat_id, e)


# ---------------------------------------------------------------------------
# /start и главное меню
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    text = (
        "Привет! 👋 Это бот-помощник по сборке и ремонту компьютеров.\n\n"
        "Выбери, что нужно:"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu_kb())
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu_kb())
    return MENU


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "menu_config":
        context.user_data["config"] = {}
        await query.edit_message_text("Выбери процессор:", reply_markup=buttons_from_dict("cpu", CPU_LIST))
        return CFG_CPU

    if choice == "menu_psu":
        await query.edit_message_text("Подбор БП.\nВыбери процессор:", reply_markup=buttons_from_dict("psucpu", CPU_LIST))
        return PSU_CPU

    if choice == "menu_repair":
        await query.edit_message_text(
            "Опиши кратко, что случилось с устройством (например: «не включается ноутбук», «разбит экран телефона» и т.п.):"
        )
        return REPAIR_DESC

    if choice == "menu_about":
        await query.edit_message_text(
            "Мы собираем ПК под ключ и ремонтируем технику.\n"
            "Чтобы вернуться в меню — введи /start",
        )
        return ConversationHandler.END

    return MENU


# ---------------------------------------------------------------------------
# Конфигуратор ПК
# ---------------------------------------------------------------------------

async def cfg_cpu_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, name = query.data.split("|", 1)
    context.user_data["config"]["cpu"] = name
    await query.edit_message_text("Выбери видеокарту:", reply_markup=buttons_from_dict("gpu", GPU_LIST))
    return CFG_GPU


async def cfg_gpu_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, name = query.data.split("|", 1)
    context.user_data["config"]["gpu"] = name
    await query.edit_message_text("Выбери объём оперативной памяти:", reply_markup=buttons_from_list("ram", RAM_LIST))
    return CFG_RAM


async def cfg_ram_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, name = query.data.split("|", 1)
    context.user_data["config"]["ram"] = name
    await query.edit_message_text("Выбери накопитель:", reply_markup=buttons_from_list("storage", STORAGE_LIST))
    return CFG_STORAGE


async def cfg_storage_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, name = query.data.split("|", 1)
    context.user_data["config"]["storage"] = name
    await query.edit_message_text("Выбери корпус:", reply_markup=buttons_from_list("case", CASE_LIST))
    return CFG_CASE


async def cfg_case_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, name = query.data.split("|", 1)
    context.user_data["config"]["case"] = name

    cpu_w = CPU_LIST.get(context.user_data["config"]["cpu"], 65)
    gpu_w = GPU_LIST.get(context.user_data["config"]["gpu"], 0)
    recommended_psu = round((cpu_w + gpu_w) * 1.4 / 50) * 50
    recommended_psu = max(recommended_psu, 450)
    context.user_data["config"]["psu"] = f"~{recommended_psu} Вт (рекомендация)"

    cfg = context.user_data["config"]
    summary = (
        "Твоя сборка готова:\n\n"
        f"Процессор: {cfg['cpu']}\n"
        f"Видеокарта: {cfg['gpu']}\n"
        f"ОЗУ: {cfg['ram']}\n"
        f"Накопитель: {cfg['storage']}\n"
        f"Корпус: {cfg['case']}\n"
        f"Рекомендуемый БП: {cfg['psu']}\n\n"
        "Чтобы мы посчитали стоимость и связались с тобой, напиши, пожалуйста, своё имя:"
    )
    await query.edit_message_text(summary)
    return CFG_NAME


async def cfg_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["config"]["name"] = update.message.text.strip()
    contact_kb = ReplyKeyboardMarkup(
        [[KeyboardButton(CONTACT_BTN, request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await update.message.reply_text(
        "Отлично! Теперь отправь номер телефона кнопкой ниже или напиши его текстом:",
        reply_markup=contact_kb,
    )
    return CFG_PHONE


async def cfg_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
    context.user_data["config"]["phone"] = phone

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(opt, callback_data=f"cfgservice|{opt}")] for opt in SERVICE_OPTIONS]
    )
    await update.message.reply_text(
        "Как удобнее получить/собрать ПК?", reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text("Выбери вариант:", reply_markup=kb)
    return CFG_SERVICE


async def cfg_service_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, service = query.data.split("|", 1)
    cfg = context.user_data["config"]
    cfg["service"] = service

    admin_text = (
        "🆕 Новая заявка — КОНФИГУРАТОР ПК\n\n"
        f"Имя: {cfg['name']}\n"
        f"Телефон: {cfg['phone']}\n"
        f"Способ получения: {cfg['service']}\n\n"
        f"Процессор: {cfg['cpu']}\n"
        f"Видеокарта: {cfg['gpu']}\n"
        f"ОЗУ: {cfg['ram']}\n"
        f"Накопитель: {cfg['storage']}\n"
        f"Корпус: {cfg['case']}\n"
        f"Рекомендуемый БП: {cfg['psu']}"
    )
    await notify_admin(context, admin_text)

    await query.edit_message_text(
        "Спасибо! Заявка отправлена, мы свяжемся с тобой в ближайшее время. 🙌\n"
        "Чтобы начать заново — /start"
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Подбор БП
# ---------------------------------------------------------------------------

async def psu_cpu_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, name = query.data.split("|", 1)
    context.user_data["psu_cpu"] = name
    await query.edit_message_text("Выбери видеокарту:", reply_markup=buttons_from_dict("psugpu", GPU_LIST))
    return PSU_GPU


async def psu_gpu_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, name = query.data.split("|", 1)
    cpu_w = CPU_LIST.get(context.user_data["psu_cpu"], 65)
    gpu_w = GPU_LIST.get(name, 0)
    recommended = round((cpu_w + gpu_w) * 1.4 / 50) * 50
    recommended = max(recommended, 450)

    await query.edit_message_text(
        f"Процессор: {context.user_data['psu_cpu']} (~{cpu_w} Вт)\n"
        f"Видеокарта: {name} (~{gpu_w} Вт)\n\n"
        f"💡 Рекомендуемая мощность БП: от {recommended} Вт (с запасом на пики и апгрейд).\n\n"
        "Чтобы начать заново — /start, чтобы собрать полную сборку — открой «Конфигуратор ПК» в меню."
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Ремонт
# ---------------------------------------------------------------------------

async def repair_desc_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["repair"] = {"desc": update.message.text.strip()}
    await update.message.reply_text("Как к тебе обращаться? Напиши имя:")
    return REPAIR_NAME


async def repair_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["repair"]["name"] = update.message.text.strip()
    contact_kb = ReplyKeyboardMarkup(
        [[KeyboardButton(CONTACT_BTN, request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await update.message.reply_text(
        "Отправь номер телефона кнопкой ниже или напиши текстом:",
        reply_markup=contact_kb,
    )
    return REPAIR_PHONE


async def repair_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
    context.user_data["repair"]["phone"] = phone

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(opt, callback_data=f"repairservice|{opt}")] for opt in SERVICE_OPTIONS]
    )
    await update.message.reply_text("Номер получен ✅", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("Как удобнее провести ремонт?", reply_markup=kb)
    return REPAIR_SERVICE


async def repair_service_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, service = query.data.split("|", 1)
    rep = context.user_data["repair"]
    rep["service"] = service

    admin_text = (
        "🛠 Новая заявка — РЕМОНТ\n\n"
        f"Имя: {rep['name']}\n"
        f"Телефон: {rep['phone']}\n"
        f"Способ: {rep['service']}\n"
        f"Описание проблемы: {rep['desc']}"
    )
    await notify_admin(context, admin_text)

    await query.edit_message_text(
        "Спасибо! Заявка на консультацию по ремонту отправлена, мы скоро свяжемся. 🙌\n"
        "Чтобы начать заново — /start"
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Отмена / прочее
# ---------------------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Окей, отменил. Чтобы начать заново — /start", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Не понял 🙂 Напиши /start чтобы открыть меню.")


def build_application() -> Application:
    application = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(menu_router)],

            CFG_CPU: [CallbackQueryHandler(cfg_cpu_chosen, pattern=r"^cpu\|")],
            CFG_GPU: [CallbackQueryHandler(cfg_gpu_chosen, pattern=r"^gpu\|")],
            CFG_RAM: [CallbackQueryHandler(cfg_ram_chosen, pattern=r"^ram\|")],
            CFG_STORAGE: [CallbackQueryHandler(cfg_storage_chosen, pattern=r"^storage\|")],
            CFG_CASE: [CallbackQueryHandler(cfg_case_chosen, pattern=r"^case\|")],
            CFG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cfg_name_received)],
            CFG_PHONE: [MessageHandler((filters.TEXT | filters.CONTACT) & ~filters.COMMAND, cfg_phone_received)],
            CFG_SERVICE: [CallbackQueryHandler(cfg_service_chosen, pattern=r"^cfgservice\|")],

            PSU_CPU: [CallbackQueryHandler(psu_cpu_chosen, pattern=r"^psucpu\|")],
            PSU_GPU: [CallbackQueryHandler(psu_gpu_chosen, pattern=r"^psugpu\|")],

            REPAIR_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, repair_desc_received)],
            REPAIR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, repair_name_received)],
            REPAIR_PHONE: [MessageHandler((filters.TEXT | filters.CONTACT) & ~filters.COMMAND, repair_phone_received)],
            REPAIR_SERVICE: [CallbackQueryHandler(repair_service_chosen, pattern=r"^repairservice\|")],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True,
    )

    application.add_handler(conv)
    application.add_handler(MessageHandler(filters.TEXT, fallback_text))
    return application


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан. Останавливаюсь.")
        sys.exit(1)

    application = build_application()

    use_polling = "--polling" in sys.argv or not RENDER_EXTERNAL_URL

    if use_polling:
        logger.info("Запуск в режиме polling (для локального теста).")
        application.run_polling()
    else:
        # Это и есть "мини веб-сервис": run_webhook сам поднимает aiohttp-сервер
        # на нужном порту, что удовлетворяет требованиям Render Web Service
        # (Render проверяет, что приложение слушает $PORT).
        webhook_path = "webhook"
        webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/{webhook_path}"
        logger.info("Запуск в режиме webhook: %s", webhook_url)
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=webhook_path,
            webhook_url=webhook_url,
        )


if __name__ == "__main__":
    main()

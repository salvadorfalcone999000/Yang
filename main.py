import os
import threading
import telebot
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from flask import Flask

# ============== MINI WEBSERVER ДЛЯ RENDER ==============
app = Flask(__name__)


@app.route("/")
def home():
    return "🖥 PC Bot is alive!"


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_flask, daemon=True).start()
# =======================================================

TOKEN = os.environ.get("BOT_TOKEN", "8603946406:AAGez8zkqNPsTFEvNj45kO3dFgy2avmP-3s")
ADMIN_CHAT_IDS = [x.strip() for x in os.environ.get("ADMIN_CHAT_ID", "1509389908").split(",") if x.strip()]

if not TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения!")

bot = telebot.TeleBot(TOKEN)

# ===================== ДАННЫЕ (отредактируй под себя) =====================

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
    "Без видеокарты": 0,
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

CONTACT_BTN = "📱 Отправить номер телефона"

# Состояния пользователей храним в памяти процесса (этого достаточно для одного инстанса)
user_state = {}

# ===================== КЛАВИАТУРЫ =====================


def main_menu_kb():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🖥 Конфигуратор ПК", callback_data="menu_config"),
        InlineKeyboardButton("⚡ Подбор блока питания", callback_data="menu_psu"),
        InlineKeyboardButton("🔧 Ремонт техники", callback_data="menu_repair"),
        InlineKeyboardButton("ℹ️ О нас", callback_data="menu_about"),
    )
    return markup


def kb_from_dict(prefix, items):
    markup = InlineKeyboardMarkup(row_width=1)
    for name in items:
        markup.add(InlineKeyboardButton(name, callback_data=f"{prefix}|{name}"))
    return markup


def kb_from_list(prefix, items):
    markup = InlineKeyboardMarkup(row_width=1)
    for item in items:
        markup.add(InlineKeyboardButton(item, callback_data=f"{prefix}|{item}"))
    return markup


def contact_kb():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton(CONTACT_BTN, request_contact=True))
    return markup


def notify_admin(text):
    for chat_id in ADMIN_CHAT_IDS:
        try:
            bot.send_message(chat_id, text)
        except Exception as e:
            print(f"Не удалось отправить админу {chat_id}: {e}")


def calc_psu(cpu_name, gpu_name):
    cpu_w = CPU_LIST.get(cpu_name, 65)
    gpu_w = GPU_LIST.get(gpu_name, 0)
    recommended = round((cpu_w + gpu_w) * 1.4 / 50) * 50
    return max(recommended, 450), cpu_w, gpu_w


# ===================== /start и ГЛАВНОЕ МЕНЮ =====================


@bot.message_handler(commands=["start"])
def start(message):
    user_state[message.from_user.id] = {}
    bot.send_message(
        message.chat.id,
        "Привет! 👋 Это бот-помощник по сборке и ремонту компьютеров.\n\nВыбери, что нужно:",
        reply_markup=main_menu_kb(),
    )


@bot.message_handler(commands=["cancel"])
def cancel(message):
    user_state[message.from_user.id] = {}
    bot.send_message(message.chat.id, "Окей, отменил. Чтобы начать заново — /start", reply_markup=ReplyKeyboardRemove())


# ===================== ОБРАБОТКА INLINE-КНОПОК =====================


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data
    state = user_state.setdefault(user_id, {})

    # ---------- ГЛАВНОЕ МЕНЮ ----------
    if data == "menu_config":
        state["mode"] = "config"
        state["config"] = {}
        bot.edit_message_text("Выбери процессор:", chat_id, msg_id, reply_markup=kb_from_dict("cpu", CPU_LIST))

    elif data == "menu_psu":
        state["mode"] = "psu"
        state["psu"] = {}
        bot.edit_message_text("Подбор БП.\nВыбери процессор:", chat_id, msg_id, reply_markup=kb_from_dict("psucpu", CPU_LIST))

    elif data == "menu_repair":
        state["mode"] = "repair"
        state["repair"] = {}
        state["step"] = "desc"
        bot.edit_message_text(
            "Опиши кратко, что случилось с устройством "
            "(например: «не включается ноутбук», «разбит экран телефона»):",
            chat_id, msg_id,
        )

    elif data == "menu_about":
        bot.edit_message_text(
            "Мы собираем ПК под ключ и ремонтируем технику.\nЧтобы вернуться в меню — введи /start",
            chat_id, msg_id,
        )

    # ---------- КОНФИГУРАТОР ПК ----------
    elif data.startswith("cpu|"):
        state["config"]["cpu"] = data.split("|", 1)[1]
        bot.edit_message_text("Выбери видеокарту:", chat_id, msg_id, reply_markup=kb_from_dict("gpu", GPU_LIST))

    elif data.startswith("gpu|"):
        state["config"]["gpu"] = data.split("|", 1)[1]
        bot.edit_message_text("Выбери объём оперативной памяти:", chat_id, msg_id, reply_markup=kb_from_list("ram", RAM_LIST))

    elif data.startswith("ram|"):
        state["config"]["ram"] = data.split("|", 1)[1]
        bot.edit_message_text("Выбери накопитель:", chat_id, msg_id, reply_markup=kb_from_list("storage", STORAGE_LIST))

    elif data.startswith("storage|"):
        state["config"]["storage"] = data.split("|", 1)[1]
        bot.edit_message_text("Выбери корпус:", chat_id, msg_id, reply_markup=kb_from_list("case", CASE_LIST))

    elif data.startswith("case|"):
        state["config"]["case"] = data.split("|", 1)[1]
        cfg = state["config"]
        psu_w, cpu_w, gpu_w = calc_psu(cfg["cpu"], cfg["gpu"])
        cfg["psu"] = f"~{psu_w} Вт (рекомендация)"

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
        bot.edit_message_text(summary, chat_id, msg_id)
        state["step"] = "config_name"

    elif data.startswith("cfgservice|"):
        service = data.split("|", 1)[1]
        cfg = state["config"]
        cfg["service"] = service
        admin_text = (
            "🆕 Новая заявка — КОНФИГУРАТОР ПК\n\n"
            f"Имя: {cfg.get('name')}\n"
            f"Телефон: {cfg.get('phone')}\n"
            f"Способ получения: {service}\n\n"
            f"Процессор: {cfg.get('cpu')}\n"
            f"Видеокарта: {cfg.get('gpu')}\n"
            f"ОЗУ: {cfg.get('ram')}\n"
            f"Накопитель: {cfg.get('storage')}\n"
            f"Корпус: {cfg.get('case')}\n"
            f"Рекомендуемый БП: {cfg.get('psu')}"
        )
        notify_admin(admin_text)
        bot.edit_message_text(
            "Спасибо! Заявка отправлена, мы свяжемся с тобой в ближайшее время. 🙌\nЧтобы начать заново — /start",
            chat_id, msg_id,
        )
        user_state[user_id] = {}

    # ---------- ПОДБОР БП ----------
    elif data.startswith("psucpu|"):
        state["psu"]["cpu"] = data.split("|", 1)[1]
        bot.edit_message_text("Выбери видеокарту:", chat_id, msg_id, reply_markup=kb_from_dict("psugpu", GPU_LIST))

    elif data.startswith("psugpu|"):
        gpu_name = data.split("|", 1)[1]
        cpu_name = state["psu"]["cpu"]
        psu_w, cpu_w, gpu_w = calc_psu(cpu_name, gpu_name)
        bot.edit_message_text(
            f"Процессор: {cpu_name} (~{cpu_w} Вт)\n"
            f"Видеокарта: {gpu_name} (~{gpu_w} Вт)\n\n"
            f"💡 Рекомендуемая мощность БП: от {psu_w} Вт (с запасом на пики и апгрейд).\n\n"
            "Чтобы начать заново — /start, чтобы собрать полную сборку — открой «Конфигуратор ПК» в меню.",
            chat_id, msg_id,
        )
        user_state[user_id] = {}

    # ---------- РЕМОНТ ----------
    elif data.startswith("repairservice|"):
        service = data.split("|", 1)[1]
        rep = state["repair"]
        rep["service"] = service
        admin_text = (
            "🛠 Новая заявка — РЕМОНТ\n\n"
            f"Имя: {rep.get('name')}\n"
            f"Телефон: {rep.get('phone')}\n"
            f"Способ: {service}\n"
            f"Описание проблемы: {rep.get('desc')}"
        )
        notify_admin(admin_text)
        bot.edit_message_text(
            "Спасибо! Заявка на консультацию по ремонту отправлена, мы скоро свяжемся. 🙌\nЧтобы начать заново — /start",
            chat_id, msg_id,
        )
        user_state[user_id] = {}

    bot.answer_callback_query(call.id)


# ===================== ОБРАБОТКА ТЕКСТА И КОНТАКТА =====================


@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    user_id = message.from_user.id
    state = user_state.get(user_id, {})
    phone = message.contact.phone_number
    step = state.get("step")

    if step == "config_phone":
        state["config"]["phone"] = phone
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(
            message.chat.id, "Как удобнее получить/собрать ПК?",
            reply_markup=kb_from_list("cfgservice", SERVICE_OPTIONS),
        )
        state["step"] = None

    elif step == "repair_phone":
        state["repair"]["phone"] = phone
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(
            message.chat.id, "Как удобнее провести ремонт?",
            reply_markup=kb_from_list("repairservice", SERVICE_OPTIONS),
        )
        state["step"] = None


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id
    state = user_state.setdefault(user_id, {})
    step = state.get("step")
    text = message.text.strip()

    if step == "config_name":
        state["config"]["name"] = text
        bot.send_message(
            message.chat.id,
            "Отлично! Теперь отправь номер телефона кнопкой ниже или напиши его текстом:",
            reply_markup=contact_kb(),
        )
        state["step"] = "config_phone"
        return

    if step == "config_phone":
        state["config"]["phone"] = text
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(
            message.chat.id, "Как удобнее получить/собрать ПК?",
            reply_markup=kb_from_list("cfgservice", SERVICE_OPTIONS),
        )
        state["step"] = None
        return

    if step == "desc":
        state["repair"]["desc"] = text
        bot.send_message(message.chat.id, "Как к тебе обращаться? Напиши имя:")
        state["step"] = "repair_name"
        return

    if step == "repair_name":
        state["repair"]["name"] = text
        bot.send_message(
            message.chat.id,
            "Отправь номер телефона кнопкой ниже или напиши текстом:",
            reply_markup=contact_kb(),
        )
        state["step"] = "repair_phone"
        return

    if step == "repair_phone":
        state["repair"]["phone"] = text
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(
            message.chat.id, "Как удобнее провести ремонт?",
            reply_markup=kb_from_list("repairservice", SERVICE_OPTIONS),
        )
        state["step"] = None
        return

    bot.send_message(message.chat.id, "Не понял 🙂 Напиши /start чтобы открыть меню.")


# ===================== ЗАПУСК =====================

print("Бот запущен, мини веб-сервис поднят на Flask...")
bot.infinity_polling(skip_pending=True)

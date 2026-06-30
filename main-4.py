# -*- coding: utf-8 -*-
"""
Telegram-бот: ИИ-конфигуратор ПК (бесплатно, через OpenRouter), ручной
конфигуратор, подбор БП, заявки на ремонт.

Сделан на pyTelegramBotAPI (telebot) + мини веб-сервер на Flask в отдельном
потоке — рабочая, проверенная схема для Render.

Переменные окружения (Render -> Environment):
  BOT_TOKEN           - токен бота от @BotFather
  ADMIN_CHAT_ID       - твой chat_id (куда слать заявки), можно несколько через запятую
  OPENROUTER_API_KEY  - бесплатный ключ с openrouter.ai для ИИ-агента
  OPENROUTER_MODEL    - (необязательно) id бесплатной модели, по умолчанию
                         deepseek/deepseek-chat-v3-0324:free
  PORT                - подставляется Render автоматически, трогать не нужно
"""

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
import requests

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
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "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")
# Бесплатная модель на OpenRouter. Список бесплатных моделей периодически
# меняется — актуальный смотри на https://openrouter.ai/models?max_price=0
# Можно переопределить через переменную окружения OPENROUTER_MODEL.
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")

if not TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения!")

bot = telebot.TeleBot(TOKEN)
AI_ENABLED = bool(OPENROUTER_API_KEY)

# ===================== ДАННЫЕ ДЛЯ РУЧНОГО КОНФИГУРАТОРА И ПОДБОРА БП =====================

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
AI_FINISH_BTN = "✅ Готово, оформить заявку"
AI_RESTART_BTN = "🔄 Начать подбор заново"

# Состояния пользователей храним в памяти процесса
user_state = {}

# ===================== СИСТЕМНЫЙ ПРОМПТ ДЛЯ ИИ-АГЕНТА =====================

AI_SYSTEM_PROMPT = """Ты — опытный консультант компьютерного магазина и сборщик ПК.
Твоя задача в диалоге с клиентом подобрать ПОЛНУЮ сборку ПК под его задачи и бюджет.

Обязательно учитывай и предлагай ВСЕ компоненты:
- Процессор (CPU)
- Материнскую плату (сокет/чипсет должны совпадать с процессором)
- Оперативную память (объём, частота)
- Видеокарту (или без неё, если задачи офисные)
- Накопитель (SSD/HDD, объём)
- Систему охлаждения — обязательно уточни и предложи конкретный тип:
  боксовый кулер (входит в комплект CPU), башенный воздушный кулер,
  или жидкостное охлаждение (СВО/AIO 240/280/360мм) — в зависимости
  от мощности процессора и бюджета.
- Корпус — обязательно уточни и предложи форм-фактор (ATX, Micro-ATX, Mini-ITX)
  в зависимости от размера материнской платы и пожеланий клиента (компактность,
  вид через стекло, поток воздуха и т.д.).
- Блок питания (рассчитывай мощность с запасом ~30-40% от пиковой нагрузки CPU+GPU).

Стиль общения:
- Общайся живо, по-человечески, на русском языке, без канцелярита.
- Сначала кратко уточни 2-4 ключевых вопроса: бюджет, для чего ПК
  (игры/работа/монтаж/офис), есть ли предпочтения по бренду (Intel/AMD,
  Nvidia/AMD), нужна ли тишина или важнее производительность, нужен ли
  Wi-Fi в материнке.
- Не закидывай клиента стеной вопросов сразу — задавай по 2-3 вопроса
  за раз, диалог должен быть живым.
- Когда информации достаточно — предложи 1-2 варианта сборки (можно
  "оптимальный" и "с запасом на будущее"), указав КОНКРЕТНЫЕ модели по
  каждому компоненту из списка выше, включая охлаждение и корпус с
  форм-фактором.
- В конце сборки явно укажи итоговый список компонентов в виде понятного
  перечня (каждый компонент на отдельной строке).
- Если клиент просит что-то поменять — корректируй сборку.
- Никогда не отвечай вне темы подбора/сборки ПК — вежливо возвращай к теме.
- Не указывай точные цены в рублях/гривнах (цены и наличие уточнит менеджер),
  можно говорить об уровне сборки (бюджетная/средняя/топовая).
"""

# ===================== КЛАВИАТУРЫ =====================


def main_menu_kb():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🤖 ИИ-подбор сборки ПК", callback_data="menu_ai_config"),
        InlineKeyboardButton("🖥 Конфигуратор ПК (вручную)", callback_data="menu_config"),
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


def ai_chat_kb():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(AI_FINISH_BTN, callback_data="ai_finish"),
        InlineKeyboardButton(AI_RESTART_BTN, callback_data="ai_restart"),
    )
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


def ask_ai(history):
    """Отправляет историю диалога в OpenRouter (бесплатная модель) и возвращает ответ."""
    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}]
    for m in history:
        role = "assistant" if m["role"] == "assistant" else "user"
        messages.append({"role": role, "content": m["content"]})

    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "max_tokens": 1000,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


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
    if data == "menu_ai_config":
        if not AI_ENABLED:
            bot.edit_message_text(
                "ИИ-подбор временно недоступен (не настроен ключ ИИ). "
                "Попробуй «Конфигуратор ПК (вручную)» или напиши нам напрямую.",
                chat_id, msg_id, reply_markup=main_menu_kb(),
            )
        else:
            state.clear()
            state["mode"] = "ai_config"
            state["step"] = "ai_chat"
            state["ai_history"] = []
            bot.edit_message_text(
                "🤖 Я помогу подобрать сборку под твои задачи и бюджет.\n\n"
                "Расскажи: для чего нужен ПК (игры/работа/монтаж/офис), "
                "какой примерно бюджет и есть ли предпочтения по железу "
                "(Intel/AMD, Nvidia/AMD)?",
                chat_id, msg_id,
            )

    elif data == "menu_config":
        state.clear()
        state["mode"] = "config"
        state["config"] = {}
        bot.edit_message_text("Выбери процессор:", chat_id, msg_id, reply_markup=kb_from_dict("cpu", CPU_LIST))

    elif data == "menu_psu":
        state.clear()
        state["mode"] = "psu"
        state["psu"] = {}
        bot.edit_message_text("Подбор БП.\nВыбери процессор:", chat_id, msg_id, reply_markup=kb_from_dict("psucpu", CPU_LIST))

    elif data == "menu_repair":
        state.clear()
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

    # ---------- ИИ-КОНФИГУРАТОР ----------
    elif data == "ai_restart":
        state["ai_history"] = []
        state["step"] = "ai_chat"
        bot.edit_message_text(
            "Окей, начнём заново 🔄\n\nРасскажи: для чего нужен ПК, какой бюджет "
            "и есть ли предпочтения по железу?",
            chat_id, msg_id,
        )

    elif data == "ai_finish":
        state["step"] = "ai_name"
        bot.edit_message_text(
            "Отлично! Чтобы менеджер посчитал точную стоимость и наличие — "
            "напиши, пожалуйста, своё имя:",
            chat_id, msg_id,
        )

    # ---------- РУЧНОЙ КОНФИГУРАТОР ПК ----------
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
            "🆕 Новая заявка — КОНФИГУРАТОР ПК (ручной)\n\n"
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
            "Чтобы начать заново — /start, чтобы собрать полную сборку — открой «ИИ-подбор» или «Конфигуратор» в меню.",
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
            "Спасибо! Заявка на консультацию по ремонту отправлена, мы скоро свяжемся. 🙌\nЧто начать заново — /start",
            chat_id, msg_id,
        )
        user_state[user_id] = {}

    bot.answer_callback_query(call.id)


# ===================== ОБРАБОТКА КОНТАКТА (кнопкой) =====================


@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    user_id = message.from_user.id
    state = user_state.get(user_id, {})
    phone = message.contact.phone_number
    step = state.get("step")

    if step == "config_phone":
        state["config"]["phone"] = phone
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(message.chat.id, "Как удобнее получить/собрать ПК?", reply_markup=kb_from_list("cfgservice", SERVICE_OPTIONS))
        state["step"] = None

    elif step == "repair_phone":
        state["repair"]["phone"] = phone
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(message.chat.id, "Как удобнее провести ремонт?", reply_markup=kb_from_list("repairservice", SERVICE_OPTIONS))
        state["step"] = None

    elif step == "ai_phone":
        state["ai_phone"] = phone
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(message.chat.id, "Как удобнее получить/собрать ПК?", reply_markup=kb_from_list("aiservice", SERVICE_OPTIONS))
        state["step"] = "ai_service"


# отдельный хендлер для финального способа получения в ИИ-режиме
@bot.callback_query_handler(func=lambda call: call.data.startswith("aiservice|"))
def ai_service_chosen(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    state = user_state.setdefault(user_id, {})
    service = call.data.split("|", 1)[1]

    history_text = ""
    for m in state.get("ai_history", []):
        role = "Клиент" if m["role"] == "user" else "ИИ-консультант"
        content = m["content"] if isinstance(m["content"], str) else str(m["content"])
        history_text += f"{role}: {content}\n\n"

    admin_text = (
        "🤖 Новая заявка — ИИ-ПОДБОР СБОРКИ ПК\n\n"
        f"Имя: {state.get('ai_name')}\n"
        f"Телефон: {state.get('ai_phone')}\n"
        f"Способ получения: {service}\n\n"
        "Переписка с ИИ-консультантом:\n"
        f"{history_text}"
    )
    notify_admin(admin_text)

    bot.edit_message_text(
        "Спасибо! Заявка с подобранной сборкой отправлена менеджеру, мы скоро свяжемся. 🙌\nЧтобы начать заново — /start",
        chat_id, msg_id,
    )
    user_state[user_id] = {}
    bot.answer_callback_query(call.id)


# ===================== ОБРАБОТКА ТЕКСТА =====================


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id
    state = user_state.setdefault(user_id, {})
    step = state.get("step")
    text = message.text.strip()

    # ---------- ИИ-КОНФИГУРАТОР: свободный диалог ----------
    if step == "ai_chat":
        state.setdefault("ai_history", []).append({"role": "user", "content": text})
        bot.send_chat_action(message.chat.id, "typing")
        try:
            reply = ask_ai(state["ai_history"])
        except Exception as e:
            print(f"Ошибка ИИ-API: {e}")
            bot.send_message(
                message.chat.id,
                "Упс, не получилось связаться с ИИ-консультантом. Попробуй ещё раз чуть позже "
                "или воспользуйся «Конфигуратор ПК (вручную)» в меню /start.",
            )
            return
        state["ai_history"].append({"role": "assistant", "content": reply})
        bot.send_message(message.chat.id, reply, reply_markup=ai_chat_kb())
        return

    if step == "ai_name":
        state["ai_name"] = text
        bot.send_message(
            message.chat.id,
            "Отправь номер телефона кнопкой ниже или напиши его текстом:",
            reply_markup=contact_kb(),
        )
        state["step"] = "ai_phone"
        return

    if step == "ai_phone":
        state["ai_phone"] = text
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(message.chat.id, "Как удобнее получить/собрать ПК?", reply_markup=kb_from_list("aiservice", SERVICE_OPTIONS))
        state["step"] = "ai_service"
        return

    # ---------- РУЧНОЙ КОНФИГУРАТОР ----------
    if step == "config_name":
        state["config"]["name"] = text
        bot.send_message(message.chat.id, "Отлично! Теперь отправь номер телефона кнопкой ниже или напиши его текстом:", reply_markup=contact_kb())
        state["step"] = "config_phone"
        return

    if step == "config_phone":
        state["config"]["phone"] = text
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(message.chat.id, "Как удобнее получить/собрать ПК?", reply_markup=kb_from_list("cfgservice", SERVICE_OPTIONS))
        state["step"] = None
        return

    # ---------- РЕМОНТ ----------
    if step == "desc":
        state["repair"]["desc"] = text
        bot.send_message(message.chat.id, "Как к тебе обращаться? Напиши имя:")
        state["step"] = "repair_name"
        return

    if step == "repair_name":
        state["repair"]["name"] = text
        bot.send_message(message.chat.id, "Отправь номер телефона кнопкой ниже или напиши текстом:", reply_markup=contact_kb())
        state["step"] = "repair_phone"
        return

    if step == "repair_phone":
        state["repair"]["phone"] = text
        bot.send_message(message.chat.id, "Номер получен ✅", reply_markup=ReplyKeyboardRemove())
        bot.send_message(message.chat.id, "Как удобнее провести ремонт?", reply_markup=kb_from_list("repairservice", SERVICE_OPTIONS))
        state["step"] = None
        return

    bot.send_message(message.chat.id, "Не понял 🙂 Напиши /start чтобы открыть меню.")


# ===================== ЗАПУСК =====================

print("Бот запущен, мини веб-сервис поднят на Flask...")
bot.infinity_polling(skip_pending=True)

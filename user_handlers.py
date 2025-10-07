from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
import db
from db import get_all_services, get_available_slots, book_slot, get_user_booked_slots, cancel_slot, get_slots_by_service, add_service_request
import config
from states import BookingForm, EditRequestForm, DeleteRequestForm, TravelRequestForm, MasterForm
from config import ADMIN_IDS, ACCOUNTANT_IDS, MASTER_IDS
import calendar


user_router = Router()

# FSM формы
class OfferForm(StatesGroup):
    text = State()

class TravelForm(StatesGroup):
    date = State()
    car_number = State()
    cargo = State()

class TravelRequestForm(StatesGroup):
    vehicle_type = State()
    date_time = State()    # дата и время поездки
    car_number = State()   # номер машины
    purpose = State()      # цель поездки

@user_router.message(F.text == "Отмена", StateFilter("*"))
async def alias_cancel(message: types.Message, state: FSMContext):
    return await cmd_cancel(message, state)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    Возвращает Reply-клавиатуру с одной кнопкой «/cancel».
    """
    builder = ReplyKeyboardBuilder()
    builder.button(text="Отмена")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

def get_main_keyboard(tg_id: int) -> ReplyKeyboardMarkup:
    """
    Возвращает Reply-клавиатуру с человекочитаемыми кнопками,
    соответствующими ролям пользователя tg_id.
    """
    builder = ReplyKeyboardBuilder()

    # — Общие для всех —
    if (tg_id not in config.MASTER_IDS and tg_id not in config.ACCOUNTANT_IDS) or (tg_id in config.ADMIN_IDS):
        builder.button(text="Новости")                   # /news
        builder.button(text="События")                   # /events
        builder.button(text="Услуги")                    # /services
        builder.button(text="Записаться на услугу")      # /book_service
        builder.button(text="Изменить свою заявку")      # /edit_service_requests
        builder.button(text="Удалить свою заявку")       # /delete_service_requests
        builder.button(text="Заявка на проезд")          # /request_travel
        # builder.button(text="Отмена")                    # /cancel

    # — Админ —
    if tg_id in config.ADMIN_IDS:
        builder.button(text="Добавить новость")      # /add_news
        builder.button(text="Редактировать новость") # /edit_news
        builder.button(text="Удалить новость")       # /delete_news

        builder.button(text="Создать событие")       # /create_event
        builder.button(text="Изменить событие")      # /create_event
        builder.button(text="Удалить событие")       # /create_event

        builder.button(text="Добавить услугу")      # /add_service
        builder.button(text="Изменить услугу")      # /edit_service
        builder.button(text="Удалить услугу")       # /delete_service

        builder.button(text="Создать слот")         # /create_slot
        builder.button(text="Изменить слот")        # /edit_slot
        builder.button(text="Удалить слот")         # /delete_slot

        builder.button(text="Заявки на проезд")     # /travel_requests

    # — Бухгалтер —
    if tg_id in config.ACCOUNTANT_IDS:
        builder.button(text="Неоплаченные счета")           # /pending_invoices
        builder.button(text="Импортировать взносы")         # /import_contributions
        builder.button(text="Создать счет")                # /generate_contributions
        builder.button(text="Напомнить должникам")          # /send_reminders
        builder.button(text="Экспортировать взносы")         # /export_contributions
        builder.button(text="Напомнить о событиях")         # /send_event_reminders
        builder.button(text="Напомнить о визите мастера")   # /send_service_reminders

    # — Мастер —
    if tg_id in config.MASTER_IDS:
        builder.button(text="Меню мастера")                 # /master

    # раскладываем по 2 кнопки в ряд
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# /start
@user_router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user = message.from_user
    kb = get_main_keyboard(user.id)
    db.add_user(
        user.id,
        f"{user.first_name} {user.last_name or ''}".strip(),
        user.last_name or "",
        user.username or ""
    )
    await message.answer("Добро пожаловать в бот Долматово! Введите /help для справки.", reply_markup=kb)
    await state.clear()

    # если это мастер и у него ещё не сохранён телефон — запрашиваем контакт
    if user.id in MASTER_IDS:
        user_id = db.get_user_id_by_tg(user.id)
        row = db.conn.execute(
            "SELECT phone FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        # если столбца phone нет или он пустой/NULL — запрашиваем
        if not row or not row[0]:
            builder = ReplyKeyboardBuilder()
            builder.button(text="Поделиться контактом", request_contact=True)
            builder.adjust(1)
            await message.answer(
                "Похоже, вы мастер.\nПожалуйста, поделитесь своим номером телефона:",
                reply_markup=builder.as_markup(resize_keyboard=True)
            )
            await state.set_state(MasterForm.wait_contact)


# /cancel
@user_router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        await message.reply("Нет активной операции.", reply_markup=get_main_keyboard(message.from_user.id))
    else:
        await state.clear()
        await message.reply("🚫 Операция отменена.", reply_markup=get_main_keyboard(message.from_user.id))



# /help
@user_router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = "Доступные команды:\n"
    # Общие команды

    if (message.from_user.id not in config.MASTER_IDS and message.from_user.id not in config.ACCOUNTANT_IDS) or (message.from_user.id in config.ADMIN_IDS):
        help_text += "/start - начать работу с ботом\n"
        help_text += "/help - показать это справочное сообщение\n"
        help_text += "/news - посмотреть объявления (новости)\n"
        help_text += "/events - список мероприятий\n"
        help_text += "/services - список доступных услуг\n"
        help_text += "/book_service - записаться на услугу\n"
        help_text += "/request_travel - подать заявку на проезд\n"
        help_text += "/cancel - отменить текущую операцию\n"
    # Админские команды
    # print(message.from_user.id)
    if message.from_user.id in ADMIN_IDS:
        help_text += "\nКоманды администратора:\n"
        help_text += "/add_news - добавить новость\n"
        help_text += "/edit_news - редактировать новость\n"
        help_text += "/add_event - создать мероприятие\n"
        help_text += "/add_service - добавить услугу\n"
        help_text += "/edit_service - переименовать услугу\n"
        help_text += "/delete_service - удалить услугу\n"
        help_text += "/create_slot - создать тайм-слот услуги\n"
        help_text += "/travel_requests - показать заявки на проезд\n"
    if message.from_user.id in ACCOUNTANT_IDS:
        help_text += "\nКоманды бухгалтера:\n"
        help_text += "/pending_invoices — список неоплаченных счетов\n"
        help_text += "/import_contributions — импорт списка взносов из CSV\n"
        help_text += "/generate_contributions — создать счет за текущий месяц выбранному пользователю\n"
        help_text += "/export_contributions — экспорт списка всех взносов в CSV\n"
        help_text += "/send_reminders — разослать напоминания должникам\n"
        help_text += "/send_event_reminders — разослать напоминания о мероприятиях сегодня\n"
        help_text += "/send_service_reminders — разослать напоминания о визите мастера завтра\n"
        help_text += "/cancel — отменить текущее действие\n"
    if message.from_user.id in MASTER_IDS:
        help_text += "\nКоманды мастера:\n"
        help_text += "/master - все функции мастера\n"
    await message.answer(text=help_text)

# /news
@user_router.message(Command("news"))
async def cmd_news(message: types.Message):
    all_news = db.get_all_news()
    if not all_news:
        await message.answer("Новостей нет.")
        return
    pinned = [n for n in all_news if n["pinned"]]
    regular = [n for n in all_news if not n["pinned"]]

    lines = []
    for news in pinned:
        lines.append(f"📌 <b>{news['id']}: {news['title']} ({news['date']})</b>\n{news['text']}\n")
    for news in regular:
        lines.append(f"{news['id']}: <b>{news['title']} ({news['date']})</b>\n{news['text']}\n")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_main_keyboard(message.from_user.id))


# /events
@user_router.message(Command("events"))
async def cmd_events(message: types.Message):
    upcoming = db.get_upcoming_events()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.cursor.execute("SELECT id, title, description, datetime, location FROM events WHERE datetime < ? ORDER BY datetime DESC", (now_str,))
    past_rows = db.cursor.fetchall()
    past = [{"id": r[0], "title": r[1], "description": r[2], "datetime": r[3], "location": r[4]} for r in past_rows]

    if not upcoming and not past:
        await message.answer("Событий нет.")
        return

    lines = []
    if upcoming:
        lines.append("🎉 <b>Ближайшие события:</b>")
        for ev in upcoming:
            lines.append(f"{ev['id']}: {ev['title']}\n    Дата: {ev['datetime']}\n    Что будет?: {ev['description']}\n    Где?: {ev['location']}")
    if past:
        lines.append("\n🕓 <b>Прошедшие события:</b>")
        for ev in past:
            lines.append(f"{ev['id']}: {ev['title']}\n    Дата: {ev['datetime']}\n    Что будет?: {ev['description']}\n    Где?: {ev['location']}")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_main_keyboard(message.from_user.id))

# /services
@user_router.message(Command("services"))
async def admin_list_services(message: types.Message):
    """
    Выводит полный список услуг из каталога (только для админов).
    """
    services = db.get_all_services()
    if not services:
        return await message.reply("Каталог услуг пуст.")
    text_lines = ["📋 Список услуг:"]
    for svc in services:
        text_lines.append(f"{svc['id']}: {svc['name']} ({svc.get("price")} ₽)")
    await message.reply("\n".join(text_lines), reply_markup=get_main_keyboard(message.from_user.id))

#1) /add_service — заказ услуги (аналог /book, но создаёт запись в service_requests)
@user_router.message(Command("book_service"))
async def cmd_add_service(message: types.Message, state: FSMContext):
    services = db.get_all_services()
    if not services:
        return await message.reply("❌ Услуг нет.")

    await message.answer(
        "Вы в режиме записи на услугу. Чтобы отменить — нажмите «Отмена».",
        reply_markup=get_cancel_keyboard()
    )

    builder = InlineKeyboardBuilder()
    for svc in services:
        builder.button(
            text=f"{svc['name']} ({svc['price']} ₽)",
            callback_data=f"ord:svc:{svc['id']}"
        )
    # one button per row:
    builder.adjust(1)
    kb = builder.as_markup()
    text = "Выберите услугу:\n"
    await message.reply(text + "\n", reply_markup=kb)
    await state.set_state(BookingForm.service)

# @user_router.callback_query(
#     lambda c: c.data and c.data.startswith("ord:svc:"),
#     StateFilter(BookingForm.service)
# )
# async def add_service_choose(cq: types.CallbackQuery, state: FSMContext):
#     svc_id = int(cq.data.split(":", 2)[2])
#     svc   = db.get_service(svc_id)
#     if not svc:
#         await cq.answer("❌ Услуга не найдена.", show_alert=True)
#         return
#
#     await state.update_data(service_id=svc_id, service_name=svc["name"])
#     slots = get_slots_by_service(svc_id)
#     if not slots:
#         await state.clear()
#         await cq.message.edit_text("❌ Нет свободных слотов.")
#         await cq.message.answer(
#             "Чем ещё могу помочь?",
#             reply_markup=get_main_keyboard(cq.from_user.id)
#         )
#         await cq.answer()
#         return
#
#     builder = InlineKeyboardBuilder()
#     for sl in slots:
#         builder.button(
#             text=sl["datetime"],
#             callback_data=f"ord:slot:{sl['id']}"
#         )
#     builder.adjust(1)
#     kb = builder.as_markup()
#
#     await state.set_state(BookingForm.slot)
#     await cq.message.edit_text(f"Свободные слоты для «{svc['name']}»:",
#                                reply_markup=kb)
#     await cq.answer()

@user_router.callback_query(
    lambda c: c.data and c.data.startswith("ord:svc:"),
    StateFilter(BookingForm.service)
)
async def add_service_choose(cq: types.CallbackQuery, state: FSMContext):
    svc_id = int(cq.data.split(":", 2)[2])
    svc    = db.get_service(svc_id)
    if not svc:
        await cq.answer("❌ Услуга не найдена.", show_alert=True)
        return

    # сохраняем id и имя
    await state.update_data(service_id=svc_id, service_name=svc["name"])

    # предлагаем выбрать год (текущий и следующий)
    this_year = datetime.now().year
    years = [this_year, this_year + 1]
    builder = InlineKeyboardBuilder()
    for y in years:
        builder.button(text=str(y), callback_data=f"book:year:{y}")
    builder.adjust(2)
    await cq.message.edit_text("📅 Выберите год:", reply_markup=builder.as_markup())
    await state.set_state(BookingForm.date_year)
    await cq.answer()

# выбор года

@user_router.callback_query(
    lambda c: c.data and c.data.startswith("book:year:"),
    StateFilter(BookingForm.date_year)
)
async def choose_year(cq: types.CallbackQuery, state: FSMContext):
    year = int(cq.data.split(":", 2)[2])
    await state.update_data(year=year)

    # предлагаем выбрать месяц
    builder = InlineKeyboardBuilder()
    for m in range(1, 13):
        builder.button(text=str(m), callback_data=f"book:month:{m}")
    builder.adjust(4)
    await cq.message.edit_text("📅 Выберите месяц:", reply_markup=builder.as_markup())
    await state.set_state(BookingForm.date_month)
    await cq.answer()

# выбор месяца

@user_router.callback_query(
    lambda c: c.data and c.data.startswith("book:month:"),
    StateFilter(BookingForm.date_month)
)
async def choose_month(cq: types.CallbackQuery, state: FSMContext):
    month = int(cq.data.split(":", 2)[2])
    data = await state.get_data()
    year = data["year"]
    await state.update_data(month=month)

    # определяем, какие дни в этом месяце есть вообще,
    # но показавем только те даты, где есть слоты
    svc_id = data["service_id"]
    all_slots = get_slots_by_service(svc_id)
    # формируем множество дней, на которые есть слоты
    days_with = {
        int(s["datetime"][8:10])
        for s in all_slots
        if int(s["datetime"][:4]) == year and int(s["datetime"][5:7]) == month
    }
    if not days_with:
        await cq.answer("На этот месяц слотов нет, выберите другой.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for day in sorted(days_with):
        builder.button(text=str(day), callback_data=f"book:day:{day}")
    builder.adjust(6)
    await cq.message.edit_text("📅 Выберите число:", reply_markup=builder.as_markup())
    await state.set_state(BookingForm.date_day)
    await cq.answer()

# выбор дня

# @user_router.callback_query(
#     lambda c: c.data and c.data.startswith("book:day:"),
#     StateFilter(BookingForm.date_day)
# )
# async def choose_day(cq: types.CallbackQuery, state: FSMContext):
#     day = int(cq.data.split(":", 2)[2])
#     data = await state.get_data()
#     year = data["year"]
#     month = data["month"]
#     svc_id = data["service_id"]
#     svc_name = data["service_name"]
#
#     # собираем слоты строго на эту дату
#     date_prefix = f"{year:04d}-{month:02d}-{day:02d}"
#     all_slots = get_slots_by_service(svc_id)
#     day_slots = [s for s in all_slots if s["datetime"].startswith(date_prefix)]
#     if not day_slots:
#         await cq.answer("На этот день слотов нет, выберите другое.", show_alert=True)
#         return
#
#     builder = InlineKeyboardBuilder()
#     for sl in day_slots:
#         # сохраняем старый префикс ord:slot:
#         builder.button(text=sl["datetime"][11:16], callback_data=f"ord:slot:{sl['id']}")
#     builder.adjust(3)
#     await cq.message.edit_text(f"Свободные слоты для «{svc_name}» на {date_prefix}:", reply_markup=builder.as_markup())
#     await state.set_state(BookingForm.slot)
#     await cq.answer()


@user_router.callback_query(
    lambda c: c.data and c.data.startswith("book:day:"),
    StateFilter(BookingForm.date_day)
)
async def choose_day(cq: types.CallbackQuery, state: FSMContext):
    data     = await state.get_data()
    year     = data["year"]
    month    = data["month"]
    svc_id   = data["service_id"]
    svc_name = data["service_name"]
    day      = int(cq.data.split(":", 2)[2])
    date_prefix = f"{year:04d}-{month:02d}-{day:02d}"

    all_slots = get_slots_by_service(svc_id)
    day_slots = [s for s in all_slots if s["datetime"].startswith(date_prefix)]
    if not day_slots:
        await cq.answer("На эту дату нет свободных слотов, выберите другую.", show_alert=True)
        return

    # берём первый слот
    slot_id = day_slots[0]["id"]
    tg_id   = cq.from_user.id
    user_id = db.get_user_id_by_tg(tg_id) or db.add_user(
        tg_id,
        f"{cq.from_user.first_name} {cq.from_user.last_name or ''}".strip(),
        cq.from_user.last_name or "",
        cq.from_user.username or ""
    )

    # резервируем и создаём заявку
    book_slot(slot_id, user_id)
    req_id = db.add_service_request(svc_id, slot_id, user_id)

    # Шаг 1: меняем старое сообщение (убираем inline‑кнопки)
    await cq.message.edit_text(
        f"✅ Вы записаны на услугу «{svc_name}» на {date_prefix}.\n"
        f"Это ваш номер в очереди (заявка #{req_id})."
    )

    # Шаг 2: отправляем новое сообщение с Reply‑клавиатурой
    await cq.message.answer(
        "Чем ещё могу помочь?",
        reply_markup=get_main_keyboard(tg_id)
    )

    db.log_action(user_id, f"User создал заявку #{req_id} на услугу ID={svc_id}")
    await state.clear()
    await cq.answer()


# 2) /edit_service — переназначить слот для НЕ взятой мастером заявки
@user_router.message(Command("edit_service_requests"))
async def cmd_edit_service(message: types.Message, state: FSMContext):
    user_id = db.get_user_id_by_tg(message.from_user.id)
    reqs = db.get_user_service_requests(user_id, statuses=["new"])
    if not reqs:
        return await message.reply("У вас нет заявок, которые можно изменить.")
    text = "Ваши незанятые заявки:\n" + "\n".join(
        f"{r['id']}: {r['service_name']} @{r['slot_datetime']}" for r in reqs
    )
    await message.reply(text + "\n\nВведите ID заявки для изменения:", reply_markup=get_cancel_keyboard())
    await state.set_state(EditRequestForm.request_id)

@user_router.message(EditRequestForm.request_id)
async def edit_service_select(message: types.Message, state: FSMContext):
    try:
        req_id = int(message.text.strip())
    except:
        return await message.reply("Неверный ID заявки.")
    req = db.get_service_request(req_id)
    if not req or req["status"] != "new" or req["user_id"] != db.get_user_id_by_tg(message.from_user.id):
        return await message.reply("Заявка не найдена или её нельзя изменить.")
    await state.update_data(request_id=req_id, service_id=req["service_id"])
    # показываем слоты по той же услуге
    slots = db.get_available_slots(req["service_id"])
    if not slots:
        await state.clear()
        return await message.reply("Нет свободных слотов.")
    text = "Выберите новый слот:\n" + "\n".join(f"{sl['id']}: {sl['datetime']}" for sl in slots)
    await message.reply(text + "\n", reply_markup=get_cancel_keyboard())
    await state.set_state(EditRequestForm.new_slot)  # -> new_slot

@user_router.message(EditRequestForm.new_slot)
async def edit_service_slot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    req_id = data["request_id"]
    new_slot_id = int(message.text.strip())
    req = db.get_service_request(req_id)
    old_slot_id = req["slot_id"]
    user_id = req["user_id"]
    # освобождаем старый слот, резервируем новый
    db.book_slot(new_slot_id, user_id)
    cursor = db.conn.cursor()
    cursor.execute("UPDATE slots SET booked_by = NULL WHERE id = ?", (old_slot_id,))
    db.conn.commit()
    # обновляем заявку
    db.conn.execute("UPDATE service_requests SET slot_id = ? WHERE id = ?", (new_slot_id, req_id))
    db.conn.commit()
    await message.reply(f"✅ Заявка #{req_id} переназначена на слот {new_slot_id}.", reply_markup=get_main_keyboard(message.from_user.id))
    db.log_action(user_id, f"User изменил заявку #{req_id} на слот {new_slot_id}")
    await state.clear()

# 3) /delete_service — отменить НЕ взятую мастером заявку
@user_router.message(Command("delete_service_requests"))
async def cmd_delete_service(message: types.Message, state: FSMContext):
    user_id = db.get_user_id_by_tg(message.from_user.id)
    reqs = db.get_user_service_requests(user_id, statuses=["new"])
    if not reqs:
        return await message.reply("У вас нет заявок для отмены.")
    text = "Ваши незанятые заявки:\n" + "\n".join(
        f"{r['id']}: {r['service_name']} @{r['slot_datetime']}" for r in reqs
    )
    await message.reply(text + "\n\nВведите ID заявки для отмены:", reply_markup=get_cancel_keyboard())
    await state.set_state(DeleteRequestForm.request_id)

@user_router.message(DeleteRequestForm.request_id)
async def delete_service_req(message: types.Message, state: FSMContext):
    req_id = int(message.text.strip())
    req = db.get_service_request(req_id)
    if not req or req["status"] != "new" or req["user_id"] != db.get_user_id_by_tg(message.from_user.id):
        return await message.reply("Заявка не найдена или её нельзя отменить.")
    # освобождаем слот и помечаем заявку
    cursor = db.conn.cursor()
    cursor.execute("UPDATE slots SET booked_by = NULL WHERE id = ?", (req["slot_id"],))
    cursor.execute("UPDATE service_requests SET status = 'canceled' WHERE id = ?", (req_id,))
    db.conn.commit()
    await message.reply(f"❌ Заявка #{req_id} отменена.", reply_markup=get_main_keyboard(message.from_user.id))
    db.log_action(req["user_id"], f"User отменил заявку #{req_id}")
    await state.clear()

# /book — пока заготовка
# @user_router.message(Command("book"), StateFilter("*"))
# async def cmd_order_service_start(message: types.Message, state: FSMContext):
#     svcs = get_all_services()
#     kb   = types.InlineKeyboardMarkup(
#         inline_keyboard=[
#             [ types.InlineKeyboardButton(
#                   s["name"],
#                   callback_data=f"ord:svc:{s['id']}"
#               )
#             ] for s in svcs
#         ]
#     )
#     await state.set_state(BookingForm.service)
#     await message.reply("Выберите услугу:", reply_markup=kb)
#
# @user_router.callback_query(lambda c: c.data and c.data.startswith("ord:svc:"), StateFilter(BookingForm.service))
# async def cmd_order_service_service_chosen(cq: types.CallbackQuery, state: FSMContext):
#     svc_id = int(cq.data.split(":")[2])
#     slots  = get_available_slots(svc_id)
#     if not slots:
#         return await cq.answer("Нет свободных слотов.", show_alert=True)
#     builder = InlineKeyboardBuilder()
#     for sl in slots:
#         builder.button(
#             text=sl["datetime"],
#             callback_data=f"ord:slot:{sl['id']}"
#         )
#     # Разместим по одной кнопке в строке
#     builder.adjust(1)
#     kb = builder.as_markup()
#     await state.update_data(service_id=svc_id)
#     await state.set_state(BookingForm.slot)
#     await cq.message.edit_text("Выберите слот:", reply_markup=kb)
#     await cq.answer()
#
# @user_router.callback_query(lambda c: c.data and c.data.startswith("ord:slot:"), StateFilter(BookingForm.slot))
# async def cmd_order_service_slot_chosen(cq: types.CallbackQuery, state: FSMContext):
#     slot_id = int(cq.data.split(":")[2])
#     user_id = db.get_user_id_by_tg(cq.from_user.id)
#     book_slot(slot_id, user_id)
#     await cq.message.edit_text(f"✅ Вы записались на слот ID {slot_id}.", reply_markup=get_main_keyboard(cq.from_user.id))
#     await cq.answer()
#     await state.clear()

@user_router.message(Command("cancel_order"), StateFilter("*"))
async def cmd_cancel_order_start(message: types.Message, state: FSMContext):
    user_id = db.get_user_id_by_tg(message.from_user.id)
    slots   = get_user_booked_slots(user_id)
    if not slots:
        return await message.reply("У вас нет записей.")
    builder = InlineKeyboardBuilder()
    for sl in slots:
        builder.button(
            text=f"{sl['id']} — {sl['datetime']}",
            callback_data=f"cad:slot:{sl['id']}"
        )
    # Размещаем по одной кнопке в строке
    builder.adjust(1)
    kb = builder.as_markup()
    await state.set_state(BookingForm.slot)
    await message.reply("Выберите слот для отмены:", reply_markup=kb)

@user_router.callback_query(lambda c: c.data and c.data.startswith("cad:slot:"), StateFilter(BookingForm.slot))
async def cmd_cancel_order_slot_chosen(cq: types.CallbackQuery):
    slot_id = int(cq.data.split(":")[2])
    cancel_slot(slot_id)
    await cq.message.edit_text(f"❌ Ваша запись на слот ID {slot_id} отменена.", reply_markup=get_main_keyboard(cq.from_user.id))
    await cq.answer()

# /request_travel
# @user_router.message(Command("request_travel"))
# async def cmd_request_travel(message: types.Message, state: FSMContext):
#     await state.set_state(TravelRequestForm.description)
#     await message.reply("Введите детали заявки на проезд:\n(например, дата, машина, цель)")
#
# @user_router.message(TravelRequestForm.description)
# async def travel_description_entered(message: types.Message, state: FSMContext):
#     description = message.text.strip()
#     user_id = db.get_user_id_by_tg(message.from_user.id)
#     req_id = db.add_travel_request(user_id, description)
#     db.log_action(user_id, f"User подал заявку на проезд ID={req_id}")
#     await message.reply("✅ Заявка отправлена на рассмотрение администраторам.", reply_markup=get_main_keyboard(message.from_user.id))
#     await state.clear()

@user_router.message(Command("request_travel"))
async def cmd_request_travel(message: types.Message, state: FSMContext):
    # Шаг 1: выбор типа машины
    kb = InlineKeyboardBuilder()
    kb.button(text="🚗 Легковая", callback_data="travel:type:passenger")
    kb.button(text="🚚 Грузовая",  callback_data="travel:type:cargo")
    kb.adjust(1)
    await message.answer("🚘 Выберите тип машины для поездки:", reply_markup=kb.as_markup())
    await state.set_state(TravelRequestForm.vehicle_type)

@user_router.callback_query(lambda c: c.data and c.data.startswith("travel:type:"),
                            StateFilter(TravelRequestForm.vehicle_type))
async def callback_travel_type(cq: types.CallbackQuery, state: FSMContext):
    vtype = cq.data.split(":", 2)[2]  # "passenger" или "cargo"
    await state.update_data(vehicle_type=vtype)
    await cq.answer()
    # Шаг 2: запрос даты/времени
    await cq.message.edit_reply_markup()
    # просим дату/время отдельным сообщением
    await cq.message.answer(
        "📅 Введите дату и время поездки в формате ГГГГ-ММ-ДД ЧЧ:ММ:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(TravelRequestForm.date_time)

# 2) Запомнили дату/время — просим номер машины
@user_router.message(TravelRequestForm.date_time)
async def travel_date_time_entered(message: types.Message, state: FSMContext):
    dt_text = message.text.strip()
    # тут можно добавить валидацию через datetime.strptime
    await state.update_data(date_time=dt_text)
    await message.answer(
        "🚗 Теперь введите номер машины:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(TravelRequestForm.car_number)

# 3) Запомнили номер машины — просим цель
@user_router.message(TravelRequestForm.car_number)
async def travel_car_entered(message: types.Message, state: FSMContext):
    car = message.text.strip()
    await state.update_data(car_number=car)
    await message.answer(
        "🎯 Наконец, укажите цель поездки:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(TravelRequestForm.purpose)

# 4) Собрали все данные — создаём заявку, счёт и уведомляем админов
@user_router.message(TravelRequestForm.purpose)
async def travel_purpose_entered(message: types.Message, state: FSMContext):
    data       = await state.get_data()
    vtype      = data["vehicle_type"]
    date_time  = data["date_time"]
    car_number = data["car_number"]
    purpose    = message.text.strip()

    tg_id  = message.from_user.id
    user_id = db.get_user_id_by_tg(tg_id)
    if user_id is None:
        # если пользователя ещё нет в БД, создаём
        fullnm = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
        user_id = db.add_user(tg_id, fullnm, message.from_user.last_name or "", message.from_user.username or "")


    # a) сохраняем заявку (с указанием типа машины)
    req_id = db.add_travel_request(user_id, date_time, vtype, car_number, purpose)

    # b) уведомляем пользователя
    await message.answer(
        f"✅ Ваша заявка №{req_id} принята и ожидает одобрения администратора.",
        reply_markup=get_main_keyboard(tg_id)
    )

    # d) шлём уведомление всем администраторам
    text_admin = (
        f"📨 Новая заявка на проезд №{req_id} от {message.from_user.full_name}:\n"
        f"• Тип: {'Грузовая' if vtype=='cargo' else 'Легковая'}\n"
        f"• Дата и время: {date_time}\n"
        f"• Машина: {car_number}\n"
        f"• Цель: {purpose}"
    )
    for admin in config.ADMIN_IDS:
        try:
            await message.bot.send_message(admin, text_admin)
        except:
            pass

    await state.clear()


# общие
@user_router.message(F.text == "Новости")
async def alias_news(message: types.Message):
    return await cmd_news(message)

@user_router.message(F.text == "События")
async def alias_events(message: types.Message):
    return await cmd_events(message)

@user_router.message(F.text == "Услуги")
async def alias_services(message: types.Message):
    return await admin_list_services(message)



@user_router.message(F.text == "Записаться на услугу")
async def alias_book(message: types.Message, state: FSMContext):
    return await cmd_add_service(message, state)

@user_router.message(F.text == "Изменить свою заявку")
async def alias_book(message: types.Message, state: FSMContext):
    return await cmd_edit_service(message, state)

@user_router.message(F.text == "Удалить свою заявку")
async def alias_book(message: types.Message, state: FSMContext):
    return await cmd_delete_service(message, state)



@user_router.message(F.text == "Заявка на проезд")
async def alias_travel(message: types.Message, state: FSMContext):
    return await cmd_request_travel(message, state)



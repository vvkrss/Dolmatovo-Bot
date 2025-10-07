# handlers_master.py
# Логика для роли «Мастер» — обработка заявок на услуги
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from user_handlers import get_main_keyboard, get_cancel_keyboard
import db
from config import ADMIN_IDS, ACCOUNTANT_IDS, MASTER_IDS
from datetime import datetime
from aiogram import F
from states import MasterForm

router = Router()

@router.message(Command("register_master"))
async def cmd_register_master(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    builder.button(
        text="Поделиться контактом",
        request_contact=True
    )
    # Одна кнопка в ряду
    builder.adjust(1)
    kb = builder.as_markup(resize_keyboard=True)
    await message.answer("Пожалуйста, поделитесь своим номером телефона:", reply_markup=kb)
    await state.set_state(MasterForm.wait_contact)


@router.message(
    StateFilter(MasterForm.wait_contact),
    F.content_type == types.ContentType.CONTACT
)
async def master_contact(message: types.Message, state: FSMContext):
    user_id = db.get_user_id_by_tg(message.from_user.id)
    db.conn.execute("UPDATE users SET phone = ? WHERE id = ?", (message.contact.phone_number, user_id))
    db.conn.commit()
    await message.answer("✅ Вы успешно зарегистрированы как мастер.", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

# Создаём таблицу service_requests, если её ещё нет
# Поля: id, service_id, slot_id, user_id, master_id, status, amount
_cursor = db.conn.cursor()
_cursor.execute("""
    CREATE TABLE IF NOT EXISTS service_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_id INTEGER NOT NULL,
        slot_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        master_id INTEGER,
        status TEXT NOT NULL DEFAULT 'new',
        amount REAL,
        FOREIGN KEY(service_id) REFERENCES services(id),
        FOREIGN KEY(slot_id) REFERENCES slots(id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(master_id) REFERENCES users(id)
    )
""")
db.conn.commit()

# FSM для ввода суммы при завершении заявки
class CompleteRequestForm(StatesGroup):
    amount = State()  # ввод суммы услуги

# Команда /master — главное меню для мастера
@router.message(Command("master"))
async def master_menu(message: types.Message):
    tg = message.from_user.id
    # проверяем, что пользователь — мастер (ни админ, ни бухгалтер, но есть в БД)
    if db.get_user_id_by_tg(tg) is None or tg not in MASTER_IDS:
        return await message.reply("❌ У вас нет доступа к меню мастера.")
    builder = InlineKeyboardBuilder()
    builder.button(text="🆕 Новые заявки", callback_data="master:new")
    builder.button(text="📋 Мои заявки",   callback_data="master:mine")
    builder.adjust(1)  # по одной кнопке в строке
    await message.reply("🔧 Меню мастера:", reply_markup=builder.as_markup())

# Список новых заявок (не распределённых)
@router.callback_query(lambda c: c.data == "master:new")
async def master_new_requests(cq: types.CallbackQuery):
    # Теперь выбираем u.username вместо u.tg_id
    rows = db.conn.execute(
        """SELECT
             sr.id,
             sr.service_id,
             s.name,
             sr.slot_id,
             sl.datetime,
             u.username
           FROM service_requests sr
           JOIN services s  ON sr.service_id = s.id
           JOIN slots sl     ON sr.slot_id     = sl.id
           JOIN users u      ON sr.user_id     = u.id
           WHERE sr.status='new'"""
    ).fetchall()

    if not rows:
        await cq.message.edit_text("Нет новых заявок.")
        return

    for req_id, svc_id, svc_name, slot_id, slot_dt, username in rows:
        # 1) Оставляем только дату
        # если slot_dt = "2025-07-20 14:30", то date_only = "2025-07-20"
        date_only = slot_dt.split(" ")[0]
        # или так:
        # date_only = datetime.strptime(slot_dt, "%Y-%m-%d %H:%M").date()

        # 2) Формируем клиента как @username
        if username:
            client = f"@{username}"
        else:
            client = "без @username"

        text = (
            f"Заявка #{req_id}\n"
            f"Услуга: {svc_name} (ID {svc_id})\n"
            f"Дата слота: {date_only} (ID {slot_id})\n"
            f"Клиент: {client}"
        )

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Принять", callback_data=f"master:accept:{req_id}")
        await cq.message.reply(text, reply_markup=builder.as_markup())

    await cq.answer()

# Мастер принимает заявку — переводим status в in_progress и назначаем master_id
@router.callback_query(lambda c: c.data and c.data.startswith("master:accept:"))
async def master_accept(cq: types.CallbackQuery):
    tg = cq.from_user.id
    master_uid = db.get_user_id_by_tg(tg)
    if not master_uid:
        return await cq.answer("Ошибка: мастер не найден в БД.", show_alert=True)

    req_id = int(cq.data.split(":")[2])
    # Проверяем, что заявка есть и новая
    row = db.conn.execute(
        "SELECT status, user_id FROM service_requests WHERE id=?", (req_id,)
    ).fetchone()
    if not row or row[0] != 'new':
        return await cq.answer("Заявка не найдена или уже принята.", show_alert=True)

    # Обновляем статус и назначаем мастера
    db.conn.execute(
        "UPDATE service_requests SET status='in_progress', master_id=? WHERE id=?",
        (master_uid, req_id)
    )
    db.conn.commit()

    await cq.answer("Заявка принята.")
    await cq.message.delete()  # убираем кнопку «Принять»

    # Извлекаем tg_id клиента
    user_id = row[1]
    service_name = row[2]
    client_tg = db.conn.execute(
        "SELECT tg_id FROM users WHERE id=?", (user_id,)
    ).fetchone()[0]

    # Достаём телефон мастера
    master_phone = db.conn.execute(
        "SELECT phone FROM users WHERE id=?", (master_uid,)
    ).fetchone()[0] or "не указан"

    # Отправляем уведомление клиенту с номером мастера
    try:
        await cq.bot.send_message(
            client_tg,
            f"🔧 Ваша заявка на услугу «{service_name}» принята мастером. Для уточнения времени можете связаться с мастером.\n"
            f"📞 Контакт мастера: {master_phone}"
        )
    except:
        pass

# Список своих заявок (in_progress и в статусах)
@router.callback_query(lambda c: c.data == "master:mine")
async def master_my_requests(cq: types.CallbackQuery):
    master_uid = db.get_user_id_by_tg(cq.from_user.id)
    rows = db.conn.execute(
        "SELECT sr.id, s.name, sl.datetime, sr.status "
        "FROM service_requests sr "
        "JOIN services s ON sr.service_id=s.id "
        "JOIN slots sl ON sr.slot_id=sl.id "
        "WHERE sr.master_id=? AND sr.status IN ('in_progress','new')",
        (master_uid,)
    ).fetchall()
    if not rows:
        await cq.message.edit_text("У вас нет активных заявок.")
        return
    for r in rows:
        req_id, svc_name, slot_dt, status = r
        text = f"#{req_id}: {svc_name} @ {slot_dt}\nСтатус: {status}"
        builder = InlineKeyboardBuilder()
        if status == 'in_progress':
            builder.button(text="✅ Завершить", callback_data=f"master:complete:{req_id}")
        await cq.message.reply(text, reply_markup=builder.as_markup())
    await cq.answer()

# Мастер завершает заявку — переходим к вводу суммы
@router.callback_query(lambda c: c.data and c.data.startswith("master:complete:"))
async def master_complete_start(cq: types.CallbackQuery, state: FSMContext):
    req_id = int(cq.data.split(":")[2])
    # Сохраняем в FSM
    await state.update_data(req_id=req_id)
    await state.set_state(CompleteRequestForm.amount)
    await cq.message.reply("Введите сумму услуги (числом):")
    await cq.answer()

# При вводе суммы — завершаем заявку, создаём счёт, уведомляем клиента и бухгалтера
@router.message(CompleteRequestForm.amount)
async def master_complete_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    req_id = data.get('req_id')
    try:
        amount = float(message.text.strip())
    except:
        return await message.reply("❌ Неверный формат. Введите число.")
    # Получаем параметры заявки
    row = db.conn.execute(
        "SELECT user_id FROM service_requests WHERE id=?", (req_id,)
    ).fetchone()
    if not row:
        await message.reply("Ошибка: заявка не найдена.")
        await state.clear()
        return
    user_id = row[0]
    # Обновляем заявку
    db.conn.execute(
        "UPDATE service_requests SET status='completed', amount=? WHERE id=?",
        (amount, req_id)
    )
    db.conn.commit()
    # Создаём счёт для клиента
    period = datetime.now().strftime("%Y-%m")
    inv_id = db.add_invoice(user_id, amount, period)
    # Уведомляем клиента
    client_tg = db.conn.execute("SELECT tg_id FROM users WHERE id=?", (user_id,)).fetchone()[0]
    try:
        await message.bot.send_message(client_tg,
            f"✅ Ваша заявка #{req_id} завершена. Сумма {amount:.2f} руб.\nСчёт #{inv_id} выставлен.")
    except:
        pass
    # Уведомляем бухгалтера
    for acct in ACCOUNTANT_IDS:
        try:
            await message.bot.send_message(acct,
                f"Новый счёт #{inv_id}: услуга по заявке #{req_id}, сумма {amount:.2f} руб.")
        except:
            continue
    await message.reply(f"Заявка #{req_id} помечена как выполненная, счёт #{inv_id} создан.")
    # Логируем
    master_uid = db.get_user_id_by_tg(message.from_user.id)
    db.log_action(master_uid, f"master completed request {req_id} amount={amount}")
    await state.clear()

# мастер
@router.message(F.text == "Меню мастера")
async def alias_master(message: types.Message):
    return await master_menu(message)

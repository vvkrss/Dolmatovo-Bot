# handlers_accountant.py
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
import csv
import io
from datetime import datetime, date, timedelta
from user_handlers import get_main_keyboard, get_cancel_keyboard

import config
import db

accountant_router = Router()
# Фильтруем по списку бухгалтеров
accountant_router.message.filter(lambda msg: msg.from_user and msg.from_user.id in config.ACCOUNTANT_IDS)
accountant_router.callback_query.filter(lambda cq: cq.from_user and cq.from_user.id in config.ACCOUNTANT_IDS)


class ImportCSVForm(StatesGroup):
    waiting_file = State()

class CreateInvoiceForm(StatesGroup):
    user   = State()  # ждем @username или Telegram‑ID
    amount = State()  # ждем сумму


# ---------- 1) /pending_invoices -------------
@accountant_router.message(Command("pending_invoices"))
async def cmd_pending_invoices(message: types.Message):
    """
    Показывает список неоплаченных счетов с кнопками 'Оплачено'.
    """
    invoices = db.get_unpaid_invoices()  # возвращает list[{"id","amount","period","user_name","tg_id"}] :contentReference[oaicite:0]{index=0}
    if not invoices:
        return await message.answer("Нет неоплаченных счетов.")
    text_lines = ["📄 *Неоплаченные взносы:*"]
    for idx, inv in enumerate(invoices, start=1):
        text_lines.append(
            f"{idx}. {inv['user_name']}: {inv['amount']} руб. за {inv['period']}"
        )

    # Строим клавиатуру через Builder
    builder = InlineKeyboardBuilder()
    for inv in invoices:
        builder.button(
            text="Оплачено",
            callback_data=f"pay_inv:{inv['id']}"
        )
    builder.adjust(1)  # по одной кнопке в строке
    kb = builder.as_markup()
    await message.answer("\n".join(text_lines), reply_markup=kb)


# ----- Callback по нажатию 'Оплачено' -----
@accountant_router.callback_query(lambda cq: cq.data and cq.data.startswith("pay_inv:"))
async def callback_mark_paid(callback: types.CallbackQuery):
    inv_id = int(callback.data.split(":", 1)[1])
    db.mark_invoice_paid(inv_id)  # помечает в БД :contentReference[oaicite:1]{index=1}
    # Логируем действие
    acct_id = db.get_user_id_by_tg(callback.from_user.id)
    db.log_action(acct_id, f"Accountant marked invoice ID={inv_id} as paid")
    await callback.answer("✅ Отмечено как оплачено.")
    # Обновляем список в сообщении
    await callback.message.edit_text(
        text="Состояние обновлено.",
        reply_markup=None
    )
    # Перерисуем /pending_invoices
    await cmd_pending_invoices(callback.message)


# ---------- 2) /import_contributions -------------
@accountant_router.message(Command("import_contributions"))
async def cmd_import_contributions(message: types.Message, state: FSMContext):
    """
    Запрашивает CSV-файл с колонками: tg_id,amount
    """
    await message.answer("📂 Пришлите CSV-файл со списком взносов (tg_id,amount) без заголовка.")
    await state.set_state(ImportCSVForm.waiting_file)

@accountant_router.message(ImportCSVForm.waiting_file)
async def process_csv_file(message: types.Message, state: FSMContext):
    if not message.document:
        return await message.answer("❌ Пожалуйста, отправьте файл в формате CSV.")
    bio = io.BytesIO()
    await message.bot.download(message.document, destination=bio)
    bio.seek(0)
    reader = csv.reader(io.TextIOWrapper(bio, encoding='utf-8'))
    period = date.today().strftime("%Y-%m")
    added = 0
    for row in reader:
        if not row or len(row) < 1:
            continue
        try:
            tg_id = int(row[0])
            amount = float(row[1]) if len(row) > 1 else config.DEFAULT_CONTRIBUTION_AMOUNT
        except:
            continue
        # Убедимся, что пользователь есть в БД
        user_id = db.get_user_id_by_tg(tg_id)
        if user_id is None:
            # добавим без имени
            user_id = db.add_user(tg_id, "", "", "", is_admin=0, is_accountant=1)
        # Добавляем счёт
        db.add_invoice(user_id, amount, period)  # :contentReference[oaicite:2]{index=2}
        added += 1
    await state.clear()
    await message.answer(f"✅ Импортировано записей: {added}.")


# ---------- 3) /generate_contributions -------------
@accountant_router.message(Command("generate_contributions"), StateFilter("*"))
async def cmd_generate_contribution_start(message: types.Message, state: FSMContext):
    await message.answer(
        "🧾 Введите Telegram‑ID или username (без @) пользователя, для которого нужно создать счёт:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(CreateInvoiceForm.user)

@accountant_router.message(StateFilter(CreateInvoiceForm.user))
async def cmd_generate_contribution_user(message: types.Message, state: FSMContext):
    text = message.text.strip()
    # попробуем найти по username
    row = db.cursor.execute(
        "SELECT id, tg_id, first_name, last_name FROM users WHERE username = ?",
        (text.lstrip("@"),)
    ).fetchone()
    if row:
        user_id, tg_id, fn, ln = row
        user_name = f"{fn} {ln}".strip()
    else:
        # если не по username, попробуем по самому числу tg_id
        try:
            tg_id = int(text)
            user_id = db.get_user_id_by_tg(tg_id)
            if user_id is None:
                raise ValueError
            row2 = db.cursor.execute(
                "SELECT first_name, last_name FROM users WHERE tg_id = ?",
                (tg_id,)
            ).fetchone()
            user_name = f"{row2[0]} {row2[1]}".strip()
        except:
            return await message.reply(
                "❌ Пользователь не найден. Введите корректный username (без @) или Telegram‑ID.",
                reply_markup=get_cancel_keyboard()
            )

    await state.update_data(user_id=user_id, tg_id=tg_id, user_name=user_name)
    await message.answer(
        f"👤 Пользователь: <b>{user_name}</b> (tg_id: <code>{tg_id}</code>)\n"
        "💵 Введите сумму счёта (например: 500 или 1250.50):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(CreateInvoiceForm.amount)

@accountant_router.message(StateFilter(CreateInvoiceForm.amount))
async def cmd_generate_contribution_amount(message: types.Message, state: FSMContext):
    txt = message.text.strip().replace(",", ".")
    try:
        amount = float(txt)
    except:
        return await message.reply(
            "❌ Неверный формат суммы. Введите, пожалуйста, только цифры, например: 500 или 1250.50.",
            reply_markup=get_cancel_keyboard()
        )

    data = await state.get_data()
    user_id   = data["user_id"]
    tg_id     = data["tg_id"]
    user_name = data["user_name"]
    period    = date.today().strftime("%Y-%m")

    invoice_id = db.add_invoice(user_id, amount, period)

    # уведомляем бухгалтера
    await message.answer(
        f"✅ Счёт №<b>{invoice_id}</b> на сумму <b>{amount:.2f} ₽</b> создан для "
        f"<b>{user_name}</b> (tg_id: <code>{tg_id}</code>) за период <code>{period}</code>.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

    # уведомляем пользователя
    try:
        await message.bot.send_message(
            tg_id,
            f"Вам выставлен счёт №{invoice_id} на сумму {amount:.2f} ₽ за период {period}.",
            reply_markup=get_main_keyboard(tg_id)
        )
    except:
        pass

    # лог
    admin_id = db.get_user_id_by_tg(message.from_user.id)
    db.log_action(admin_id, f"Создан счёт #{invoice_id} ({amount:.2f} ₽) для user_id={user_id}")

    await state.clear()


# ---------- 4) /send_reminders -------------
@accountant_router.message(Command("send_reminders"))
async def cmd_send_reminders(message: types.Message):
    """
    Рассылает напоминания должникам.
    """
    invoices = db.get_unpaid_invoices()  # :contentReference[oaicite:3]{index=3}
    debts = {}
    for inv in invoices:
        debts.setdefault(inv['tg_id'], 0.0)
        debts[inv['tg_id']] += inv['amount']
    sent = 0
    for tg_id, total in debts.items():
        try:
            await message.bot.send_message(tg_id, f"🔔 Напоминание: ваша задолженность {total:.2f} руб.")
            sent += 1
        except:
            continue
    await message.answer(f"✅ Напоминаний отправлено: {sent}.")


# ---------- 5) /send_event_reminders -------------
@accountant_router.message(Command("send_event_reminders"))
async def cmd_send_event_reminders(message: types.Message):
    """
    Напоминания о событиях сегодня.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    events = db.get_upcoming_events()  # :contentReference[oaicite:4]{index=4}
    todays = [ev for ev in events if ev['datetime'].startswith(today_str)]
    if not todays:
        return await message.answer("Нет мероприятий на сегодня.")
    lines = [f"📅 Сегодня:"]
    for ev in todays:
        time = ev['datetime'][11:16]
        lines.append(f"– {ev['title']} в {time}, {ev['location']}")
    text = "\n".join(lines)
    # Шлём всем пользователям
    db.cursor.execute("SELECT tg_id FROM users")
    tgs = [r[0] for r in db.cursor.fetchall()]
    sent = 0
    for tg in tgs:
        try:
            await message.bot.send_message(tg, text)
            sent += 1
        except:
            continue
    await message.answer(f"✅ Напоминаний о событиях: {sent}.")


# ---------- 6) /send_service_reminders -------------
@accountant_router.message(Command("send_service_reminders"))
async def cmd_send_service_reminders(message: types.Message):
    """
    Напоминания о визите мастера завтра.
    """
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    # Берём все забронированные слоты на завтра
    db.cursor.execute("""
        SELECT sl.datetime, sl.booked_by, s.name
        FROM slots sl
        JOIN services s ON sl.service_id = s.id
        WHERE sl.booked_by IS NOT NULL
          AND substr(sl.datetime,1,10)=?
    """, (tomorrow_str,))
    rows = db.cursor.fetchall()  # [(datetime, user_id, service_name), ...]
    sent = 0
    for dt_str, user_id, svc_name in rows:
        time = dt_str[11:16]
        # Получаем tg_id
        db.cursor.execute("SELECT tg_id FROM users WHERE id = ?", (user_id,))
        tg = db.cursor.fetchone()
        if not tg:
            continue
        tg_id = tg[0]
        try:
            await message.bot.send_message(
                tg_id,
                f"🔔 Напоминание: завтра к вам придёт {svc_name} в {time}."
            )
            sent += 1
        except:
            continue
    await message.answer(f"✅ Сервисных напоминаний: {sent}.")


# ---------- 7) /export_contributions -------------
@accountant_router.message(Command("export_contributions"))
async def cmd_export_contributions(message: types.Message):
    """
    Предлагает скачать CSV всех счетов.
    """
    # Кнопка через Builder
    builder = InlineKeyboardBuilder()
    builder.button(text="📥 Скачать CSV", callback_data="export_csv")
    builder.adjust(1)
    kb = builder.as_markup()

    await message.answer(
        "Нажмите кнопку, чтобы получить CSV со всеми взносами:",
        reply_markup=kb
    )


@accountant_router.callback_query(lambda cq: cq.data == "export_csv")
async def callback_export_contributions(callback: types.CallbackQuery):
    """
    Генерирует и отправляет CSV со всеми счетами,
    используя точку с запятой как разделитель.
    """
    # Формируем CSV в памяти
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=';')  # <-- разделитель ';'
    # Заголовки
    writer.writerow(["invoice_id", "tg_id", "user_name", "amount", "period", "status"])
    # Данные
    db.cursor.execute("""
        SELECT inv.id, u.tg_id, u.first_name, u.last_name, inv.amount, inv.period, inv.status
        FROM invoices inv
        JOIN users u ON inv.user_id = u.id
        ORDER BY inv.id
    """)
    for inv_id, tg_id, fn, ln, amt, per, status in db.cursor.fetchall():
        name = fn or ""
        if ln:
            name += " " + ln
        writer.writerow([inv_id, tg_id, name.strip(), amt, per, status])
    output.seek(0)

    # Считываем байты и отправляем
    csv_bytes = output.getvalue().encode("utf-8")
    file = BufferedInputFile(csv_bytes, filename="all_invoices.csv")

    await callback.message.bot.send_document(
        chat_id=callback.from_user.id,
        document=file,
        caption="✅ Все счета в CSV (разделитель — точка с запятой)"
    )
    await callback.answer()


# ---------- 8) /cancel -------------
@accountant_router.message(Command("cancel"))
async def cancel_accountant(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        return await message.answer("Нет активных действий.")
    await state.clear()
    await message.answer("✖️ Действие отменено.")

# бухгалтер
@accountant_router.message(F.text == "Неоплаченные счета")
async def alias_pending_invoices(message: types.Message):
    return await cmd_pending_invoices(message)

@accountant_router.message(F.text == "Импортировать взносы")
async def alias_import_contrib(message: types.Message, state: FSMContext):
    return await cmd_import_contributions(message, state)

@accountant_router.message(F.text == "Создать счет")
async def alias_generate_contrib(message: types.Message, state: FSMContext):
    return await cmd_generate_contribution_start(message, state)

@accountant_router.message(F.text == "Напомнить должникам")
async def alias_send_reminders(message: types.Message):
    return await cmd_send_reminders(message)

@accountant_router.message(F.text == "Экспортировать взносы")
async def alias_export_contrib(message: types.Message):
    return await cmd_export_contributions(message)

@accountant_router.message(F.text == "Напомнить о событиях")
async def alias_send_event_reminders(message: types.Message):
    return await cmd_send_event_reminders(message)

@accountant_router.message(F.text == "Напомнить о визите мастера")
async def alias_send_service_reminders(message: types.Message):
    return await cmd_send_service_reminders(message)

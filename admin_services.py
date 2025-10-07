from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from datetime import timedelta
from config import ADMIN_IDS
import config
from states import ServiceCreateForm, ServiceEditForm, ServiceDeleteForm, SlotCreateForm, SlotEditForm, SlotDeleteForm, ManualSlotForm
from user_handlers import get_main_keyboard, get_cancel_keyboard

import db
from db import get_service, get_slot, get_slots_by_service, add_slot, get_all_services, add_service
from db import update_slot, delete_slot

# Router for service management (admin only)
router = Router()
router.message.filter(lambda msg: msg.from_user and msg.from_user.id in config.ADMIN_IDS)
router.callback_query.filter(lambda cq: cq.from_user and cq.from_user.id in config.ADMIN_IDS)

# class AddServiceForm(StatesGroup):
#     name = State()
#
# class EditServiceForm(StatesGroup):
#     service_id = State()
#     new_name = State()
#
# class DeleteServiceForm(StatesGroup):
#     service_id = State()
#
# class SlotForm(StatesGroup):
#     service_id = State()
#     datetime = State()

#
# /create_slot — уже было, оставляем как есть:
#
@router.message(Command("create_slot"), StateFilter("*"))
async def admin_create_slot_start(message: types.Message, state: FSMContext):
    """
    Заменяет старый create_slot: показываем кнопки с услугами.
    """
    svcs = get_all_services()
    if not svcs:
        return await message.reply("❌ Нет услуг.")
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text = s["name"], callback_data=f"slot:svc:{s['id']}")] for s in svcs]
    )
    await state.set_state(ManualSlotForm.service_id)
    await message.reply("Выберите услугу для нового слота:", reply_markup=kb)

@router.callback_query(lambda c: c.data and c.data.startswith("slot:svc:"), StateFilter(ManualSlotForm.service_id))
async def admin_create_slot_service_selected(cq: types.CallbackQuery, state: FSMContext):
    """
    Новый handler: запомнили service_id, спрашиваем время.
    """
    svc_id = int(cq.data.split(":")[2])
    await state.update_data(service_id=svc_id)
    await state.set_state(ManualSlotForm.start_time)
    await cq.message.edit_text("Введите начало слота в формате YYYY-MM-DD HH:MM")
    await cq.answer()

@router.message(StateFilter(ManualSlotForm.start_time))
async def admin_create_slot_start_time(message: types.Message, state: FSMContext):
    """
    Новый handler: после начала — спрашиваем длительность.
    """
    try:
        dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
    except:
        return await message.reply("❌ Неверный формат даты/времени.")
    await state.update_data(start_dt=dt)
    await state.set_state(ManualSlotForm.duration)
    await message.reply("Введите длительность слота в минутах:")

@router.message(StateFilter(ManualSlotForm.duration))
async def admin_create_slot_duration(message: types.Message, state: FSMContext):
    """
    Новый handler: проверка коллизии и создание слота.
    """
    try:
        length = int(message.text.strip())
    except:
        return await message.reply("❌ Введите число минут.")
    data = await state.get_data()
    svc_id = data["service_id"]
    start  = data["start_dt"]
    end    = start + timedelta(minutes=length)
    # Проверяем пересечение со всеми слотами этой услуги
    existing = get_slots_by_service(svc_id)
    for sl in existing:
        sl_start = datetime.strptime(sl["datetime"], "%Y-%m-%d %H:%M")
        sl_end   = sl_start + timedelta(minutes=length)
        if not (end <= sl_start or start >= sl_end):
            return await message.reply("❌ Пересечение со слотом ID "
                                       f"{sl['id']} ({sl['datetime']}). Выберите другое время.")
    # dt_str = start.strftime("%Y-%m-%d %H:%M")
    # slot_id = add_slot(svc_id, dt_str)
    # await message.reply(f"✅ Слот ID {slot_id} создан для услуги {svc_id} в {dt_str}.", reply_markup=get_main_keyboard(message.from_user.id))
    # await state.clear()
    # сохраняем параметры и просим дни недели
    await state.update_data(duration=length)
    WEEKDAYS = [("Пн",0),("Вт",1),("Ср",2),("Чт",3),("Пт",4),("Сб",5),("Вс",6)]
    builder = InlineKeyboardBuilder()
    for name, idx in WEEKDAYS:
        builder.button(text=f"◻️ {name}", callback_data=f"slot:wd:toggle:{idx}")
    builder.button(text="Готово", callback_data="slot:wd:done")
    builder.adjust(3)
    await message.reply("Выберите дни недели для этого слота:", reply_markup=builder.as_markup())
    await state.set_state(ManualSlotForm.weekdays)

@router.callback_query(lambda c: c.data.startswith("slot:wd:"), StateFilter(ManualSlotForm.weekdays))
async def slot_toggle_weekday(cq: types.CallbackQuery, state: FSMContext):
    parts = cq.data.split(":")
    data = await state.get_data()
    stored = set(data.get("weekdays", []))
    if parts[2] == "toggle":
        idx = int(parts[3])
        stored ^= {idx}
        await state.update_data(weekdays=list(stored))
        # перестроим кнопки точно как выше
        WEEKDAYS = [("Пн",0),("Вт",1),("Ср",2),("Чт",3),("Пт",4),("Сб",5),("Вс",6)]
        builder = InlineKeyboardBuilder()
        for name, idx in WEEKDAYS:
            mark = "✅" if idx in stored else "◻️"
            builder.button(text=f"{mark} {name}", callback_data=f"slot:wd:toggle:{idx}")
        builder.button(text="Готово", callback_data="slot:wd:done")
        builder.adjust(3)
        await cq.message.edit_reply_markup(reply_markup=builder.as_markup())
        await cq.answer()
    else:
        if not stored:
            return await cq.answer("Выберите хотя бы один день.", show_alert=True)
        await cq.message.edit_text("Введите период для дублирования в формате YYYY-MM-DD - YYYY-MM-DD:")
        await state.set_state(ManualSlotForm.period)
        await cq.answer()

@router.message(StateFilter(ManualSlotForm.period))
async def slot_set_period(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    try:
        start_s, end_s = [s.strip() for s in txt.split(" - ")]
        start_date = datetime.strptime(start_s, "%Y-%m-%d").date()
        end_date   = datetime.strptime(end_s, "%Y-%m-%d").date()
    except:
        return await message.reply("❌ Неверный формат. Пример: 2025-08-01 - 2025-08-31")
    data     = await state.get_data()
    svc_id   = data["service_id"]
    start_dt = data["start_dt"]
    length   = data["duration"]
    weekdays = data["weekdays"]
    count = 0
    curr = start_date
    while curr <= end_date:
        if curr.weekday() in weekdays:
            t0 = datetime.combine(curr, start_dt.time())
            t1 = t0 + timedelta(minutes=length)
            # коллизия можно пропустить или оставить как есть
            db.add_slot(svc_id, t0.strftime("%Y-%m-%d %H:%M"))
            count += 1
        curr += timedelta(days=1)
    await message.reply(f"✅ Создано {count} слотов для услуги ID {svc_id}.", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

#
# /edit_slot — переносим незабронированный слот
#
@router.message(Command("edit_slot"), StateFilter("*"))
async def admin_edit_slot_start(message: types.Message, state: FSMContext):
    """
    Заменяет старый edit_slot: сначала выбираем услугу кнопками.
    """
    svcs = get_all_services()
    builder = InlineKeyboardBuilder()
    for svc in svcs:
        builder.button(
            text=svc["name"],
            callback_data=f"eslot:svc:{svc['id']}"
        )
    # Размещаем по одной кнопке в строке
    builder.adjust(1)
    kb = builder.as_markup()
    await state.set_state(ManualSlotForm.service_id)
    await message.reply("Выберите услугу для редактирования слота:", reply_markup=kb)

@router.callback_query(lambda c: c.data and c.data.startswith("eslot:svc:"), StateFilter(ManualSlotForm.service_id))
async def admin_edit_slot_pick_svc(cq: types.CallbackQuery, state: FSMContext):
    svc_id = int(cq.data.split(":")[2])
    slots  = get_slots_by_service(svc_id)
    if not slots:
        return await cq.answer("Нет слотов для этой услуги.", show_alert=True)
    builder = InlineKeyboardBuilder()
    for sl in slots:
        builder.button(
            text=f"{sl['id']} — {sl['datetime']}",
            callback_data=f"eslot:slot:{sl['id']}:{svc_id}"
        )
    # Размещаем по одной кнопке в строке
    builder.adjust(1)
    kb = builder.as_markup()
    await state.update_data(service_id=svc_id)
    await state.set_state(ManualSlotForm.slot_id)
    await cq.message.edit_text("Выберите слот для редактирования:", reply_markup=kb)
    await cq.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("eslot:slot:"), StateFilter(ManualSlotForm.slot_id))
async def admin_edit_slot_pick_slot(cq: types.CallbackQuery, state: FSMContext):
    _, _, slot_id, svc_id = cq.data.split(":")
    await state.update_data(slot_id=int(slot_id))
    await state.set_state(ManualSlotForm.start_time)
    await cq.message.edit_text("Введите новое начало слота (YYYY-MM-DD HH:MM):")
    await cq.answer()

@router.message(StateFilter(ManualSlotForm.start_time))
async def admin_edit_slot_new_time(message: types.Message, state: FSMContext):
    try:
        new_dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
    except:
        return await message.reply("❌ Неверный формат.")
    data    = await state.get_data()
    slot_id = data["slot_id"]
    update_slot(slot_id, new_dt.strftime("%Y-%m-%d %H:%M"))
    await message.reply(f"✅ Слот ID {slot_id} перенесён на {new_dt}.", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

# /delete_slot
@router.message(Command("delete_slot"), StateFilter("*"))
async def admin_delete_slot_start(message: types.Message, state: FSMContext):
    svcs = get_all_services()
    builder = InlineKeyboardBuilder()
    for svc in svcs:
        builder.button(
            text=svc["name"],
            callback_data=f"dslot:svc:{svc['id']}"
        )
    builder.adjust(1)  # по одной кнопке в строке
    kb = builder.as_markup()
    await state.set_state(ManualSlotForm.service_id)
    await message.reply("Выберите услугу для удаления слота:", reply_markup=kb)

@router.callback_query(lambda c: c.data and c.data.startswith("dslot:svc:"), StateFilter(ManualSlotForm.service_id))
async def admin_delete_slot_pick_svc(cq: types.CallbackQuery, state: FSMContext):
    svc_id = int(cq.data.split(":")[2])
    slots  = get_slots_by_service(svc_id)
    if not slots:
        return await cq.answer("Нет слотов.", show_alert=True)
    builder = InlineKeyboardBuilder()
    for sl in slots:
        builder.button(
            text=f"{sl['id']} — {sl['datetime']}",
            callback_data=f"dslot:slot:{sl['id']}"
        )
    builder.adjust(1)  # по одной кнопке в строке
    kb = builder.as_markup()
    await state.set_state(ManualSlotForm.slot_id)
    await cq.message.edit_text("Выберите слот для удаления:", reply_markup=kb)
    await cq.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("dslot:slot:"), StateFilter(ManualSlotForm.slot_id))
async def admin_delete_slot_confirm(cq: types.CallbackQuery):
    slot_id = int(cq.data.split(":")[2])
    delete_slot(slot_id)
    await cq.message.edit_text(f"✅ Слот ID {slot_id} удалён.", reply_markup=get_main_keyboard(cq.from_user.id))
    await cq.answer()


#=================================================================================================================
# /add_service — создаем услугу
#=================================================================================================================


@router.message(Command("add_service"), StateFilter("*"))
async def admin_add_service_start(message: types.Message, state: FSMContext):
    """
    Заменяет старый admin_add_service_start:
    сначала спрашиваем только имя услуги.
    """
    await state.set_state(ServiceCreateForm.name)
    await message.reply("Введите название новой услуги:")

@router.message(StateFilter(ServiceCreateForm.name))
async def admin_add_service_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(ServiceCreateForm.price)
    await message.reply("Введите цену услуги в рублях (число, например, 500):")

# @router.message(StateFilter(ServiceCreateForm.name))
# async def admin_add_service_name(message: types.Message, state: FSMContext):
#     """
#     Заменяет старый admin_add_service_name.
#     После ввода имени спрашиваем — автогенерировать слоты?
#     """
#     name = message.text.strip()
#     await state.update_data(name=name)
#     await state.set_state(ServiceCreateForm.generate)
#     kb = types.InlineKeyboardMarkup(inline_keyboard=[
#         [types.InlineKeyboardButton(text = "Да, сгенерировать",  callback_data="svc:gen:yes")],
#         [types.InlineKeyboardButton(text = "Нет, вручную",      callback_data="svc:gen:no")],
#     ])
#     await message.reply("Генерировать слоты автоматически?", reply_markup=kb)

@router.message(StateFilter(ServiceCreateForm.price))
async def admin_add_service_price(message: types.Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        price = float(text)
    except ValueError:
        return await message.reply("❌ Неверный формат цены. Введите число, например 750.0.")
    await state.update_data(price=price)
    # дальше — спрашиваем автогенерацию слотов
    await state.set_state(ServiceCreateForm.generate)
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Да, сгенерировать", callback_data="svc:gen:yes")],
        [types.InlineKeyboardButton(text="Нет, вручную",     callback_data="svc:gen:no")],
    ])
    await message.reply(f"Услуга «{(await state.get_data())['name']}» по цене {price} ₽. Генерировать слоты автоматически?", reply_markup=kb)

@router.callback_query(lambda c: c.data and c.data.startswith("svc:gen:"), StateFilter(ServiceCreateForm.generate))
async def admin_service_generate_choice(cq: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    name  = data["name"]
    price = data["price"]
    svc_id = db.add_service(name, price)
    choice = cq.data.split(":", 2)[2]
    if choice == "yes":
        await state.update_data(service_id=svc_id)
        await state.set_state(ServiceCreateForm.work_time)
        await cq.message.edit_text(
            f"✅ Услуга «{name}» ({price} ₽) создана (ID {svc_id}).\n"
            "Введите рабочее время в формате HH:MM-HH:MM"
        )
    else:
        await state.clear()
        await cq.message.edit_text(f"✅ Услуга «{name}» ({price} ₽) создана (ID {svc_id}).")
        await cq.message.answer(
            "Вы вернулись в главное меню. Добавлять слоты можно командой /create_slot",
            reply_markup=get_main_keyboard(cq.from_user.id)
        )
    await cq.answer()

@router.message(StateFilter(ServiceCreateForm.work_time))
async def admin_service_set_worktime(message: types.Message, state: FSMContext):
    """
    Новый handler: парсим рабочее время и спрашиваем длину слота.
    """
    text = message.text.strip()
    try:
        start_s, end_s = text.split("-")
        start = datetime.strptime(start_s, "%H:%M").time()
        end   = datetime.strptime(end_s, "%H:%M").time()
    except:
        return await message.reply("❌ Неверный формат. Попробуйте HH:MM-HH:MM")
    await state.update_data(work_start=start, work_end=end)
    await state.set_state(ServiceCreateForm.slot_length)
    await message.reply("Введите длину одного слота в минутах (целое число):")

@router.message(StateFilter(ServiceCreateForm.slot_length))
async def admin_service_set_slotlength(message: types.Message, state: FSMContext):
    """
    Новый handler: генерируем слоты и завершаем FSM.
    """
    try:
        length = int(message.text.strip())
    except:
        return await message.reply("❌ Неверный формат. Введите число минут.")
    data = await state.get_data()
    await state.update_data(slot_length=length)
    # svc_id      = data["service_id"]
    # start, end  = data["work_start"], data["work_end"]
    # # Генерация
    # curr = datetime.combine(datetime.today(), start)
    # end_dt = datetime.combine(datetime.today(), end)
    # count = 0
    # while curr + timedelta(minutes=length) <= end_dt:
    #     dt_str = curr.strftime("%Y-%m-%d %H:%M")
    #     add_slot(svc_id, dt_str)
    #     count += 1
    #     curr += timedelta(minutes=length)
    # await message.reply(f"✅ Сгенерировано {count} слотов для услуги ID {svc_id}.", reply_markup=get_main_keyboard(message.from_user.id))
    # await state.clear()
    # 1) спрашиваем дни недели
    WEEKDAYS = [
        ("Пн", 0), ("Вт", 1), ("Ср", 2),
        ("Чт", 3), ("Пт", 4), ("Сб", 5), ("Вс", 6),
    ]
    builder = InlineKeyboardBuilder()
    for name, idx in WEEKDAYS:
        builder.button(
            text=f"◻️ {name}",
            callback_data=f"svc:wd:toggle:{idx}"
        )
    builder.button(text="Готово", callback_data="svc:wd:done")
    builder.adjust(3)

    await message.reply("Выберите дни недели для расписания:", reply_markup=builder.as_markup())
    await state.set_state(ServiceCreateForm.weekdays)

@router.callback_query(lambda c: c.data.startswith("svc:wd:"), StateFilter(ServiceCreateForm.weekdays))
async def svc_toggle_weekday(cq: types.CallbackQuery, state: FSMContext):
    # c.data = "svc:wd:toggle:3" или "svc:wd:done"
    parts = cq.data.split(":")
    data = await state.get_data()
    stored = set(data.get("weekdays", []))
    if parts[2] == "toggle":
        idx = int(parts[3])
        if idx in stored:
            stored.remove(idx)
        else:
            stored.add(idx)
        await state.update_data(weekdays=list(stored))
        # перестраиваем клавиатуру
        WEEKDAYS = [("Пн",0),("Вт",1),("Ср",2),("Чт",3),("Пт",4),("Сб",5),("Вс",6)]
        builder = InlineKeyboardBuilder()
        for name, idx in WEEKDAYS:
            mark = "✅" if idx in stored else "◻️"
            builder.button(text=f"{mark} {name}", callback_data=f"svc:wd:toggle:{idx}")
        builder.button(text="Готово", callback_data="svc:wd:done")
        builder.adjust(3)
        await cq.message.edit_reply_markup(reply_markup=builder.as_markup())
        await cq.answer()
    else:  # done
        if not stored:
            return await cq.answer("Выберите хотя бы один день.", show_alert=True)
        await cq.message.edit_text("Введите период в формате YYYY-MM-DD - YYYY-MM-DD:")
        await state.set_state(ServiceCreateForm.period)
        await cq.answer()

@router.message(StateFilter(ServiceCreateForm.period))
async def svc_set_period(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    try:
        start_s, end_s = [s.strip() for s in txt.split(" - ")]
        start_date = datetime.strptime(start_s, "%Y-%m-%d").date()
        end_date   = datetime.strptime(end_s, "%Y-%m-%d").date()
    except:
        return await message.reply("❌ Неверный формат. Пример: 2025-08-01 - 2025-08-31")
    data = await state.get_data()
    svc_id      = data["service_id"]
    work_start  = data["work_start"]
    work_end    = data["work_end"]
    length      = data["slot_length"]
    weekdays    = data["weekdays"]
    count = 0
    curr = start_date
    while curr <= end_date:
        if curr.weekday() in weekdays:
            t0 = datetime.combine(curr, work_start)
            t_end = datetime.combine(curr, work_end)
            while t0 + timedelta(minutes=length) <= t_end:
                db.add_slot(svc_id, t0.strftime("%Y-%m-%d %H:%M"))
                count += 1
                t0 += timedelta(minutes=length)
        curr += timedelta(days=1)
    await message.reply(f"✅ Сгенерировано {count} слотов для услуги ID {svc_id}.", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

# --- переименовать услугу в каталоге ---
@router.message(Command("edit_service"))
async def admin_edit_service_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("❌ У вас нет прав.")
    services = db.get_all_services()
    if not services:
        return await message.reply("Каталог пуст.")
    text = "Каталог услуг:\n" + "\n".join(f"{s['id']}: {s['name']}" for s in services)
    await message.reply(text + "\n\nВведите ID услуги для переименования:", reply_markup=get_cancel_keyboard())
    await state.set_state(ServiceEditForm.service_id)

@router.message(ServiceEditForm.service_id)
async def admin_edit_service_choose(message: types.Message, state: FSMContext):
    try:
        svc_id = int(message.text.strip())
    except:
        return await message.reply("❌ Неверный ID.")
    svc = db.get_service(svc_id)
    if not svc:
        return await message.reply("❌ Услуга не найдена.")
    await state.update_data(service_id=svc_id)
    await message.reply(f"Введите новое название для услуги «{svc['name']}»:")
    await state.set_state(ServiceEditForm.new_name)

@router.message(StateFilter(ServiceEditForm.new_name))
async def admin_edit_service_choose_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    await state.update_data(new_name=new_name)
    # предлагаем выбор: изменить цену или оставить
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Изменить цену",
        callback_data="svc_edit:price:yes"
    )
    builder.button(
        text="Не менять цену",
        callback_data="svc_edit:price:no"
    )
    # две кнопки в одном ряду
    builder.adjust(2)
    await message.reply("Хотите изменить цену услуги?", reply_markup=builder.as_markup())
    await state.set_state(ServiceEditForm.price_choice)

@router.callback_query(lambda c: c.data == "svc_edit:price:yes", StateFilter(ServiceEditForm.price_choice))
async def admin_edit_service_price_yes(cq: types.CallbackQuery, state: FSMContext):
    # Пользователь выбрал «Изменить цену»
    await state.set_state(ServiceEditForm.new_price)
    await cq.message.edit_text("Введите новую цену услуги в рублях (число, например 750.0):")
    await cq.answer()

@router.callback_query(lambda c: c.data == "svc_edit:price:no", StateFilter(ServiceEditForm.price_choice))
async def admin_edit_service_price_no(cq: types.CallbackQuery, state: FSMContext):
    # Пользователь выбрал «Не менять цену»
    data = await state.get_data()
    svc_id   = data["service_id"]
    new_name = data["new_name"]
    # обновляем только название
    db.update_service(svc_id, new_name)
    await cq.message.edit_text(
        f"✅ Услуга ID {svc_id} обновлена:\n"
        f"• Название: «{new_name}»\n"
        "• Цена оставлена прежней."
    )

    # 3) Send a _new_ message with your reply keyboard
    await cq.message.answer(
        "Что ещё хотите сделать?",
        reply_markup=get_main_keyboard(cq.from_user.id)
    )
    await state.clear()
    await cq.answer("Цена не изменилась.")

@router.message(StateFilter(ServiceEditForm.new_price))
async def admin_edit_service_price(message: types.Message, state: FSMContext):
    txt = message.text.strip().replace(",", ".")
    try:
        price = float(txt)
    except ValueError:
        return await message.reply("❌ Цена должна быть числом, например 500 или 499.99.")
    data = await state.get_data()
    svc_id    = data["service_id"]
    new_name  = data["new_name"]
    # обновляем и имя, и цену
    db.update_service(svc_id, new_name, price)
    await message.reply(
        f"✅ Услуга ID {svc_id} обновлена:\n"
        f"• Название: «{new_name}»\n"
        f"• Цена: {price} ₽",
        reply_markup=get_main_keyboard(message.from_user.id)
    )
    await state.clear()

# --- удалить услугу из каталога ---
@router.message(Command("delete_service"))
async def admin_delete_service_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("❌ У вас нет прав.")
    services = db.get_all_services()
    if not services:
        return await message.reply("Каталог пуст.")
    text = "Каталог услуг:\n" + "\n".join(f"{s['id']}: {s['name']}" for s in services)
    await message.reply(text + "\n\nВведите ID услуги для удаления:")
    await state.set_state(ServiceDeleteForm.service_id)

@router.message(ServiceDeleteForm.service_id)
async def admin_delete_service_confirm(message: types.Message, state: FSMContext):
    try:
        svc_id = int(message.text.strip())
    except:
        return await message.reply("❌ Неверный ID.")
    svc = db.get_service(svc_id)
    if not svc:
        return await message.reply("❌ Услуга не найдена.")
    db.delete_service(svc_id)
    await message.reply(f"✅ Удалена услуга «{svc['name']}» (ID {svc_id}) и все её слоты.", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()


@router.message(F.text == "Добавить услугу")
async def alias_add_service_admin(message: types.Message, state: FSMContext):
    return await admin_add_service_start(message, state)

@router.message(F.text == "Изменить услугу")
async def alias_edit_service_admin(message: types.Message, state: FSMContext):
    return await admin_edit_service_start(message, state)

@router.message(F.text == "Удалить услугу")
async def alias_delete_service_admin(message: types.Message, state: FSMContext):
    return await admin_delete_service_start(message, state)



@router.message(F.text == "Создать слот")
async def alias_create_slot(message: types.Message, state: FSMContext):
    return await admin_create_slot_start(message, state)

@router.message(F.text == "Изменить слот")
async def alias_edit_slot(message: types.Message, state: FSMContext):
    return await admin_edit_slot_start(message, state)

@router.message(F.text == "Удалить слот")
async def alias_edit_slot(message: types.Message, state: FSMContext):
    return await admin_delete_slot_start(message, state)


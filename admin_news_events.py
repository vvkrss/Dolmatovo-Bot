from aiogram import Router, types, F
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command, StateFilter
from datetime import datetime
#from states import NewsForm
import config
import db
from db import add_news, get_all_news, get_news, update_news
from user_handlers import get_main_keyboard

# Router for news and events management (admin only)
admin_router = Router()
admin_router.message.filter(lambda msg: msg.from_user and msg.from_user.id in config.ADMIN_IDS)
admin_router.callback_query.filter(lambda cq: cq.from_user and cq.from_user.id in config.ADMIN_IDS)

class AddNewsForm(StatesGroup):
    title = State()
    text = State()
    date = State()
    pin = State()

class EditNewsForm(StatesGroup):
    id = State()
    title = State()
    text = State()
    date = State()
    pin = State()



class EventForm(StatesGroup):
    """FSM-форма для поэтапного ввода нового события (мероприятия)."""
    title = State()       # ожидание ввода заголовка события
    desc = State()        # ожидание ввода описания события
    datetime = State()    # ожидание ввода даты и времени события
    place = State()       # ожидание ввода места проведения события

class EditEventForm(StatesGroup):
    """FSM-форма для поэтапного редактирования существующего события."""
    event_id = State()    # ожидание ввода ID редактируемого события
    title = State()       # новый заголовок (или 0, чтобы оставить без изменений)
    desc = State()        # новое описание (или 0, чтобы оставить без изменений)
    datetime = State()    # новая дата/время (или 0, чтобы оставить без изменений)
    place = State()       # новое место проведения (или 0, чтобы оставить без изменений)

class DeleteNewsState(StatesGroup):
    waiting_id = State()
    confirm = State()

class DeleteEventState(StatesGroup):
    waiting_id = State()
    confirm = State()

#=============================================================================================================================================
#                                                       /add_news
#=============================================================================================================================================
@admin_router.message(Command("add_news"))
async def cmd_add_news(message: types.Message, state: FSMContext):
    await state.set_state(AddNewsForm.title)
    await message.answer("Введите заголовок новости:")

@admin_router.message(AddNewsForm.title)
async def add_news_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddNewsForm.text)
    await message.answer("Введите текст новости:")

@admin_router.message(AddNewsForm.text)
async def add_news_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text.strip())
    await state.set_state(AddNewsForm.date)
    await message.answer("Введите дату (ГГГГ-ММ-ДД) или отправьте 0 для сегодняшней:")

@admin_router.message(AddNewsForm.date)
async def add_news_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "0":
        date_str = datetime.now().strftime(config.DATE_FORMAT)
    else:
        try:
            date_str = datetime.strptime(text, config.DATE_FORMAT).strftime(config.DATE_FORMAT)
        except ValueError:
            await message.answer("❌ Неверный формат даты. Введите ГГГГ-ММ-ДД:")
            return
    await state.update_data(date=date_str)
    await state.set_state(AddNewsForm.pin)
    await message.answer("Закрепить новость? (да/нет):")

@admin_router.message(AddNewsForm.pin)
async def add_news_pin(message: types.Message, state: FSMContext):
    pinned = message.text.strip().lower() == "да"
    data = await state.get_data()
    news_id = db.add_news(data["title"], data["text"], data["date"], pinned)
    await message.answer(f"✅ Новость добавлена (ID {news_id}).", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()


#=============================================================================================================================================
#                                                       /edit_news
#=============================================================================================================================================

@admin_router.message(Command("edit_news"))
async def cmd_edit_news(message: types.Message, state: FSMContext):
    news_list = db.get_all_news()
    if not news_list:
        await message.answer("Новостей пока нет.")
        return
    text = "Список новостей:\n" + "\n".join(f"{n['id']}: {n['title']} ({n['date']})" for n in news_list)
    await state.set_state(EditNewsForm.id)
    await message.answer(f"{text}\n\nВведите ID новости для редактирования:")

@admin_router.message(EditNewsForm.id)
async def edit_news_id(message: types.Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("Введите числовой ID:")
        return
    news_id = int(message.text.strip())
    news = db.get_news(news_id)
    if not news:
        await message.answer("Новость не найдена. Попробуйте снова:")
        return
    await state.update_data(id=news_id, old=news)
    await state.set_state(EditNewsForm.title)
    await message.answer(f"Текущий заголовок: {news['title']}\nВведите новый заголовок или 0, чтобы оставить без изменений:")

@admin_router.message(EditNewsForm.title)
async def edit_news_title(message: types.Message, state: FSMContext):
    data = await state.get_data()
    title = data["old"]["title"] if message.text.strip() == "0" else message.text.strip()
    await state.update_data(title=title)
    await state.set_state(EditNewsForm.text)
    await message.answer(f"Текущий текст: {data['old']['text']}\nВведите новый текст или 0:")

@admin_router.message(EditNewsForm.text)
async def edit_news_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = data["old"]["text"] if message.text.strip() == "0" else message.text.strip()
    await state.update_data(text=text)
    await state.set_state(EditNewsForm.date)
    await message.answer(f"Текущая дата: {data['old']['date']}\nВведите новую дату (ГГГГ-ММ-ДД) или 0:")

@admin_router.message(EditNewsForm.date)
async def edit_news_date(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text.strip() == "0":
        date_str = data["old"]["date"]
    else:
        try:
            date_str = datetime.strptime(message.text.strip(), config.DATE_FORMAT).strftime(config.DATE_FORMAT)
        except ValueError:
            await message.answer("❌ Неверный формат. Введите ГГГГ-ММ-ДД или 0:")
            return
    await state.update_data(date=date_str)
    await state.set_state(EditNewsForm.pin)
    status = "да" if data["old"]["pinned"] else "нет"
    await message.answer(f"Новость сейчас {'закреплена' if data['old']['pinned'] else 'не закреплена'}. Закрепить? (да / нет / 0):")

@admin_router.message(EditNewsForm.pin)
async def edit_news_pin(message: types.Message, state: FSMContext):
    data = await state.get_data()
    txt = message.text.strip().lower()
    if txt == "0":
        pinned = data["old"]["pinned"]
    elif txt in ["да", "yes", "1"]:
        pinned = True
    elif txt in ["нет", "no", "false"]:
        pinned = False
    else:
        await message.answer("Введите 'да', 'нет' или '0':")
        return
    db.update_news(
        data["id"],
        data["title"],
        data["text"],
        data["date"],
        pinned
    )
    await message.answer(f"✅ Новость ID {data['id']} успешно обновлена.", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

@admin_router.message(Command("list_news"))
async def cmd_list_news(message: types.Message):
    news_list = db.get_all_news()
    if not news_list:
        await message.answer("Список новостей пуст.")
        return
    text = "\n".join(f"{n['id']}: {n['title']} ({n['date']}){' [PIN]' if n['pinned'] else ''}" for n in news_list)
    await message.answer("📰 Новости:\n" + text, reply_markup=get_main_keyboard(message.from_user.id))


#==========================================================================================================================================
#                                                       /delete_news
#==========================================================================================================================================

@admin_router.message(Command("delete_news"))
async def cmd_delete_news(message: types.Message, state: FSMContext):
    news_list = db.get_all_news()
    if not news_list:
        await message.answer("Список новостей пуст.")
        return

    lines = ["🗞 <b>Список новостей:</b>"]
    for n in news_list:
        lines.append(f"{n['id']}: {n['title']} ({n['date']})")
    lines.append("\nВведите ID новости для удаления:")
    await message.answer("\n".join(lines), parse_mode="HTML")
    await state.set_state(DeleteNewsState.waiting_id)

@admin_router.message(DeleteNewsState.waiting_id)
async def process_delete_news_id(message: types.Message, state: FSMContext):
    try:
        news_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID.")
        return

    news = db.get_news(news_id)
    if not news:
        await message.answer("❌ Новость с таким ID не найдена.")
        await state.clear()
        return

    await state.update_data(news_id=news_id)
    await state.set_state(DeleteNewsState.confirm)
    await message.answer(f"Вы уверены, что хотите удалить новость #{news_id} '{news['title']}'? (да/нет)")

@admin_router.message(DeleteNewsState.confirm)
async def process_delete_news_confirm(message: types.Message, state: FSMContext):
    text = message.text.strip().lower()
    if text != "да":
        await message.answer("❌ Удаление отменено.")
        await state.clear()
        return

    data = await state.get_data()
    news_id = data.get("news_id")
    db.delete_news(news_id)
    await message.answer(f"✅ Новость #{news_id} удалена.", reply_markup=get_main_keyboard(message.from_user.id))
    admin_id = db.get_user_id_by_tg(message.from_user.id)
    db.log_action(admin_id, f"Admin удалил новость ID={news_id}")
    await state.clear()


#==========================================================================================================================================
#                                                       /add_event
#==========================================================================================================================================


@admin_router.message(Command("add_event"))
async def cmd_add_event(message: types.Message, state: FSMContext):
    """Админ-команда: начать добавление нового мероприятия."""
    await message.answer("Добавление события. Введите заголовок события:")
    await state.set_state(EventForm.title)  # переходим в состояние ожидания заголовка

@admin_router.message(EventForm.title)
async def process_event_title(message: types.Message, state: FSMContext):
    """Обрабатываем введенный заголовок нового мероприятия."""
    await state.update_data(title=message.text.strip())  # сохраняем заголовок во временное состояние
    await message.answer("Введите описание события:")
    await state.set_state(EventForm.desc)  # запрашиваем описание

@admin_router.message(EventForm.desc)
async def process_event_desc(message: types.Message, state: FSMContext):
    """Обрабатываем введенное описание мероприятия."""
    await state.update_data(desc=message.text.strip())  # сохраняем описание
    await message.answer("Введите дату и время события в формате YYYY-MM-DD HH:MM:")
    await state.set_state(EventForm.datetime)  # запрашиваем дату и время

@admin_router.message(EventForm.datetime)
async def process_event_datetime(message: types.Message, state: FSMContext):
    """Обрабатываем введенную дату и время мероприятия."""
    date_text = message.text.strip()
    try:
        # Парсим дату и время по заданному формату
        event_dt = datetime.strptime(date_text, config.DATETIME_FORMAT)
    except ValueError:
        # Если формат неверный, просим повторить ввод
        await message.answer("❌ Неверный формат даты/времени. Пожалуйста, введите в формате YYYY-MM-DD HH:MM:")
        return  # остаемся в том же состоянии, не переходя дальше
    # Если дата корректна, сохраняем объект datetime во временные данные состояния
    await state.update_data(event_dt=event_dt)
    await message.answer("Введите место проведения события:")
    await state.set_state(EventForm.place)  # запрашиваем место проведения

@admin_router.message(EventForm.place)
async def process_event_place(message: types.Message, state: FSMContext):
    """Финальный шаг добавления мероприятия: получаем место и сохраняем мероприятие в БД."""
    place = message.text.strip()
    # Получаем ранее введенные данные (заголовок, описание, дату/время)
    data = await state.get_data()
    title = data.get("title")
    desc = data.get("desc")
    event_dt = data.get("event_dt")  # это объект datetime
    # Конвертируем дату/время в строку по формату перед сохранением
    datetime_str = event_dt.strftime(config.DATETIME_FORMAT) if event_dt else None
    # Сохраняем новое событие в базе данных и получаем его ID
    event_id = db.add_event(title, desc, datetime_str, place)
    # Очищаем состояние FSM, завершая процесс добавления
    await state.clear()
    # Логируем в консоль и отправляем подтверждение админу
    import logging
    logging.info(f"Admin {message.from_user.id} added event {event_id}")
    await message.answer(f"✅ Событие #{event_id} добавлено.", reply_markup=get_main_keyboard(message.from_user.id))  # уведомляем о добавлении
    # (При необходимости можно добавить отправку уведомления пользователям о новом событии)

@admin_router.message(Command("edit_event"))
async def cmd_edit_event(message: types.Message, state: FSMContext):
    """Показать список всех мероприятий перед запросом ID."""
    upcoming = db.get_upcoming_events()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.cursor.execute("SELECT id, title, datetime FROM events WHERE datetime < ? ORDER BY datetime DESC", (now_str,))
    past_rows = db.cursor.fetchall()
    past = [{"id": r[0], "title": r[1], "datetime": r[2]} for r in past_rows]

    if not upcoming and not past:
        await message.answer("Список мероприятий пуст.")
        return

    lines = ["📋 <b>Список событий с ID:</b>"]
    for ev in upcoming:
        lines.append(f"{ev['id']}: {ev['title']} ({ev['datetime']})")
    for ev in past:
        lines.append(f"{ev['id']}: {ev['title']} ({ev['datetime']})")

    lines.append("\nВведите ID события для изменения:")
    await message.answer("\n".join(lines), parse_mode="HTML")
    await state.set_state(EditEventForm.event_id)


@admin_router.message(EditEventForm.event_id)
async def process_edit_event_id(message: types.Message, state: FSMContext):
    """Обрабатываем ввод ID события для редактирования."""
    text = message.text.strip()
    if not text.isdigit():
        # Если введено не число, просим повторить ввод ID
        await message.answer("❌ Пожалуйста, введите числовой ID события:")
        return
    event_id = int(text)
    # Проверяем, существует ли событие с таким ID в базе
    event_record = db.get_event(event_id)
    if event_record is None:
        await message.answer("❌ Событие с таким ID не найдено. Отмена операции.")
        await state.clear()
        return
    # Сохраняем ID события в состояние (для дальнейших шагов редактирования)
    await state.update_data(event_id=event_id)
    # Предлагаем ввести новый заголовок (0 - оставить без изменений)
    current_title = event_record["title"]
    await message.answer(f"Текущий заголовок: {current_title}\nВведите новый заголовок события (введите 0, чтобы оставить без изменений):")
    await state.set_state(EditEventForm.title)

@admin_router.message(EditEventForm.title)
async def process_edit_event_title(message: types.Message, state: FSMContext):
    """Обрабатываем новый заголовок (или пропуск) для редактируемого события."""
    title_text = message.text.strip()
    # Если админ ввел "0", оставляем заголовок без изменений (не сохраняем новое значение)
    if title_text == "0":
        # Сохраняем None, чтобы далее интерпретировать как отсутствие изменений
        await state.update_data(new_title=None)
    else:
        # Сохраняем новый заголовок (может быть пустая строка, если админ просто пробел отправил)
        await state.update_data(new_title=title_text)
    await message.answer("Введите новое описание события (введите 0, чтобы оставить без изменений):")
    await state.set_state(EditEventForm.desc)

@admin_router.message(EditEventForm.desc)
async def process_edit_event_desc(message: types.Message, state: FSMContext):
    """Обрабатываем новое описание (или пропуск) для редактируемого события."""
    desc_text = message.text.strip()
    if desc_text == "0":
        await state.update_data(new_desc=None)  # 0 означает без изменений
    else:
        await state.update_data(new_desc=desc_text)
    await message.answer("Введите новую дату/время события в формате YYYY-MM-DD HH:MM (введите 0, чтобы оставить без изменений):")
    await state.set_state(EditEventForm.datetime)

@admin_router.message(EditEventForm.datetime)
async def process_edit_event_datetime(message: types.Message, state: FSMContext):
    """Обрабатываем новую дату/время (или пропуск) для редактируемого события."""
    date_text = message.text.strip()
    new_dt = None
    if date_text == "0" or date_text == "":
        # Если "0" или пусто - оставляем дату/время без изменений (new_dt остается None)
        new_dt = None
    else:
        try:
            # Парсим введенную дату/время
            new_dt = datetime.strptime(date_text, config.DATETIME_FORMAT)
        except ValueError:
            await message.answer("❌ Неверный формат. Введите дату/время в формате YYYY-MM-DD HH:MM (или 0 для пропуска):")
            return
    # Сохраняем новое значение даты/времени (объект datetime или None) в состоянии
    await state.update_data(new_dt=new_dt)
    await message.answer("Введите новое место проведения события (введите 0, чтобы оставить без изменений):")
    await state.set_state(EditEventForm.place)

@admin_router.message(EditEventForm.place)
async def process_edit_event_place(message: types.Message, state: FSMContext):
    """Финальный шаг редактирования события: обновляем запись в базе данных."""
    place_text = message.text.strip()
    # Получаем накопленные данные о редактировании
    data = await state.get_data()
    event_id = data.get("event_id")
    # Получаем текущие сохраненные данные события из БД (чтобы знать старые значения)
    event = db.get_event(event_id)
    if event is None:
        await message.answer("❌ Ошибка: событие не найдено в базе.")
        await state.clear()
        return
    # Определяем новые значения полей или оставляем старые, если ввели 0 (None)
    new_title = data.get("new_title")
    new_desc = data.get("new_desc")
    new_dt_obj = data.get("new_dt")  # может быть datetime или None
    # Формируем окончательные значения для обновления, подставляя старые, если новые не указаны
    updated_title = new_title if new_title not in (None, "") else event["title"]
    updated_desc = new_desc if new_desc not in (None, "") else event["description"]
    if new_dt_obj is not None:
        # Если введена новая дата/время, конвертируем в строку перед сохранением
        updated_dt_str = new_dt_obj.strftime(config.DATETIME_FORMAT)
    else:
        updated_dt_str = event["datetime"]  # оставляем старое значение (в виде строки)
    updated_place = place_text if place_text not in ("", "0") else event["location"]
    # Обновляем запись о событии в базе данных новыми значениями
    # (предполагается, что функция update_event реализована в db.py по аналогии с update_news)
    db.cursor.execute("UPDATE events SET title = ?, description = ?, datetime = ?, location = ? WHERE id = ?",
                      (updated_title, updated_desc, updated_dt_str, updated_place, event_id))
    db.conn.commit()
    # Завершаем FSM-сессию редактирования
    await state.clear()
    # Логируем изменение и уведомляем администратора об успешном обновлении
    import logging
    logging.info(f"Admin {message.from_user.id} edited event {event_id}")
    await message.answer(f"✅ Событие #{event_id} обновлено.", reply_markup=get_main_keyboard(message.from_user.id))

@admin_router.message(Command("list_events"))
async def cmd_list_events(message: types.Message):
    """Админ-команда: вывести список всех мероприятий, отсортированных по дате."""
    # Получаем предстоящие события (сегодняшние и будущие) из базы, отсортированные по дате возрастанию
    upcoming_events = db.get_upcoming_events()  # список словарей событий с datetime >= сейчас
    # Получаем прошедшие события (дата < сейчас), отсортированные по дате убыванию (последние прошедшие сверху)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.cursor.execute("SELECT id, title, datetime, location FROM events WHERE datetime < ? ORDER BY datetime DESC", (now_str,))
    past_rows = db.cursor.fetchall()
    past_events = [{"id": r[0], "title": r[1], "datetime": r[2], "location": r[3]} for r in past_rows]
    # Формируем сообщение со списком
    if not upcoming_events and not past_events:
        await message.answer("Список событий пуст.")
        return
    lines = ["📅 <b>События</b>:"]
    # Добавляем предстоящие (ближайшие) события первым блоком
    if upcoming_events:
        lines.append("➡️ <i>Предстоящие мероприятия:</i>")
        for ev in upcoming_events:
            ev_date = ev["datetime"]  # строка в формате YYYY-MM-DD HH:MM
            ev_title = ev["title"]
            ev_location = ev["location"]
            lines.append(f"{ev['id']}. {ev_title} — {ev_date} @ {ev_location}")
    # Добавляем прошедшие события следующим блоком
    if past_events:
        lines.append("\n✅ <i>Прошедшие мероприятия:</i>")
        for ev in past_events:
            ev_date = ev["datetime"]
            ev_title = ev["title"]
            ev_location = ev["location"]
            lines.append(f"{ev['id']}. {ev_title} — {ev_date} @ {ev_location}")
    # Отправляем составленный список одним сообщением (сохраняя форматирование)
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_main_keyboard(message.from_user.id))

#===============================================================================================================================================
#                                                               /delete_event
#===============================================================================================================================================

@admin_router.message(Command("delete_event"))
async def cmd_delete_event(message: types.Message, state: FSMContext):
    upcoming = db.get_upcoming_events()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.cursor.execute("SELECT id, title, datetime FROM events WHERE datetime < ? ORDER BY datetime DESC", (now_str,))
    past_rows = db.cursor.fetchall()
    past = [{"id": r[0], "title": r[1], "datetime": r[2]} for r in past_rows]

    if not upcoming and not past:
        await message.answer("Список мероприятий пуст.")
        return

    lines = ["📅 <b>Список событий:</b>"]
    for ev in upcoming:
        lines.append(f"{ev['id']}: {ev['title']} ({ev['datetime']})")
    for ev in past:
        lines.append(f"{ev['id']}: {ev['title']} ({ev['datetime']})")

    lines.append("\nВведите ID события для удаления:")
    await message.answer("\n".join(lines), parse_mode="HTML")
    await state.set_state(DeleteEventState.waiting_id)


@admin_router.message(DeleteEventState.waiting_id)
async def process_delete_event_id(message: types.Message, state: FSMContext):
    try:
        event_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID.")
        return

    event = db.get_event(event_id)
    if not event:
        await message.answer("❌ Событие с таким ID не найдено.")
        await state.clear()
        return

    await state.update_data(event_id=event_id)
    await state.set_state(DeleteEventState.confirm)
    await message.answer(f"Вы уверены, что хотите удалить событие #{event_id} '{event['title']}'? (да/нет)")

@admin_router.message(DeleteEventState.confirm)
async def process_delete_event_confirm(message: types.Message, state: FSMContext):
    text = message.text.strip().lower()
    if text != "да":
        await message.answer("❌ Удаление отменено.")
        await state.clear()
        return

    data = await state.get_data()
    event_id = data.get("event_id")
    db.delete_event(event_id)
    await message.answer(f"✅ Событие #{event_id} удалено.", reply_markup=get_main_keyboard(message.from_user.id))
    admin_id = db.get_user_id_by_tg(message.from_user.id)
    db.log_action(admin_id, f"Admin удалил событие ID={event_id}")
    await state.clear()

# Обработчик команды /cancel (отмена текущей операции) остается без изменений
from aiogram.filters import StateFilter

@admin_router.message(Command("cancel"), StateFilter("*"))
async def cancel_action(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного действия.")
    else:
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=get_main_keyboard(message.from_user.id))


def register_news_event_handlers(dp: Dispatcher):
    dp.include_router(admin_router)

# админ
@admin_router.message(F.text == "Добавить новость")
async def alias_add_news(message: types.Message, state: FSMContext):
    return await cmd_add_news(message, state)

@admin_router.message(F.text == "Редактировать новость")
async def alias_edit_news(message: types.Message, state: FSMContext):
    return await cmd_edit_news(message, state)

@admin_router.message(F.text == "Удалить новость")
async def alias_delete_news(message: types.Message, state: FSMContext):
    return await cmd_delete_news(message, state)

# @admin_router.message(F.text == "Список новостей")
# async def alias_list_news(message: types.Message, state: FSMContext):
#     return await cmd_list_news(message, state)



@admin_router.message(F.text == "Создать событие")
async def alias_create_event(message: types.Message, state: FSMContext):
    return await cmd_add_event(message, state)

@admin_router.message(F.text == "Удалить событие")
async def alias_delete_event(message: types.Message, state: FSMContext):
    return await cmd_delete_event(message, state)

@admin_router.message(F.text == "Изменить событие")
async def alias_edit_event(message: types.Message, state: FSMContext):
    return await cmd_edit_event(message, state)

# @admin_router.message(F.text == "Список событий")
# async def alias_list_event(message: types.Message, state: FSMContext):
#     return await cmd_list_events(message, state)



@admin_router.message(F.text == "Отмена")
async def alias_cancel(message: types.Message, state: FSMContext):
    return await cancel_action(message, state)

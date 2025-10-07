# admin_requests.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_IDS
import db
from user_handlers import get_main_keyboard

router = Router()

@router.message(Command("travel_requests"))
async def cmd_travel_requests(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("❌ У вас нет прав для этой команды.")
        return

    # возвращает list[{"id","user_name","tg_id","travel_dt","car_number","purpose"}]
    requests = db.get_pending_travel_requests()
    if not requests:
        await message.reply("Нет заявок, ожидающих утверждения.")
        return

    for req in requests:
        req_id     = req["id"]
        user_name  = req["user_name"]
        travel_dt    = req["travel_dt"]
        vehicle_type = req["vehicle_type"]
        car_number   = req["car_number"]
        purpose      = req["purpose"]

        text = (
            f"Заявка #{req_id} от {user_name}:\n"
            f"🚘 Тип: {'Грузовая' if vehicle_type=='cargo' else 'Легковая'}\n"
            f"📅 Дата/время: {travel_dt}\n"
            f"🚗 Машина: {car_number}\n"
            f"🎯 Цель: {purpose}"
        )

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Одобрить", callback_data=f"travel:approve:{req_id}")
        builder.button(text="❌ Отклонить",  callback_data=f"travel:reject:{req_id}")
        builder.adjust(2)  # две кнопки в ряд

        await message.reply(text, reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("travel:"))
async def callback_travel_request(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    _, action, sid = callback.data.split(":")
    req_id = int(sid)
    req = db.get_travel_request(req_id)
    if not req:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    # обновляем статус
    new_status = "approved" if action == "approve" else "rejected"
    db.update_travel_request_status(req_id, new_status)
    # если одобрено и грузовая — выставляем счёт 500 ₽  
    if new_status == "approved" and req["vehicle_type"] == "cargo":
        invoice_id = db.add_invoice(req["user_id"], 500, req["travel_dt"])
    # готовим текст уведомления
    message_text = f"Ваша заявка на проезд {('одобрена' if new_status=='approved' else 'отклонена')}."
    if new_status == "approved" and req["vehicle_type"] == "cargo":
        message_text += f" Счёт №{invoice_id} на 500 ₽ выставлен."

    # помечаем в исходном сообщении
    mark = "✅ Одобрена" if new_status == "approved" else "❌ Отклонена"
    new_text = callback.message.text + f"\n\nСтатус: {mark}"
    try:
        await callback.message.edit_text(new_text)
    except:
        # если не удалось изменить текст, просто убираем кнопки
        await callback.message.edit_reply_markup(reply_markup=None)

    await callback.answer("Статус обновлён.")

    # уведомляем пользователя
    try:
        await callback.bot.send_message(
            req["tg_id"],
            message_text,
            reply_markup=get_main_keyboard(req["tg_id"])
        )
    except:
        pass


    # логируем
    admin_id = db.get_user_id_by_tg(callback.from_user.id)
    db.log_action(admin_id, f"Admin {new_status} travel_request ID={req_id}")


# alias для кнопки в меню
@router.message(F.text == "Заявки на проезд")
async def alias_travel_requests(message: types.Message):
    return await cmd_travel_requests(message)

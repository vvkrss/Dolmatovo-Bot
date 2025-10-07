import asyncio
import logging
import shutil
import os
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import db
from user_handlers import user_router
#import handlers_admin
# import handlers_accountant
from config import BOT_TOKEN, DB_PATH
from admin_requests import router as travel_router
from admin_services import router as service_router

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from admin_news_events import register_news_event_handlers

from admin_news_events import admin_router
from accountant_payments import accountant_router
from master_handlers import router as master_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

async def main():
    # 1) Инициализация БД
    db.init_db()

    # 2) Планировщик фоновых задач
    scheduler = AsyncIOScheduler()
    # Ежедневный бэкап в 3:00
    def backup_db():
        if not os.path.exists('backups'):
            os.makedirs('backups')
        name = datetime.now().strftime("backup_%Y%m%d.db")
        shutil.copy(DB_PATH, os.path.join('backups', name))
        logging.info(f"Backup saved as {name}")
    scheduler.add_job(backup_db, 'cron', hour=3, minute=0)
    scheduler.start()

    # 3) Бот и диспетчер
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # 4) Подключаем роутеры

    dp.include_router(user_router)

    #handlers_admin.register_admin_handlers(dp, scheduler)
    dp.include_router(admin_router)
    dp.include_router(travel_router)
    dp.include_router(master_router)
    dp.include_router(service_router)
    dp.include_router(accountant_router)
    # dp.include_router(handlers_accountant.router)
    #register_news_event_handlers(dp)

    logging.info("Bot started, polling...")
    # 5) Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

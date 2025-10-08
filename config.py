# config.py: Configuration constants for the Telegram bot
# Здесь храним конфигурационные параметры: токен бота, списки администраторов и бухгалтеров, и др.

BOT_TOKEN = "8301063279:AAH3GacUaNDknOzxa0TAqYAhLwMNjLymrTY"

# Списки ID пользователей Telegram, имеющих роли Админа и Бухгалтера
ADMIN_IDS = [5424756440, 6981724635]
ACCOUNTANT_IDS = [940696947]
MASTER_IDS = [5191119160]

# Путь к базе данных SQLite
DB_PATH = "data.db"

# Временные параметры напоминаний
EVENT_REMINDER_HOUR = 9  # час утра для напоминания о событиях (например, 9 = 9:00 утра в день события)

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_CONTRIBUTION_AMOUNT = 1000.0

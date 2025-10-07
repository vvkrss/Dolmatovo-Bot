# states.py: Определение состояний (Finite State Machine) для многошаговых команд

from aiogram.fsm.state import State, StatesGroup

# Состояния для добавления/редактирования новости (5.1)
#class NewsForm(StatesGroup):
#    title = State()   # ожидание ввода заголовка новости
#    text = State()    # ожидание ввода текста новости
#    date = State()    # ожидание ввода даты новости
#    pin = State()     # ожидание флага "закрепить новость"

# Состояния для создания мероприятия (5.2)
#class EventForm(StatesGroup):
#    title = State()       # ожидание ввода названия события
#    description = State() # ожидание ввода описания события
#    datetime = State()    # ожидание ввода даты/времени события
#    location = State()    # ожидание ввода места проведения

# Состояния для добавления услуги (5.3) - здесь одна стадия (название услуги)
class ServiceForm(StatesGroup):
    name = State()        # ожидание ввода названия новой услуги

# Состояния для редактирования услуги (5.3)
class ServiceEditForm(StatesGroup):
    service_id    = State()
    new_name      = State()
    price_choice  = State()
    new_price     = State()

# Состояния для удаления услуги (5.3)
class ServiceDeleteForm(StatesGroup):
    service_id = State()  # ожидание ввода ID услуги для удаления

# Состояния для создания тайм-слота услуги (5.3)
class SlotCreateForm(StatesGroup):
    service_id = State()
    datetime   = State()

class SlotEditForm(StatesGroup):
    service_id = State()
    slot_id    = State()
    datetime   = State()

class SlotDeleteForm(StatesGroup):
    service_id = State()
    slot_id    = State()

# Состояние для заявки на проезд (5.4 со стороны жителя)
class TravelRequestForm(StatesGroup):
    vehicle_type = State() # выбор типа машины: легковая/грузовая
    date_time    = State() # дата и время поездки
    car_number   = State() # номер машины
    purpose      = State() # цель поездки

# Состояние для загрузки CSV взносов (5.6 импорт списка взносов)
class ImportCSVState(StatesGroup):
    waiting_file = State() # ожидание загрузки файла CSV от пользователя (бухгалтера)

# Состояния для процесса бронирования услуги жителем
class BookingForm(StatesGroup):
    service    = State()  # уже был
    date_year  = State()  # новый
    date_month = State()  # новый
    date_day   = State()  # новый
    slot       = State()  # уже был

class EditRequestForm(StatesGroup):
    request_id = State()
    new_slot   = State()

class DeleteRequestForm(StatesGroup):
    request_id = State()

class ServiceCreateForm(StatesGroup):
    name         = State()  # старое: ServiceForm.name
    price        = State()
    generate     = State()
    work_time    = State()  # формат "HH:MM-HH:MM"
    slot_length  = State()  # минуты
    weekdays     = State()    # <--- новый
    period       = State()

class ManualSlotForm(StatesGroup):
    service_id = State()   # ожидание выбора услуги
    slot_id    = State()   # ожидание выбора ID слота (для edit/delete)
    start_time = State()   # ввод времени начала
    duration   = State()   # ввод длительности в минутах
    weekdays   = State()    # <--- новый
    period     = State()

class MasterForm(StatesGroup):
    wait_contact = State()

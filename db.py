# db.py: Работа с базой данных (SQLite) для хранения данных (7.1)
import sqlite3
from datetime import datetime
from config import DB_PATH

# Устанавливаем соединение с БД SQLite
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON;")  # включаем поддержку foreign key
cursor = conn.cursor()

def init_db():
    """Создает таблицы в базе данных, если их еще нет."""
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        tg_id INTEGER UNIQUE,
        first_name TEXT,
        last_name TEXT,
        username TEXT,
        phone TEXT,
        is_admin INTEGER,
        is_accountant INTEGER
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        text TEXT,
        date TEXT,
        pinned INTEGER
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        datetime TEXT,
        location TEXT
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY,
            name TEXT,
            price REAL DEFAULT 0
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS slots (
        id INTEGER PRIMARY KEY,
        service_id INTEGER,
        datetime TEXT,
        booked_by INTEGER,
        FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE,
        FOREIGN KEY(booked_by) REFERENCES users(id)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS travel_requests (
        id             INTEGER PRIMARY KEY,
        user_id        INTEGER,
        travel_dt      TEXT,
        vehicle_type   TEXT,
        car_number     TEXT,
        purpose        TEXT,
        status         TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
# --- миграция: добавляем столбец vehicle_type, если его нет ---
    cursor.execute("PRAGMA table_info(travel_requests)")
    cols = [row[1] for row in cursor.fetchall()]
    if "vehicle_type" not in cols:
        cursor.execute("ALTER TABLE travel_requests ADD COLUMN vehicle_type TEXT")
    conn.commit()
    cursor.execute("""CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        status TEXT,
        period TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS actions_log (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        user_id INTEGER,
        action TEXT
    )""")
    conn.commit()

# ----- Пользователи -----
def add_user(tg_id, first_name, last_name, username, is_admin=0, is_accountant=0):
    """Добавляет пользователя в БД (если его нет). Возвращает id пользователя."""
    try:
        cursor.execute("INSERT INTO users (tg_id, first_name, last_name, username, is_admin, is_accountant) VALUES (?, ?, ?, ?, ?, ?)",
                       (tg_id, first_name, last_name, username, is_admin, is_accountant))
        conn.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        # Пользователь уже существует, получим его id
        cursor.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
        result = cursor.fetchone()
        user_id = result[0] if result else None
    return user_id

def set_user_role(tg_id, is_admin=None, is_accountant=None):
    """Обновляет флаги ролей пользователя (если он существует в БД)."""
    cursor.execute("SELECT id, is_admin, is_accountant FROM users WHERE tg_id = ?", (tg_id,))
    result = cursor.fetchone()
    if result:
        user_id, current_admin, current_accountant = result
        new_admin = current_admin if is_admin is None else (1 if is_admin else 0)
        new_accountant = current_accountant if is_accountant is None else (1 if is_accountant else 0)
        cursor.execute("UPDATE users SET is_admin = ?, is_accountant = ? WHERE id = ?", (new_admin, new_accountant, user_id))
        conn.commit()

def get_user_id_by_tg(tg_id):
    """Возвращает внутренний ID пользователя по его Telegram ID."""
    cursor.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return None

# ----- Новости -----
def add_news(title, text, date_str, pinned):
    cursor.execute("INSERT INTO news (title, text, date, pinned) VALUES (?, ?, ?, ?)", (title, text, date_str, 1 if pinned else 0))
    conn.commit()
    return cursor.lastrowid

def update_news(news_id, title, text, date_str, pinned):
    cursor.execute("UPDATE news SET title = ?, text = ?, date = ?, pinned = ? WHERE id = ?",
                   (title, text, date_str, 1 if pinned else 0, news_id))
    conn.commit()

def get_all_news():
    cursor.execute("SELECT id, title, text, date, pinned FROM news")
    rows = cursor.fetchall()
    news_list = []
    for r in rows:
        news_list.append({"id": r[0], "title": r[1], "text": r[2], "date": r[3], "pinned": bool(r[4])})
    return news_list

def get_news(news_id):
    cursor.execute("SELECT id, title, text, date, pinned FROM news WHERE id = ?", (news_id,))
    row = cursor.fetchone()
    if row:
        return {"id": row[0], "title": row[1], "text": row[2], "date": row[3], "pinned": bool(row[4])}
    return None

def delete_news(news_id):
    cursor.execute("DELETE FROM news WHERE id = ?", (news_id,))
    conn.commit()

def delete_event(event_id):
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()


# ----- Мероприятия -----
def add_event(title, description, datetime_str, location):
    cursor.execute("INSERT INTO events (title, description, datetime, location) VALUES (?, ?, ?, ?)",
                   (title, description, datetime_str, location))
    conn.commit()
    return cursor.lastrowid

def get_upcoming_events():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("SELECT id, title, description, datetime, location FROM events WHERE datetime >= ? ORDER BY datetime", (now_str,))
    rows = cursor.fetchall()
    events = []
    for r in rows:
        events.append({"id": r[0], "title": r[1], "description": r[2], "datetime": r[3], "location": r[4]})
    return events

def get_event(event_id):
    cursor.execute("SELECT id, title, description, datetime, location FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    if row:
        return {"id": row[0], "title": row[1], "description": row[2], "datetime": row[3], "location": row[4]}
    return None

# ----- Услуги -----
def add_service(name, price):
    cursor.execute(
        "INSERT INTO services (name, price) VALUES (?, ?)",
        (name, price)
    )
    conn.commit()
    return cursor.lastrowid

def update_service(service_id, new_name, price=None):
    if price is None:
        cursor.execute("UPDATE services SET name = ? WHERE id = ?", (new_name, service_id))
    else:
        cursor.execute(
            "UPDATE services SET name = ?, price = ? WHERE id = ?",
            (new_name, price, service_id)
        )
    conn.commit()

def delete_service(service_id):
    # Удаляем слоты услуги
    cursor.execute("DELETE FROM slots WHERE service_id = ?", (service_id,))
    cursor.execute("DELETE FROM services WHERE id = ?", (service_id,))
    conn.commit()

def get_all_services():
    cursor.execute("SELECT id, name, price FROM services")
    rows = cursor.fetchall()
    return [
        {"id": r[0], "name": r[1], "price": r[2]}
        for r in rows
    ]

def get_service(svc_id):
    cursor.execute("SELECT id, name, price FROM services WHERE id = ?", (svc_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "price": row[2]}

def add_service_request(service_id: int, slot_id: int, user_id: int) -> int:
    """
    Создаёт новую заявку для мастера при бронировании слота.
    Возвращает internal id записи в service_requests.
    """
    cursor.execute("""
        INSERT INTO service_requests (service_id, slot_id, user_id)
        VALUES (?, ?, ?)
    """, (service_id, slot_id, user_id))
    conn.commit()
    return cursor.lastrowid

# ----- Услуги -----
def get_user_service_requests(user_id: int, statuses: list) -> list:
    """
    Возвращает список заявок данного пользователя с указанными статусами.
    """
    placeholder = ",".join("?" for _ in statuses)
    cursor.execute(f"""
        SELECT sr.id, sr.service_id, s.name, sr.slot_id, sl.datetime, sr.status
        FROM service_requests sr
        JOIN services s ON sr.service_id = s.id
        JOIN slots sl ON sr.slot_id = sl.id
        WHERE sr.user_id = ? AND sr.status IN ({placeholder})
        ORDER BY sr.id
    """, (user_id, *statuses))
    rows = cursor.fetchall()
    return [
        {
            "id":    r[0],
            "service_id": r[1],
            "service_name": r[2],
            "slot_id": r[3],
            "slot_datetime": r[4],
            "status": r[5]
        }
        for r in rows
    ]

def get_service_request(req_id: int) -> dict | None:
    """Возвращает словарь по заявке или None."""
    cursor.execute("""
        SELECT id, service_id, slot_id, user_id, master_id, status, amount
        FROM service_requests WHERE id = ?
    """, (req_id,))
    r = cursor.fetchone()
    if not r:
        return None
    return {
        "id": r[0], "service_id": r[1], "slot_id": r[2],
        "user_id": r[3], "master_id": r[4],
        "status": r[5], "amount": r[6]
    }

# ----- Тайм-слоты -----
def add_slot(service_id, datetime_str):
    cursor.execute("INSERT INTO slots (service_id, datetime, booked_by) VALUES (?, ?, NULL)", (service_id, datetime_str))
    conn.commit()
    return cursor.lastrowid

def book_slot(slot_id, user_id):
    cursor.execute("UPDATE slots SET booked_by = ? WHERE id = ?", (user_id, slot_id))
    conn.commit()

def get_available_slots(service_id):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("SELECT id, datetime FROM slots WHERE service_id = ? AND booked_by IS NULL AND datetime >= ? ORDER BY datetime", (service_id, now_str))
    rows = cursor.fetchall()
    slots = []
    for r in rows:
        slots.append({"id": r[0], "datetime": r[1]})
    return slots

def get_slot(slot_id):
    cursor.execute("SELECT id, service_id, datetime, booked_by FROM slots WHERE id = ?", (slot_id,))
    row = cursor.fetchone()
    if row:
        return {"id": row[0], "service_id": row[1], "datetime": row[2], "booked_by": row[3]}
    return None

def update_slot(slot_id: int, datetime_str: str):
    """
    Переносит слот в новое время.
    """
    cursor.execute(
        "UPDATE slots SET datetime = ? WHERE id = ?",
        (datetime_str, slot_id)
    )
    conn.commit()

def delete_slot(slot_id: int):
    """
    Удаляет слот.
    """
    cursor.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
    conn.commit()

# ----- Заявки на проезд -----
def add_travel_request(user_id: int, travel_dt: str, vehicle_type: str, car_number: str, purpose: str) -> int:
    cursor.execute("""
        INSERT INTO travel_requests
            (user_id, travel_dt, vehicle_type, car_number, purpose, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
        """,
        (user_id, travel_dt, vehicle_type, car_number, purpose)
    )
    conn.commit()
    return cursor.lastrowid

def get_pending_travel_requests():
    cursor.execute("""
        SELECT
          tr.id,
          tr.travel_dt,
          tr.vehicle_type,
          tr.car_number,
          tr.purpose,
          u.first_name,
          u.last_name,
          u.tg_id
        FROM travel_requests tr
          JOIN users u ON tr.user_id = u.id
        WHERE tr.status = 'pending'
    """)
    requests = []
    for r in cursor.fetchall():
        user_name = " ".join(filter(None, (r[5], r[6])))
        requests.append({
            "id":           r[0],
            "travel_dt":    r[1],
            "vehicle_type": r[2],
            "car_number":   r[3],
            "purpose":      r[4],
            "user_name":    user_name,
            "tg_id":        r[7],
        })

    return requests

def update_travel_request_status(req_id: int, status: str) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE travel_requests SET status = ? WHERE id = ?",
        (status, req_id)
    )
    conn.commit()


def get_travel_request(request_id):
    cursor.execute("""
        SELECT
          tr.id,
          tr.user_id,         -- добавили user_id
          tr.travel_dt,
          tr.vehicle_type,
          tr.car_number,
          tr.purpose,
          tr.status,
          u.tg_id
        FROM travel_requests tr
        JOIN users u ON tr.user_id = u.id
        WHERE tr.id = ?
    """, (request_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "id":           row[0],
        "user_id":      row[1],  # теперь доступно
        "travel_dt":    row[2],
        "vehicle_type": row[3],
        "car_number":   row[4],
        "purpose":      row[5],
        "status":       row[6],
        "tg_id":        row[7],
    }

# ----- Счета/взносы -----
def add_invoice(user_id, amount, period):
    cursor.execute("INSERT INTO invoices (user_id, amount, status, period) VALUES (?, ?, 'unpaid', ?)", (user_id, amount, period))
    conn.commit()
    return cursor.lastrowid

def get_unpaid_invoices():
    cursor.execute("SELECT inv.id, inv.amount, inv.period, u.first_name, u.last_name, u.tg_id FROM invoices inv JOIN users u ON inv.user_id = u.id WHERE inv.status = 'unpaid'")
    rows = cursor.fetchall()
    invoices = []
    for r in rows:
        user_name = r[3] if r[3] else ""
        if r[4]:
            user_name += " " + r[4]
        invoices.append({"id": r[0], "amount": r[1], "period": r[2], "user_name": user_name.strip(), "tg_id": r[5]})
    return invoices

def mark_invoice_paid(invoice_id):
    cursor.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (invoice_id,))
    conn.commit()

def get_user_unpaid_sum(user_id):
    cursor.execute("SELECT SUM(amount) FROM invoices WHERE user_id = ? AND status = 'unpaid'", (user_id,))
    result = cursor.fetchone()
    if result and result[0]:
        return float(result[0])
    return 0.0

# ----- Логирование действий -----
def log_action(user_id, action_text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO actions_log (timestamp, user_id, action) VALUES (?, ?, ?)", (timestamp, user_id, action_text))
    conn.commit()


def get_user_booked_slots(user_id: int) -> list[dict]:
    """
    Возвращает список слотов, забронированных данным пользователем.
    Каждый элемент — словарь с полями 'id' и 'datetime'.
    """
    cursor.execute("""
        SELECT id, datetime
        FROM slots
        WHERE booked_by = ?
        ORDER BY datetime
    """, (user_id,))
    rows = cursor.fetchall()
    return [{"id": r[0], "datetime": r[1]} for r in rows]


def cancel_slot(slot_id: int) -> None:
    """
    Отменяет бронь слота — сбрасывает booked_by в NULL.
    """
    cursor.execute(
        "UPDATE slots SET booked_by = NULL WHERE id = ?",
        (slot_id,)
    )
    conn.commit()


def get_slots_by_service(service_id: int) -> list[dict]:
    """
    Возвращает список свободных (booked_by IS NULL) слотов для данной услуги.
    Каждый элемент — словарь с полями 'id' и 'datetime'.
    """
    cursor.execute(
        """
        SELECT id, datetime
        FROM slots
        WHERE service_id = ? AND booked_by IS NULL
        ORDER BY datetime
        """,
        (service_id,),
    )
    rows = cursor.fetchall()
    return [{"id": r[0], "datetime": r[1]} for r in rows]

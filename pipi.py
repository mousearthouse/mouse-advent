import os
import telebot
import random
import time
import schedule
import threading
import json
import requests
import psycopg2

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from telebot import apihelper

API_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot(API_TOKEN)

IMAGES_DIR = "/app/images"
YANDEX_PUBLIC_KEY = "https://disk.yandex.ru/d/FD7SyyPVQuoP4A"

def download_all_images():
    url = "https://cloud-api.yandex.net/v1/disk/public/resources"
    params = {"public_key": YANDEX_PUBLIC_KEY, "limit": 1000}

    data = requests.get(url, params=params).json()
    items = data.get("_embedded", {}).get("items", [])

    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)

    files = {}

    for item in items:
        name = item.get("name")
        if name.lower().endswith(".jpg"):
            file_url = item.get("file")
            if not file_url:
                continue

            filepath = os.path.join(IMAGES_DIR, name)

            if not os.path.exists(filepath):
                print(f"Скачиваю {name}...")
                resp = requests.get(file_url)
                with open(filepath, "wb") as f:
                    f.write(resp.content)

            day = name.split('.')[0]
            files[day] = filepath

    print("Все картинки загружены.")
    return files

print("Загружаю картинки из Яндекс.Диска...")
pictures = download_all_images()
print("Готово!", pictures)

ANEKDOTES_URL = "https://disk.yandex.ru/d/067XkjwlbOS8aw"

def load_anekdotes():
    url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
    params = {
        "public_key": ANEKDOTES_URL
    }

    try:
        data = requests.get(url, params=params, timeout=10).json()

        download_url = data.get("href")
        if not download_url:
            return {}
        resp = requests.get(download_url, timeout=10)
        resp.raise_for_status()
        return json.loads(resp.text)

    except Exception as e:
        print("ERROR:", e)
        return {}

anekdotes = load_anekdotes()
print(anekdotes)

default_start_time = "10:30"

def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS general (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            sent_images TEXT
        );
    """)

    cursor.execute("""
        INSERT INTO general (key, value)
        VALUES ('current_day', '0')
        ON CONFLICT (key) DO NOTHING;
    """)

    conn.commit()
    cursor.close()
    conn.close()

def get_conn():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )

# Utility functions
def get_current_day():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM general WHERE key='current_day'")
    value = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return int(value)

def increment_day():
    conn = get_conn()
    cursor = conn.cursor()
    current_day = get_current_day() + 1
    cursor.execute(
        "UPDATE general SET value=%s WHERE key='current_day'",
        (str(current_day),)
    )
    conn.commit()
    cursor.close()
    conn.close()

def add_user(user_id, username):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (user_id, username, sent_images)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, username, "[]")
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_user(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT sent_images FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None

def update_user_images(user_id, sent_images):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET sent_images=%s WHERE user_id=%s",
        (sent_images, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

def find_right_users(all_users):
    current_day = get_current_day()
    right_users = []
    for (uid,) in all_users:
        user_images = get_user(uid)

        if not user_images:
            bot.send_message(uid, "Похоже, что мы еще не знакомы. Отправь /start.")
            continue

        sent_images = eval(user_images)
        remaining_days = current_day - len(sent_images)
        if remaining_days > 0:
            right_users.append(uid)
    return right_users

# Bot logic
def send_daily_message(user_id=None):
    current_day = get_current_day()
    conn = get_conn()
    cursor = conn.cursor()
    if user_id:
        users = [(user_id,)]
    else:
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()

    right_users = find_right_users(users)
    for user in right_users:
        uid = user
        print(uid)
        try:
            keyboard = InlineKeyboardMarkup()
            open_button = InlineKeyboardButton("Открыть 🎀", callback_data="open_image")
            keyboard.add(open_button)

            bot.send_message(
                uid,
                f"День {current_day}! Нажми кнопку, чтобы открыть картинку ✨",
                reply_markup=keyboard
            )
        except apihelper.ApiTelegramException as e:
            if e.result.status_code == 403 and "bot was blocked by the user" in e.description:
                print(f"Пользователь {uid} заблокировал бота. Удаляю его из базы.")
                cursor.execute("DELETE FROM users WHERE user_id=%s", (uid,))
                conn.commit()
            elif e.result.status_code == 400:
                print(f"Пользователь {uid} удалил бота. Удаляю его из базы.")
                cursor.execute("DELETE FROM users WHERE user_id=%s", (uid,))
                conn.commit()
            else:
                print(f"Ошибка при отправке сообщения пользователю {uid}: {e}")
    cursor.close()
    conn.close()

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = str(message.chat.id)
    username = message.from_user.username or "Unknown"
    add_user(user_id, username)

    bot.reply_to(
        message,
        f"Добро пожаловать! Сегодня {get_current_day()} день адвента. Каждый день ты можешь получить две смешнявки: картинку и анекдот. Некоторые анекдоты взяты из интернета, некоторые сгенерированы нейронкой, некоторые подкинули мне друзья 🎄 Можно предложить свой анекдот или идею для картинки - я буду благодарна! Для этого можно написать мне в личку: @forggi. Надеюсь, адвент тебе понравится :D"
    )
    send_daily_message(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "open_image")
def handle_open_image(call):
    user_id = str(call.message.chat.id)
    current_day = get_current_day()

    user_images = get_user(user_id)
    if user_images is None:
        bot.send_message(
            user_id,
            "Похоже, что мы ещё не знакомы. Отправь команду /start."
        )
        return

    try:
        sent_images = json.loads(user_images)
    except Exception:
        sent_images = []

    remaining_days = current_day - len(sent_images)
    if remaining_days <= 0:
        bot.send_message(user_id, "Ты уже открыл все доступные на сегодня картинки!")
        return
    available_days = [int(day) for day in pictures.keys() if int(day) not in sent_images]
    if not available_days:
        bot.send_message(user_id, "Ты уже открыл все доступные на сегодня картинки!")
        return

    chosen_day = random.choice(available_days)
    chosen_path = pictures[str(chosen_day)]  # теперь путь вида /app/images/3.jpg

    try:
        with open(chosen_path, "rb") as img:
            bot.send_photo(user_id, img)
    except Exception as e:
        bot.send_message(user_id, f"Ошибка при загрузке файла: {e}")
        return

    bot.send_message(user_id, f"Картинка за {len(sent_images)+1}-й день открыта! 🎊")
    anekdot = anekdotes.get(str(chosen_day), "Анекдот не найден :(")
    bot.send_message(user_id, anekdot)
    sent_images.append(chosen_day)
    update_user_images(user_id, json.dumps(sent_images))

    if current_day - len(sent_images) > 0:
        bot.send_message(
            user_id,
            "У тебя остались ещё доступные картинки. Нажми кнопку «Открыть» ещё раз!"
        )

def schedule_daily_messages():
    print("Ежедневная рассылка запущена!")
    start_time = os.environ.get("START_TIME", default_start_time)
    print("Время старта нового дня:", start_time)

    schedule.every().day.at(start_time).do(increment_day)
    schedule.every().day.at(f"{start_time}:05").do(send_daily_message)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    init_db()  # Initialize database
    threading.Thread(target=schedule_daily_messages, daemon=True).start()
    bot.polling(none_stop=True)

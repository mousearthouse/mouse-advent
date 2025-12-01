import os
import telebot
import random
import time
import sqlite3
import schedule
import threading
import json
import requests
import psycopg2

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from telebot import apihelper

# API_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot("7669754606:AAGf4XaWyIUJKxYna3vCzcgLIh_EcxOrc1k")

YANDEX_PUBLIC_KEY = "https://disk.yandex.ru/d/FD7SyyPVQuoP4A"

def load_pictures_from_yandex():
    url = "https://cloud-api.yandex.net/v1/disk/public/resources"
    params = {
        "public_key": YANDEX_PUBLIC_KEY,
        "limit": 1000
    }

    data = requests.get(url, params=params, timeout = 10).json()

    pictures = {}

    for item in data.get('_embedded', {}).get('items', []):
        name = item.get('name', '')
        if name.lower().endswith('.jpg'):
            day = name.split('.')[0]
            direct_url = item.get('file')
            if direct_url:
                pictures[day] = direct_url

    return pictures

pictures = load_pictures_from_yandex()
print(pictures)

anekdotes_file = 'anekdotes.json'
default_start_time = "23:36"
# Initialize the database
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

def load_anekdotes():
    try:
        with open(anekdotes_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

anekdotes = load_anekdotes()
print(anekdotes)

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
            return []

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
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    right_users = find_right_users(users)
    for user in right_users:
        uid = user
        print(uid)
        try:
            keyboard = InlineKeyboardMarkup()
            open_button = InlineKeyboardButton("Открыть", callback_data="open_image")
            keyboard.add(open_button)

            bot.send_message(
                uid,
                f"День {current_day}! Нажми кнопку, чтобы открыть картинку",
                reply_markup=keyboard
            )
        except apihelper.ApiTelegramException as e:
            if e.result.status_code == 403 and "bot was blocked by the user" in e.description:
                print(f"Пользователь {uid} заблокировал бота. Удаляю его из базы.")
                cursor.execute("DELETE FROM users WHERE user_id=?", (uid,))
                conn.commit()
            elif e.result.status_code == 400:
                print(f"Пользователь {uid} удалил бота. Удаляю его из базы.")
                cursor.execute("DELETE FROM users WHERE user_id=?", (uid,))
                conn.commit()
            else:
                print(f"Ошибка при отправке сообщения пользователю {uid}: {e}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = str(message.chat.id)
    username = message.from_user.username or "Unknown"
    add_user(user_id, username)

    bot.reply_to(
        message,
        f"Добро пожаловать! Сегодня {get_current_day()} день адвента. Каждый день ты сможешь получить две смешнявки: картинку и анекдот. Некоторые анекдоты сгенерированы нейронкой, некоторые взяты из интернета, некоторые подкинули мне друзья 🎄"
    )
    send_daily_message(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "open_image")
def handle_open_image(call):
    user_id = str(call.message.chat.id)
    current_day = get_current_day()

    user_images = get_user(user_id)
    if not user_images:
        bot.send_message(user_id, f"Похоже, что мы еще не знакомы. Отправь команду /start.")
        return
    
    sent_images = list(map(int, eval(user_images)))
    remaining_days = current_day - len(sent_images)

    if remaining_days > 0:
        available_days = [
            int(day) for day in pictures.keys()
            if int(day) not in sent_images
        ]
        chosen_day = random.choice(available_days)
        chosen_url = pictures[str(chosen_day)]

        bot.send_photo(user_id, chosen_url)
        bot.send_message(user_id, f"Картинка за {current_day}-й день открыта!")
        anekdot = anekdotes.get(str(chosen_day), "Анекдот не найден :()")
        bot.send_message(user_id, anekdot)
        sent_images.append(chosen_day)
        update_user_images(user_id, str(sent_images))
        remaining_days = current_day - len(sent_images)
        if remaining_days > 0:
            bot.send_message(user_id, "Ты открыл не все доступные картинки. Нажми на кнопку 'открыть' еще раз!")
    else:
        bot.send_message(user_id, "Ты уже открыл все доступные на сегодня картинки!")

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

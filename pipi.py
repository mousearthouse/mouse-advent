import os
import telebot
import random
import time
import sqlite3
import schedule
import threading
import json

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from telebot import apihelper


API_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot(API_TOKEN)

pictures_dir = os.path.join(os.path.dirname(__file__), 'pictures')
pictures = [os.path.join(pictures_dir, f'{i}.png') for i in range(1, 24)]

db_file = 'data/advent_bot.db'
anekdotes_file = 'anekdotes.json'
default_start_time = "07:00"

# Initialize the database
def init_db():
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        # Create tables
        cursor.execute('''CREATE TABLE IF NOT EXISTS general (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            sent_images TEXT
        )''')
        # Initialize current_day if not set
        cursor.execute("INSERT OR IGNORE INTO general (key, value) VALUES ('current_day', '0')")
        conn.commit()


def load_anekdotes():
    try:
        with open(anekdotes_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

anekdotes = load_anekdotes()

# Utility functions
def get_current_day():
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM general WHERE key='current_day'")
        return int(cursor.fetchone()[0])

def increment_day():
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        current_day = get_current_day() + 1
        cursor.execute("UPDATE general SET value=? WHERE key='current_day'", (str(current_day),))
        conn.commit()

def add_user(user_id, username):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('''INSERT OR IGNORE INTO users (user_id, username, sent_images) 
                          VALUES (?, ?, ?)''', (user_id, username, '[]'))
        conn.commit()

def get_user(user_id):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sent_images FROM users WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None

def update_user_images(user_id, sent_images):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET sent_images=? WHERE user_id=?", (sent_images, user_id))
        conn.commit()

def find_right_users(all_users):
    current_day = get_current_day()
    right_users = []
    for (uid,) in all_users:
        user_images = get_user(uid)

        if not user_images:
            bot.send_message(uid, f"Похоже, что мы еще не знакомы. Отправь команду /start.")
            return
        
        sent_images = eval(user_images)
        remaining_days = current_day - len(sent_images)
        if remaining_days > 0:
            right_users.append(uid)
    return right_users

# Bot logic
def send_daily_message(user_id=None):
    current_day = get_current_day()
    with sqlite3.connect(db_file) as conn:
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
    
    sent_images = eval(user_images)  # Retrieve sent images as a list
    remaining_days = current_day - len(sent_images)
    
    if remaining_days > 0:
        available_images = list(set(pictures) - set(sent_images))
        chosen_image = random.choice(available_images)
        
        bot.send_photo(user_id, open(chosen_image, 'rb'))
        bot.send_message(user_id, f"Картинка за {current_day}-й день открыта!")
        chosen_image_name = os.path.basename(chosen_image)
        anekdot = anekdotes.get(chosen_image_name, "Анекдот не найден :()")
        bot.send_message(user_id, anekdot)
        sent_images.append(chosen_image)
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

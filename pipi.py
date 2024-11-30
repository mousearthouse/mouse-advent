import os
import telebot
import random
import time
import sqlite3
import schedule
import threading

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup


API_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot(API_TOKEN)

pictures_dir = os.path.join(os.path.dirname(__file__), 'pictures')
pictures = [os.path.join(pictures_dir, f'{i}.png') for i in range(1, 4)]

db_file = 'advent_bot.db'

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

        for (uid,) in users:
            keyboard = InlineKeyboardMarkup()
            open_button = InlineKeyboardButton("Открыть", callback_data="open_image")
            keyboard.add(open_button)

            bot.send_message(
                uid,
                f"День {current_day}! Нажми кнопку, чтобы открыть картинку",
                reply_markup=keyboard
            )

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = str(message.chat.id)
    username = message.from_user.username or "Unknown"
    add_user(user_id, username)

    bot.reply_to(
        message,
        f"Добро пожаловать! Сегодня {get_current_day()} день адвента. Каждый день ты сможешь получить одну смешнявку 🎄"
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
        sent_images.append(chosen_image)
        update_user_images(user_id, str(sent_images))  # Update sent images
        bot.send_photo(user_id, open(chosen_image, 'rb'))
        bot.send_message(user_id, f"Картинка за {current_day}-й день открыта!")
    else:
        bot.send_message(user_id, "Ты уже открыл все доступные на сегодня картинки!")

def schedule_daily_messages():
    print("Ежедневная рассылка запущена!")
    schedule.every().day.at("07:00").do(increment_day)
    schedule.every().day.at("07:00:05").do(send_daily_message)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    init_db()  # Initialize database
    threading.Thread(target=schedule_daily_messages, daemon=True).start()
    bot.polling(none_stop=True)

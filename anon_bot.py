import telebot
import uuid
import sqlite3
from telebot import types
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

API_TOKEN = 'FIND IT YOURSELF'
bot = telebot.TeleBot(API_TOKEN)
ADMIN_ID = 0


conn = sqlite3.connect('user_links.db', check_same_thread=False)
cursor = conn.cursor()


cursor.execute('''CREATE TABLE IF NOT EXISTS links (
                    user_id INTEGER PRIMARY KEY, 
                    link TEXT NOT NULL)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS stats (
                    date TEXT NOT NULL, 
                    user_count INTEGER DEFAULT 0, 
                    total_messages INTEGER DEFAULT 0,
                    daily_messages INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS total_stats (
                    total_messages INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id INTEGER PRIMARY KEY, 
                    subscribed INTEGER DEFAULT 1)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS ignored_users (
                    user_id INTEGER PRIMARY KEY)''')
conn.commit()
 

messages = {}
reply_mode = {}

def is_ignored(user_id):
    cursor.execute('SELECT 1 FROM ignored_users WHERE user_id = ?', (user_id,))
    return cursor.fetchone() is not None


def get_current_date():
    return datetime.now().strftime('%Y-%m-%d')

def initialize_stats():
    today = get_current_date()
    cursor.execute('SELECT * FROM stats WHERE date = ?', (today,))
    result = cursor.fetchone()


    cursor.execute('SELECT COUNT(*) FROM links')
    user_count = cursor.fetchone()[0]

    if not result:
        cursor.execute('INSERT INTO stats (date, user_count, daily_messages) VALUES (?, ?, ?)', (today, user_count, 0))
    else:
        cursor.execute('UPDATE stats SET user_count = ? WHERE date = ?', (user_count, today))
    
    conn.commit()


def increment_message_count():
    today = get_current_date()
    cursor.execute('UPDATE stats SET daily_messages = daily_messages + 1 WHERE date = ?', (today,))
    cursor.execute('INSERT OR IGNORE INTO total_stats (total_messages) VALUES (0)')
    cursor.execute('UPDATE total_stats SET total_messages = total_messages + 1')
    conn.commit()

def get_stats():
    today = get_current_date()
    cursor.execute('SELECT user_count, daily_messages FROM stats WHERE date = ?', (today,))
    result = cursor.fetchone()
    cursor.execute('SELECT total_messages FROM total_stats')
    result2 = cursor.fetchone()
    if result:
        return {
            'user_count': result[0],
            'total_messages': result2[0],
            'daily_messages': result[1]
        }
    return None


def save_link(user_id, link):
    cursor.execute('INSERT OR IGNORE INTO links (user_id, link) VALUES (?, ?)', (user_id, link))
    conn.commit()
    initialize_stats()

def get_link(user_id):
    cursor.execute('SELECT link FROM links WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def find_user_by_link(link_code):
    cursor.execute('SELECT user_id FROM links WHERE link = ?', (link_code,))
    result = cursor.fetchone()
    return result[0] if result else None

def delete_link(user_id):
    cursor.execute('DELETE FROM links WHERE user_id = ?', (user_id,))
    conn.commit()
    initialize_stats()

@bot.message_handler(func=lambda message: message.text and message.text.startswith('/start '))
def handle_unique_link(message):
    user_id = message.chat.id
    cancel(message)
    link_code = message.text.split()[1]
    target_user_id = find_user_by_link(link_code)

    if target_user_id == user_id:
        bot.send_message(user_id, '<b>Ошибка:</b> нельзя отправить сообщение самому себе.', parse_mode='HTML')
    elif target_user_id:
        bot.send_message(user_id, 'Отправьте анонимное сообщение.')
        bot.send_message(user_id, '/cancel чтобы отменить.')
        messages[user_id] = target_user_id
    else:
        bot.send_message(user_id, '<b>Ошибка:</b> ссылка недействительна.', parse_mode='HTML')

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    cancel(message)
    if get_link(user_id) is None:
        unique_link = str(uuid.uuid4())
        save_link(user_id, unique_link)
        messages[user_id] = None
        cursor.execute('INSERT OR IGNORE INTO subscriptions (user_id) VALUES (?)', (user_id,))
        conn.commit()
        bot.send_message(user_id, f'Ваша уникальная ссылка: https://t.me/messeanoni_bot?start={unique_link}')
        bot.send_message(user_id, '/delete чтобы удалить свою ссылку.')
    else:
        bot.send_message(user_id, '<b>Ошибка:</b> У вас уже есть ссылка. /delete чтобы удалить свою ссылку.', parse_mode='HTML')

@bot.message_handler(commands=['cancel'])
def cancel(message):
    user_id = message.chat.id
    if user_id in messages and messages[user_id] is not None:
        messages[user_id] = None
        bot.send_message(user_id, 'Посление отменено.')
    elif user_id in reply_mode:
        del reply_mode[user_id]
        bot.send_message(user_id, 'Ответ отменён.')

@bot.message_handler(commands=['delete'])
def delete(message):
    user_id = message.chat.id
    cancel(message)
    if get_link(user_id):
        delete_link(user_id)
        bot.send_message(user_id, 'Ваша ссылка успешно удалена.')
    else:
        bot.send_message(user_id, '<b>Ошибка:</b> у вас нет активной ссылки.', parse_mode='HTML')

@bot.message_handler(commands=['updatehistory'])
def subscribe_again(message):
    user_id = message.chat.id
    cancel(message)
    cursor.execute('REPLACE INTO subscriptions (user_id, subscribed) VALUES (?, 1)', (user_id,))
    conn.commit()

    bot.send_message(user_id, 'Вы успешно подписались на обновления.')


@bot.message_handler(commands=['stats'])
def stats(message):
    user_id = message.chat.id
    cancel(message)
    if user_id != ADMIN_ID:
        bot.send_message(user_id, '<b>Ошибка:</b> команда недоступна.', parse_mode='HTML')
        return 
    
    stats = get_stats()

    if stats:
        bot.send_message(user_id, f"Статистика:\nПользователей: {stats['user_count']}\nВсего сообщений: {stats['total_messages']}\nСообщений за сегодня: {stats['daily_messages']}")
    else:
        bot.send_message(user_id, '<b>Ошибка:</b> нет доступной статистики.', parse_mode='HTML')


@bot.message_handler(commands=['update'])
def send_update(message):
    user_id = message.chat.id
    cancel(message)
    if user_id != ADMIN_ID:
        bot.send_message(user_id, '<b>Ошибка:</b> команда недоступна.', parse_mode='HTML')
        return

    update_text = message.text[len('/update'):].strip()

    if update_text == "":
        bot.send_message(user_id, '<b>Ошибка:</b> укажите текст обновления.', parse_mode='HTML')
        return

    cursor.execute('SELECT user_id FROM subscriptions WHERE subscribed = 1')
    subscribed_users = cursor.fetchall()

    for user in subscribed_users:
        try:
            markup = types.InlineKeyboardMarkup()
            unsubscribe_button = types.InlineKeyboardButton("Отписаться", callback_data=f'unsubscribe_{user[0]}')
            markup.add(unsubscribe_button)
            
            bot.send_message(user[0], update_text, parse_mode='HTML', reply_markup=markup)
        except Exception as e:
            print(f"Ошибка при отправке сообщения пользователю {user[0]}: {e}")

    bot.send_message(user_id, 'Обновление успешно отправлено.')

@bot.message_handler(commands=['bug'])
def report_bug(message):
    user_id = message.chat.id
    cancel(message)
    bug_report = message.text[len('/bug'):].strip()

    if bug_report == "":
        bot.send_message(user_id, '<b>Ошибка:</b> опишите проблему после команды /bug.', parse_mode='HTML')
        return

    formatted_report = f'<b>Новый баг-репорт</b>\n\n' \
                       f'<b>От пользователя:</b> <code>{user_id}</code>\n' \
                       f'<b>Сообщение:</b>\n{bug_report}\n\n' \
                       f'<b>Дата:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'

    markup = types.InlineKeyboardMarkup()
    ignore_button = types.InlineKeyboardButton("Игнорировать", callback_data=f'ignore_{user_id}')
    markup.add(ignore_button)

    if not is_ignored(user_id):
        bot.send_message(ADMIN_ID, formatted_report, parse_mode='HTML', reply_markup=markup)
    bot.send_message(user_id, 'Спасибо за сообщение! Ваш баг-репорт был отправлен администратору.')


def send_message(user_id, content_type, file_id=None, caption=None):
    if user_id in messages and messages[user_id] is not None:
        target_user_id = messages[user_id]
        if target_user_id != user_id:
            bot.send_message(user_id, 'Послание отправлено!', parse_mode='HTML')
            increment_message_count()
            markup = types.InlineKeyboardMarkup()
            reply_button = types.InlineKeyboardButton("Ответить", callback_data=f'reply_{user_id}')
            markup.add(reply_button)
            if content_type == 'text':
                bot.send_message(target_user_id, f'<b>Новое послание:</b>\n\n<i>{caption}</i>', parse_mode='HTML', reply_markup=markup)
            else: 
                bot.send_message(target_user_id, f'<b>Новое послание:</b>', parse_mode='HTML', reply_markup=markup)
                if content_type == 'sticker':    
                    bot.send_sticker(target_user_id, file_id)
                elif content_type == 'voice':
                    bot.send_voice(target_user_id, file_id)
                elif content_type == 'video_note':
                    bot.send_video_note(target_user_id, file_id)
                elif content_type == 'video':
                    bot.send_video(target_user_id, file_id, caption=caption)
                elif content_type == 'photo':
                    bot.send_photo(target_user_id, file_id, caption=caption)
                elif content_type == 'document':
                    bot.send_document(target_user_id, file_id, caption=caption)
                elif content_type == 'animation':
                    bot.send_animation(target_user_id, file_id, caption=caption)
    
    elif user_id in reply_mode and reply_mode[user_id]:
        recipient_id = reply_mode[user_id]
        increment_message_count()
        bot.send_message(user_id, 'Ваш ответ был отправлен.')
        del reply_mode[user_id]
        markup = types.InlineKeyboardMarkup()
        reply_button = types.InlineKeyboardButton("Ответить", callback_data=f'reply_{user_id}')
        markup.add(reply_button)
        if content_type == 'text':
            bot.send_message(recipient_id, f'<b>Пришёл ответ:</b>\n\n<i>{caption}</i>', parse_mode='HTML', reply_markup=markup)
        else: 
            bot.send_message(recipient_id, f'<b>Пришёл ответ:</b>', parse_mode='HTML', reply_markup=markup)
            if content_type == 'sticker':
                bot.send_sticker(recipient_id, file_id)
            elif content_type == 'voice':
                bot.send_voice(recipient_id, file_id)
            elif content_type == 'video_note':
                bot.send_video_note(recipient_id, file_id)
            elif content_type == 'video':
                bot.send_video(recipient_id, file_id, caption=caption)
            elif content_type == 'photo':
                bot.send_photo(recipient_id, file_id, caption=caption)
            elif content_type == 'document':
                bot.send_document(recipient_id, file_id, caption=caption)
            elif content_type == 'animation':
                bot.send_animation(recipient_id, file_id, caption=caption)
    else:
        bot.send_message(user_id, 'Вы никому не отправляете сообщение.')



@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    text = message.text
    send_message(user_id, 'text', caption=text)

@bot.message_handler(content_types=['sticker'])
def handle_sticker(message):
    user_id = message.chat.id
    sticker_id = message.sticker.file_id
    send_message(user_id, 'sticker', file_id=sticker_id)

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.chat.id
    voice_id = message.voice.file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'voice', file_id=voice_id, caption=caption)

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    photo_id = message.photo[-1].file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'photo', file_id=photo_id, caption=caption)

@bot.message_handler(content_types=['video'])
def handle_video(message):
    user_id = message.chat.id
    video_id = message.video.file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'video', file_id=video_id, caption=caption)

@bot.message_handler(content_types=['video_note'])
def handle_video_note(message):
    user_id = message.chat.id
    video_note_id = message.video_note.file_id
    send_message(user_id, 'video_note', file_id=video_note_id)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.chat.id
    document_id = message.document.file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'document', file_id=document_id, caption=caption)

@bot.message_handler(content_types=['animation'])
def handle_animation(message):
    user_id = message.chat.id
    animation_id = message.animation.file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'animation', file_id=animation_id, caption=caption)


@bot.callback_query_handler(func=lambda call: call.data.startswith('reply_'))
def handle_reply_button(call):
    user_id = call.message.chat.id
    sender_id = call.data.split('_')[1]
    cancel(call.message)
    bot.send_message(user_id, 'Напишите ответ:')
    reply_mode[user_id] = sender_id
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('unsubscribe_'))
def handle_unsubscribe(call):
    user_id = int(call.data.split('_')[1])
    cancel(call.message)
    cursor.execute('UPDATE subscriptions SET subscribed = 0 WHERE user_id = ?', (user_id,))
    conn.commit()

    bot.send_message(user_id, 'Вы отписались от обновлений.')
    bot.send_message(user_id, '/updatehistory чтобы подписаться обратно.')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ignore_'))
def handle_ignore(call):
    user_id = int(call.data.split('_')[1])
    cancel(call.message)
    cursor.execute('INSERT OR IGNORE INTO ignored_users (user_id) VALUES (?)', (user_id,))
    conn.commit()

    bot.send_message(call.message.chat.id, f'Пользователь {user_id} был добавлен в список игнорируемых.')
    bot.answer_callback_query(call.id, text="Пользователь игнорируется.")


initialize_stats()

scheduler = BackgroundScheduler()
scheduler.add_job(initialize_stats, 'interval', days=1)
scheduler.start()

bot.polling()

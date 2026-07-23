import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
import re
import time
import random
import datetime
import hashlib

from config import *
from database import *
from games import *

init_db()
bot = telebot.TeleBot(BOT_TOKEN)

active_games = {}
user_states = {}
promo_data = {}


def log_action(action, user_id=None, admin_id=None, details=None, balance=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if user_id and admin_id:
        msg = f"[{timestamp}] {action} | user={user_id} | admin={admin_id}"
    elif user_id:
        msg = f"[{timestamp}] {action} | user={user_id}"
    elif admin_id:
        msg = f"[{timestamp}] {action} | admin={admin_id}"
    else:
        msg = f"[{timestamp}] {action}"
    if details:
        msg += f" | {details}"
    if balance is not None:
        msg += f" | new_balance={balance}"
    print(msg)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_user_balance(user_id):
    return get_user(user_id)['balance']

def get_balance_text(user_id):
    user = get_user(user_id)
    return (f"💰 Баланс: {user['balance']} чапиксов\n"
            f"🏆 Выиграно: {user['total_won']} чапиксов\n"
            f"💸 Проиграно: {user['total_lost']} чапиксов")

def get_main_keyboard(user_id, chat_type):
    if chat_type != 'private':
        return ReplyKeyboardRemove()
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    buttons = [
        KeyboardButton("🎁 Бонус"),
        KeyboardButton("👥 Реферал"),
        KeyboardButton("🧪 Химворс"),
        KeyboardButton("💎 Донат"),
        KeyboardButton("🏆 Богач"),
        KeyboardButton("💬 Чаты"),
        KeyboardButton("❓ Помощь"),
        KeyboardButton("💰 Баланс")
    ]
    if is_admin(user_id):
        buttons.append(KeyboardButton("⚙️ Админ панель"))
    keyboard.add(*buttons)
    return keyboard

def admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("💰 Выдать чапиксы"),
        KeyboardButton("⚙️ Установить баланс"),
        KeyboardButton("🔄 Обнулить баланс"),
        KeyboardButton("🔄 Обнулить ВСЕМ"),
        KeyboardButton("📊 Статистика"),
        KeyboardButton("🎫 Создать промокод"),
        KeyboardButton("📋 Список промокодов"),
        KeyboardButton("🗑 Удалить промокод"),
        KeyboardButton("📤 Выдать промокод"),
        KeyboardButton("🔙 Назад")
    ]
    keyboard.add(*buttons)
    return keyboard

def referral_inline(user_id):
    keyboard = InlineKeyboardMarkup()
    if not get_referred_by(user_id):
        keyboard.add(InlineKeyboardButton("📥 Ввести ID пригласившего", callback_data="ref_enter_id"))
    return keyboard if keyboard.keyboard else None


@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    chat_type = message.chat.type
    
    ref_code = None
    if len(message.text.split()) > 1:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            ref_code = param[4:]
    user = get_user(user_id)
    if ref_code and not get_referred_by(user_id):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (ref_code,))
        row = cursor.fetchone()
        conn.close()
        if row:
            referrer_id = row['user_id']
            if referrer_id != user_id:
                set_referral(user_id, referrer_id)
                add_referral_record(referrer_id, user_id, REFERRAL_BONUS_REFERRER, REFERRAL_BONUS_REFERRED)
                update_balance(user_id, REFERRAL_BONUS_REFERRED)
                update_balance(referrer_id, REFERRAL_BONUS_REFERRER)
                log_action("👥 Реферал", user_id=referrer_id, details=f"пригласил user={user_id}, +{REFERRAL_BONUS_REFERRER} (реферер) и +{REFERRAL_BONUS_REFERRED} (реферал)")
                bot.send_message(user_id, f"🎉 Вы получили {REFERRAL_BONUS_REFERRED} чапиксов за регистрацию по реферальной ссылке!")
                try:
                    bot.send_message(referrer_id, f"🎉 Ваш реферал {user_id} зарегистрировался! Вы получили {REFERRAL_BONUS_REFERRER} чапиксов.")
                except:
                    pass
    bot.send_message(
        message.chat.id,
        f"🎰 Добро пожаловать в Чапикс!\n"
        f"Твой баланс: {get_user_balance(user_id)} чапиксов\n\n"
        f"Выбери действие на клавиатуре:",
        reply_markup=get_main_keyboard(user_id, chat_type)
    )


@bot.message_handler(commands=['aend'])
def admin_send_message(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "⛔ У вас нет прав для этой команды.")
        return

    args = message.text.split(maxsplit=1)
    reply_to_msg = message.reply_to_message

    
    if len(args) == 1:
        bot.reply_to(message, 
                     "✏️ Используйте:\n"
                     "`/aend Текст` – отправить в текущий чат\n"
                     "`/aend ID_чата Текст` – отправить в указанный чат\n"
                     "Ответьте на сообщение и напишите `/aend Текст` – ответить в текущем чате",
                     parse_mode='Markdown')
        return

    
    first_part = args[1]
    parts = first_part.split(maxsplit=1)
    target_chat_id = None
    text_to_send = None

    
    try:
        potential_id = int(parts[0])
        target_chat_id = potential_id
        if len(parts) > 1:
            text_to_send = parts[1]
        else:
            bot.reply_to(message, "✏️ Укажите текст сообщения после ID чата.")
            return
    except ValueError:
        
        text_to_send = first_part
        target_chat_id = message.chat.id

    if not text_to_send:
        bot.reply_to(message, "✏️ Укажите текст сообщения.")
        return

    if target_chat_id is None:
        target_chat_id = message.chat.id

    
    try:
        if reply_to_msg and target_chat_id == message.chat.id:
            bot.send_message(target_chat_id, text_to_send, reply_to_message_id=reply_to_msg.message_id)
        else:
            bot.send_message(target_chat_id, text_to_send)
        log_action("📤 Отправка от лица бота", admin_id=user_id, details=f"chat_id={target_chat_id}, текст: {text_to_send[:50]}...")
        bot.reply_to(message, f"✅ Сообщение отправлено в чат `{target_chat_id}`.", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при отправке: {e}")
        log_action("❌ Ошибка отправки от лица бота", admin_id=user_id, details=str(e))


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type
    text = message.text.strip()

    remove_kb = chat_type != 'private'

    if text.startswith('/'):
        return


    if text.lower() in ["ид", "айди"]:
        if message.reply_to_message:
            target_user = message.reply_to_message.from_user
            target_id = target_user.id
            username = target_user.username or "без username"
            name = target_user.first_name or ""
            bot.reply_to(message, f"🆔 ID пользователя @{username} ({name}): `{target_id}`", parse_mode='Markdown',
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            log_action("🆔 Запрос ID", user_id=user_id, details=f"показал ID пользователя {target_id}")
        else:
            username = message.from_user.username or "без username"
            name = message.from_user.first_name or ""
            bot.reply_to(message, f"🆔 Твой ID: `{user_id}`\nUsername: @{username}\nИмя: {name}", parse_mode='Markdown',
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            log_action("🆔 Запрос ID", user_id=user_id, details=f"показал свой ID")
        return

   
    if text.lower().startswith("п ") and message.reply_to_message:
        parts = text.split()
        if len(parts) != 2:
            bot.reply_to(message, "❌ Формат: `п [сумма]` в ответ на сообщение получателя.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        try:
            amount = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Сумма должна быть числом.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        if amount <= 0:
            bot.reply_to(message, "❌ Сумма должна быть положительной.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        recipient_id = message.reply_to_message.from_user.id
        if recipient_id == user_id:
            bot.reply_to(message, "❌ Нельзя перевести самому себе.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        sender_balance = get_user_balance(user_id)
        if sender_balance < amount:
            bot.reply_to(message, f"❌ Недостаточно средств. Ваш баланс: {sender_balance} чапиксов.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        get_user(recipient_id)
        update_balance(user_id, -amount)
        update_balance(recipient_id, amount)
        log_action("💰 Перевод", user_id=user_id, details=f"перевел {amount} чапиксов пользователю {recipient_id}, новый баланс {get_user_balance(user_id)}")
        bot.reply_to(message, f"✅ Переведено {amount} чапиксов пользователю @{message.reply_to_message.from_user.username or recipient_id}.\nНовый баланс: {get_user_balance(user_id)} чапиксов",
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        try:
            bot.send_message(recipient_id, f"💰 Вы получили {amount} чапиксов от {message.from_user.first_name} (@{message.from_user.username or user_id}).\nНовый баланс: {get_user_balance(recipient_id)} чапиксов")
        except:
            pass
        return

    
    if text.startswith("#"):
        code = text[1:].strip()
        if code:
            success, msg, reward = use_promocode(user_id, code)
            if success:
                log_action("🎫 Промокод активирован", user_id=user_id, details=f"code={code}, reward={reward}, новый баланс {get_user_balance(user_id)}")
                bot.reply_to(message, f"✅ {msg} Вы получили {reward} чапиксов! Новый баланс: {get_user_balance(user_id)}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            else:
                log_action("❌ Промокод не активирован", user_id=user_id, details=f"code={code}, причина: {msg}")
                bot.reply_to(message, f"❌ {msg}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return

    if text.lower().startswith("промо "):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            code = parts[1].strip()
            success, msg, reward = use_promocode(user_id, code)
            if success:
                log_action("🎫 Промокод активирован", user_id=user_id, details=f"code={code}, reward={reward}, новый баланс {get_user_balance(user_id)}")
                bot.reply_to(message, f"✅ {msg} Вы получили {reward} чапиксов! Новый баланс: {get_user_balance(user_id)}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            else:
                log_action("❌ Промокод не активирован", user_id=user_id, details=f"code={code}, причина: {msg}")
                bot.reply_to(message, f"❌ {msg}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return

    
    if user_id in user_states:
        state = user_states[user_id]
        if state == 'awaiting_referrer_id':
            try:
                referrer_id = int(text)
            except ValueError:
                bot.reply_to(message, "❌ Введите корректный числовой ID.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                return
            if not user_exists(referrer_id):
                bot.reply_to(message, "❌ Пользователь с таким ID не найден.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                return
            if referrer_id == user_id:
                bot.reply_to(message, "❌ Вы не можете пригласить самого себя.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                return
            if get_referred_by(user_id):
                bot.reply_to(message, "❌ Вы уже привязаны к рефералу.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                return
            set_referral(user_id, referrer_id)
            add_referral_record(referrer_id, user_id, REFERRAL_BONUS_REFERRER, REFERRAL_BONUS_REFERRED)
            update_balance(user_id, REFERRAL_BONUS_REFERRED)
            update_balance(referrer_id, REFERRAL_BONUS_REFERRER)
            log_action("👥 Реферал", user_id=referrer_id, details=f"пригласил user={user_id}, +{REFERRAL_BONUS_REFERRER} (реферер) и +{REFERRAL_BONUS_REFERRED} (реферал)")
            bot.reply_to(message, f"🎉 Вы получили {REFERRAL_BONUS_REFERRED} чапиксов за привязку к рефералу!",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            try:
                bot.send_message(referrer_id, f"🎉 Пользователь {user_id} ввёл ваш ID как реферала! Вы получили {REFERRAL_BONUS_REFERRER} чапиксов.")
            except:
                pass
            del user_states[user_id]
            bot.send_message(message.chat.id, "Главное меню:", reply_markup=get_main_keyboard(user_id, chat_type))
            return

        elif state == 'awaiting_promo_code':
            success, msg, reward = use_promocode(user_id, text)
            if success:
                log_action("🎫 Промокод активирован", user_id=user_id, details=f"code={text}, reward={reward}, новый баланс {get_user_balance(user_id)}")
                bot.reply_to(message, f"✅ {msg} Вы получили {reward} чапиксов! Новый баланс: {get_user_balance(user_id)}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            else:
                log_action("❌ Промокод не активирован", user_id=user_id, details=f"code={text}, причина: {msg}")
                bot.reply_to(message, f"❌ {msg}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            del user_states[user_id]
            return

        elif state == 'admin_awaiting_give':
            if not is_admin(user_id):
                bot.reply_to(message, "⛔ Нет прав.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                del user_states[user_id]
                return
            try:
                parts = text.split()
                if len(parts) != 2:
                    bot.reply_to(message, "❌ Введите ID и сумму через пробел.",
                                 reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                    return
                target_id = int(parts[0])
                amount = int(parts[1])
                if not user_exists(target_id):
                    bot.reply_to(message, "❌ Пользователь с таким ID не найден.",
                                 reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                    return
                user = get_user(target_id)
                set_balance(target_id, user['balance'] + amount)
                log_action("💰 Админ выдал чапиксы", user_id=target_id, admin_id=user_id, details=f"amount={amount}, новый баланс {user['balance'] + amount}")
                bot.reply_to(message, f"✅ Пользователю {target_id} выдано {amount} чапиксов. Новый баланс: {user['balance'] + amount}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                try:
                    bot.send_message(target_id, f"💰 Администратор выдал вам {amount} чапиксов. Ваш баланс: {user['balance'] + amount}")
                except:
                    pass
                del user_states[user_id]
                bot.send_message(message.chat.id, "Админ-панель:", reply_markup=admin_keyboard() if chat_type == 'private' else ReplyKeyboardRemove())
            except ValueError:
                bot.reply_to(message, "❌ ID и сумма должны быть числами.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            except Exception as e:
                bot.reply_to(message, f"❌ Ошибка: {e}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return

        elif state == 'admin_awaiting_set_balance':
            if not is_admin(user_id):
                bot.reply_to(message, "⛔ Нет прав.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                del user_states[user_id]
                return
            try:
                parts = text.split()
                if len(parts) != 2:
                    bot.reply_to(message, "❌ Введите ID и новую сумму через пробел.",
                                 reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                    return
                target_id = int(parts[0])
                new_balance = int(parts[1])
                if new_balance < 0:
                    bot.reply_to(message, "❌ Баланс не может быть отрицательным.",
                                 reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                    return
                if not user_exists(target_id):
                    bot.reply_to(message, "❌ Пользователь с таким ID не найден.",
                                 reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                    return
                set_balance(target_id, new_balance)
                log_action("⚙️ Установлен баланс", user_id=target_id, admin_id=user_id, details=f"новый баланс = {new_balance}")
                bot.reply_to(message, f"✅ Баланс пользователя {target_id} установлен на {new_balance} чапиксов.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                try:
                    bot.send_message(target_id, f"⚙️ Администратор установил ваш баланс на {new_balance} чапиксов.")
                except:
                    pass
                del user_states[user_id]
                bot.send_message(message.chat.id, "Админ-панель:", reply_markup=admin_keyboard() if chat_type == 'private' else ReplyKeyboardRemove())
            except ValueError:
                bot.reply_to(message, "❌ ID и сумма должны быть числами.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            except Exception as e:
                bot.reply_to(message, f"❌ Ошибка: {e}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return

        elif state == 'admin_awaiting_reset_balance':
            if not is_admin(user_id):
                bot.reply_to(message, "⛔ Нет прав.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                del user_states[user_id]
                return
            try:
                target_id = int(text.strip())
                if not user_exists(target_id):
                    bot.reply_to(message, "❌ Пользователь с таким ID не найден.",
                                 reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                    return
                set_balance(target_id, 0)
                log_action("🔄 Обнулён баланс", user_id=target_id, admin_id=user_id)
                bot.reply_to(message, f"✅ Баланс пользователя {target_id} обнулён.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                try:
                    bot.send_message(target_id, f"🔄 Администратор обнулил ваш баланс. Теперь он равен 0.")
                except:
                    pass
                del user_states[user_id]
                bot.send_message(message.chat.id, "Админ-панель:", reply_markup=admin_keyboard() if chat_type == 'private' else ReplyKeyboardRemove())
            except ValueError:
                bot.reply_to(message, "❌ Введите корректный числовой ID.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            except Exception as e:
                bot.reply_to(message, f"❌ Ошибка: {e}",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return

        elif state == 'admin_promo_code':
            if not is_admin(user_id):
                bot.reply_to(message, "⛔ Нет прав.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                del user_states[user_id]
                return
            code = text.strip().upper()
            if not code:
                bot.reply_to(message, "❌ Код не может быть пустым.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                return
            if get_promocode(code):
                bot.reply_to(message, "❌ Промокод с таким названием уже существует. Введите другой код.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                return
            promo_data[user_id] = {'code': code}
            user_states[user_id] = 'admin_promo_reward'
            bot.reply_to(message, "Введите награду (количество чапиксов):",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return

        elif state == 'admin_promo_reward':
            if not is_admin(user_id):
                bot.reply_to(message, "⛔ Нет прав.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                del user_states[user_id]
                return
            try:
                reward = int(text)
                if reward <= 0:
                    bot.reply_to(message, "❌ Награда должна быть положительным числом.",
                                 reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                    return
                promo_data[user_id]['reward'] = reward
                keyboard = InlineKeyboardMarkup(row_width=3)
                buttons = [
                    InlineKeyboardButton("1", callback_data="promo_uses_1"),
                    InlineKeyboardButton("5", callback_data="promo_uses_5"),
                    InlineKeyboardButton("10", callback_data="promo_uses_10"),
                    InlineKeyboardButton("50", callback_data="promo_uses_50"),
                    InlineKeyboardButton("100", callback_data="promo_uses_100"),
                    InlineKeyboardButton("♾ Безлимит", callback_data="promo_uses_-1")
                ]
                keyboard.add(*buttons)
                bot.send_message(message.chat.id, "Выберите количество активаций:", reply_markup=keyboard)
                user_states[user_id] = 'admin_promo_uses'
            except ValueError:
                bot.reply_to(message, "❌ Введите число.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return

        elif state == 'admin_give_promo_user':
            if not is_admin(user_id):
                bot.reply_to(message, "⛔ Нет прав.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                del user_states[user_id]
                return
            if message.reply_to_message:
                target_id = message.reply_to_message.from_user.id
            else:
                try:
                    target_id = int(text)
                except ValueError:
                    bot.reply_to(message, "❌ Введите корректный ID пользователя или ответьте на его сообщение.",
                                 reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                    return
            if not user_exists(target_id):
                bot.reply_to(message, "❌ Пользователь с таким ID не найден.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                return
            promo_id = promo_data[user_id].get('give_promo_id')
            if not promo_id:
                bot.reply_to(message, "❌ Ошибка: промокод не выбран.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                del user_states[user_id]
                return
            promo = get_promocode_by_id(promo_id)
            if not promo:
                bot.reply_to(message, "❌ Промокод не найден.",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                del user_states[user_id]
                return
            bot.send_message(target_id, f"🎁 Вам выдан промокод: `{promo['code']}`\n"
                                        f"Награда: {promo['reward']} чапиксов\n"
                                        f"Активируйте его командой: `промокод {promo['code']}` или просто напишите `#{promo['code']}`", parse_mode='Markdown')
            log_action("📤 Выдача промокода", user_id=target_id, admin_id=user_id, details=f"code={promo['code']}, reward={promo['reward']}")
            bot.reply_to(message, f"✅ Промокод `{promo['code']}` отправлен пользователю {target_id}.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            del user_states[user_id]
            del promo_data[user_id]
            return


    if text == "🎁 Бонус":
        if can_claim_daily(user_id):
            update_balance(user_id, DAILY_BONUS)
            set_daily_claimed(user_id)
            log_action("🎁 Бонус", user_id=user_id, details=f"+{DAILY_BONUS}, новый баланс {get_user_balance(user_id)}")
            bot.reply_to(message, f"🎁 Ты получил {DAILY_BONUS} чапиксов!\nНовый баланс: {get_user_balance(user_id)} чапиксов",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        else:
            bot.reply_to(message, "❌ Ты уже получал бонус сегодня. Возвращайся завтра!",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    if text == "👥 Реферал":
        code = get_referral_code(user_id)
        ref_link = f"https://t.me/{bot.get_me().username}?start=ref_{code}"
        count = count_referrals(user_id)
        referred_by = get_referred_by(user_id)
        msg = f"👥 **Реферальная система**\n\n"
        msg += f"Твоя реферальная ссылка:\n`{ref_link}`\n\n"
        msg += f"Количество приглашённых: {count}\n"
        if referred_by:
            msg += f"Ты был приглашён пользователем ID: `{referred_by}`"
        else:
            msg += "Ты ещё не привязан к рефералу. Введи ID пригласившего, чтобы получить бонус!"
        bot.reply_to(message, msg, parse_mode='Markdown',
                     reply_markup=referral_inline(user_id) if chat_type == 'private' else ReplyKeyboardRemove())
        return

    if text == "🧪 Химворс":
        bot.reply_to(message, "🧪 Химворс – игра, которая будет добавлена позже.\nСледи за обновлениями!",
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    if text == "💎 Донат":
        donate_text = (
            "❗ Прайс ❗\n\n"
            "- Прайс чапиксы принимаем звезды / NFT / USDT\n\n"
            "5.000.000 ⭐ - 15 ⭐\n"
            "100.000.000 ⭐ - 300 ⭐\n"
            "500.000.000 ⭐ - 1500 ⭐\n\n"
            "❗ Ниже мега акция ❗\n"
            "1.000.000.000 ⭐ - 2799 зв⭐\n"
            "Для покупки напишите администратору: @nedodelov, @lyfehater"
        )
        bot.reply_to(message, donate_text,
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    if text == "🏆 Богач":
        top = get_top_players(10)
        if not top:
            bot.reply_to(message, "Пока нет игроков.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        reply = "🏆 ТОП-10 БОГАЧЕЙ:\n\n"
        for i, (uid, balance) in enumerate(top, 1):
            try:
                user = bot.get_chat(uid)
                name = user.first_name or f"User{uid}"
                username = user.username
                if username:
                    link = f"@{username}"
                else:
                    link = f"[{name}](tg://user?id={uid})"
                reply += f"{i}. {link} — {balance} чапиксов\n"
            except Exception:
                reply += f"{i}. User{uid} — {balance} чапиксов\n"
        bot.reply_to(message, reply, parse_mode='Markdown',
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    if text == "💬 Чаты":
        bot.reply_to(message, "💬 Наши чаты:\n• Основной чат: @chat1\n• Новости: @chat2",
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    if text == "❓ Помощь":
        help_text = (
            "🎰 Доступные команды:\n\n"
            f"• {CMD_BALANCE} / {CMD_BALANCE_ALT} – показать баланс\n"
            "• мины [сумма] – игра «Мины»\n"
            "• мины вб – игра на весь баланс\n"
            "• кости [сумма] [число 1-6] – игра «Кости»\n"
            "• рулетка [сумма] [red/black/число] – рулетка\n"
            "• баскет [сумма] – ставка на попадание (шанс 20%, ×2)\n"
            "• баскет мимо [сумма] – ставка на промах (шанс 80%, ×1.5)\n"
            "• баскет вб – ставка на попадание на весь баланс\n"
            "• баскет вб мимо (или баскет мимо вб) – ставка на промах на весь баланс\n"
            f"• {CMD_TOP} – топ-10 игроков\n"
            f"• {CMD_DAILY} – ежедневный бонус\n"
            "• промокод [код] – активировать промокод\n"
            "• промо [код] – активировать промокод (короткая версия)\n"
            "• #[код] – активировать промокод через хештег\n"
            "• п [сумма] – перевести чапиксы (ответьте на сообщение)\n"
            "• ид / айди – показать ID (свой или того, на чьё сообщение ответили)\n"
            "• помощь – это сообщение\n\n"
            "Если вы администратор, используйте кнопку «Админ панель»."
        )
        bot.reply_to(message, help_text,
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    if text == "💰 Баланс":
        bot.reply_to(message, get_balance_text(user_id),
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    if text == "⚙️ Админ панель" and is_admin(user_id):
        if chat_type == 'private':
            bot.send_message(message.chat.id, "⚙️ Админ-панель:", reply_markup=admin_keyboard())
        else:
            bot.reply_to(message, "Админ-панель доступна только в личных сообщениях.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    
    if is_admin(user_id) and chat_type == 'private':
        if text == "💰 Выдать чапиксы":
            bot.send_message(message.chat.id, "Введите ID пользователя и сумму через пробел, например:\n`1607756200 5000`", parse_mode='Markdown')
            user_states[user_id] = 'admin_awaiting_give'
            return

        if text == "⚙️ Установить баланс":
            bot.send_message(message.chat.id, "Введите ID пользователя и новую сумму через пробел, например:\n`1607756200 10000`", parse_mode='Markdown')
            user_states[user_id] = 'admin_awaiting_set_balance'
            return

        if text == "🔄 Обнулить баланс":
            bot.send_message(message.chat.id, "Введите ID пользователя, баланс которого нужно обнулить:")
            user_states[user_id] = 'admin_awaiting_reset_balance'
            return

        if text == "🔄 Обнулить ВСЕМ":
           
            bot.send_message(message.chat.id, "⚠️ ВНИМАНИЕ! Вы собираетесь обнулить баланс ВСЕМ пользователям.\n"
                                             "Это действие необратимо.\n"
                                             "Для подтверждения введите команду: `обнулить_всех_ДА`")
            user_states[user_id] = 'admin_awaiting_reset_all_confirm'
            return

        if text == "📊 Статистика":
            stats = get_total_stats()
            promos = list_promocodes()
            promo_count = len(promos)
            total_referrals = 0
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM referrals")
            total_referrals = cursor.fetchone()['total']
            conn.close()
            reply = (
                "📊 **ОБЩАЯ СТАТИСТИКА**\n\n"
                f"👤 Всего пользователей: {stats['total_users']}\n"
                f"💰 Общий баланс: {stats['total_balance']} чапиксов\n"
                f"🏆 Всего выиграно: {stats['total_won']} чапиксов\n"
                f"💸 Всего проиграно: {stats['total_lost']} чапиксов\n"
                f"🎮 Всего сыграно игр: {stats['total_games']}\n"
                f"👥 Всего рефералов: {total_referrals}\n"
                f"🎫 Создано промокодов: {promo_count}"
            )
            bot.send_message(message.chat.id, reply, parse_mode='Markdown')
            return

        if text == "🎫 Создать промокод":
            promo_data[user_id] = {}
            user_states[user_id] = 'admin_promo_code'
            bot.send_message(message.chat.id, "Введите код промокода (буквы и цифры, например: PROMO2025):")
            return

        if text == "📋 Список промокодов":
            promos = list_promocodes()
            if not promos:
                bot.send_message(message.chat.id, "📋 Промокодов пока нет.")
                return
            msg = "📋 СПИСОК ПРОМОКОДОВ:\n\n"
            for p in promos:
                expires = p['expires_at'] if p['expires_at'] else "бессрочно"
                uses = f"{p['used_count']}/{p['max_uses'] if p['max_uses'] != -1 else '∞'}"
                msg += f"• `{p['code']}` – {p['reward']} чап., активаций: {uses}, срок: {expires}\n"
            bot.send_message(message.chat.id, msg, parse_mode='Markdown')
            return

        if text == "🗑 Удалить промокод":
            promos = list_promocodes()
            if not promos:
                bot.send_message(message.chat.id, "Нет промокодов для удаления.")
                return
            keyboard = InlineKeyboardMarkup()
            for p in promos:
                keyboard.add(InlineKeyboardButton(f"❌ {p['code']}", callback_data=f"delpromo_{p['id']}"))
            keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_back_to_menu"))
            bot.send_message(message.chat.id, "Выберите промокод для удаления:", reply_markup=keyboard)
            return

        if text == "📤 Выдать промокод":
            promos = list_promocodes()
            if not promos:
                bot.send_message(message.chat.id, "Нет созданных промокодов.")
                return
            keyboard = InlineKeyboardMarkup()
            for p in promos:
                keyboard.add(InlineKeyboardButton(f"📤 {p['code']} ({p['reward']} чап.)", callback_data=f"givepromo_{p['id']}"))
            keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_back_to_menu"))
            bot.send_message(message.chat.id, "Выберите промокод для выдачи:", reply_markup=keyboard)
            return

        if text == "🔙 Назад":
            bot.send_message(message.chat.id, "Главное меню:", reply_markup=get_main_keyboard(user_id, chat_type))
            return

    
    first_word = text.split()[0].lower() if text.split() else ''


    if first_word == 'баскет':
        parts = text.lower().split()
        miss = "мимо" in parts
        bet = None
        if "вб" in parts:
            bet = 'all'
        else:
            for part in parts:
                try:
                    bet = int(part)
                    break
                except ValueError:
                    continue
            if bet is None:
                bot.reply_to(message, "❌ Введи ставку: баскет [сумма] или баскет вб (или баскет мимо ...)",
                             reply_markup=ReplyKeyboardRemove() if remove_kb else None)
                return
        log_action("🎮 Баскет начат", user_id=user_id, details=f"miss={miss}, bet={'все' if bet == 'all' else bet}")
        play_basketball_dice(message, user_id, chat_id, bet, miss, remove_kb)
        return

    
    if first_word == 'промокод':
        parts = text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Введите код промокода: промокод КОД",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        code = parts[1]
        success, msg, reward = use_promocode(user_id, code)
        if success:
            log_action("🎫 Промокод активирован", user_id=user_id, details=f"code={code}, reward={reward}, новый баланс {get_user_balance(user_id)}")
            bot.reply_to(message, f"✅ {msg} Вы получили {reward} чапиксов! Новый баланс: {get_user_balance(user_id)}",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        else:
            log_action("❌ Промокод не активирован", user_id=user_id, details=f"code={code}, причина: {msg}")
            bot.reply_to(message, f"❌ {msg}",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    
    known_commands = ['мины', 'кости', 'рулетка', CMD_BALANCE, CMD_BALANCE_ALT,
                      CMD_TOP, CMD_DAILY, CMD_HELP]
    if first_word not in known_commands:
        return

    result = parse_bet_from_text(text)
    if result is None:
        return
    cmd, data, err = result
    if err:
        bot.reply_to(message, err,
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    if cmd == 'balance':
        bot.reply_to(message, get_balance_text(user_id),
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return
    if cmd == 'top':
        top = get_top_players(10)
        if not top:
            bot.reply_to(message, "Пока нет игроков.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        reply = "🏆 ТОП-10 БОГАЧЕЙ:\n\n"
        for i, (uid, balance) in enumerate(top, 1):
            try:
                user = bot.get_chat(uid)
                name = user.first_name or f"User{uid}"
                username = user.username
                if username:
                    link = f"@{username}"
                else:
                    link = f"[{name}](tg://user?id={uid})"
                reply += f"{i}. {link} — {balance} чапиксов\n"
            except:
                reply += f"{i}. User{uid} — {balance} чапиксов\n"
        bot.reply_to(message, reply, parse_mode='Markdown',
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return
    if cmd == 'daily':
        if can_claim_daily(user_id):
            update_balance(user_id, DAILY_BONUS)
            set_daily_claimed(user_id)
            log_action("🎁 Бонус", user_id=user_id, details=f"+{DAILY_BONUS}, новый баланс {get_user_balance(user_id)}")
            bot.reply_to(message, f"🎁 Ты получил {DAILY_BONUS} чапиксов! Новый баланс: {get_user_balance(user_id)} чапиксов",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        else:
            bot.reply_to(message, "❌ Ты уже получал бонус сегодня. Возвращайся завтра!",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return
    if cmd == 'help':
        help_text = (
            "🎰 Доступные команды:\n\n"
            f"• {CMD_BALANCE} / {CMD_BALANCE_ALT} – показать баланс\n"
            "• мины [сумма] – игра «Мины»\n"
            "• мины вб – игра на весь баланс\n"
            "• кости [сумма] [число 1-6] – игра «Кости»\n"
            "• рулетка [сумма] [red/black/число] – рулетка\n"
            "• баскет [сумма] – ставка на попадание (шанс 20%, ×2)\n"
            "• баскет мимо [сумма] – ставка на промах (шанс 80%, ×1.5)\n"
            "• баскет вб – ставка на попадание на весь баланс\n"
            "• баскет вб мимо (или баскет мимо вб) – ставка на промах на весь баланс\n"
            f"• {CMD_TOP} – топ-10 игроков\n"
            f"• {CMD_DAILY} – ежедневный бонус\n"
            "• промокод [код] – активировать промокод\n"
            "• промо [код] – активировать промокод (короткая версия)\n"
            "• #[код] – активировать промокод через хештег\n"
            "• п [сумма] – перевести чапиксы (ответьте на сообщение)\n"
            "• ид / айди – показать ID (свой или того, на чьё сообщение ответили)\n"
            "• помощь – это сообщение\n\n"
            "Если вы администратор, используйте кнопку «Админ панель»."
        )
        bot.reply_to(message, help_text,
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    
    if cmd == 'mines':
        bet = data
        if bet == 'all':
            bet = get_user_balance(user_id)
        if bet < MIN_BET or bet > MAX_BET:
            bot.reply_to(message, f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET} чапиксов.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        if bet > get_user_balance(user_id):
            bot.reply_to(message, f"❌ Недостаточно средств. Баланс: {get_user_balance(user_id)} чапиксов",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        
        seed = generate_seed()
        hash_val = hash_seed(seed)
        game_hash_id = save_game_hash(user_id, 'mines', seed, hash_val)
        log_action("🔐 Хэш для игры (мины)", user_id=user_id, details=f"seed={seed}, hash={hash_val}")
        
        grid, mines = generate_mines_field(MINES_FIELD_SIZE, MINES_COUNT)
        active_games[user_id] = {
            'type': 'mines',
            'grid': grid,
            'mines': mines,
            'bet': bet,
            'clicked': 0,
            'message_id': None,
            'chat_id': chat_id,
            'game_hash_id': game_hash_id,
            'seed': seed,
            'hash': hash_val
        }
        log_action("🎮 Мины начаты", user_id=user_id, details=f"bet={bet}")
        keyboard = InlineKeyboardMarkup(row_width=5)
        for r in range(MINES_FIELD_SIZE):
            row_buttons = []
            for c in range(MINES_FIELD_SIZE):
                row_buttons.append(
                    InlineKeyboardButton("⬜", callback_data=f"mines_{r}_{c}")
                )
            keyboard.row(*row_buttons)
        keyboard.row(
            InlineKeyboardButton("💰 Забрать", callback_data="mines_cashout")
        )
        field_text = (f"💣 Игра «Мины»\n"
                      f"Ставка: {bet} чапиксов\n"
                      f"Мин: {MINES_COUNT}\n"
                      f"Открывай клетки. Найдёшь мину – проиграешь.")
        sent_msg = bot.reply_to(message, field_text, reply_markup=keyboard)
        active_games[user_id]['message_id'] = sent_msg.message_id
        return

    if cmd == 'dice':
        bet, guess = data
        if bet == 'all':
            bet = get_user_balance(user_id)
        if bet < MIN_BET or bet > MAX_BET:
            bot.reply_to(message, f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET} чапиксов.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        if bet > get_user_balance(user_id):
            bot.reply_to(message, f"❌ Недостаточно средств. Баланс: {get_user_balance(user_id)} чапиксов",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        
        seed = generate_seed()
        hash_val = hash_seed(seed)
        game_hash_id = save_game_hash(user_id, 'dice', seed, hash_val)
        log_action("🔐 Хэш для игры (кости)", user_id=user_id, details=f"seed={seed}, hash={hash_val}")
        
        result = roll_dice()
        win = 0
        if result == guess:
            win = bet * 5
            update_balance(user_id, win)
            add_game_stat(user_id, 'dice', bet, win)
            log_action("✅ Выигрыш в кости", user_id=user_id, details=f"guess={guess}, result={result}, win={win}, новый баланс {get_user_balance(user_id)}")
            result_text = f"🎲 Выпало: {result}\n✅ Ты угадал! Выигрыш: {win} чапиксов\n💰 Новый баланс: {get_user_balance(user_id)} чапиксов"
        else:
            update_balance(user_id, -bet)
            add_game_stat(user_id, 'dice', bet, 0)
            log_action("❌ Проигрыш в кости", user_id=user_id, details=f"guess={guess}, result={result}, lost={bet}, новый баланс {get_user_balance(user_id)}")
            result_text = f"🎲 Выпало: {result}\n❌ Ты не угадал. Потеряно: {bet} чапиксов\n💰 Новый баланс: {get_user_balance(user_id)} чапиксов"
        
        update_game_result(game_hash_id, str(result))
        bot.reply_to(
            message,
            result_text,
            reply_markup=ReplyKeyboardRemove() if remove_kb else None
        )
        return

    if cmd == 'roulette':
        bet, choice = data
        if bet == 'all':
            bet = get_user_balance(user_id)
        if bet < MIN_BET or bet > MAX_BET:
            bot.reply_to(message, f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET} чапиксов.",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        if bet > get_user_balance(user_id):
            bot.reply_to(message, f"❌ Недостаточно средств. Баланс: {get_user_balance(user_id)} чапиксов",
                         reply_markup=ReplyKeyboardRemove() if remove_kb else None)
            return
        
        seed = generate_seed()
        hash_val = hash_seed(seed)
        game_hash_id = save_game_hash(user_id, 'roulette', seed, hash_val)
        log_action("🔐 Хэш для игры (рулетка)", user_id=user_id, details=f"seed={seed}, hash={hash_val}")
        
        number, color = roulette_spin()
        win = 0
        if choice in ['red', 'black']:
            if choice == color:
                win = bet * 2
        else:
            if int(choice) == number:
                win = bet * 36
        if win > 0:
            update_balance(user_id, win)
            add_game_stat(user_id, 'roulette', bet, win)
            log_action("✅ Выигрыш в рулетке", user_id=user_id, details=f"choice={choice}, number={number}, color={color}, win={win}, новый баланс {get_user_balance(user_id)}")
            result_text = f"🎰 Выпало: {number} ({color})\n✅ Ты выиграл! +{win} чапиксов\n💰 Новый баланс: {get_user_balance(user_id)} чапиксов"
        else:
            update_balance(user_id, -bet)
            add_game_stat(user_id, 'roulette', bet, 0)
            log_action("❌ Проигрыш в рулетке", user_id=user_id, details=f"choice={choice}, number={number}, color={color}, lost={bet}, новый баланс {get_user_balance(user_id)}")
            result_text = f"🎰 Выпало: {number} ({color})\n❌ Ты проиграл. -{bet} чапиксов\n💰 Новый баланс: {get_user_balance(user_id)} чапиксов"
        
        update_game_result(game_hash_id, f"{number},{color}")
        bot.reply_to(
            message,
            result_text,
            reply_markup=ReplyKeyboardRemove() if remove_kb else None
        )
        return

    return


def play_basketball_dice(message, user_id, chat_id, bet, miss=False, remove_kb=False):
    if bet == 'all':
        bet = get_user_balance(user_id)
    if bet < MIN_BET or bet > MAX_BET:
        bot.reply_to(message, f"❌ Ставка должна быть от {MIN_BET} до {MAX_BET} чапиксов.",
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return
    if bet > get_user_balance(user_id):
        bot.reply_to(message, f"❌ Недостаточно средств. Баланс: {get_user_balance(user_id)} чапиксов",
                     reply_markup=ReplyKeyboardRemove() if remove_kb else None)
        return

    seed = generate_seed()
    hash_val = hash_seed(seed)
    game_hash_id = save_game_hash(user_id, 'basketball', seed, hash_val)
    log_action("🔐 Хэш для игры (баскет)", user_id=user_id, details=f"seed={seed}, hash={hash_val}")
    
    sent_msg = bot.send_dice(chat_id, emoji="🏀")
    dice_value = sent_msg.dice.value
    update_balance(user_id, -bet)
    hit = (dice_value == 5)

    if miss:
        if not hit:
            win = int(bet * BASKET_MISS_MULTIPLIER)
            update_balance(user_id, win)
            add_game_stat(user_id, 'basketball_miss', bet, win)
            log_action("✅ Выигрыш в баскете (промах)", user_id=user_id, details=f"miss=True, dice={dice_value}, win={win}, новый баланс {get_user_balance(user_id)}")
            result_text = f"❌ Промах! ✅ (выигрышная ставка)\nТы выиграл {win} чапиксов!\n💰 Новый баланс: {get_user_balance(user_id)} чапиксов"
        else:
            add_game_stat(user_id, 'basketball_miss', bet, 0)
            log_action("❌ Проигрыш в баскете (промах)", user_id=user_id, details=f"miss=True, dice={dice_value}, lost={bet}, новый баланс {get_user_balance(user_id)}")
            result_text = f"✅ Попадание! ❌ (ты проиграл)\nПотеряно: {bet} чапиксов\n💰 Новый баланс: {get_user_balance(user_id)} чапиксов"
    else:
        if hit:
            win = int(bet * BASKET_MULTIPLIER)
            update_balance(user_id, win)
            add_game_stat(user_id, 'basketball', bet, win)
            log_action("✅ Выигрыш в баскете (попадание)", user_id=user_id, details=f"miss=False, dice={dice_value}, win={win}, новый баланс {get_user_balance(user_id)}")
            result_text = f"✅ Попадание! ✅\nТы выиграл {win} чапиксов!\n💰 Новый баланс: {get_user_balance(user_id)} чапиксов"
        else:
            add_game_stat(user_id, 'basketball', bet, 0)
            log_action("❌ Проигрыш в баскете (попадание)", user_id=user_id, details=f"miss=False, dice={dice_value}, lost={bet}, новый баланс {get_user_balance(user_id)}")
            result_text = f"❌ Промах! ❌\nПотеряно: {bet} чапиксов\n💰 Новый баланс: {get_user_balance(user_id)} чапиксов"
    
    update_game_result(game_hash_id, str(dice_value))
    bot.send_message(
        chat_id,
        result_text,
        reply_markup=ReplyKeyboardRemove() if remove_kb else None
    )


@bot.message_handler(func=lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == 'admin_awaiting_reset_all_confirm')
def handle_reset_all_confirm(message):
    user_id = message.from_user.id
    text = message.text.strip()
    if text == "обнулить_всех_ДА":
        reset_all_balances()
        log_action("🔄 Обнулён баланс ВСЕХ пользователей", admin_id=user_id)
        bot.reply_to(message, "✅ Баланс всех пользователей обнулён.")
        
        if user_id in user_states:
            del user_states[user_id]
        
        bot.send_message(message.chat.id, "Админ-панель:", reply_markup=admin_keyboard())
    else:
        bot.reply_to(message, "❌ Команда не распознана. Обнуление отменено.")
        if user_id in user_states:
            del user_states[user_id]
        bot.send_message(message.chat.id, "Админ-панель:", reply_markup=admin_keyboard())


def get_promocode_by_id(promo_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promocodes WHERE id = ?", (promo_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data
    chat_type = call.message.chat.type
    remove_kb = chat_type != 'private'
    print(f"🔔 Callback: {data} от {user_id}")

    if data == "ref_enter_id":
        if get_referred_by(user_id):
            bot.answer_callback_query(call.id, "Вы уже привязаны к рефералу.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Введите числовой ID пользователя, который вас пригласил:")
        user_states[user_id] = 'awaiting_referrer_id'
        return


    if data.startswith("promo_uses_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Нет прав.", show_alert=True)
            return
        max_uses = int(data.split("_")[2])
        code = promo_data[user_id]['code']
        reward = promo_data[user_id]['reward']
        create_promocode(code, reward, max_uses, None, user_id)
        log_action("📦 Создан промокод", admin_id=user_id, details=f"code={code}, reward={reward}, max_uses={max_uses}")
        bot.answer_callback_query(call.id, "✅ Промокод создан!")
        bot.edit_message_text(
            f"✅ Промокод `{code}` создан!\n"
            f"Награда: {reward} чапиксов\n"
            f"Активаций: {max_uses if max_uses != -1 else 'безлимит'}\n"
            f"Срок: бессрочно",
            call.message.chat.id,
            call.message.message_id
        )
        if user_id in promo_data:
            del promo_data[user_id]
        if user_id in user_states:
            del user_states[user_id]
        bot.send_message(call.message.chat.id, "Админ-панель:", reply_markup=admin_keyboard())
        return

   
    if data.startswith("givepromo_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Нет прав.", show_alert=True)
            return
        promo_id = int(data.split("_")[1])
        promo = get_promocode_by_id(promo_id)
        if not promo:
            bot.answer_callback_query(call.id, "❌ Промокод не найден.")
            return
        promo_data[user_id] = {'give_promo_id': promo_id}
        user_states[user_id] = 'admin_give_promo_user'
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"Введите ID пользователя (или ответьте на его сообщение), которому хотите выдать промокод `{promo['code']}`:")
        return

    
    if data.startswith("delpromo_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Нет прав.", show_alert=True)
            return
        promo_id = int(data.split("_")[1])
        promo = get_promocode_by_id(promo_id)
        delete_promocode(promo_id)
        log_action("🗑 Удалён промокод", admin_id=user_id, details=f"id={promo_id}, code={promo['code'] if promo else 'unknown'}")
        bot.answer_callback_query(call.id, "✅ Промокод удалён.")
        bot.edit_message_text("✅ Промокод удалён.", call.message.chat.id, call.message.message_id)
        return

    if data == "admin_back_to_menu":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=get_main_keyboard(user_id, chat_type))
        return

    if data.startswith("mines_"):
        handle_mines_callback(call)
        return

    bot.answer_callback_query(call.id, "Неизвестная команда.")


def handle_mines_callback(call):
    user_id = call.from_user.id
    data = call.data
    print(f"🔍 Обработка мин: {data} от {user_id}")

    if user_id not in active_games:
        bot.answer_callback_query(call.id, "❌ Игра не найдена. Начните заново.", show_alert=True)
        return

    game = active_games[user_id]
    if game['type'] != 'mines':
        bot.answer_callback_query(call.id, "❌ Неверный тип игры.", show_alert=True)
        return

    if data == "mines_cashout":
        if game['clicked'] == 0:
            bot.edit_message_text(
                f"💰 Ты забрал ставку обратно (0 клеток открыто).\n"
                f"💳 Баланс не изменился: {get_user_balance(user_id)} чапиксов",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )
            update_game_result(game['game_hash_id'], "cashout_0")
            del active_games[user_id]
            bot.answer_callback_query(call.id, "↩️ Ставка возвращена")
            return
        multiplier = calculate_mines_multiplier(
            game['clicked'],
            MINES_COUNT,
            MINES_FIELD_SIZE * MINES_FIELD_SIZE
        )
        win = int(game['bet'] * multiplier)
        update_balance(user_id, win)
        add_game_stat(user_id, 'mines', game['bet'], win)
        log_action("💰 Выигрыш в минах (забрал)", user_id=user_id, details=f"clicked={game['clicked']}, multiplier={multiplier}, win={win}, новый баланс {get_user_balance(user_id)}")
        bot.edit_message_text(
            f"💰 Ты забрал {win} чапиксов!\n"
            f"💳 Новый баланс: {get_user_balance(user_id)} чапиксов",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
        update_game_result(game['game_hash_id'], f"cashout_{game['clicked']}")
        del active_games[user_id]
        bot.answer_callback_query(call.id, f"💰 +{win} чапиксов!")
        return

    parts = data.split("_")
    if len(parts) != 3:
        bot.answer_callback_query(call.id, "❌ Неверный формат.")
        return

    row, col = int(parts[1]), int(parts[2])
    if game['grid'][row][col] == -1:
        bot.answer_callback_query(call.id, "⚠️ Клетка уже открыта.")
        return

    if game['grid'][row][col] == 1:
        del active_games[user_id]
        update_balance(user_id, -game['bet'])
        add_game_stat(user_id, 'mines', game['bet'], 0)
        log_action("❌ Проигрыш в минах", user_id=user_id, details=f"наступил на мину, потеряно {game['bet']}, новый баланс {get_user_balance(user_id)}")
        field_text = "💥 Ты наступил на мину!\n\n"
        for r in range(MINES_FIELD_SIZE):
            row_text = ""
            for c in range(MINES_FIELD_SIZE):
                if game['grid'][r][c] == 1:
                    row_text += "💣 "
                elif game['grid'][r][c] == -1:
                    row_text += "✅ "
                else:
                    row_text += "⬜ "
            field_text += row_text + "\n"
        field_text += f"\n💰 Потеряно: {game['bet']} чапиксов"
        field_text += f"\n💳 Новый баланс: {get_user_balance(user_id)} чапиксов"
        bot.edit_message_text(
            field_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
        update_game_result(game['game_hash_id'], "mine_hit")
        bot.answer_callback_query(call.id, "💥 Ты проиграл!")
        return
    else:
        game['grid'][row][col] = -1
        game['clicked'] += 1
        multiplier = calculate_mines_multiplier(
            game['clicked'],
            MINES_COUNT,
            MINES_FIELD_SIZE * MINES_FIELD_SIZE
        )
        print(f"🔢 Множитель: {multiplier} (clicked={game['clicked']}, mines={MINES_COUNT}, total={MINES_FIELD_SIZE*MINES_FIELD_SIZE})")
        current_win = int(game['bet'] * multiplier)
        keyboard = InlineKeyboardMarkup(row_width=5)
        for r in range(MINES_FIELD_SIZE):
            row_buttons = []
            for c in range(MINES_FIELD_SIZE):
                if game['grid'][r][c] == -1:
                    label = "✅"
                else:
                    label = "⬜"
                row_buttons.append(
                    InlineKeyboardButton(label, callback_data=f"mines_{r}_{c}")
                )
            keyboard.row(*row_buttons)
        keyboard.row(
            InlineKeyboardButton("💰 Забрать", callback_data="mines_cashout")
        )
        field_text = (f"💣 Игра «Мины»\n"
                      f"Ставка: {game['bet']} чапиксов\n"
                      f"Мин: {MINES_COUNT}\n"
                      f"Открыто: {game['clicked']}\n"
                      f"Текущий выигрыш: {current_win} чапиксов (x{multiplier})")
        bot.edit_message_text(
            field_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id, "✅ Безопасно!")
        return


def parse_bet_from_text(text):
    parts = text.strip().lower().split()
    if not parts:
        return None, None, "Пустое сообщение"
    cmd = parts[0]
    if cmd in [CMD_BALANCE, CMD_BALANCE_ALT]:
        return 'balance', None, None
    if cmd == CMD_TOP:
        return 'top', None, None
    if cmd == CMD_DAILY:
        return 'daily', None, None
    if cmd == CMD_HELP:
        return 'help', None, None
    if cmd == 'мины':
        if len(parts) == 1:
            return 'mines', None, "Введи ставку: мины [сумма] или мины вб"
        if parts[1] == 'вб':
            return 'mines', 'all', None
        try:
            bet = int(parts[1])
            return 'mines', bet, None
        except ValueError:
            return None, None, "Ставка должна быть числом"
    if cmd == 'кости':
        if len(parts) < 3:
            return None, None, "Формат: кости [ставка] [число 1-6]"
        if parts[1] == 'вб':
            bet = 'all'
        else:
            try:
                bet = int(parts[1])
            except ValueError:
                return None, None, "Ставка должна быть числом"
        try:
            guess = int(parts[2])
            if guess < 1 or guess > 6:
                return None, None, "Число должно быть от 1 до 6"
            return 'dice', (bet, guess), None
        except ValueError:
            return None, None, "Число должно быть целым"
    if cmd == 'рулетка':
        if len(parts) < 3:
            return None, None, "Формат: рулетка [ставка] [red/black/число 0-36]"
        if parts[1] == 'вб':
            bet = 'all'
        else:
            try:
                bet = int(parts[1])
            except ValueError:
                return None, None, "Ставка должна быть числом"
        choice = parts[2].lower()
        if choice not in ['red', 'black'] and not (choice.isdigit() and 0 <= int(choice) <= 36):
            return None, None, "Ставьте на red, black или число 0-36"
        return 'roulette', (bet, choice), None
    return None, None, f"Неизвестная команда. Напиши {CMD_HELP}"

if __name__ == "__main__":
    print("🎰 Бот 'Чапикс' запущен! Команды работают в группах без слеша.")
    bot.infinity_polling()
import sqlite3
import datetime
import random
import string
from config import START_BALANCE

DB_NAME = "casino_bot.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    table_exists = cursor.fetchone()
    
    if table_exists:
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        balance_type = None
        for col in columns:
            if col['name'] == 'balance':
                balance_type = col['type']
                break
        if balance_type and balance_type.upper() == 'INTEGER':
            cursor.execute('''
                CREATE TABLE users_new (
                    user_id INTEGER PRIMARY KEY,
                    balance TEXT DEFAULT '0',
                    total_won TEXT DEFAULT '0',
                    total_lost TEXT DEFAULT '0',
                    last_daily DATE,
                    referral_code TEXT,
                    referred_by INTEGER
                )
            ''')
            cursor.execute('''
                INSERT INTO users_new (user_id, balance, total_won, total_lost, last_daily, referral_code, referred_by)
                SELECT user_id, CAST(balance AS TEXT), CAST(total_won AS TEXT), CAST(total_lost AS TEXT), last_daily, referral_code, referred_by
                FROM users
            ''')
            cursor.execute("DROP TABLE users")
            cursor.execute("ALTER TABLE users_new RENAME TO users")
            conn.commit()
    else:
        cursor.execute('''
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                balance TEXT DEFAULT '0',
                total_won TEXT DEFAULT '0',
                total_lost TEXT DEFAULT '0',
                last_daily DATE,
                referral_code TEXT,
                referred_by INTEGER
            )
        ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            bonus_referrer INTEGER,
            bonus_referred INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            reward INTEGER,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            expires_at DATE,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            promo_id INTEGER,
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, promo_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_type TEXT,
            bet INTEGER,
            win INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_hashes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_type TEXT,
            seed TEXT,
            hash TEXT,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def generate_referral_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        code = generate_referral_code()
        cursor.execute(
            "INSERT INTO users (user_id, balance, referral_code) VALUES (?, ?, ?)",
            (user_id, str(START_BALANCE), code)
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    user_dict = dict(user)
    try:
        user_dict['balance'] = int(user_dict['balance'])
    except:
        user_dict['balance'] = 0
    try:
        user_dict['total_won'] = int(user_dict['total_won'])
    except:
        user_dict['total_won'] = 0
    try:
        user_dict['total_lost'] = int(user_dict['total_lost'])
    except:
        user_dict['total_lost'] = 0
    conn.close()
    return user_dict

def update_balance(user_id, amount):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        get_user(user_id)
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    try:
        current = int(row['balance'])
    except:
        current = 0
    new_balance = current + amount
    cursor.execute(
        "UPDATE users SET balance = ? WHERE user_id = ?",
        (str(new_balance), user_id)
    )
    conn.commit()
    conn.close()

def set_balance(user_id, new_balance):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET balance = ? WHERE user_id = ?",
        (str(new_balance), user_id)
    )
    conn.commit()
    conn.close()

def reset_all_balances():
    """Обнуляет баланс всех пользователей (устанавливает 0). Возвращает количество обновлённых пользователей."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = '0'")
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected

def add_game_stat(user_id, game_type, bet, win):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO game_stats (user_id, game_type, bet, win) VALUES (?, ?, ?, ?)",
        (user_id, game_type, bet, win)
    )
    if win > 0:
        cursor.execute("SELECT total_won FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            try:
                total_won = int(row['total_won']) + win
            except:
                total_won = win
            cursor.execute(
                "UPDATE users SET total_won = ? WHERE user_id = ?",
                (str(total_won), user_id)
            )
    else:
        cursor.execute("SELECT total_lost FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            try:
                total_lost = int(row['total_lost']) + bet
            except:
                total_lost = bet
            cursor.execute(
                "UPDATE users SET total_lost = ? WHERE user_id = ?",
                (str(total_lost), user_id)
            )
    conn.commit()
    conn.close()

def get_top_players(limit=10):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance FROM users")
    rows = cursor.fetchall()
    conn.close()
    players = []
    for row in rows:
        try:
            bal = int(row['balance'])
            if bal >= 0:
                players.append((row['user_id'], bal))
        except (ValueError, TypeError):
            continue
    players.sort(key=lambda x: x[1], reverse=True)
    return players[:limit]

def can_claim_daily(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return True
    last_daily = datetime.datetime.strptime(row[0], "%Y-%m-%d").date()
    return last_daily < datetime.date.today()

def set_daily_claimed(user_id):
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.date.today().isoformat()
    cursor.execute(
        "UPDATE users SET last_daily = ? WHERE user_id = ?",
        (today, user_id)
    )
    conn.commit()
    conn.close()

def get_total_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = cursor.fetchone()['total_users']
    cursor.execute("SELECT balance FROM users")
    rows = cursor.fetchall()
    total_balance = 0
    for row in rows:
        try:
            total_balance += int(row['balance'])
        except:
            pass
    cursor.execute("SELECT SUM(win) as total_won FROM game_stats WHERE win > 0")
    total_won = cursor.fetchone()['total_won'] or 0
    cursor.execute("SELECT SUM(bet) as total_lost FROM game_stats WHERE win = 0")
    total_lost = cursor.fetchone()['total_bet'] or 0
    cursor.execute("SELECT COUNT(*) as total_games FROM game_stats")
    total_games = cursor.fetchone()['total_games'] or 0
    conn.close()
    return {
        'total_users': total_users,
        'total_balance': total_balance,
        'total_won': total_won,
        'total_lost': total_lost,
        'total_games': total_games
    }

def set_referral(user_id, referrer_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET referred_by = ? WHERE user_id = ?",
        (referrer_id, user_id)
    )
    conn.commit()
    conn.close()

def get_referral_code(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row['referral_code'] if row else None

def add_referral_record(referrer_id, referred_id, bonus_ref, bonus_refd):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO referrals (referrer_id, referred_id, bonus_referrer, bonus_referred) VALUES (?, ?, ?, ?)",
        (referrer_id, referred_id, bonus_ref, bonus_refd)
    )
    conn.commit()
    conn.close()

def count_referrals(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row['cnt'] if row else 0

def get_referred_by(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row['referred_by'] if row else None

def user_exists(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def create_promocode(code, reward, max_uses, expires_at, created_by):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO promocodes (code, reward, max_uses, expires_at, created_by) VALUES (?, ?, ?, ?, ?)",
        (code, reward, max_uses, expires_at, created_by)
    )
    conn.commit()
    conn.close()

def get_promocode(code):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promocodes WHERE code = ?", (code,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def use_promocode(user_id, code):
    promo = get_promocode(code)
    if not promo:
        return False, "Промокод не найден.", 0
    if promo['expires_at']:
        exp_date = datetime.datetime.strptime(promo['expires_at'], "%Y-%m-%d").date()
        if exp_date < datetime.date.today():
            return False, "Срок действия промокода истёк.", 0
    if promo['max_uses'] != -1 and promo['used_count'] >= promo['max_uses']:
        return False, "Промокод уже использован максимальное количество раз.", 0
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM promo_activations WHERE user_id = ? AND promo_id = ?",
        (user_id, promo['id'])
    )
    if cursor.fetchone():
        conn.close()
        return False, "Вы уже активировали этот промокод.", 0
    cursor.execute(
        "INSERT INTO promo_activations (user_id, promo_id) VALUES (?, ?)",
        (user_id, promo['id'])
    )
    cursor.execute(
        "UPDATE promocodes SET used_count = used_count + 1 WHERE id = ?",
        (promo['id'],)
    )
    conn.commit()
    conn.close()
    reward = promo['reward']
    update_balance(user_id, reward)
    return True, "Промокод успешно активирован!", reward

def list_promocodes():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_promocode(promo_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM promo_activations WHERE promo_id = ?", (promo_id,))
    cursor.execute("DELETE FROM promocodes WHERE id = ?", (promo_id,))
    conn.commit()
    conn.close()

def save_game_hash(user_id, game_type, seed, hash_val, result=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO game_hashes (user_id, game_type, seed, hash, result) VALUES (?, ?, ?, ?, ?)",
        (user_id, game_type, seed, hash_val, result)
    )
    game_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return game_id

def update_game_result(game_id, result):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE game_hashes SET result = ? WHERE id = ?",
        (result, game_id)
    )
    conn.commit()
    conn.close()

def get_last_game_hash(user_id, game_type):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM game_hashes WHERE user_id = ? AND game_type = ? ORDER BY id DESC LIMIT 1",
        (user_id, game_type)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
import random
import hashlib

def generate_seed():
    """Генерирует случайный seed в виде hex-строки (32 символа)"""
    return hashlib.sha256(str(random.getrandbits(256)).encode()).hexdigest()

def hash_seed(seed):
    """Возвращает SHA-256 хэш от seed"""
    return hashlib.sha256(seed.encode()).hexdigest()

def generate_mines_field(size, mines_count):
    total_cells = size * size
    mine_indices = random.sample(range(total_cells), mines_count)
    grid = [[0 for _ in range(size)] for _ in range(size)]
    mine_positions = []
    for idx in mine_indices:
        row = idx // size
        col = idx % size
        grid[row][col] = 1
        mine_positions.append((row, col))
    return grid, mine_positions

def calculate_mines_multiplier(clicked_count, mines_count, total_cells):
    """
    Вычисляет множитель выигрыша для игры "Мины".
    Формула: 1 + (clicked_count / safe_cells) * 2
    """
    safe_cells = total_cells - mines_count
    if safe_cells <= 0:
        
        print(f"⚠️ Ошибка: safe_cells={safe_cells}, clicked={clicked_count}, mines={mines_count}, total={total_cells}")
        return 1.0
    if clicked_count == 0:
        return 1.0
    multiplier = 1 + (clicked_count / safe_cells) * 2
    
    if multiplier > 10:
        print(f"⚠️ Аномальный множитель: {multiplier} (clicked={clicked_count}, safe={safe_cells}). Принудительно 1.0")
        return 1.0
    
    return round(multiplier, 2)

def roll_dice():
    return random.randint(1, 6)

def roulette_spin():
    number = random.randint(0, 36)
    if number == 0:
        color = 'green'
    elif number in [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]:
        color = 'red'
    else:
        color = 'black'
    return number, color
import pygame
import sys
import random
import time
import psycopg2
from psycopg2 import sql
from pygame.locals import *

# Initialize pygame
pygame.init()

# PostgreSQL connection
def get_db_connection():
    return psycopg2.connect(
        host="127.0.0.1",
        database="snake_game",
        user="kirillchumikov",
        password="1234"  # Change this to your PostgreSQL password
    )

# Database setup
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create user table if not exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create user_score table if not exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_scores (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        level INTEGER NOT NULL,
        speed INTEGER NOT NULL,
        snake_body TEXT NOT NULL,
        food_pos TEXT NOT NULL,
        food_weight INTEGER NOT NULL,
        saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create levels table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS levels (
        level INTEGER PRIMARY KEY,
        speed INTEGER NOT NULL,
        walls TEXT NOT NULL,
        description TEXT NOT NULL
    )
    ''')
    
    # Insert default levels if not exists
    cursor.execute('SELECT COUNT(*) FROM levels')
    if cursor.fetchone()[0] == 0:
        default_levels = [
            (1, 9, '[]', 'Basic level - no obstacles'),
            (2, 12, '[[100,100,200,20],[300,400,20,200]]', 'Intermediate - simple walls'),
            (3, 15, '[[50,50,400,20],[50,430,20,400],[430,50,20,400]]', 'Advanced - border walls'),
            (4, 18, '[[0,0,500,10],[0,490,500,10],[0,0,10,500],[490,0,10,500],[100,100,300,20],[100,380,300,20]]', 'Expert - complex maze')
        ]
        insert_query = sql.SQL('INSERT INTO levels VALUES {}').format(
            sql.SQL(',').join(map(sql.Literal, default_levels))
        )
        cursor.execute(insert_query)
    
    conn.commit()
    conn.close()

init_db()

# Game constants
WIDTH, HEIGHT = 500, 500
CELL_SIZE = 25
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
GOLD = (255, 215, 0)
WALL_COLOR = (100, 100, 100)

# Set up display
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption('Snake Game')

# Game variables
current_user = None
snake_pos = [WIDTH//2, HEIGHT//2]
snake_body = []
direction = 'RIGHT'
change_to = direction
score = 0
level = 1
SPEED = 9
walls = []
food_pos = [0, 0]
food_spawn = False
food_weight = 1
food_colors = [RED, BLUE, GOLD]
food_timer = 0
FOOD_LIFETIME = 10
growing = False
paused = False

# Game clock
clock = pygame.time.Clock()

# Fonts
font = pygame.font.SysFont('arial', 20)
large_font = pygame.font.SysFont('arial', 30)

def get_user(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
    user = cursor.fetchone()
    conn.close()
    return user[0] if user else None

def create_user(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (username) VALUES (%s) RETURNING id', (username,))
    user_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return user_id

def get_last_save(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT score, level, speed, snake_body, food_pos, food_weight 
    FROM user_scores 
    WHERE user_id = %s 
    ORDER BY saved_at DESC 
    LIMIT 1
    ''', (user_id,))
    save = cursor.fetchone()
    conn.close()
    return save

def save_game(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO user_scores 
    (user_id, score, level, speed, snake_body, food_pos, food_weight)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (
        user_id,
        score,
        level,
        SPEED,
        str(snake_body),
        str(food_pos),
        food_weight
    ))
    conn.commit()
    conn.close()

def get_level_details(level_num):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT speed, walls FROM levels WHERE level = %s', (level_num,))
    details = cursor.fetchone()
    conn.close()
    return details

def spawn_food():
    global food_pos, food_spawn, food_weight, food_timer
    while True:
        food_pos = [
            random.randint(0, WIDTH // CELL_SIZE -1) * CELL_SIZE,
            random.randint(0, HEIGHT // CELL_SIZE -1) * CELL_SIZE
        ]
        # Check if food spawns on snake or walls
        valid_position = True
        for wall in walls:
            wall_rect = pygame.Rect(wall)
            if wall_rect.collidepoint(food_pos[0], food_pos[1]):
                valid_position = False
                break
        
        if food_pos not in snake_body and valid_position:
            food_spawn = True
            food_weight = random.randint(1, 3)
            food_timer = time.time()
            break

def check_collision():
    # Check wall collision
    for wall in walls:
        wall_rect = pygame.Rect(wall)
        if wall_rect.collidepoint(snake_pos[0], snake_pos[1]):
            return True
    
    # Check screen boundaries
    if (snake_pos[0] < 0 or snake_pos[0] >= WIDTH or 
        snake_pos[1] < 0 or snake_pos[1] >= HEIGHT):
        return True
    
    # Check self collision
    for block in snake_body[1:]:
        if snake_pos == block:
            return True
    
    return False

def check_food_collision():
    global score, level, SPEED, growing
    if snake_pos[0] == food_pos[0] and snake_pos[1] == food_pos[1]:
        score += food_weight
        growing = True  
        if score % 3 == 0:  
            level += 1
            level_details = get_level_details(level)
            if level_details:
                SPEED = level_details[0]
                global walls
                walls = eval(level_details[1])
        return True
    return False

def show_game_over():
    screen.fill(BLACK)
    game_over_surface = large_font.render('GAME OVER!', True, RED)
    score_surface = font.render(f'Final Score: {score}', True, WHITE)
    level_surface = font.render(f'Final Level: {level}', True, WHITE)
    
    screen.blit(game_over_surface, (WIDTH//2 - 100, HEIGHT//2 - 60))
    screen.blit(score_surface, (WIDTH//2 - 70, HEIGHT//2))
    screen.blit(level_surface, (WIDTH//2 - 70, HEIGHT//2 + 30))
    pygame.display.flip()
    time.sleep(3)
    pygame.quit()
    sys.exit()

def update_score():
    score_surface = font.render(f'Score: {score}', True, WHITE)
    level_surface = font.render(f'Level: {level}', True, WHITE)
    speed_surface = font.render(f'Speed: {SPEED}', True, WHITE)
    user_surface = font.render(f'Player: {current_user}', True, WHITE)
    
    screen.blit(score_surface, (10, 10))
    screen.blit(level_surface, (10, 40))
    screen.blit(speed_surface, (10, 70))
    screen.blit(user_surface, (10, 100))

def draw_snake():
    for i, pos in enumerate(snake_body):
        color = GREEN
        if i == 0:
            color = (0, 200, 0)  # Darker green for head
        pygame.draw.rect(screen, color, pygame.Rect(pos[0], pos[1], CELL_SIZE, CELL_SIZE))

def draw_food():
    if time.time() - food_timer > FOOD_LIFETIME:
        spawn_food()
    
    pygame.draw.rect(screen, food_colors[food_weight-1], pygame.Rect(food_pos[0], food_pos[1], CELL_SIZE, CELL_SIZE))
    
    # Draw timer bar
    time_left = max(0, FOOD_LIFETIME - (time.time() - food_timer))
    timer_width = (time_left / FOOD_LIFETIME) * CELL_SIZE
    pygame.draw.rect(screen, WHITE, (food_pos[0], food_pos[1] - 5, CELL_SIZE, 3))
    pygame.draw.rect(screen, RED, (food_pos[0], food_pos[1] - 5, timer_width, 3))

def draw_walls():
    for wall in walls:
        pygame.draw.rect(screen, WALL_COLOR, pygame.Rect(wall))

def show_pause_screen():
    pause_surface = large_font.render('PAUSED', True, WHITE)
    info_surface = font.render('Press P to continue, S to save', True, WHITE)
    screen.blit(pause_surface, (WIDTH//2 - 60, HEIGHT//2 - 30))
    screen.blit(info_surface, (WIDTH//2 - 120, HEIGHT//2 + 20))
    pygame.display.flip()

def show_login_screen():
    username = ""
    input_active = True
    
    while True:
        screen.fill(BLACK)
        title_surface = large_font.render('SNAKE GAME', True, GREEN)
        prompt_surface = font.render('Enter your username:', True, WHITE)
        input_surface = font.render(username, True, WHITE)
        
        screen.blit(title_surface, (WIDTH//2 - 100, HEIGHT//2 - 100))
        screen.blit(prompt_surface, (WIDTH//2 - 100, HEIGHT//2 - 30))
        pygame.draw.rect(screen, WHITE, (WIDTH//2 - 100, HEIGHT//2, 200, 30), 2)
        screen.blit(input_surface, (WIDTH//2 - 90, HEIGHT//2 + 5))
        
        pygame.display.flip()
        
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == KEYDOWN:
                if event.key == K_RETURN and username:
                    return username
                elif event.key == K_BACKSPACE:
                    username = username[:-1]
                elif event.key == K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                elif len(username) < 15:
                    username += event.unicode

# User login
username = show_login_screen()
user_id = get_user(username)
if user_id is None:
    user_id = create_user(username)
    # Initialize new game
    level_details = get_level_details(1)
    SPEED = level_details[0]
    walls = eval(level_details[1])
    snake_body = [
        [WIDTH//2, HEIGHT//2],
        [WIDTH//2 - CELL_SIZE, HEIGHT//2],
        [WIDTH//2 - (2 * CELL_SIZE), HEIGHT//2]
    ]
else:
    # Load saved game if exists
    save = get_last_save(user_id)
    if save:
        score, level, SPEED, body, f_pos, f_weight = save
        snake_body = eval(body)
        food_pos = eval(f_pos)
        food_weight = f_weight
        food_timer = time.time()
        level_details = get_level_details(level)
        walls = eval(level_details[1])
    else:
        # Initialize new game for returning user
        level_details = get_level_details(1)
        SPEED = level_details[0]
        walls = eval(level_details[1])
        snake_body = [
            [WIDTH//2, HEIGHT//2],
            [WIDTH//2 - CELL_SIZE, HEIGHT//2],
            [WIDTH//2 - (2 * CELL_SIZE), HEIGHT//2]
        ]

current_user = username
snake_pos = snake_body[0].copy()
spawn_food()

# Main game loop
running = True
while running:
    for event in pygame.event.get():
        if event.type == QUIT:
            running = False
        elif event.type == KEYDOWN:
            if event.key == K_UP and direction != 'DOWN':
                change_to = 'UP'
            elif event.key == K_DOWN and direction != 'UP':
                change_to = 'DOWN'
            elif event.key == K_RIGHT and direction != 'LEFT':
                change_to = 'RIGHT'
            elif event.key == K_LEFT and direction != 'RIGHT':
                change_to = 'LEFT'
            elif event.key == K_p:
                paused = not paused
            elif event.key == K_s and paused:
                save_game(user_id)
    
    if paused:
        show_pause_screen()
        continue
    
    direction = change_to
    if direction == 'UP':
        snake_pos[1] -= CELL_SIZE
    elif direction == 'DOWN':
        snake_pos[1] += CELL_SIZE
    elif direction == 'LEFT':
        snake_pos[0] -= CELL_SIZE
    elif direction == 'RIGHT':
        snake_pos[0] += CELL_SIZE
    
    snake_body.insert(0, list(snake_pos))
    if not growing:
        snake_body.pop()
    else:
        growing = False
    
    if check_food_collision():
        spawn_food()
    
    if check_collision():
        show_game_over()
    
    screen.fill(BLACK)
    draw_walls()
    draw_snake()
    draw_food()
    update_score()
    pygame.display.flip()
    clock.tick(SPEED)

pygame.quit()
sys.exit()
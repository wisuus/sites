from flask import Flask, render_template, request, jsonify, session, Response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import time
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super-secret-key-for-session-safety'
DATABASE = 'database.db'

DEFAULT_PREDICTIONS = [
    "Сегодня идеальный день для написания кода на Python! 🐍",
    "Вас ждет неожиданный, но очень приятный звонок. 📞",
    "Кто-то думает о вас прямо сейчас. 😊",
    "Ваши баги превратятся в фичи, не переживайте! 🐛",
    "Сделайте паузу и выпейте чашечку чая или кофе. ☕",
    "Скоро перед вами откроется дверь, которая была заперта. 🚪",
    "Вас ждет финансовый успех там, где вы его не ждали. 💰",
    "Доверяйте своей интуиции сегодня, она не подведет. 🧠"
]

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                last_cookie_time REAL DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                prediction TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                stars INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()

        # СОЗДАНИЕ АДМИНИСТРАТОРА ПО УМОЛЧАНИЮ
        cursor.execute("SELECT * FROM users WHERE email = 'admin@admin.com'")
        if not cursor.fetchone():
            hashed_admin_pass = generate_password_hash('admin123')
            cursor.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                ('Администратор', 'admin@admin.com', hashed_admin_pass, 'admin')
            )
            conn.commit()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    if not name or not email or not password:
        return jsonify({'error': 'Заполните все поля'}), 400
    hashed_password = generate_password_hash(password)
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, hashed_password))
            conn.commit()
        return jsonify({'message': 'Регистрация успешна!'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Такой Email уже зарегистрирован'}), 400

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
    
    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_role'] = user['role']
        
        has_rated = False
        if user['role'] == 'user':
            cursor.execute("SELECT stars FROM ratings WHERE user_id = ?", (user['id'],))
            rating = cursor.fetchone()
            if rating:
                has_rated = True
                
        return jsonify({'name': user['name'], 'role': user['role'], 'has_rated': has_rated}), 200
    return jsonify({'error': 'Неверный email или пароль'}), 400
# МАРШРУТ СТАТИСТИКИ ДЛЯ АДМИНИСТРАТОРА
@app.route('/get-admin-stats', methods=['GET'])
def get_admin_stats():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        return jsonify({'error': 'Доступ запрещен'}), 403
        
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Считаем пользователей
        cursor.execute("SELECT COUNT(*) as total FROM users WHERE role = 'user'")
        total_users = cursor.fetchone()['total']
        
        # 2. Считаем среднюю оценку
        cursor.execute("SELECT AVG(stars) as avg_stars FROM ratings")
        avg_rating_row = cursor.fetchone()['avg_stars']
        avg_rating = round(avg_rating_row, 2) if avg_rating_row else 0.0
        
        # 3. Считаем разломанные печенья
        cursor.execute("SELECT COUNT(*) as total FROM history")
        total_cookies = cursor.fetchone()['total']
        
        # 4. Получаем подробный список всех оценок с именами
        cursor.execute('''
            SELECT users.name, ratings.stars 
            FROM ratings 
            JOIN users ON ratings.user_id = users.id 
            ORDER BY ratings.id DESC
        ''')
        ratings_rows = cursor.fetchall()
        ratings_list = [{'name': row['name'], 'stars': row['stars']} for row in ratings_rows]
        
    return jsonify({
        'total_users': total_users,
        'avg_rating': avg_rating,
        'total_cookies': total_cookies,
        'ratings': ratings_list
    }), 200

@app.route('/send-rating', methods=['POST'])
def send_rating():
    if 'user_id' not in session:
        return jsonify({'error': 'Необходима авторизация'}), 401
    data = request.json
    stars = data.get('stars')
    user_id = session['user_id']
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO ratings (user_id, stars) VALUES (?, ?)", (user_id, stars))
            conn.commit()
        return jsonify({'message': 'Спасибо за вашу оценку! ❤️'}), 200
    except Exception as e:
        return jsonify({'error': 'Ошибка сохранения оценки'}), 500

@app.route('/add-prediction', methods=['POST'])
def add_prediction():
    if 'user_id' not in session:
        return jsonify({'error': 'Необходима авторизация'}), 401
    data = request.json
    text = data.get('text', '').strip()
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO custom_predictions (text) VALUES (?)", (text,))
        conn.commit()
    return jsonify({'message': 'Предсказание успешно добавлено в пул!'}), 200

@app.route('/break-cookie', methods=['POST'])
def break_cookie():
    if 'user_id' not in session:
        return jsonify({'error': 'Необходима авторизация'}), 401
    user_id = session['user_id']
    current_time = time.time()
    cooldown = 15.0
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT last_cookie_time FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        time_passed = current_time - user['last_cookie_time']
        if time_passed < cooldown:
            return jsonify({'error': 'Печенье еще не испеклось!', 'time_left': cooldown - time_passed}), 429
        
        cursor.execute("SELECT text FROM custom_predictions")
        custom_rows = cursor.fetchall()
        all_pool = DEFAULT_PREDICTIONS + [row['text'] for row in custom_rows]
        
        random_prediction = random.choice(all_pool)
        date_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        cursor.execute("UPDATE users SET last_cookie_time = ? WHERE id = ?", (current_time, user_id))
        cursor.execute("INSERT INTO history (user_id, prediction, created_at) VALUES (?, ?, ?)", (user_id, random_prediction, date_str))
        conn.commit()
        
    return jsonify({'prediction': random_prediction}), 200

@app.route('/get-history', methods=['GET'])
def get_history():
    if 'user_id' not in session:
        return jsonify({'error': 'Необходима авторизация'}), 401
    user_id = session['user_id']
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT prediction, created_at FROM history WHERE user_id = ? ORDER BY id DESC", (user_id,))
        rows = cursor.fetchall()
        history_list = [{'prediction': row['prediction'], 'created_at': row['created_at']} for row in rows]
    return jsonify(history_list), 200

@app.route('/export-history', methods=['GET'])
def export_history():
    if 'user_id' not in session:
        return "Необходима авторизация", 401
    user_id = session['user_id']
    user_name = session.get('user_name', 'User')
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT prediction, created_at FROM history WHERE user_id = ? ORDER BY id ASC", (user_id,))
        rows = cursor.fetchall()
    file_content = f"История предсказаний пользователя {user_name}\n"
    file_content += "="*50 + "\n\n"
    if not rows:
        file_content += "Вы еще не разломали ни одного печенья.\n"
    else:
        for i, row in enumerate(rows, 1):
            file_content += f"[{row['created_at']}] {i}. {row['prediction']}\n"
    return Response(file_content, mimetype="text/plain", headers={"Content-Disposition": f"attachment;filename=predictions_history.txt"})

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Вы вышли из системы'}), 200

if __name__ == '__main__':
    app.run(port=3000, debug=True)

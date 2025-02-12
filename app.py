from flask import Flask, render_template, request, redirect, url_for, session, flash, current_app
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
from os import path
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'secret_key'
load_dotenv()

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'секрет')
app.config['DB_TYPE'] = os.getenv('DB_TYPE', 'postgres')

def is_admin():
    return 'user_id' in session and session.get('role') == 'admin'

def db_connect():
    if app.config['DB_TYPE'] == 'postgres':
        conn = psycopg2.connect(
            host='127.0.0.1',
            database='igor_bogachev_knowledge_base',
            user='postgres',
            password='postgres',
            port=5432
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
    else:
        dir_path = path.dirname(path.realpath(__file__))
        db_path = path.join(dir_path, "database.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
    return conn, cur

def db_close(conn, cur):
    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    try:
        offset = int(request.args.get('offset', 20))
    except ValueError:
        offset = 20

    conn, cur = db_connect()
    try:
        if current_app.config['DB_TYPE'] == 'postgres':
            cur.execute("SELECT * FROM initiatives ORDER BY created_at DESC LIMIT %s", (offset,))
        else:
            cur.execute("SELECT * FROM initiatives ORDER BY created_at DESC LIMIT ?", (offset,))
        initiatives = cur.fetchall()
    except Exception as e:
        logger.error(f"Ошибка при получении инициатив: {e}")
        initiatives = []
    finally:
        db_close(conn, cur)

    return render_template('index.html', initiatives=initiatives, offset=offset)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']

        if not login or not password:
            flash('Логин и пароль не могут быть пустыми')
            return redirect('/register')

        conn, cur = db_connect()
        try:
            if current_app.config['DB_TYPE'] == 'postgres':
                cur.execute("SELECT * FROM users WHERE login = %s", (login,))
            else:
                cur.execute("SELECT * FROM users WHERE login = ?", (login,))
            existing_user = cur.fetchone()

            if existing_user:
                flash('Пользователь с таким логином уже существует')
                return redirect('/register')

            hashed_password = generate_password_hash(password)

            if current_app.config['DB_TYPE'] == 'postgres':
                cur.execute("INSERT INTO users (login, password, role) VALUES (%s, %s, %s)", (login, hashed_password, 'user'))
            else:
                cur.execute("INSERT INTO users (login, password, role) VALUES (?, ?, ?)", (login, hashed_password, 'user'))

            flash('Регистрация успешна')
            return redirect('/login')
        except Exception as e:
            logger.error(f"Ошибка при регистрации: {e}")
            flash('Произошла ошибка при регистрации')
            return redirect('/register')
        finally:
            db_close(conn, cur)

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']
        conn, cur = db_connect()
        try:
            if current_app.config['DB_TYPE'] == 'postgres':
                cur.execute("SELECT * FROM users WHERE login = %s", (login,))
            else:
                cur.execute("SELECT * FROM users WHERE login = ?", (login,))
            user = cur.fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['login'] = user['login']
                session['role'] = user['role']
                flash('Вход выполнен')
                return redirect('/')
            else:
                flash('Неверный логин или пароль')
        except Exception as e:
            logger.error(f"Ошибка при входе: {e}")
            flash('Произошла ошибка при входе')
        finally:
            db_close(conn, cur)

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('login', None)
    session.pop('role', None)
    flash('Выход выполнен')
    return redirect('/')

@app.route('/create_initiative', methods=['GET', 'POST'])
def create_initiative():
    if 'user_id' not in session:
        flash('Требуется авторизация')
        return redirect('/login')

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        conn, cur = db_connect()
        try:
            if current_app.config['DB_TYPE'] == 'postgres':
                cur.execute("INSERT INTO initiatives (title, content, user_id) VALUES (%s, %s, %s)",
                            (title, content, session['user_id']))
            else:
                cur.execute("INSERT INTO initiatives (title, content, user_id) VALUES (?, ?, ?)",
                            (title, content, session['user_id']))
            flash('Инициатива создана')
            return redirect('/')
        except Exception as e:
            logger.error(f"Ошибка при создании инициативы: {e}")
            flash('Произошла ошибка при создании инициативы')
            return redirect('/create_initiative')
        finally:
            db_close(conn, cur)

    return render_template('create_initiative.html')

@app.route('/vote/<int:initiative_id>/<int:vote>')
def vote(initiative_id, vote):
    if 'user_id' not in session:
        flash('Требуется авторизация')
        return redirect('/login')

    conn, cur = db_connect()
    try:
        if current_app.config['DB_TYPE'] == 'postgres':
            cur.execute("SELECT * FROM initiatives WHERE id = %s", (initiative_id,))
        else:
            cur.execute("SELECT * FROM initiatives WHERE id = ?", (initiative_id,))
        initiative = cur.fetchone()

        if not initiative:
            flash('Инициатива не найдена')
            return redirect('/')

        if vote == 0:
            vote = -1

        if current_app.config['DB_TYPE'] == 'postgres':
            cur.execute("UPDATE initiatives SET score = score + %s WHERE id = %s", (vote, initiative_id))
        else:
            cur.execute("UPDATE initiatives SET score = score + ? WHERE id = ?", (vote, initiative_id))

        if vote == -1:
            if current_app.config['DB_TYPE'] == 'postgres':
                cur.execute("SELECT score FROM initiatives WHERE id = %s", (initiative_id,))
            else:
                cur.execute("SELECT score FROM initiatives WHERE id = ?", (initiative_id,))
            initiative_score = cur.fetchone()

            if initiative_score and initiative_score['score'] <= -10:
                if current_app.config['DB_TYPE'] == 'postgres':
                    cur.execute("DELETE FROM initiatives WHERE id = %s", (initiative_id,))
                else:
                    cur.execute("DELETE FROM initiatives WHERE id = ?", (initiative_id,))
                flash('Инициатива удалена из-за превышения голосов "против"')

        flash('Голос учтён')
        return redirect('/')
    except Exception as e:
        logger.error(f"Ошибка при голосовании: {e}")
        flash('Произошла ошибка при голосовании')
        return redirect('/')
    finally:
        db_close(conn, cur)

@app.route('/delete_initiative/<int:initiative_id>')
def delete_initiative(initiative_id):
    if 'user_id' not in session:
        flash('Требуется авторизация')
        return redirect('/login')

    conn, cur = db_connect()
    try:
        if current_app.config['DB_TYPE'] == 'postgres':
            cur.execute("SELECT * FROM initiatives WHERE id = %s", (initiative_id,))
        else:
            cur.execute("SELECT * FROM initiatives WHERE id = ?", (initiative_id,))
        initiative = cur.fetchone()

        if not initiative:
            flash('Инициатива не найдена')
            return redirect('/')

        if session.get('role') == 'admin' or initiative['user_id'] == session['user_id']:
            if current_app.config['DB_TYPE'] == 'postgres':
                cur.execute("DELETE FROM initiatives WHERE id = %s", (initiative_id,))
            else:
                cur.execute("DELETE FROM initiatives WHERE id = ?", (initiative_id,))
            flash('Инициатива удалена')
        else:
            flash('У вас нет прав для удаления этой инициативы')
    except Exception as e:
        logger.error(f"Ошибка при удалении инициативы: {e}")
        flash('Произошла ошибка при удалении инициативы')
    finally:
        db_close(conn, cur)

    return redirect('/')

@app.route('/admin/users')
def admin_users():
    if not is_admin():
        flash('Доступ запрещён')
        return redirect('/')

    conn, cur = db_connect()
    try:
        cur.execute("SELECT id, login, role FROM users")
        users = cur.fetchall()
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        users = []
    finally:
        db_close(conn, cur)

    return render_template('admin_users.html', users=users)

@app.route('/admin/delete_user/<int:user_id>')
def admin_delete_user(user_id):
    if not is_admin():
        flash('Доступ запрещён')
        return redirect('/')

    conn, cur = db_connect()
    try:
        if current_app.config['DB_TYPE'] == 'postgres':
            cur.execute("DELETE FROM initiatives WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        else:
            cur.execute("DELETE FROM initiatives WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        flash('Пользователь удалён')
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя: {e}")
        flash('Произошла ошибка при удалении пользователя')
    finally:
        db_close(conn, cur)

    return redirect('/admin/users')

@app.route('/delete_account', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        flash('Требуется авторизация')
        return redirect('/login')

    user_id = session['user_id']
    conn, cur = db_connect()
    try:
        if current_app.config['DB_TYPE'] == 'postgres':
            cur.execute("DELETE FROM initiatives WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        else:
            cur.execute("DELETE FROM initiatives WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        session.pop('user_id', None)
        session.pop('login', None)
        session.pop('role', None)
        flash('Ваш аккаунт успешно удалён')
    except Exception as e:
        logger.error(f"Ошибка при удалении аккаунта: {e}")
        flash('Произошла ошибка при удалении аккаунта')
    finally:
        db_close(conn, cur)

    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
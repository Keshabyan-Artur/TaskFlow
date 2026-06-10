from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# ========== НАСТРОЙКА ПРИЛОЖЕНИЯ ==========
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ОТКЛЮЧАЕМ КЭШ (чтобы не было проблем с обновлением)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ========== БАЗА ДАННЫХ ==========
db = SQLAlchemy(app)

# ========== НАСТРОЙКА ВХОДА ==========
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'

# ========== МОДЕЛИ ==========
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship('Task', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='new')  # new, in_progress, done
    deadline = db.Column(db.Date, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========== ЗАГРУЗЧИК ПОЛЬЗОВАТЕЛЯ ==========
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ========== МАРШРУТЫ ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password2 = request.form.get('password2')

        # Проверки
        if not username or not email or not password:
            flash('Пожалуйста, заполните все поля', 'error')
            return redirect(url_for('register'))

        if password != password2:
            flash('Пароли не совпадают', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Пользователь с такой почтой уже существует', 'error')
            return redirect(url_for('register'))

        # Создаём пользователя
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Регистрация успешна! Теперь войдите в систему.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('Неверное имя пользователя или пароль', 'error')
            return redirect(url_for('login'))

        login_user(user)
        flash(f'Добро пожаловать, {username}!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
    return render_template('dashboard.html', tasks=tasks)

@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    title = request.form.get('title')
    description = request.form.get('description')
    deadline_str = request.form.get('deadline')
    
    if not title:
        flash('Название задачи обязательно!', 'error')
        return redirect(url_for('dashboard'))
    
    # Преобразуем строку с датой в объект date
    from datetime import datetime
    deadline = None
    if deadline_str:
        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    task = Task(
        title=title,
        description=description or '',
        deadline=deadline,
        user_id=current_user.id
    )
    
    db.session.add(task)
    db.session.commit()
    
    flash('Задача создана!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Проверяем, что задача принадлежит текущему пользователю
    if task.user_id != current_user.id:
        flash('У вас нет доступа к этой задаче!', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        deadline_str = request.form.get('deadline')
        
        if not title:
            flash('Название задачи обязательно!', 'error')
            return redirect(url_for('edit_task', task_id=task_id))
        
        task.title = title
        task.description = description or ''
        
        if deadline_str:
            try:
                task.deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
            except ValueError:
                task.deadline = None
        else:
            task.deadline = None
        
        db.session.commit()
        flash('Задача обновлена!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('edit_task.html', task=task)

@app.route('/delete_task/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('У вас нет доступа к этой задаче!', 'error')
        return redirect(url_for('dashboard'))
    
    db.session.delete(task)
    db.session.commit()
    
    flash('Задача удалена!', 'info')
    return redirect(url_for('dashboard'))

@app.route('/change_status/<int:task_id>/<status>')
@login_required
def change_status(task_id, status):
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('У вас нет доступа к этой задаче!', 'error')
        return redirect(url_for('dashboard'))
    
    if status in ['new', 'in_progress', 'done']:
        task.status = status
        db.session.commit()
        flash(f'Статус изменён!', 'success')
    
    return redirect(url_for('dashboard'))

# ========== СОЗДАНИЕ ТАБЛИЦ ПРИ ПЕРВОМ ЗАПУСКЕ ==========
with app.app_context():
    db.create_all()

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    app.run(debug=True)
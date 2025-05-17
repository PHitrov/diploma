import os
import re
from datetime import datetime, timezone
from docx import Document as DocxDocument
import PyPDF2
from quart import Quart, request, jsonify, session, redirect, url_for, render_template
from langdetect import detect
from translate import Translator as GoogleTranslator
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import IntegrityError, ProgrammingError

# --- Настройка логирования ---
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройка БД ---
DATABASE_URL = "postgresql+asyncpg://translator_user:translator_password@127.0.0.1/translator_db"
Base = declarative_base()

# --- Модели ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    progress = relationship("UserProgress", back_populates="user")

class TranslationHistory(Base):
    __tablename__ = "translation_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    source_lang = Column(String(10))
    target_lang = Column(String(10))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class UserProgress(Base):
    __tablename__ = "user_progress"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    user = relationship("User", back_populates="progress")
    total_translations = Column(Integer, default=0)
    points = Column(Integer, default=0)
    level = Column(Integer, default=1)
    last_active = Column(DateTime(timezone=True), server_default=func.now())

# --- Quart и ORM ---
app = Quart(__name__)
app.secret_key = 'your_secret_key_here'

# --- Инициализация БД ---
engine = create_async_engine(DATABASE_URL, echo=True, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@app.before_serving
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("База данных и таблицы успешно созданы")

# --- Регистрация ---
@app.route('/register', methods=['POST'])
async def register():
    data = await request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Логин и пароль обязательны'}), 400

    async with AsyncSessionLocal() as db_session:
        try:
            # Проверка существования пользователя
            result = await db_session.execute(
                select(User).where(User.username == username)
            )
            if result.scalars().first():
                return jsonify({'error': 'Пользователь уже существует'}), 400

            # Создание пользователя
            new_user = User(username=username, password=password)
            db_session.add(new_user)
            await db_session.flush()  # Ожидаем, пока id будет присвоен

            # Создание прогресса
            progress = UserProgress(user_id=new_user.id)
            db_session.add(progress)
            await db_session.commit()

            return jsonify({'message': 'Регистрация успешна'})
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Ошибка регистрации: {e}")
            return jsonify({'error': str(e)}), 500

# --- Вход ---
@app.route('/login', methods=['GET', 'POST'])
async def login():
    if request.method == 'POST':
        data = await request.form
        username = data.get('username').strip()
        password = data.get('password').strip()

        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                select(User).where(User.username == username)
            )
            user = result.scalars().first()

            if not user or user.password != password:
                return jsonify({'error': 'Неверный логин или пароль'}), 401

            session['logged_in'] = True
            session['username'] = user.username
            session.modified = True
            return jsonify({'redirect': '/'})

    return await render_template('login.html')

# --- Основная страница ---
@app.route('/')
async def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return await render_template('index.html')

# --- Выход из аккаунта ---
@app.route('/logout', methods=['POST'])
async def logout():
    session.clear()
    return redirect(url_for('login'))

# --- Получение прогресса ---
@app.route('/progress', methods=['GET'])
async def get_progress():
    if not session.get('logged_in'):
        return jsonify({'error': 'Не авторизован'}), 401

    username = session.get('username')
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(UserProgress).join(User).where(User.username == username)
        )
        progress = result.scalars().first()

        if not progress:
            return jsonify({'error': 'Прогресс не найден'}), 500

        return jsonify({
            'level': progress.level,
            'total_translations': progress.total_translations,
            'points': progress.points,
            'last_active': progress.last_active.isoformat() if progress.last_active else None
        })

# --- Перевод текста ---
@app.route('/translate', methods=['POST'])
async def translate_text():
    if not session.get('logged_in'):
        return jsonify({'translation': '', 'error': 'Не авторизован'}), 401

    data = await request.get_json()
    text = data.get('text', '').strip()
    dest_lang = data.get('dest_lang', 'ru').lower()

    if not text:
        return jsonify({'translation': '', 'error': 'Текст не указан'}), 400

    try:
        username = session.get('username')
        async with AsyncSessionLocal() as db_session:
            # Получение пользователя
            result = await db_session.execute(
                select(User).where(User.username == username)
            )
            user = result.scalars().first()
            if not user:
                return jsonify({'translation': '', 'error': 'Пользователь не найден'}), 404

            # Обнаружение языка
            try:
                source_lang = detect(text)
            except Exception as e:
                logger.warning(f"Не удалось определить язык: {e}")
                source_lang = 'en'

            if source_lang == dest_lang:
                return jsonify({'translation': 'Языки совпадают'})

            # Перевод
            try:
                translator = GoogleTranslator(to_lang=dest_lang)
                translation = translator.translate(text)
                if not translation:
                    raise ValueError("Пустой результат перевода")
            except Exception as e:
                logger.error(f"Ошибка перевода: {e}")
                return jsonify({'translation': '', 'error': 'Ошибка перевода'}), 500

            # Сохранение истории
            history = TranslationHistory(
                user_id=user.id,
                original_text=text,
                translated_text=translation,
                source_lang=source_lang,
                target_lang=dest_lang
            )
            db_session.add(history)
            await db_session.flush()

            # Обновление прогресса
            progress = await db_session.get(UserProgress, user.id)
            if not progress:
                progress = UserProgress(user_id=user.id)
                db_session.add(progress)

            progress.total_translations += 1
            progress.points += 5
            progress.last_active = datetime.now(timezone.utc)
            await db_session.commit()

            return jsonify({
                'translation': translation,
                'source_lang': source_lang,
                'target_lang': dest_lang
            })

    except Exception as e:
        await db_session.rollback()
        logger.error(f"Ошибка перевода: {e}")
        return jsonify({'translation': '', 'error': str(e)}), 500


@app.route('/api/history', methods=['GET'])
async def api_get_history():
    if not session.get('logged_in'):
        return jsonify({'error': 'Не авторизован'}), 401

    username = session.get('username')
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(TranslationHistory)
                .where(TranslationHistory.user_id == User.id)
                .where(User.username == username)
                .where(TranslationHistory.source_lang != TranslationHistory.target_lang)
                .where(TranslationHistory.translated_text != TranslationHistory.original_text)
                .order_by(TranslationHistory.timestamp.desc())
            )
            history = result.scalars().all()

            return jsonify([{
                'original_text': h.original_text.strip('"'),
                'translated_text': h.translated_text.strip('"').rstrip('.'),
                'source_lang': h.source_lang or 'en',
                'target_lang': h.target_lang or 'ru',
                'timestamp': h.timestamp.isoformat() if h.timestamp else '-'
            } for h in history])
        except Exception as e:
            logger.error(f"Ошибка получения истории: {e}")
            return jsonify([])
# --- Сохранение перевода вручную ---
def clean_text(text):
    return text.strip('"').rstrip('.')
@app.route('/save-translation', methods=['POST'])
async def save_translation():
    data = await request.get_json()
    original = clean_text(data.get('original_text', ''))
    translated = clean_text(data.get('translated_text', ''))
    source = data.get('source_lang', 'en')
    target = data.get('target_lang', 'ru')

    if not original or not translated:
        return jsonify({'error': 'Пустой оригинал или перевод'}), 400

    if source == target or original == translated:
        return jsonify({'error': 'Дубликат или одинаковые языки'}), 400

    async with AsyncSessionLocal() as db_session:
        try:
            # Получение пользователя
            result = await db_session.execute(
                select(User).where(User.username == session.get('username'))
            )
            user = result.scalars().first()

            # Сохранение в истории
            history = TranslationHistory(
                user_id=user.id,
                original_text=original,
                translated_text=translated,
                source_lang=source,
                target_lang=target
            )
            db_session.add(history)
            await db_session.flush()

            # Обновление прогресса
            progress = await db_session.get(UserProgress, user.id)
            if not progress:
                progress = UserProgress(user_id=user.id)

            progress.total_translations += 1
            progress.points += 5
            progress.last_active = datetime.now(timezone.utc)
            await db_session.commit()

            return jsonify({'success': True})
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Ошибка сохранения: {e}")
            return jsonify({'error': str(e)}), 500

# --- Получение истории ---
@app.route('/history', methods=['GET'])
async def get_history():
    if not session.get('logged_in'):
        return jsonify({'error': 'Не авторизован'}), 401
    return await render_template('history.html')

    username = session.get('username')
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(TranslationHistory)
                .join(User)
                .where(User.username == username)
                .where(TranslationHistory.source_lang != TranslationHistory.target_lang)
                .where(TranslationHistory.translated_text != TranslationHistory.original_text)
                .order_by(TranslationHistory.timestamp.desc())
            )
            history = result.scalars().all()

            # Добавьте проверку на наличие данных
            if not history:
                return jsonify([])

            return jsonify([{
                'original_text': h.original_text,
                'translated_text': h.translated_text,
                'source_lang': h.source_lang,
                'target_lang': h.target_lang,
                'timestamp': h.timestamp.isoformat()
            } for h in history])

        except Exception as e:
            logger.error(f"Ошибка получения истории: {e}")
            return jsonify([])

# --- Загрузка файлов ---
@app.route('/upload', methods=['POST'])
async def upload_file():
    if not session.get('logged_in'):
        return jsonify({'error': 'Не авторизован'}), 401

    files = await request.files
    file = files.get('file')

    if not file:
        return jsonify({'error': 'Файл не выбран'}), 400

    filename = file.filename.lower()
    try:
        if filename.endswith('.txt'):
            # Обработка .txt с кодировкой utf-8-sig
            content = (await file.read()).decode('utf-8-sig').strip()
        elif filename.endswith('.pdf'):
            # Сохраняем временно, чтобы корректно обработать PDF
            temp_path = f'temp_{file.filename}'
            await file.save(temp_path)
            reader = PyPDF2.PdfReader(temp_path)
            content = '\n'.join(page.extract_text() or '' for page in reader.pages).strip()
            os.remove(temp_path)
        elif filename.endswith(('.doc', '.docx')):
            # Сохраняем временно, чтобы обработать .doc(x)
            temp_path = f'temp_{file.filename}'
            await file.save(temp_path)
            doc = DocxDocument(temp_path)
            content = '\n'.join(p.text for p in doc.paragraphs).strip()
            os.remove(temp_path)
        else:
            return jsonify({'error': 'Формат файла не поддерживается'}), 400

        return jsonify({'text': content})
    except Exception as e:
        logger.error(f"Ошибка чтения файла: {e}")
        return jsonify({'error': f'Ошибка чтения файла: {e}'}), 500

# --- Запуск сервера ---
if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config
    import asyncio

    config = Config()
    config.bind = ["127.0.0.1:5000"]
    try:
        asyncio.run(hypercorn.asyncio.serve(app, config))
    except Exception as e:
        print(f"Ошибка запуска сервера: {e}")
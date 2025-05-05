from quart import Quart, render_template, request, jsonify, session, redirect, url_for
import os
import logging
from langdetect import detect
from translate import Translator as GoogleTranslator
from docx import Document as DocxDocument
import PyPDF2

app = Quart(__name__)
app.secret_key = 'super_secret_key'  # Секретный ключ для сессий
logging.basicConfig(level=logging.INFO)

USERS = {
    "admin": "password123",
    "user": "qwerty"
}


@app.route('/')
async def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return await render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
async def login():
    if request.method == 'POST':
        data = await request.form
        username = data.get('username')
        password = data.get('password')

        if USERS.get(username) == password:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return jsonify({'error': 'Неверный логин или пароль'}), 401
    return await render_template('login.html')


@app.route('/logout', methods=['POST'])
async def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/translate', methods=['POST'])
async def translate_text():
    if not session.get('logged_in'):
        return jsonify({'error': 'Неавторизирован'}), 401

    data = await request.get_json()
    text = data.get('text', '').strip()
    dest_lang = data.get('dest_lang', 'ru').lower()

    if not text:
        return jsonify({'error': 'Текст не указан'}), 400

    try:
        source_lang = detect(text) if text else 'en'
        if source_lang == dest_lang:
            return jsonify({'translation': 'Языки совпадают'})

        translator = GoogleTranslator(to_lang=dest_lang)
        translation = translator.translate(text)
        return jsonify({'translation': translation})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/upload', methods=['POST'])
async def upload_file():
    if not session.get('logged_in'):
        return jsonify({'error': 'Неавторизирован'}), 401

    files = await request.files
    file = files.get('file')

    if not file:
        return jsonify({'error': 'Файл не выбран'}), 400

    filename = file.filename.lower()
    try:
        if filename.endswith('.txt'):
            content = file.read().decode('utf-8-sig').strip()
        elif filename.endswith('.pdf'):
            reader = PyPDF2.PdfReader(file.stream._file)
            content = '\n'.join(page.extract_text() for page in reader.pages).strip()
        elif filename.endswith(('.doc', '.docx')):
            doc = DocxDocument(file.stream._file)
            content = '\n'.join(paragraph.text for paragraph in doc.paragraphs).strip()
        else:
            return jsonify({'error': 'Поддерживаются только .txt, .pdf, .doc(x)'}), 400

        return jsonify({'text': content})
    except Exception as e:
        return jsonify({'error': f'Ошибка чтения файла: {str(e)}'}), 500


if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config
    import asyncio

    config = Config()
    config.bind = ["127.0.0.1:5000"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
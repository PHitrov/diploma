let currentText = '';
let currentTranslation = '';
let currentSourceLang = '';
let currentTargetLang = '';

// --- Функция для декодирования HTML-сущностей ---
function decodeHTMLEntities(text) {
    const textArea = document.createElement('textarea');
    textArea.innerHTML = text;
    return textArea.value.replace(/^"|"$/g, '');
}

// --- Функция для декодирования юникода ---
function decodeUnicode(text) {
    return text.replace(/\\u[\dA-F]{4}/gi, match => {
        return String.fromCharCode(parseInt(match.replace(/\\u/g, ''), 16));
    });
}

// --- Показывает лоадер ---
function showLoader() {
    const loader = document.getElementById('loading');
    if (loader) loader.style.display = 'block';
}

// --- Скрывает лоадер ---
function hideLoader() {
    const loader = document.getElementById('loading');
    if (loader) loader.style.display = 'none';
}

// --- Перевод выделенного текста ---
document.getElementById('text-container').addEventListener('mouseup', async () => {
    const selection = window.getSelection().toString().trim();
    if (!selection) return;

    currentText = selection;
    currentTargetLang = document.getElementById('languageSelect').value;

    try {
        showLoader();
        const response = await fetch('/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: selection, dest_lang: currentTargetLang })
        });

        const data = await response.json();
        if (data.error) {
            alert('Ошибка перевода: ' + data.error);
            return;
        }

        if (data.translation === '') {
            alert('Пустой результат перевода');
            return;
        }

        // Убираем кавычки и точки из перевода
        currentTranslation = decodeHTMLEntities(data.translation);
        currentSourceLang = data.source_lang || 'en';
        currentTargetLang = data.target_lang || 'ru';

        showTranslation(currentTranslation);

    } catch (e) {
        alert('Ошибка сервера при переводе');
        console.error('Ошибка перевода:', e);
    } finally {
        hideLoader();
    }
});

// --- Показать перевод в попапе ---
function showTranslation(translation) {
    const popup = document.getElementById('translationPopup');
    const rect = window.getSelection().getRangeAt(0).getBoundingClientRect();

    popup.style.left = `${rect.left + window.scrollX}px`;
    popup.style.top = `${rect.bottom + window.scrollY + 10}px`;
    popup.style.display = 'block';
    document.getElementById('translationContent').textContent = translation;
}

// --- Сохранить перевод вручную ---
async function saveTranslation() {
    if (!currentText || !currentTranslation) {
        alert('Нет данных для сохранения');
        return;
    }

    if (currentSourceLang === currentTargetLang) {
        alert('Языки совпадают — сохранение не требуется');
        return;
    }

    if (currentTranslation === currentText) {
        alert('Перевод совпадает с оригиналом — сохранение не требуется');
        return;
    }

    try {
        showLoader();
        const response = await fetch('/save-translation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                original_text: currentText,
                translated_text: currentTranslation,
                source_lang: currentSourceLang,
                target_lang: currentTargetLang
            })
        });

        const data = await response.json();
        if (data.success) {
            alert('Перевод сохранён');
            updateProgress();  // Обновление прогресса
            loadHistory();     // Обновление истории
        } else {
            alert('Ошибка сохранения: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (e) {
        alert('Ошибка сервера при сохранении');
        console.error('Ошибка сохранения:', e);
    } finally {
        hideLoader();
        document.getElementById('translationPopup').style.display = 'none';
    }
}

// --- Обновление прогресса ---
async function updateProgress() {
    try {
        const response = await fetch('/progress');
        const data = await response.json();
        document.getElementById('level').textContent = data.level;
        document.getElementById('translates').textContent = data.total_translations;
        document.getElementById('points').textContent = data.points;
        document.getElementById('last-active').textContent = new Date(data.last_active).toLocaleString();
        document.getElementById('progress-fill').style.width = `${data.points % 100}%`;
    } catch (e) {
        console.error('Ошибка обновления прогресса:', e);
    }
}

// --- Загрузка истории переводов ---
async function loadHistory() {
    const table = document.getElementById('history-table');
    if (!table) return;

    try {
        const response = await fetch('/api/history');
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }

        const data = await response.json();
        console.log('Полученные данные:', data); // <<< Отладка

        table.innerHTML = '';
        if (!data.length) {
            table.innerHTML = '<tr><td colspan="5">Нет истории переводов</td></tr>';
            return;
        }

        data.forEach(entry => {
            // Пропуск дубликатов
            if (entry.source_lang === entry.target_lang || entry.original_text === entry.translated_text) return;

            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${decodeHTMLEntities(entry.original_text)}</td>
                <td>${decodeHTMLEntities(entry.translated_text)}</td>
                <td>${entry.source_lang.toUpperCase()}</td>
                <td>${entry.target_lang.toUpperCase()}</td>
                <td>${new Date(entry.timestamp).toLocaleString()}</td>
            `;
            table.appendChild(row);
        });

    } catch (e) {
        console.error('Ошибка загрузки истории:', e);
        table.innerHTML = '<tr><td colspan="5">Ошибка загрузки данных</td></tr>';
    }
}

window.onload = () => {
    console.log('Запрос истории...');
    loadHistory();
};


// --- Выход из аккаунта ---
async function logout() {
    try {
        await fetch('/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        window.location.href = '/login';
    } catch (e) {
        alert('Ошибка выхода');
        window.location.href = '/login';
    }
}
async function loadFile() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) {
        alert('Выберите файл');
        return;
    }

    const allowed = ['txt', 'pdf', 'doc', 'docx'];
    const fileExt = file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(fileExt)) {
        alert('Поддерживаются только .txt, .pdf, .doc(x)');
        return;
    }

    try {
        showLoader();
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        const textContainer = document.getElementById('text-container');

        if (data.text && data.text.trim()) {
            textContainer.textContent = data.text;
        } else {
            alert('Файл пустой или не поддерживается');
            textContainer.textContent = '';
        }
    } catch (e) {
        alert('Ошибка загрузки файла');
        console.error('Ошибка загрузки файла:', e);
    } finally {
        hideLoader();
    }
}
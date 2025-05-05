# Языковой помощник

## Описание
Веб-приложение для перевода текста между английским и русским языками с поддержкой:
- Загрузки файлов (TXT, PDF, DOCX)
- Перевода с автоматическим определением языка
- Озвучивания через Web Speech API

## Тестовые файлы
- `1.txt`: "Я люблю свой дипломный проект"
- `2.txt`: 
  - "Good morning" → "Доброе утро"
  - "Break a leg!" → "Ни пуха ни пера!"
  - "Photosynthesis equation: 6CO₂ + 6H₂O → C₆H₁₂O₆ + 6O₂"

## Зависимости
```bash
pip install quart python-docx PyPDF2 translate langdetect
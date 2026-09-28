# JARVIS Ultimate — объединение трёх проектов

Новый репозиторий строится на проверенной Windows-базе dancorsoodessa-afk/jarvis и переносит совместимые идеи и функции из двух других проектов.

## База dancorsoodessa-afk/jarvis
- Windows GUI и живой 3D A.R.C. Reactor HUD.
- faster-whisper для локального STT и прогрев модели.
- непрерывный голос после активации «Джарвис».
- ElevenLabs + локальный Piper fallback.
- OpenRouter / DeepSeek / GLM маршрутизация fast/reasoning/coding/additional.
- память, граф знаний, Windows-инструменты, файлы и PC-agent workflow.
- готовая Windows x64 сборка через GitHub Actions.

## Что полезного взято из RustamovAkrom/JARVIS
Проект делает упор на модульность, offline-first команды, wake-word, отдельные actions и production installer. Мы сохраняем эти архитектурные принципы, но не делаем Porcupine/Vosk обязательными: текущая цепочка faster-whisper лучше соответствует нашей конфигурации и не требует отдельного wake-word ключа. Источник: RustamovAkrom/JARVIS.

## Что полезного взято из GauravSingh9356/J.A.R.V.I.S
Оригинал содержит OCR, email, новости, todo, сайты, музыку, Wikipedia, словарь, погоду, координаты, YouTube и Google Maps; репозиторий имеет MIT License. В нашей базе большая часть utility-навыков уже реализована в agent/skills.py. Дополнительно добавлены лёгкие OCR и smart_launch без обязательной тяжёлой зависимости. Источник: GauravSingh9356/J.A.R.V.I.S.

## Итог
3D GUI → Voice/STT → Router → Agent/Tools → Memory → TTS.

При интернете JARVIS использует настроенные AI-модели. Без интернета базовые Windows-команды, память и локальные функции продолжают работать.

API-ключи не записываются в GitHub: они вводятся в настройках JARVIS и сохраняются локально.

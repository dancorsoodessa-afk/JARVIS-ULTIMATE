2026-10-10 — аудит сборки (агент Cline)

== Статус CI ==
- origin/main = 335fde4; последний ран build-exe.yml («Build JARVIS для Windows») — completed/success.
- Единственные workflow: .github/workflows/build-exe.yml (push main + dispatch) и build-windows.yml (только workflow_dispatch, ручной фолбэк).
- Оба собирают один артефакт: release/JARVIS.exe из jarvis_desktop.spec.

== Ключевая проблема: Android отсутствует ==
- Папок ui/, android/, pubspec, .dart нет ни в дереве, ни в истории.
- В .github/workflows нет ни одного Android/APK-workflow.
- При этом README.md (раздел «## Android», строки ~239-241) и AGENTS.md (Verification policy, строка 23) описывают Android APK-сборку.
- Вывод: это устаревшие ссылки на прежний «foundation»-проект; текущая база — только Windows. README и AGENTS.md вводят в заблуждение.

== Windows-сборка: всё сходится ==
- build_exe.ps1: pip install -e .[all], затем отдельно pyinstaller pytest faster-whisper huggingface-hub (pytest НЕ попадает в пакет через extras — доустановка строкой 8 обязательна).
- Скачивает Systran/faster-whisper-base -> vendor/stt_model и Piper + голос ru_RU-dmitri-medium -> vendor/piper (с ретраями на 429).
- Прогоняет pytest, потом pyinstaller jarvis_desktop.spec -> dist/jarvis_desktop.exe -> release/JARVIS.exe (+ README.txt).
- vendor/ создается только в CI, локально его нет; jarvis_desktop.spec ссылается на vendor/stt_model и vendor/piper — локальная сборка без предварительного скачивания упадет.

== Мелкие найденные расхождения (не критичны) ==
- README.md:236 говорит, что UI пакетируется как «JARVIS-Desktop.exe», но фактическое имя артефакта — JARVIS.exe.
- install_autostart.ps1 по умолчанию ищет dist/jarvis.exe, а build кладет dist/jarvis_desktop.exe (и копирует в release/JARVIS.exe). Значение по умолчанию неверно; работает только через явный -ExePath.
- jarvis.spec (CLI) существует, но build_exe.ps1 его не собирает — собирает только jarvis_desktop.spec. CLI-спека не используется текущей сборкой.

== Безопасность ==
- jarvis.log в рабочей папке не отслеживается git (*.log в .gitignore); ключей в истории нет. API-ключи в README только как плейсхолдеры.

== Тесты ==
- Тестов для сборки/спек/workflow нет вообще (19 test_*.py — только юнит-тесты агента). Полный сьют зеленый: 128 passed, 2 skipped.

== Локальное состояние на момент аудита ==
- HEAD локально выше origin/main на 2 коммита: e845dd6 (docs, Windows build artifact) и 2b9d31e (fix порядка проверок в agent/stt.py transcribe).
- .claude/, .continue/, CLAUDE.md, copilot-инструкции — untracked, не коммитить (per AGENTS.md).
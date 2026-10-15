2026-10-10 — аудит сборки (агент Cline)
Обновлено 2026-10-15: см. секцию «Итоги после аудита» внизу.

== Статус CI (на 2026-10-10) ==
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

== Мелкие найденные расхождения (не критичны; исправлены 2026-10-15, коммит 00a8727) ==
- README.md:236 говорил, что UI пакетируется как «JARVIS-Desktop.exe», но фактическое имя артефакта — JARVIS.exe. ИСПРАВЛЕНО.
- install_autostart.ps1 по умолчанию искал dist/jarvis.exe, а build кладет dist/jarvis_desktop.exe (и копирует в release/JARVIS.exe). ИСПРАВЛЕНО: по умолчанию release\JARVIS.exe.
- jarvis.spec (CLI) существует, но build_exe.ps1 его не собирает — собирает только jarvis_desktop.spec. CLI-спека не используется текущей сборкой. РЕШЕНИЕ: оставлена как ручная CLI-спека; покрыта контрактным тестом (tests/test_build_contract.py), удалена не была.

== Безопасность ==
- jarvis.log в рабочей папке не отслеживается git (*.log в .gitignore); ключей в истории нет. API-ключи в README только как плейсхолдеры.

== Тесты ==
- Тестов для сборки/спек/workflow нет вообще (19 test_*.py — только юнит-тесты агента). Полный сьют зеленый: 128 passed, 2 skipped.

== Локальное состояние на момент аудита ==
- HEAD локально выше origin/main на 2 коммита: e845dd6 (docs, Windows build artifact) и 2b9d31e (fix порядка проверок в agent/stt.py transcribe).
- .claude/, .continue/, CLAUDE.md, copilot-инструкции — untracked, не коммитить (per AGENTS.md).
== Итоги после аудита (2026-10-15) ==
Все найденные проблемы устранены; origin/main = 32675a3, оба последних рана build-exe.yml — completed/success, артефакт JARVIS-Windows-x64 (316 МБ) опубликован.
- Android-ссылки в README.md и AGENTS.md исправлены (коммит 00a8727): Android/Flutter-сборки в проекте нет.
- install_autostart.ps1 и README исправлены (00a8727).
- Добавлен tests/test_build_contract.py (7 smoke-тестов согласованности сборки: workflows, build_exe.ps1, обе спеки, .gitignore).
- vendor/ и release/ добавлены в .gitignore (сборка создает их локально, коммитить нельзя).
- 32675a3: чистка мертвого кода по итогам pyflakes (двойной вызов adb devices -l в android_app_diagnostics, бессмысленный file-handle в _speak_piper, мертвые импорты/переменные).
- Тестовый сьют: 135 passed, 2 skipped (posix-only).
- Локальное состояние: .claude/, .continue/, CLAUDE.md, copilot-инструкции — untracked, не коммитить (per AGENTS.md).

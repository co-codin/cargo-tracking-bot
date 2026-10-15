# Бот статистики CarGoRuqsat (FastAPI + Telegram)

Парсит страницу https://cgr.qoldau.kz/ru/information/stat, отвечает статистикой в Telegram и отдаёт её по HTTP API в JSON. Работает под uvicorn; бот запускается внутри FastAPI (webhook или long polling).

## Структура
```
app/
  main.py              FastAPI, lifespan: запуск бота (webhook / polling), маршрут webhook
  config.py            настройки (pydantic-settings, переменные окружения / .env)
  api/routes.py        GET /health, /api/stats, /api/posts, /api/posts/{name}
  bot/application.py   сборка python-telegram-bot Application
  bot/handlers/        commands.py, callbacks.py, inline.py, text.py, common.py
  bot/keyboards.py     инлайн-клавиатуры
  bot/formatters.py    тексты ответов (HTML)
  services/parser.py   разбор HTML страницы
  services/cache.py    кэш: Redis (single-flight, устаревшие данные) или память
  services/matching.py нечёткий поиск пунктов пропуска
tests/                 pytest: поиск, API, кэш
```

## Запуск в Docker (рекомендуется)
```bash
cp .env.example .env      # впишите TELEGRAM_BOT_TOKEN
chmod 600 .env
docker compose up -d --build
docker compose ps         # оба контейнера должны быть healthy
curl http://127.0.0.1:8000/health
docker compose logs -f bot
```
Контейнеры: `bot` (uvicorn, порт `127.0.0.1:8000`, непривилегированный пользователь) и `redis` (redis:7-alpine, AOF на томе `redis-data`, порт наружу не публикуется).
Одновременно получать обновления может только один экземпляр бота — перед запуском остановите другие копии.

## Локальный запуск без Docker
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="123456:ABC..."   # не добавляйте токен в репозиторий
export REDIS_URL=redis://localhost:6379/0   # необязательно
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Переменные окружения
| Переменная | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | токен от @BotFather; без него работает только HTTP API |
| `WEBHOOK_URL` | пусто | публичный HTTPS-адрес (например `https://bot.example.com`); если задан — webhook на `/telegram/webhook/{WEBHOOK_SECRET}`, иначе long polling |
| `WEBHOOK_SECRET` | случайный | секрет в пути webhook и в заголовке `X-Telegram-Bot-Api-Secret-Token` |
| `REDIS_URL` | пусто | адрес Redis; без него или при недоступности Redis — кэш в памяти |
| `CACHE_TTL` | `300` | время жизни кэша, сек |
| `CACHE_LOG_LEVEL` | `INFO` | `DEBUG` — логировать попадания/промахи кэша |
| `LOG_LEVEL` | `INFO` | уровень логов |
| `RUN_BOT` | `true` | `false` — запустить только API |

## HTTP API
- `GET /health` — `{"status":"ok","bot":"polling|webhook|disabled","redis":"ok|unavailable"}`
- `GET /api/stats` — сводка (пользователи, бронирования, платежи по годам, реестр)
- `GET /api/posts` — все пункты пропуска: сегодня и сумма свободных мест
- `GET /api/posts/{name}` — один пункт (нечёткий поиск, как в боте); 404 с подсказками, если не найден
- `/docs` — Swagger UI

## Кэширование
Данные хранятся в Redis как JSON (`cgr:stat:data`, TTL = `CACHE_TTL`). Блокировка `cgr:stat:lock` не даёт скачивать сайт параллельно. Последние успешные данные лежат в `cgr:stat:stale` без TTL: если сайт недоступен, бот отдаёт их с пометкой, что данные могут быть устаревшими.

## Поиск и инлайн-режим
Поиск понимает части названия, опечатки, латиницу и английскую раскладку (`ljcnsr` → «достык»). Обычный текст в личном чате = `/post <текст>`.
Инлайн-режим (`@имя_бота хоргос` в любом чате) включается только вручную в @BotFather: `/setinline` → выбрать бота → задать подсказку. При старте бот пишет в лог предупреждение, если он выключен.

## Тесты
```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q tests   # образец страницы: tests/fixtures/stat.html (можно переопределить STAT_HTML)
```

## Парсер отдельно
```bash
python -m app.services.parser            # живая страница
python -m app.services.parser stat.html  # локальная копия
```

## Ограничения
- Суммы оплаты по размеру платежа (1/20/100 МРП) доступны только через POST-форму сайта с защитой от подделки запросов; бот показывает общую сумму.
- Свободные места сайт показывает только за 1 и 100 МРП.

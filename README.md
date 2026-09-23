# Аким на 5 часов

Симулятор городского управления. Игрок выбирает ровно 5 мер при бюджете 100. Числа считает детерминированный движок. LLM только объясняет уже посчитанный JSON и не участвует в Score.

## Архитектура

- `backend/app/data/dataset.json` — единственный источник районов, мер, весов, синергий и запретов. Лишних районов нет.
- `backend/app/engine/validate.py` — правила набора. Невалидный план не получает Score, только список `{code, message}`.
- `backend/app/engine/score.py` — чистая арифметика: доля эффекта `(8 − L) / 8`, фиксированные синергии без лага, обрезка показателей в `[0, 100]`, затем

  `Score = 0.7 × D_avg + 0.3 × min(D_d) − N_crit`

  Остаток бюджета на Score не влияет.
- `POST /simulate` вызывает только этот код.
- `POST /explain` отправляет готовый JSON в OpenAI-совместимый `/chat/completions`. Модель не пересчитывает метрики.

## Запуск

Нужен Python 3.11+.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Интерфейс: http://127.0.0.1:5173 (проксирует `/api` на порт 8000).

Для кнопки «Объяснить» скопируйте `.env.example` в `.env` в корне репозитория и задайте `OPENAI_API_KEY`. Модель берётся из `OPENAI_MODEL`, адрес API — из `OPENAI_BASE_URL`.

## Золотой тест

```bash
cd backend
pytest
```

Пустой план: Score **52.56** (`0.7 × 56.86 + 0.3 × 49.18 − 2`). Две критические ячейки — S1 и S2 в Нуре. Значение ровно 40 критическим не считается.

Пример из датасета (стоимость 95):

| Мера | Район |
| --- | --- |
| M7 | nura |
| M8 | nura |
| M10 | nura |
| M12 | город |
| M5 | saryarka |

Движок даёт Score **56.54** (сырое значение 56.5431, допуск к 56.5 — 0.05), `N_crit = 0`, синергия M10+M12 добавляет B1 +2 в Нуре и лагом не масштабируется. Дельта к базе в API: **+3.98**.

```bash
curl -s http://127.0.0.1:8000/simulate \
  -H 'Content-Type: application/json' \
  -d '{"decisions":[
    {"measure_id":"M7","district":"nura"},
    {"measure_id":"M8","district":"nura"},
    {"measure_id":"M10","district":"nura"},
    {"measure_id":"M12","district":null},
    {"measure_id":"M5","district":"saryarka"}
  ]}'
```

В ответе `valid=true`, `cost=95`, `baseline_score=52.56`, `score=56.54`, `synergies_applied[0].district="nura"`.

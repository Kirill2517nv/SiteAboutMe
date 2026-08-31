# Перенос банка задач ЕГЭ на прод

Что переносим и чем именно. Порядок шагов важен: медиа – до `load_ege`,
пулы – после.

## Что везём

| Артефакт | Где | Объём | Чем везём |
|---|---|---|---|
| Код тренажёра | ветка с миграциями `quizzes 0035+` | – | `git push` / `git pull` |
| Банки задач | `fixtures/bank-*.json`, 23 файла (без `bank-27.json`) | 750 задач | `scp`, файлы в `.gitignore` |
| Медиа банков | `media/ege/bank-*/` | 315 МБ (из них `bank-24/files` – 250 МБ) | `rsync` |
| Пулы и настройки заданий | `fixtures/ege-pools.json` | 118 «в классе», 114 «в экзамене», 27 заданий | `scp` |

Варианты (`quiz_type='exam'`) не трогаем: на проде их шесть, локально два –
это разные наборы, и переезд банка их не касается.

## Состояние на 2026-08-31

* **Прод** – миграции `quizzes 0034` / `textbook 0007`: тренажёра там ещё нет,
  банков ноль, `EgeTask` ноль. Ученические данные живые: 15 721 `UserAnswer`,
  2 637 `CodeSubmission` – их ничто в этом переносе не трогает.
* **Дев** – 23 банка, 750 задач. `bank-27.json` лежит в фикстурах, но в дев-базу
  не загружен и на прод **не едет**: пулы по заданию 27 ещё не размечены, а везти
  банк без разметки – это отдать все 30 задач в тренировку. Банка задания 23 нет
  ни в базе, ни в фикстурах: задание останется на карте с пустым пулом.
* Задание 17 в дев-базе было 33 задачи: три из них (`kompege-17-000001`,
  `kompege-17-000002`, `kompege-17-000099`) заводились вручную при отладке
  загрузчика. **В `bank-17.json` их нет**, поэтому на прод они бы не поехали
  и так; из дев-базы они удалены 2026-08-31 вместе с 25 отладочными
  `PracticeItem` и осиротевшим `media/ege/bank-17/files/17_1.txt`, чтобы дев
  и прод показывали по заданию 17 одно и то же число.

## Почему нужен `ege_pools`, а не только json

Сверка дев-базы с `fixtures/bank-*.json` по `external_id`: `difficulty`,
`points`, `title`, `topic`, `correct_text_answer` совпадают у всех 750 задач –
json полностью описывает задачу как она пришла от парсера.

Чего в json нет и что живёт только в базе:

* `Question.classroom_only` / `exam_only` – в какой пул учитель положил задачу;
* `EgeTask.exam_size` / `exam_unlock_threshold` / `classroom_enabled`.

Это решения, принятые в приложении, а не вывод парсера, поэтому они и не в
`bank-*.json`: следующая перепарсовка банка их бы стёрла. Их снимает и
накатывает `python manage.py ege_pools`, связка – по `external_id`.

## Порядок выкатки

```bash
# 1. На деве: снять актуальные пулы (файл уже выгружен, но лишний раз не мешает)
python manage.py ege_pools --dump fixtures/ege-pools.json

# 2. Залить фикстуры и медиа. Медиа – строго до load_ege:
#    load_ege создаёт QuestionFile/QuestionImage по путям из json,
#    и без файлов на диске в банке окажутся битые ссылки.
rsync -avz --exclude 'bank-27' --exclude 'bank-23' -e "ssh -p 2222" \
      media/ege/bank-* admin@192.168.1.199:/home/admin/site/media/ege/
scp -P 2222 $(ls fixtures/bank-*.json | grep -v bank-27) fixtures/ege-pools.json \
      admin@192.168.1.199:/home/admin/site/fixtures/

# 3. На проде: код и схема
ssh admin@192.168.1.199 -p 2222
cd /home/admin/site && git pull && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate

# 4. Справочник заданий 1–27 (без него ege_pools не к чему применять)
python manage.py seed_ege_tasks

# 5. Банки. Порядок между файлами не важен, дедуп идёт по external_id
for f in fixtures/bank-*.json; do python manage.py load_ege "$f"; done

# 6. Пулы и настройки заданий
python manage.py ege_pools --load fixtures/ege-pools.json --dry-run
python manage.py ege_pools --load fixtures/ege-pools.json

# 7. Статика и перезапуск
python manage.py collectstatic --noinput
sudo systemctl restart site celery celerybeat daphne
```

## Проверка после

```bash
python manage.py shell -c "
from quizzes.models import Question
b = Question.objects.filter(quiz__quiz_type='bank')
print(b.count(), b.filter(classroom_only=True).count(), b.filter(exam_only=True).count())
"
```

Должно совпасть с девом: `750 118 114`.

Повторный `ege_pools --load` ничего не меняет – это полная синхронизация
состояния, а не доливка: задача, которой нет в списках файла, оба флага теряет.
Так и задумано, иначе снятая учителем пометка «в классе» жила бы вечно.

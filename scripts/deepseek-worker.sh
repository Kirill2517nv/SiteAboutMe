#!/usr/bin/env bash
# Воркер на DeepSeek: выполняет рутинную задачу в репозитории через
# Anthropic-совместимый эндпоинт DeepSeek. Оркестратор (Claude) ставит задачу,
# проверяет результат через git diff.
#
# Использование: scripts/deepseek-worker.sh "текст задания"
#         или:   scripts/deepseek-worker.sh -f задание.txt
set -euo pipefail

# Ключ из окружения, иначе из файла: setx виден только новым процессам,
# а файл читается уже запущенной сессией.
key="${DEEPSEEK_API_KEY:-$(cat ~/.deepseek_key 2>/dev/null || true)}"
: "${key:?нет ключа: ни DEEPSEEK_API_KEY, ни ~/.deepseek_key}"

if [[ "${1:-}" == "-f" ]]; then
    task="$(cat "$2")"
else
    task="${1:?не передано задание}"
fi

# Воркеру намеренно не выдан Bash: сборку и запуск тестов делает оркестратор.
ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic" \
ANTHROPIC_AUTH_TOKEN="$key" \
ANTHROPIC_API_KEY="$key" \
claude -p "$task" \
    --model "deepseek-flash[1m]" \
    --permission-mode acceptEdits \
    --strict-mcp-config \
    --allowed-tools Read Write Edit Glob Grep

# Песочница для решений на C++: компилятор и раннер в одном образе.
# Раннер (runner_cpp.py) написан на Python, поэтому база – тот же
# python:3.11-slim, что и у песочницы Python; g++ добавляет ~200 МБ
# (официальный gcc:13 весит 1,2 ГБ).
#
# Сборка (на dev и на проде, после изменения этого файла):
#   docker build -t site-sandbox-cpp docker/sandbox-cpp
FROM python:3.11-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*

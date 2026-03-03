FROM python:3.11-slim

WORKDIR /app

# 🔥 关键优化：先装系统依赖（加速）
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 🔥 关键优化：关闭 pip 缓存 + 提前编译
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080

# 🔥 关键：使用 exec 形式 + workers=1
CMD exec uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1

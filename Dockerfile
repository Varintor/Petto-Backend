FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.lock ./

# --- แก้ไขบรรทัดนี้: เพิ่ม --default-timeout=1000 เข้าไป ---
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.lock

COPY . .

# --- คำสั่งรัน FastAPI (ใช้ shell form เพื่อรองรับ $PORT) ---
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

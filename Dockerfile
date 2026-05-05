FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# --- แก้ไขบรรทัดนี้: เพิ่ม --default-timeout=1000 เข้าไป ---
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

COPY . .
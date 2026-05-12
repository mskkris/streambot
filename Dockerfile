FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY stream_bot.py .

CMD ["python", "stream_bot.py"]

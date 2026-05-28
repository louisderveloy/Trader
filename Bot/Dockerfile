FROM python:3.14-slim

# Force python to flush the out
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

ENTRYPOINT [ "python", "/app/main.py" ]
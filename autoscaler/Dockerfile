FROM python:3.11-slim

WORKDIR /service

COPY requirements-base.txt /requirements-base.txt
COPY autoscaler/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY autoscaler/ .

CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8001"]
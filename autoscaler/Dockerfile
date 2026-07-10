FROM python:3.11-slim
WORKDIR /autoscaler
COPY . /autoscaler
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "main.py"]

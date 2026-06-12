FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the api/ package into /app/api so that 'from api.xxx import yyy' resolves correctly.
COPY . /app/api/

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

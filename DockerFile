# Use official Python slim image — smaller than full Python image
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements first — Docker caches this layer
# If requirements don't change, Docker won't reinstall on every build
COPY service/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the service code
COPY service/ .

# Default command — runs the API
# Worker overrides this in docker-compose.yml
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
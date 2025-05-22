# Use Python base image
FROM python:3.13-slim

# Install system dependencies (incl. poppler)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    build-essential \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy project
COPY . /app/

# Install Python packages
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Collect static files (optional for prod)
RUN mkdir -p /vol/web/media

# Run Django dev server (for now)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

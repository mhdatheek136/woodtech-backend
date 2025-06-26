FROM python:3.13-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    poppler-utils \
    build-essential \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Work directory
WORKDIR /app

# Copy code
COPY . /app/

# Install Python deps
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Collect static files (optional)
# RUN mkdir -p /vol/web/media  # DEV
# RUN python manage.py collectstatic --noinput  

# Expose port
EXPOSE 8000

# Run Gunicorn in prod or Django server in dev
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
# For production: 
# CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000"]
CMD ["sh", "-c", "python manage.py collectstatic --noinput && gunicorn backend.wsgi:application --bind 0.0.0.0:8000"]



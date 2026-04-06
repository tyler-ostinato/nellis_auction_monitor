# Use specific Playwright version to match system requirements
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create data and logs directories
RUN mkdir -p data logs

# Run the application
CMD ["python", "-m", "app.main"]

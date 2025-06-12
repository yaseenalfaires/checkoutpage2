FROM python:3.11-slim

# Install system dependencies for Chromium
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    fonts-liberation libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libx11-xcb1 libxcb-dri3-0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libxshmfence1 libxss1 \
    libxext6 libxfixes3 libglib2.0-0 libgtk-3-0 xvfb && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and download browsers
RUN pip install playwright && playwright install chromium

# Copy the entire project code
COPY . .

# Run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

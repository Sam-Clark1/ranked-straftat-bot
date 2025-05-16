# 1. Base image
FROM python:3.11-slim

# 2. Set working directory inside the container
WORKDIR /app

# 3. Install any OS-level build tools
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# 4. Copy only requirements first
COPY requirements.txt .

# 5. Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy code into the container
COPY . .

# 7. Default command: start the bot
CMD ["python", "__main__.py"]

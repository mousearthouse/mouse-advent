# Use the official Python image as a base
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pyTelegramBotAPI schedule

# Copy the rest of the application files into the container
COPY . .

# Set the default command to run the bot
CMD ["python", "pipi.py"]

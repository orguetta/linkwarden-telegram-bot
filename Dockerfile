FROM python:3.13.7-alpine

# Set the working directory
WORKDIR /app

# Copy requirements.txt if you have one
COPY requirements.txt .

# Upgrade pip and setuptools, then install dependencies
RUN pip install --upgrade pip setuptools && pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY bot.py .

# Start the bot
CMD ["python", "bot.py"]

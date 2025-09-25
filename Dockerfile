# Stage 1: Build stage
FROM python:3.11.7 AS builder

# Set the working directory
WORKDIR /usr/src/app

# Copy only the requirements file first to leverage Docker caching
COPY requirements.txt ./

# Install virtualenv
RUN pip install --no-cache-dir virtualenv
RUN pip install --upgrade pip setuptools wheel

# Create a virtual environment
RUN virtualenv venv

# Install dependencies in the virtual environment
RUN ./venv/bin/pip install --no-cache-dir -r requirements.txt

# Install Uvicorn in the virtual environment
RUN ./venv/bin/pip install uvicorn

# Check if Uvicorn is installed using Python
RUN ./venv/bin/python -c "import uvicorn; print(uvicorn.__version__)"

# Copy the rest of the application code
COPY . .

# Apply migrations (optional, depends on your application needs)
RUN ./venv/bin/python manage.py migrate

# Stage 2: Production stage
FROM python:3.11.7 AS runtime

# Set the working directory
WORKDIR /usr/src/app

# Copy the virtual environment and necessary files from the builder stage
COPY --from=builder /usr/src/app /usr/src/app

# Ensure that the virtual environment's bin directory is in the PATH
ENV PATH="/usr/src/app/venv/bin:${PATH}"

# Expose the port the app runs on
EXPOSE 4052

# Start the application with Uvicorn (with WSGI support and SSL)
CMD ["uvicorn", "--wsgi", "--factory", "ai_powered_phr.wsgi:application", "--host", "0.0.0.0", "--port", "4052", "--ssl-certfile", "/cert/carecloud.pem", "--ssl-keyfile", "/cert/carecloud.key", "--log-level", "debug"]
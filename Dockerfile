FROM --platform=linux/amd64 rocker/r-ver:4.3.0

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install R packages
RUN Rscript -e "install.packages(c('anomalize', 'tibble', 'dplyr', 'jsonlite', 'readr'), repos='https://cran.r-project.org')"

# Copy and install Python packages
COPY requirements-docker.txt .
RUN pip3 install --upgrade pip && pip3 install -r requirements-docker.txt

# Copy project files
COPY . /app
WORKDIR /app

EXPOSE 8501

CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]

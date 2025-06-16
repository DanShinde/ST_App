# FROM python:3.11-slim

# # 1) Install ODBC libraries + build tools
# RUN apt-get update && \
#     apt-get install -y --no-install-recommends \
#       unixodbc \
#       unixodbc-dev \
#       gcc \
#       g++ && \
#     rm -rf /var/lib/apt/lists/*

# # 2) Copy requirements & install Python deps
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# # 3) Copy your app code
# COPY . .

# EXPOSE 8501
# CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
FROM python:3.11-slim

ENV ACCEPT_EULA=Y
# install FreeTDS and dependencies
RUN apt-get update \
 && apt-get install unixodbc -y \
 && apt-get install unixodbc-dev -y \
 && apt-get install freetds-dev -y \
 && apt-get install freetds-bin -y \
 && apt-get install tdsodbc -y \
 && apt-get install --reinstall build-essential -y

# populate "ocbcinst.ini"
RUN echo "[FreeTDS]\n\
Description = FreeTDS unixODBC Driver\n\
Driver = /usr/lib/x86_64-linux-gnu/odbc/libtdsodbc.so\n\
Setup = /usr/lib/x86_64-linux-gnu/odbc/libtdsS.so" >> /etc/odbcinst.ini

# 1) Install Microsoft ODBC 17 + unixODBC + build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gnupg \
      apt-transport-https && \
    \
    # Add MS package keyring
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor \
      > /usr/share/keyrings/microsoft-archive-keyring.gpg && \
    \
    # Add the MS repo signed by that key
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-archive-keyring.gpg] \
      https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/mssql-release.list && \
    \
    # Install ODBC driver, unixODBC & build tools
    apt-get update && \
    apt-get install -y --no-install-recommends \
      msodbcsql17 \
      unixodbc \
      unixodbc-dev \
      gcc \
      g++ && \
    rm -rf /var/lib/apt/lists/*

# 2) Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Your app
COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]

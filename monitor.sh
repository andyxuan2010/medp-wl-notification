#!/bin/bash

# === Configuration ===
REPO_URL="https://github.com/andyxuan2010/medp-wl-notification.git"
WORK_DIR="$HOME/shared/scripts/medp-wl-notification"
PYTHON_BIN=$(which python3)
CRON_TIME="*/10 * * * *"

echo "📦 Creating working directory: $WORK_DIR"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR" || exit 1

echo "⬇️ Cloning GitHub repository..."
if [ -d ".git" ]; then
    echo "✅ Repository already exists. Running git pull to update."
    git pull
else
    #git clone "$REPO_URL" .
    git init
    git remote add origin $REPO_URL
    git fetch
    git checkout -t origin/main
fi

echo "🐍 Checking/Creating Python virtual environment..."
if [ ! -d "venv" ]; then
    $PYTHON_BIN -m venv venv
fi

echo "✅ Activating virtual environment and installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# === Create .env file if missing ===
if [ ! -f ".env" ]; then
  echo "⚠️ .env file not found. Creating with default values for Videotron setup..."
  cat <<EOF > .env
EMAIL_SENDER=your_email@videotron.ca
EMAIL_PASSWORD=
SMTP_SERVER=relais.videotron.ca
SMTP_PORT=25
USE_AUTH=False
DEFAULT_RECIPIENTS_FILE=.recipients
EOF
  echo "✅ .env file created. You can edit it manually to change settings."
else
  echo "✅ .env file already exists."
fi

echo "🚀 Running monitor.py once for testing..."
python monitor.py

echo "⏰ Adding cron job (if not already added)..."
CRON_JOB="$CRON_TIME cd $WORK_DIR && chmod +x monitor.sh && /bin/bash monitor.sh >> monitor_cron.log 2>&1"

# Check if cron job already exists
(crontab -l 2>/dev/null | grep -F "monitor.sh") >/dev/null
if [ $? -ne 0 ]; then
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✅ Cron job added: $CRON_JOB"
else
    echo "🔁 Cron job already exists. Skipping addition."
fi

echo "🎉 Setup complete! Daily monitoring is active. Logs will be saved in monitor_cron.log."
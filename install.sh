#!/bin/bash

# Django Panel Installation Script for Debian 12
# Usage: curl -sL https://github.com/your-repo/install.sh | bash

set -e

GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Django VPS Panel Installation...${NC}"

# 1. System Updates & Dependencies
echo "Updating system packages..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip python3-full nginx git acl libpq-dev

# Stop Apache2 if it exists (common conflict on VPS)
if systemctl is-active --quiet apache2; then
    echo "Apache2 detected. Stopping and disabling Apache2 to free up Port 80..."
    sudo systemctl stop apache2
    sudo systemctl disable apache2
fi

# 2. Setup User & Directory
INSTALL_DIR="$HOME/djangoPanel"

# Check if we are already in the project directory (e.g. uploaded manually)
if [ -f "manage.py" ]; then
    INSTALL_DIR=$(pwd)
    echo "Files detected in current directory. Installing in $INSTALL_DIR"
else
    # Ask for Repo URL if not found
    if [ -d "$INSTALL_DIR" ]; then
        echo "Directory $INSTALL_DIR already exists."
        read -p "Do you want to update it? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cd "$INSTALL_DIR"
            git pull
        fi
    else
        echo "Please paste your Git Repository URL (e.g. https://github.com/user/repo.git):"
        read REPO_URL
        if [ -z "$REPO_URL" ]; then
            echo "Error: Repository URL is required."
            exit 1
        fi
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
fi

cd "$INSTALL_DIR"

# 3. Virtual Environment
echo "Setting up Virtual Environment..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Django Setup
echo "Running Migrations..."
python manage.py migrate
python manage.py collectstatic --noinput

# Create Superuser
echo "Would you like to create a superuser now? (Recommended for admin access)"
read -p "Create superuser? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python manage.py createsuperuser
fi

# 5. Gunicorn Systemd Service
echo "Configuring Systemd..."
cat <<EOF | sudo tee /etc/systemd/system/djangopanel.service
[Unit]
Description=Django Panel Daemon
After=network.target

[Service]
User=$USER
Group=www-data
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 config.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable djangopanel
sudo systemctl restart djangopanel

# 6. Nginx Setup
echo "Configuring Nginx..."
cat <<EOF | sudo tee /etc/nginx/sites-available/djangopanel
server {
    listen 80;
    server_name _;  # Listen on all IPs, or set your domain here

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static/ {
        alias /var/www/djangopanel/static/;
    }
}
EOF

# Ensure static directory permissions
echo "Fixing static files permissions..."
sudo mkdir -p /var/www/djangopanel/static
# Run collectstatic again to populate the new path (settings.py now points there)
python manage.py collectstatic --noinput
# Give ownership to www-data (Nginx user) just in case, or make world readable
sudo chown -R www-data:www-data /var/www/djangopanel/static
sudo chmod -R 755 /var/www/djangopanel/static

# Remove default Nginx site if it exists to avoid conflicts
if [ -f /etc/nginx/sites-enabled/default ]; then
    echo "Removing default Nginx site configuration..."
    sudo rm /etc/nginx/sites-enabled/default
fi

sudo ln -sf /etc/nginx/sites-available/djangopanel /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

echo -e "${GREEN}Installation Complete! Your panel should be accessible at http://<YOUR_VPS_IP>${NC}"

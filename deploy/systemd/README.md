# Systemd Deployment (Linux)

## Installation

### 1. Create system user

```bash
sudo useradd -r -s /bin/false -d /opt/whitemirror whitemirror
```

### 2. Install the service agent

```bash
# Create directories
sudo mkdir -p /opt/whitemirror/service-agent
sudo mkdir -p /var/log/whitemirror

# Copy files
sudo cp -r . /opt/whitemirror/service-agent/
sudo chown -R whitemirror:whitemirror /opt/whitemirror
sudo chown -R whitemirror:whitemirror /var/log/whitemirror

# Create virtual environment
cd /opt/whitemirror/service-agent
sudo -u whitemirror python3 -m venv venv
sudo -u whitemirror venv/bin/pip install -r requirements.txt
```

### 3. Configure

```bash
# Copy and edit configuration
sudo cp config.yaml.example config.yaml
sudo nano config.yaml
```

### 4. Install systemd service

```bash
# Copy service file
sudo cp deploy/systemd/service-agent.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start
sudo systemctl enable service-agent
sudo systemctl start service-agent
```

## Management

```bash
# Check status
sudo systemctl status service-agent

# View logs
sudo journalctl -u service-agent -f

# Restart
sudo systemctl restart service-agent

# Stop
sudo systemctl stop service-agent
```

## Troubleshooting

### Check logs
```bash
sudo journalctl -u service-agent --since "10 minutes ago"
```

### Check permissions
```bash
ls -la /opt/whitemirror/service-agent/
```

### Test manual run
```bash
sudo -u whitemirror /opt/whitemirror/service-agent/venv/bin/python /opt/whitemirror/service-agent/main.py
```

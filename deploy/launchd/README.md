# launchd Deployment (macOS)

## Installation

### 1. Install the service agent

```bash
# Create directories
sudo mkdir -p /usr/local/whitemirror/service-agent
sudo mkdir -p /usr/local/whitemirror/service-agent/logs

# Copy files
sudo cp -r . /usr/local/whitemirror/service-agent/

# Create virtual environment
cd /usr/local/whitemirror/service-agent
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Set permissions
sudo chown -R $(whoami) /usr/local/whitemirror
```

### 2. Configure

```bash
# Copy and edit configuration
cp config.yaml.example config.yaml
nano config.yaml
```

### 3. Install launchd service

#### As User Agent (runs when user logs in)
```bash
cp deploy/launchd/com.whitemirror.service-agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.whitemirror.service-agent.plist
```

#### As System Daemon (runs at boot, requires root)
```bash
sudo cp deploy/launchd/com.whitemirror.service-agent.plist /Library/LaunchDaemons/
sudo launchctl load /Library/LaunchDaemons/com.whitemirror.service-agent.plist
```

## Management

### Check status
```bash
# User agent
launchctl list | grep whitemirror

# System daemon
sudo launchctl list | grep whitemirror
```

### View logs
```bash
tail -f /usr/local/whitemirror/service-agent/logs/stdout.log
tail -f /usr/local/whitemirror/service-agent/logs/stderr.log
```

### Restart
```bash
# User agent
launchctl stop com.whitemirror.service-agent
launchctl start com.whitemirror.service-agent

# System daemon
sudo launchctl stop com.whitemirror.service-agent
sudo launchctl start com.whitemirror.service-agent
```

### Unload (stop and disable)
```bash
# User agent
launchctl unload ~/Library/LaunchAgents/com.whitemirror.service-agent.plist

# System daemon
sudo launchctl unload /Library/LaunchDaemons/com.whitemirror.service-agent.plist
```

## Troubleshooting

### Check if running
```bash
ps aux | grep service-agent
lsof -i :9100
```

### Debug launch issues
```bash
launchctl debug com.whitemirror.service-agent --stdout --stderr
```

### Manual test run
```bash
cd /usr/local/whitemirror/service-agent
./venv/bin/python main.py
```

## Log Rotation

Add to `/etc/newsyslog.d/whitemirror.conf`:

```
/usr/local/whitemirror/service-agent/logs/stdout.log   644  7     1000  *     J
/usr/local/whitemirror/service-agent/logs/stderr.log   644  7     1000  *     J
```

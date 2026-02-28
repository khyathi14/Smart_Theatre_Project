# Smart Theatre Monitoring System

## Strict Single Flow: Generate → SQS → Lambda → SQLite → Dashboard

### End-to-end sequence (everything goes through SQS and Lambda)

1. **generate_sensors.py** generates sensor values every 5 seconds.
2. **Sensor payload sent to SQS** (`SmartTheatreQueue`).
3. **AWS Lambda** (`ProcessTheatreSensors`) triggered by SQS event.
4. **Lambda stores to SQLite** (`smart_theatre.db`) in `/tmp` (local ephemeral storage).
5. **Lambda logs to CloudWatch** (monitoring + audit trail).
6. **Flask app** (`app.py`) reads from local SQLite (rebuilt by Lambda writes).
7. **Dashboard** (`dashboard.html`) retrieves data via Flask API.
8. **Dashboard updates every 5 seconds** with latest timestamps.

### Key Points

- **No direct writes**: Generator sends ONLY to SQS, NOT directly to SQLite.
- **Lambda is the gatekeeper**: Processes all data from SQS before it reaches the database.
- **CloudWatch integration**: Every Lambda execution is logged (invocations, metrics, errors).
- **Single source of truth**: SQLite is populated only by Lambda, consumed only by Flask/Dashboard.

## Architecture Diagram

```mermaid
flowchart LR
    A[generate_sensors.py\nFOG data generator] -->|Send to queue| C[AWS SQS\nSmartTheatreQueue]
    C -->|Event source mapping| D[AWS Lambda\nProcessTheatreSensors]
    D -->|Store data| B[(smart_theatre.db\nLocal SQLite)]
    D -->|Log executions| E[CloudWatch Logs\n/aws/lambda/ProcessTheatreSensors]
    D -->|Send metrics| F[CloudWatch Metrics\nSmartTheatre namespace]
    B -->|Read data| H[Flask API\napp.py]
    H -->|Serve API| I[dashboard.html\nChart.js auto-refresh 5s]
### Application Stack
- Python 3.14
- Flask + Flask-CORS
- SQLite (`smart_theatre.db`)
- Chart.js (frontend graphs)
- python-dotenv
- boto3 (AWS SDK)

### AWS Services
- Amazon SQS (`SmartTheatreQueue`)
- AWS Lambda (`ProcessTheatreSensors`)
- Amazon CloudWatch Logs
- Amazon CloudWatch Metrics

### Development / Debug Tools Used During Setup
- VS Code
- PowerShell terminal
- Browser DevTools (network/console checks)
- API checks via `Invoke-WebRequest`

## Demo Steps (End-to-End)

### 1) Install dependencies
```bash
pip install -r requirements.txt
```

### 2) Configure `.env`
Set these keys:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN` (if your lab uses temporary creds)
- `AWS_DEFAULT_REGION=us-east-1`
- `SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/<account>/SmartTheatreQueue`

### 3) Start Flask backend
```bash
python app.py
```

### 4) Start sensor generator (new terminal)
```bash
python generate_sensors.py
```

### 5) Open dashboard
- URL: `http://localhost:5000`
- Expected: values and timestamps update every ~5 seconds.

### 6) Verify cloud path
In AWS Console:
1. Go to **Lambda → ProcessTheatreSensors**.
2. Open **Monitoring** and check invocations increasing.
3. Open **CloudWatch Logs** log group:
   - `/aws/lambda/ProcessTheatreSensors`
4. Use recent time range (last 5–15 min) and refresh/log tail.

### 7) Verify SQLite and dashboard path
Run:
```bash
python -c "import sqlite3; c=sqlite3.connect('smart_theatre.db'); cur=c.cursor(); cur.execute('select sensor,timestamp,value,status from sensor_data order by timestamp desc limit 5'); print(cur.fetchall()); c.close()"
```

Then open:
- `http://localhost:5000/dashboard.html`
- Confirm timestamps move every 5 seconds.

## API Endpoints

- `GET /api/all-sensors` → latest value for all sensors
- `GET /api/data/<sensor>?limit=50` → chart data for one sensor
- `GET /api/stats/<sensor>` → min/max/avg/count
- `GET /api/health` → service health

## Notes

- Flask no longer consumes SQS (to avoid competing with Lambda).
- Dashboard data is sourced from local SQLite entries written by `generate_sensors.py`.
- Lambda logs/metrics confirm SQS → Lambda processing in cloud.
- If CloudWatch log stream list looks stale, use **Live tail** or set recent time range and refresh.

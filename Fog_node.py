"""
Sensor Data Generator (FOG Layer)
Generates random sensor data, writes to local SQLite for the dashboard,
and sends to SQS so Lambda can log to CloudWatch.

Data Flow:
  Generator → SQLite → Flask API → Dashboard  (live chart)
  Generator → SQS → Lambda → CloudWatch       (cloud logging)

Usage: python Fog_node.py
"""

import boto3
import json
import time
import random
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import os
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = Path(__file__).resolve().parent


def load_environment_files():
    """Load env vars from common deployment locations."""
    candidate_paths = [
        BASE_DIR / '.env',
        Path.cwd() / '.env',
        Path.home() / '.env',
        Path('/etc/smart-theatre/.env'),
        Path('/etc/default/smart-theatre-generator'),
    ]

    for path in candidate_paths:
        if path.exists():
            load_dotenv(path, override=False)


load_environment_files()

DEFAULT_QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/515610050494/SmartTheatreQueue'
QUEUE_URL = os.getenv('SQS_QUEUE_URL') or DEFAULT_QUEUE_URL
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
DB_PATH = 'smart_theatre.db'
DEFAULT_MODE = os.getenv('THEATRE_MODE', 'movie')
DATA_SOURCE = os.getenv('DATA_SOURCE', 'hybrid').strip().lower()
LIVE_LATITUDE = float(os.getenv('LIVE_LATITUDE', '51.5072'))
LIVE_LONGITUDE = float(os.getenv('LIVE_LONGITUDE', '-0.1276'))
LIVE_CACHE_SECONDS = int(os.getenv('LIVE_CACHE_SECONDS', '60'))

WEATHER_API_URL = 'https://api.open-meteo.com/v1/forecast'
AIR_API_URL = 'https://air-quality-api.open-meteo.com/v1/air-quality'

MODE_THRESHOLDS = {
    'movie': {
        'temperature': {'normal': (20.0, 23.0), 'warning': (19.0, 24.5)},
        'motion': {'normal': (0.0, 5.0), 'warning': (0.0, 8.0)},
        'light': {'normal': (0.0, 15.0), 'warning': (0.0, 25.0)},
        'noise': {'normal': (65.0, 85.0), 'warning': (60.0, 90.0)},
        'smoke': {'normal': (0.0, 5.0), 'warning': (0.0, 7.0)}
    },

}

SENSOR_LIMITS = {
    'temperature': (15.0, 30.0),
    'motion': (0.0, 100.0),
    'light': (0.0, 1200.0),
    'noise': (30.0, 110.0),
    'smoke': (0.0, 15.0)
}

# Movie-mode shaping: keep values realistic while making 100 rare.
MOVIE_WARNING_PROB = 0.45

class SensorGenerator:
    def __init__(self, mode=DEFAULT_MODE):
        self.mode = self.normalize_mode(mode)
        self.data_source = DATA_SOURCE if DATA_SOURCE in {'mock', 'live', 'hybrid'} else 'hybrid'
        self.live_snapshot = None
        self.live_snapshot_ts = 0
        self.sqs = boto3.client('sqs', region_name=AWS_REGION)
        self.initialize_db()

    def normalize_mode(self, mode):
        """Normalize supported mode aliases."""
        mode_value = (mode or 'movie').strip().lower()
        aliases = {
            'movie': 'movie'
        }
        return aliases.get(mode_value, 'movie')

    def set_mode(self, mode):
        self.mode = self.normalize_mode(mode)

    def clamp_value(self, sensor_type, value):
        """Clamp generated values to realistic sensor limits."""
        min_limit, max_limit = SENSOR_LIMITS[sensor_type]
        return round(max(min(value, max_limit), min_limit), 2)

    def movie_biased_value(self, sensor_type, normal_range, warning_range):
        """Sample movie values from normal/warning bands so score stays 80+ naturally."""
        if random.random() < MOVIE_WARNING_PROB:
            low, high = warning_range
        else:
            low, high = normal_range
        return self.clamp_value(sensor_type, random.uniform(low, high))

    def fetch_live_snapshot(self):
        """Fetch live temperature and PM2.5, then map PM2.5 to smoke proxy in ppm-like scale."""
        if requests is None:
            return None

        now_ts = time.time()
        if self.live_snapshot and (now_ts - self.live_snapshot_ts) < LIVE_CACHE_SECONDS:
            return self.live_snapshot

        try:
            weather_res = requests.get(
                WEATHER_API_URL,
                params={
                    'latitude': LIVE_LATITUDE,
                    'longitude': LIVE_LONGITUDE,
                    'current': 'temperature_2m'
                },
                timeout=8
            )
            weather_res.raise_for_status()
            weather_json = weather_res.json()

            air_res = requests.get(
                AIR_API_URL,
                params={
                    'latitude': LIVE_LATITUDE,
                    'longitude': LIVE_LONGITUDE,
                    'current': 'pm2_5'
                },
                timeout=8
            )
            air_res.raise_for_status()
            air_json = air_res.json()

            temperature = weather_json.get('current', {}).get('temperature_2m')
            pm25 = air_json.get('current', {}).get('pm2_5')

            if temperature is None and pm25 is None:
                return None

            # Convert PM2.5 (ug/m3) to bounded smoke proxy (ppm-like 0-15 for dashboard compatibility).
            smoke_proxy = None
            if pm25 is not None:
                smoke_proxy = round(max(0.0, min(15.0, float(pm25) / 5.0)), 2)

            self.live_snapshot = {
                'temperature': float(temperature) if temperature is not None else None,
                'smoke': smoke_proxy,
                'pm25': float(pm25) if pm25 is not None else None
            }
            self.live_snapshot_ts = now_ts
            return self.live_snapshot
        except Exception as e:
            print(f"[LIVE API WARN] Falling back to mock values: {e}")
            return None

    def initialize_db(self):
        """Ensure local SQLite table exists for dashboard"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                value REAL NOT NULL,
                status TEXT NOT NULL,
                unit TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'movie',
                received_at TEXT NOT NULL
            )
        ''')
        try:
            cursor.execute("ALTER TABLE sensor_data ADD COLUMN mode TEXT NOT NULL DEFAULT 'movie'")
        except sqlite3.OperationalError:
            pass
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sensor_timestamp
            ON sensor_data(sensor, timestamp DESC)
        ''')
        conn.commit()
        conn.close()

    def store_to_sqlite(self, message):
        """Write sensor reading to local SQLite for the Flask dashboard"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sensor_data (sensor, timestamp, value, status, unit, mode, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                message['sensor'],
                message['timestamp'],
                message['value'],
                message['status'],
                message['unit'],
                message['mode'],
                datetime.now().isoformat()
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] {e}")
        
    def generate_temperature(self):
        """Generate realistic temperature by mode."""
        if self.data_source in {'live', 'hybrid'}:
            live = self.fetch_live_snapshot()
            if live and live.get('temperature') is not None:
                return self.clamp_value('temperature', live['temperature'])

        if self.mode == 'movie':
            # Normal: 20.5-22.5, Warning: 23.0-24.4
            return self.movie_biased_value('temperature', (20.5, 22.5), (23.0, 24.4))
        else:
            value = random.uniform(21.0, 24.0)
        return self.clamp_value('temperature', value)
    
    def generate_motion(self):
        """Generate realistic motion percentage by mode."""
        if self.mode == 'movie':
            # Normal: 0-3, Warning: 3.1-8.0
            return self.movie_biased_value('motion', (0.0, 3.0), (3.1, 8.0))
        else:
            value = random.uniform(20.0, 60.0)
        return self.clamp_value('motion', value)
    
    def generate_light(self):
        """Generate realistic light level by mode (lux)."""
        if self.mode == 'movie':
            # Normal: 0-8, Warning: 8.1-25
            return self.movie_biased_value('light', (0.0, 8.0), (8.1, 25.0))
        else:
            value = random.uniform(30.0, 120.0)
        return self.clamp_value('light', value)
    
    def generate_noise(self):
        """Generate realistic noise level by mode (dB)."""
        if self.mode == 'movie':
            # Normal: 68-80, Warning: 80.1-90
            return self.movie_biased_value('noise', (68.0, 80.0), (80.1, 90.0))
        else:
            value = random.uniform(50.0, 70.0)
        return self.clamp_value('noise', value)
    
    def generate_smoke(self):
        """Generate realistic smoke value in ppm (usually safe)."""
        if self.data_source in {'live', 'hybrid'}:
            live = self.fetch_live_snapshot()
            if live and live.get('smoke') is not None:
                return self.clamp_value('smoke', live['smoke'])

        if self.mode == 'movie':
            # Normal: 0-2, Warning: 2.1-7
            return self.movie_biased_value('smoke', (0.0, 2.0), (2.1, 7.0))
        else:
            value = random.uniform(0.0, 3.0)
        return self.clamp_value('smoke', value)
    
    def determine_status(self, sensor_type, value):
        """Determine status based on mode-specific ranges."""
        mode_thresholds = MODE_THRESHOLDS.get(self.mode, {})
        sensor_threshold = mode_thresholds.get(sensor_type)

        if not sensor_threshold:
            return 'normal'

        normal_low, normal_high = sensor_threshold['normal']
        warning_low, warning_high = sensor_threshold['warning']

        if normal_low <= value <= normal_high:
            return 'normal'
        if warning_low <= value <= warning_high:
            return 'warning'
        return 'alert'
    
    def send_to_sqs(self, sensor_type, value, unit):
        """Write reading to local SQLite (dashboard) and send to SQS (Lambda/CloudWatch)"""
        try:
            message = {
                'sensor': sensor_type,
                'value': value,
                'status': self.determine_status(sensor_type, value),
                'unit': unit,
                'mode': self.mode,
                'timestamp': datetime.now().astimezone().isoformat()
            }
            
            # Write to local SQLite so the Flask dashboard shows live data
            self.store_to_sqlite(message)

            # Also send to SQS → Lambda will log to CloudWatch
            response = self.sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    'SensorType': {
                        'StringValue': sensor_type,
                        'DataType': 'String'
                    }
                }
            )
            
            print(f"[SENT] {sensor_type}: {value} {unit} → SQS ID: {response['MessageId'][:12]}...")
            return True
            
        except Exception as e:
            print(f"[ERROR] {sensor_type}: {e}")
            return False
    
    def generate_all_sensors(self):
        """Generate and send data for all sensors"""
        sensors = [
            ('temperature', self.generate_temperature(), '°C'),
            ('motion', self.generate_motion(), '%'),
            ('light', self.generate_light(), 'lux'),
            ('noise', self.generate_noise(), 'dB'),
            ('smoke', self.generate_smoke(), 'ppm'),
        ]
        
        for sensor_type, value, unit in sensors:
            self.send_to_sqs(sensor_type, value, unit)
            time.sleep(0.1)

def main():
    print("\n" + "="*70)
    print("Sensor Data Generator - Smart Theatre")
    print("="*70)
    print("\nData Flow: Generator → SQS → Lambda → SQLite → Dashboard\n")
    
    if not QUEUE_URL or QUEUE_URL == '':
        print("[ERROR] SQS_QUEUE_URL not set in .env file!")
        print("[ACTION] Edit .env and set: SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/...")
        return False
    
    try:
        generator = SensorGenerator(DEFAULT_MODE)
        print("[OK] Connected to SQS\n")
        print(f"[MODE] Running generator in: {generator.mode}\n")
        print(f"[DATA SOURCE] {generator.data_source} (live temperature + smoke proxy in hybrid/live)")
        print(f"[LIVE COORDS] lat={LIVE_LATITUDE}, lon={LIVE_LONGITUDE}\n")
        
        # Generate data continuously
        interval = 5  # Send data every 5 seconds
        count = 0
        
        print("Starting sensor data generation (Ctrl+C to stop)...\n")
        
        while True:
            count += 1
            print(f"\n[BATCH {count}] Generating sensor readings at {datetime.now().strftime('%H:%M:%S')}")
            print("-" * 70)
            
            generator.generate_all_sensors()
            
            print(f"\nWaiting {interval}s before next batch...")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n[STOP] Generator stopped by user")
        print("\n" + "="*70)
        print("Next steps:")
        print("="*70)
        print("\n1. Check dashboard: http://localhost:5000/dashboard.html")
        print("2. Run: python app.py (if not already running)")
        print("3. Sensor data should be displayed on dashboard!\n")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False

if __name__ == "__main__":
    success = main()

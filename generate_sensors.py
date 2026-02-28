"""
Sensor Data Generator (FOG Layer)
Generates random sensor data and sends ONLY to SQS.
Lambda consumes SQS messages, stores to SQLite.
Dashboard reads from SQLite populated by Lambda.

Data Flow (Strict Single Path):
  Generator → SQS → Lambda → SQLite → Flask API → Dashboard

Usage: python generate_sensors.py
"""

import boto3
import json
import time
import random
from datetime import datetime
from dotenv import load_dotenv
import os

# Load credentials from .env
load_dotenv()

QUEUE_URL = os.getenv('SQS_QUEUE_URL')
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')

class SensorGenerator:
    def __init__(self):
        self.sqs = boto3.client('sqs', region_name=AWS_REGION)
        
    def generate_temperature(self):
        """Generate realistic temperature (22-28°C)"""
        return round(random.gauss(25, 1.5), 2)
    
    def generate_motion(self):
        """Generate motion (0-100%, 20% chance of detection)"""
        if random.random() < 0.2:
            return round(random.uniform(50, 100), 2)
        return 0
    
    def generate_light(self):
        """Generate light level (0-1000 lux)"""
        return round(random.gauss(400, 200), 2)
    
    def generate_noise(self):
        """Generate noise level (30-80 dB)"""
        return round(random.gauss(60, 10), 2)
    
    def generate_smoke(self):
        """Generate smoke level (0-5%, rarely higher)"""
        if random.random() < 0.95:
            return round(random.uniform(0, 2), 2)
        return round(random.uniform(0, 10), 2)
    
    def determine_status(self, sensor_type, value):
        """Determine status based on thresholds"""
        thresholds = {
            'temperature': {'warning': 28, 'alert': 30},
            'motion': {'warning': 75, 'alert': 90},
            'light': {'warning': 100, 'alert': 50},
            'noise': {'warning': 70, 'alert': 80},
            'smoke': {'warning': 5, 'alert': 10}
        }
        
        t = thresholds.get(sensor_type, {})
        if value >= t.get('alert', 999):
            return 'alert'
        elif value >= t.get('warning', 999):
            return 'warning'
        return 'normal'
    
    def send_to_sqs(self, sensor_type, value, unit):
        """Send sensor data ONLY to SQS - Lambda handles SQLite storage for dashboard"""
        try:
            message = {
                'sensor': sensor_type,
                'value': value,
                'status': self.determine_status(sensor_type, value),
                'unit': unit,
                'timestamp': datetime.now().isoformat()
            }
            
            # Send ONLY to SQS → Lambda will consume and store to SQLite
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
            ('smoke', self.generate_smoke(), '%'),
        ]
        
        for sensor_type, value, unit in sensors:
            self.send_to_sqs(sensor_type, value, unit)
            time.sleep(0.1)

def main():
    print("\n" + "="*70)
    print("Sensor Data Generator - Smart Theatre")
    print("="*70)
    print("\nData Flow: Generator → SQS → Lambda → SQLite → Dashboard\n")
    
    # Validate config
    if not QUEUE_URL or QUEUE_URL == '':
        print("[ERROR] SQS_QUEUE_URL not set in .env file!")
        print("[ACTION] Edit .env and set: SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/...")
        return False
    
    try:
        generator = SensorGenerator()
        print("[OK] Connected to SQS\n")
        
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

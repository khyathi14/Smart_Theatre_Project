import json
import sqlite3
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')

# SQLite database path
DB_PATH = '/tmp/smart_theatre.db'

def initialize_db():
    """Create SQLite table if not exists"""
    try:
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
                received_at TEXT NOT NULL
            )
        ''')
        
        # Create index for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sensor_timestamp 
            ON sensor_data(sensor, timestamp DESC)
        ''')
        
        conn.commit()
        conn.close()
        print("✓ SQLite database initialized")
    except Exception as e:
        print(f"✗ Database error: {e}")

def lambda_handler(event, context):
    """
    Process SQS messages containing sensor data
    """
    initialize_db()
    processed_count = 0
    errors = []
    
    try:
        for record in event['Records']:
            try:
                # Parse message
                body = json.loads(record['body'])
                
                # Extract data
                sensor_data = {
                    'sensor': body.get('sensor'),
                    'value': body.get('value'),
                    'status': body.get('status'),
                    'unit': body.get('unit'),
                    'timestamp': body.get('timestamp'),
                    'received_at': datetime.now().isoformat()
                }
                
                # Store to SQLite
                store_in_sqlite(sensor_data)
                
                # Send to CloudWatch (optional monitoring)
                send_to_cloudwatch(sensor_data)
                
                print(f"✓ Processed: {sensor_data['sensor']} = {sensor_data['value']} {sensor_data['unit']}")
                processed_count += 1
                
            except Exception as e:
                error_msg = f"Error processing record: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Processed {processed_count} messages',
                'stored_in': 'SQLite',
                'errors': errors
            })
        }
        
    except Exception as e:
        print(f"Lambda error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def store_in_sqlite(sensor_data):
    """Store sensor data in SQLite"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sensor_data 
            (sensor, timestamp, value, status, unit, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            sensor_data['sensor'],
            sensor_data['timestamp'],
            sensor_data['value'],
            sensor_data['status'],
            sensor_data['unit'],
            sensor_data['received_at']
        ))
        
        # Keep only 75 records per sensor (clean old data)
        cursor.execute('''
            DELETE FROM sensor_data WHERE id NOT IN (
                SELECT id FROM sensor_data 
                WHERE sensor = ? 
                ORDER BY timestamp DESC LIMIT 75
            )
        ''', (sensor_data['sensor'],))
        
        conn.commit()
        conn.close()
        print(f"✓ Stored {sensor_data['sensor']} in SQLite: {sensor_data['value']} {sensor_data['unit']}")
        return True
        
    except Exception as e:
        print(f"✗ SQLite error: {str(e)}")
        return False

def send_to_cloudwatch(sensor_data):
    """Send sensor metrics to CloudWatch (optional)"""
    try:
        cloudwatch.put_metric_data(
            Namespace='SmartTheatre',
            MetricData=[
                {
                    'MetricName': f"{sensor_data['sensor'].upper()}_Value",
                    'Value': sensor_data['value'],
                    'Unit': 'None',
                    'Timestamp': datetime.now(),
                    'Dimensions': [
                        {
                            'Name': 'Status',
                            'Value': sensor_data['status']
                        }
                    ]
                }
            ]
        )
    except Exception as e:
        print(f"CloudWatch error: {str(e)}")

# Test locally
if __name__ == "__main__":
    test_event = {
        'Records': [
            {
                'body': json.dumps({
                    'sensor': 'temperature',
                    'value': 26.42,
                    'status': 'normal',
                    'unit': '°C',
                    'timestamp': datetime.now().isoformat()
                }),
                'messageAttributes': {
                    'SensorType': {'stringValue': 'temperature'}
                }
            }
        ]
    }
    
    result = lambda_handler(test_event, None)
    print("Test result:", result)

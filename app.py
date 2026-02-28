"""
Smart Theatre Dashboard - Flask Backend
Reads sensor data from local SQLite database
SQS is consumed by Lambda only (for CloudWatch logging)
Local development server for dashboard

Data flow: FOG → EDGE → SQS → Lambda/Flask → SQLite → Dashboard

Run: python app.py
Visit: http://localhost:5000/
"""

from flask import Flask, jsonify, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# SQLite database path (same as Lambda uses)
DB_PATH = 'smart_theatre.db'
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')

def initialize_db():
    """Create SQLite table if not exists"""
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
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sensor_timestamp 
        ON sensor_data(sensor, timestamp DESC)
    ''')
    
    conn.commit()
    conn.close()
    print("✓ SQLite database initialized at:", DB_PATH)

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def query_sensor_data(sensor_type, limit=75):
    """Query recent sensor data from SQLite - LATEST records"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Subquery: Get latest N records in DESC order, then flip to ASC for chart display
        cursor.execute('''
            SELECT sensor, timestamp, value, status, unit, received_at
            FROM (
                SELECT sensor, timestamp, value, status, unit, received_at
                FROM sensor_data 
                WHERE sensor = ? 
                ORDER BY timestamp DESC
                LIMIT ?
            )
            ORDER BY timestamp ASC
        ''', (sensor_type, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Convert to list of dicts
        data = []
        for row in rows:
            data.append({
                'sensor': row['sensor'],
                'timestamp': row['timestamp'],
                'value': row['value'],
                'status': row['status'],
                'unit': row['unit'],
                'received_at': row['received_at']
            })
        
        return data
    except Exception as e:
        print(f"Query error: {e}")
        return []

@app.route('/api/sensor/<sensor_type>', methods=['GET'])
def get_sensor(sensor_type):
    """Get recent readings for a sensor"""
    data = query_sensor_data(sensor_type, limit=75)
    
    if not data:
        return jsonify({
            'sensor': sensor_type,
            'records': [],
            'status': 'no_data'
        })
    
    return jsonify({
        'sensor': sensor_type,
        'records': data,
        'status': 'success',
        'source': 'SQLite (Lambda processed)'
    })

@app.route('/api/data/<sensor_type>', methods=['GET'])
def get_sensor_data(sensor_type):
    """Get sensor data for dashboard (compatible format)"""
    from flask import request
    limit = request.args.get('limit', 50, type=int)
    data = query_sensor_data(sensor_type, limit=limit)
    
    if not data:
        return jsonify({'data': []})
    
    return jsonify({'data': data})

@app.route('/api/all-sensors', methods=['GET'])
def get_all_sensors():
    """Get latest reading from each sensor"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        sensors = ['motion', 'temperature', 'light', 'noise', 'smoke']
        latest = {}
        
        for sensor in sensors:
            cursor.execute('''
                SELECT * FROM sensor_data 
                WHERE sensor = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (sensor,))
            
            row = cursor.fetchone()
            if row:
                latest[sensor] = {
                    'value': row['value'],
                    'status': row['status'],
                    'unit': row['unit'],
                    'timestamp': row['timestamp']
                }
            else:
                latest[sensor] = {
                    'value': 0,
                    'status': 'no_data',
                    'unit': '',
                    'timestamp': None
                }
        
        conn.close()
        return jsonify(latest)
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/<sensor_type>', methods=['GET'])
def get_stats(sensor_type):
    """Get min, max, average for a sensor"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get last 75 records
        cursor.execute('''
            SELECT value FROM sensor_data 
            WHERE sensor = ? 
            ORDER BY timestamp DESC 
            LIMIT 75
        ''', (sensor_type,))
        
        values = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not values:
            return jsonify({
                'sensor': sensor_type,
                'min': 0,
                'max': 0,
                'avg': 0,
                'count': 0
            })
        
        return jsonify({
            'sensor': sensor_type,
            'min': round(min(values), 2),
            'max': round(max(values), 2),
            'avg': round(sum(values) / len(values), 2),
            'count': len(values),
            'source': 'SQLite'
        })
    except Exception as e:
        print(f"Stats error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/recent/<sensor_type>', methods=['GET'])
def get_recent(sensor_type):
    """Get last 5 readings for a sensor"""
    data = query_sensor_data(sensor_type, limit=5)
    return jsonify({
        'sensor': sensor_type,
        'recent': data
    })

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'database': 'SQLite',
        'location': DB_PATH,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/')
@app.route('/dashboard.html')
def dashboard():
    """Serve dashboard HTML with no-cache headers at root and /dashboard.html"""
    response = send_file('dashboard.html', mimetype='text/html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    initialize_db()
    
    print("\n" + "="*60)
    print("🎬 Smart Theatre Dashboard - SQLITE MODE")
    print("="*60)
    print("✓ Data Source: SQLite (updated by generator)")
    print("✓ Database: smart_theatre.db")
    print("✓ Data Flow: FOG → (SQS → Lambda/CloudWatch) + (SQLite → Dashboard)")
    print("="*60)
    print("\nVisit: http://localhost:5000/")
    print("API: http://localhost:5000/api/all-sensors")
    print("\nPress CTRL+C to stop\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)

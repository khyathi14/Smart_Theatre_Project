Smart Theatre Monitoring System
Overview

This project is designed to monitor theatre conditions using sensors and process the data through Fog and Cloud layers. The system collects real-time environmental data, processes it efficiently, and displays insights on a dashboard.

Architecture Layers
1. Sensor Layer
Sensors are placed inside the theatre environment
Types of sensors used:
Temperature sensor
Smoke sensor
Motion sensor
Noise sensor
Light sensor
These sensors continuously collect real-time data
2. Fog Layer
Acts as an intermediate processing layer between sensors and cloud
Components:
Eclipse Mosquitto Broker
Handles communication using MQTT protocol (port 8883)
Fog Node (fog_node.py)
Receives sensor data
Fetches live data from Open-Meteo APIs
Data Processor
Cleans and processes incoming data
Cloud Dispatcher
Sends processed data to the cloud using HTTP
3. Cloud Layer (AWS)
Responsible for storage, processing, and monitoring
Components:
Amazon SQS (SmartTheatreQueue)
Stores incoming data messages from fog layer
AWS Lambda
Triggered by SQS
Processes data in real time
Amazon EC2 (Flask Backend)
Handles API requests
Reads and writes data to database
Amazon CloudWatch
Stores logs and monitors system performance
4. Data Storage
SQLite Database
Stores processed data
Used by backend for retrieval and updates
5. Dashboard
Displays processed data in visual format
Shows real-time insights like:
Temperature trends
Air quality conditions
Alerts for abnormal conditions
Data Flow
Sensors collect data from theatre
Data is sent to Mosquitto Broker using MQTT
Fog Node receives and processes the data
Processed data is sent to Cloud via HTTP
Data is stored in SQS queue
Lambda processes data from queue
EC2 backend stores data in SQLite
Dashboard displays final output
APIs Used
Weather API:
https://api.open-meteo.com/v1/forecast
Air Quality API:
https://air-quality-api.open-meteo.com/v1/air-quality
Technologies Used
Python (Fog Node & Backend)
MQTT (Mosquitto Broker)
AWS (SQS, Lambda, EC2, CloudWatch)
Flask (Backend API)
SQLite (Database)
Chart.js (Dashboard visualization)
Key Features
Real-time monitoring system
Fog computing to reduce cloud load
Cloud-based processing and storage
Scalable and efficient architecture
Live environmental data integration
Conclusion

This system demonstrates how IoT, Fog Computing, and Cloud Computing can be integrated to build a smart monitoring solution. It improves real-time decision making and reduces latency by processing data closer to the source.

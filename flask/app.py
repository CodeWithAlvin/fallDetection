from flask import Flask, request, jsonify, render_template_string
import csv
import os
from datetime import datetime
import pytz  # For timezone handling
import time
from pymongo import MongoClient  # Added for MongoDB support
from twilio.rest import Client  # Added for Twilio SMS support
from dotenv import load_dotenv

# Load environment variables from .env file
if os.path.exists('.env'):
    load_dotenv()

# MongoDB Configuration
MONGO_URI = os.getenv('MONGO_URI')
DB_NAME = os.getenv('DB_NAME')
COLLECTION_NAME = os.getenv('COLLECTION_NAME')

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER')
EMERGENCY_CONTACT = os.getenv('EMERGENCY_CONTACT')

app = Flask(__name__)

# Configuration
CSV_FILE = 'fall_events.csv'
TIMEZONE = 'Asia/Kolkata'  # Change to your timezone (e.g., 'America/New_York', 'Europe/London')
SERVER_HOSTNAME = 'falldetection'  # The hostname for your server (without .local)
PORT = 5000

# Initialize Twilio client
try:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    TWILIO_AVAILABLE = True
    print("Connected to Twilio messaging API")
except Exception as e:
    print(f"Failed to connect to Twilio: {e}")
    print("Install Twilio with: pip install twilio")
    print("Make sure you have valid Twilio credentials")
    TWILIO_AVAILABLE = False

# Initialize MongoDB client
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    events_collection = db[COLLECTION_NAME]
    print(f"Connected to MongoDB: {DB_NAME}.{COLLECTION_NAME}")
    MONGO_AVAILABLE = True
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    print("Install MongoDB and pymongo with: pip install pymongo")
    print("Make sure MongoDB server is running")
    MONGO_AVAILABLE = False

# Initialize CSV file if it doesn't exist
def initialize_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['timestamp', 'detection', 'alert_type', 'device_id', 'sms_sent'])
        print(f"Created new CSV file: {CSV_FILE}")

# Get current timestamp with timezone
def get_current_timestamp():
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')

# Get current timestamp as datetime object
def get_current_datetime():
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz)

# Send SMS alert
def send_sms_alert(device_id, alert_type):
    if not TWILIO_AVAILABLE:
        print("Twilio not available. SMS alert not sent.")
        return False
    
    try:
        message = twilio_client.messages.create(
            body=f"ALERT: A person may have fallen! Device ID: {device_id}, Alert type: {alert_type}. Please check immediately.",
            from_=TWILIO_FROM_NUMBER,
            to=EMERGENCY_CONTACT
        )
        print(f"SMS alert sent with SID: {message.sid}")
        return True
    except Exception as e:
        print(f"Error sending SMS alert: {e}")
        return False

# Add event to CSV
def log_event(detection, alert_type, device_id):
    timestamp = get_current_timestamp()
    sms_sent = "No"
    
    # Send SMS alert if it's a real fall detection
    if detection and alert_type == "real alert":
        sms_success = send_sms_alert(device_id, alert_type)
        sms_sent = "Yes" if sms_success else "Failed"
    
    # Log to CSV (keeping for backward compatibility)
    with open(CSV_FILE, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([timestamp, detection, alert_type, device_id, sms_sent])
    
    # Log to MongoDB if available
    if MONGO_AVAILABLE:
        try:
            event_doc = {
                'timestamp': get_current_datetime(),
                'timestamp_str': timestamp,
                'device_id': device_id,
                'detection': detection,
                'alert_type': alert_type,
                'sms_sent': sms_sent
            }
            result = events_collection.insert_one(event_doc)
            print(f"Event saved to MongoDB with ID: {result.inserted_id}")
        except Exception as e:
            print(f"Error saving to MongoDB: {e}")
    
    return sms_sent

@app.route('/')
def index():
    # Get last 20 events - preferably from MongoDB, fallback to CSV
    events = []
    
    if MONGO_AVAILABLE:
        try:
            # Get events from MongoDB (newest first)
            mongo_events = list(events_collection.find().sort('timestamp', -1).limit(20))
            for event in mongo_events:
                events.append([
                    event.get('timestamp_str', str(event.get('timestamp'))),
                    str(event.get('detection')),
                    event.get('alert_type', 'unknown'),
                    event.get('device_id', 'unknown'),
                    event.get('sms_sent', 'No')
                ])
        except Exception as e:
            print(f"Error fetching from MongoDB: {e}")
            # Fallback to CSV
            events = get_events_from_csv()
    else:
        # Use CSV if MongoDB is not available
        events = get_events_from_csv()
    
    return render_template_string('''
    <html>
        <head>
            <title>Fall Detection System</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                h1 { color: #333; }
                table { border-collapse: collapse; width: 100%; margin-top: 20px; }
                th, td { text-align: left; padding: 12px; border-bottom: 1px solid #ddd; }
                th { background-color: #f2f2f2; color: #333; }
                tr:hover { background-color: #f5f5f5; }
                .status { padding: 6px 12px; border-radius: 4px; display: inline-block; }
                .real { background-color: #ffcccc; }
                .false { background-color: #ffffcc; }
                .none { background-color: #ccffcc; }
                .sms-sent { background-color: #ccffcc; }
                .sms-failed { background-color: #ffcccc; }
                .refresh { margin-top: 20px; padding: 10px; }
                .server-info { margin-top: 20px; background-color: #f8f8f8; padding: 15px; border-radius: 5px; }
                .service-status { margin-top: 10px; padding: 8px; border-radius: 4px; }
                .service-connected { background-color: #d4edda; color: #155724; }
                .service-disconnected { background-color: #f8d7da; color: #721c24; }
            </style>
            <script>
                function refreshEvents() {
                    window.location.reload();
                }
                
                // Auto refresh every 30 seconds
                setInterval(refreshEvents, 30000);
            </script>
        </head>
        <body>
            <h1>Fall Detection Monitoring System</h1>
            <p>This system monitors fall detection events from connected ESP8266 devices.</p>
            
            <div class="server-info">
                <h3>Connection Information</h3>
                <p><strong>API Endpoint:</strong> http://{{ server_ip }}:{{ port }}/fall_event</p>
                
                <div class="service-status {{ 'service-connected' if mongo_available else 'service-disconnected' }}">
                    <strong>Database Status:</strong> 
                    {% if mongo_available %}
                        Connected to MongoDB ({{ db_name }}.{{ collection_name }})
                    {% else %}
                        MongoDB unavailable. Using CSV storage only.
                    {% endif %}
                </div>
                
                <div class="service-status {{ 'service-connected' if twilio_available else 'service-disconnected' }}">
                    <strong>SMS Alerts:</strong> 
                    {% if twilio_available %}
                        Twilio messaging service connected
                    {% else %}
                        Twilio messaging service unavailable. SMS alerts disabled.
                    {% endif %}
                </div>
            </div>
            
            <h2>Recent Events</h2>
            <table>
                <tr>
                    <th>Timestamp</th>
                    <th>Detection</th>
                    <th>Alert Type</th>
                    <th>Device ID</th>
                    <th>SMS Alert</th>
                </tr>
                {% for event in events %}
                <tr>
                    <td>{{ event[0] }}</td>
                    <td>{{ event[1] }}</td>
                    <td>
                        {% if event[2] == 'real alert' %}
                        <span class="status real">{{ event[2] }}</span>
                        {% elif event[2] == 'false alert' %}
                        <span class="status false">{{ event[2] }}</span>
                        {% else %}
                        <span class="status none">{{ event[2] }}</span>
                        {% endif %}
                    </td>
                    <td>{{ event[3] }}</td>
                    <td>
                        {% if event[4] == 'Yes' %}
                        <span class="status sms-sent">Sent</span>
                        {% elif event[4] == 'Failed' %}
                        <span class="status sms-failed">Failed</span>
                        {% else %}
                        <span class="status none">Not Sent</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </table>
            
            <button class="refresh" onclick="refreshEvents()">Refresh Events</button>
        </body>
    </html>
    ''', events=events, server_ip=request.host.split(':')[0], port=PORT,
       mongo_available=MONGO_AVAILABLE, db_name=DB_NAME, collection_name=COLLECTION_NAME,
       twilio_available=TWILIO_AVAILABLE)

# Helper function to get events from CSV
def get_events_from_csv():
    events = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader)  # Skip header
            events = list(reader)
            events.reverse()  # Newest first
            events = events[:20]  # Limit to 20 events
            
            # Add device_id and sms_sent columns if they don't exist in older records
            for event in events:
                if len(event) < 4:
                    event.append('unknown')  # device_id
                if len(event) < 5:
                    event.append('No')  # sms_sent
    return events

@app.route('/events')
def events():
    try:
        # Get events - preferably from MongoDB, fallback to CSV
        events = []
        
        if MONGO_AVAILABLE:
            try:
                # Get events from MongoDB (newest first)
                mongo_events = list(events_collection.find().sort('timestamp', -1).limit(20))
                for event in mongo_events:
                    events.append({
                        'timestamp': event.get('timestamp_str', str(event.get('timestamp'))),
                        'detection': event.get('detection'),
                        'alert_type': event.get('alert_type', 'unknown'),
                        'device_id': event.get('device_id', 'unknown'),
                        'sms_sent': event.get('sms_sent', 'No'),
                        '_id': str(event.get('_id'))
                    })
            except Exception as e:
                print(f"Error fetching from MongoDB: {e}")
                # Fallback to CSV format
                csv_events = get_events_from_csv()
                events = []
                for e in csv_events:
                    event_dict = {
                        'timestamp': e[0], 
                        'detection': e[1], 
                        'alert_type': e[2]
                    }
                    if len(e) > 3:
                        event_dict['device_id'] = e[3]
                    if len(e) > 4:
                        event_dict['sms_sent'] = e[4]
                    events.append(event_dict)
        else:
            # Use CSV if MongoDB is not available
            csv_events = get_events_from_csv()
            events = []
            for e in csv_events:
                event_dict = {
                    'timestamp': e[0], 
                    'detection': e[1], 
                    'alert_type': e[2]
                }
                if len(e) > 3:
                    event_dict['device_id'] = e[3]
                if len(e) > 4:
                    event_dict['sms_sent'] = e[4]
                events.append(event_dict)
        
        return jsonify(events)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/fall_event', methods=['POST'])
def fall_event():
    try:
        data = request.json
        
        # Extract data from request
        detected = data.get('detect', False)
        alert_type = data.get('type', 'unknown')
        device_id = data.get('device_id', 'unknown')
        
        print(f"Received fall event: Detected={detected}, Type={alert_type}, Device={device_id}")
        
        # Log to CSV and MongoDB, send SMS if needed
        sms_status = log_event(detected, alert_type, device_id)
        
        return jsonify({
            "status": "success", 
            "message": "Event logged successfully",
            "sms_alert": sms_status
        })
    except Exception as e:
        print(f"Error processing fall event: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/config')
def config():
    """Endpoint that provides configuration for ESP8266 devices"""
    server_ip = request.host.split(':')[0]
    return jsonify({
        "server_ip": server_ip,
        "api_endpoint": f"http://{server_ip}:{PORT}/fall_event"
    })

@app.route('/status', methods=['GET'])
def api_status():
    # Simple status endpoint to check if API is running
    record_count = 0
    
    # Get record count from MongoDB if available
    if MONGO_AVAILABLE:
        try:
            record_count = events_collection.count_documents({})
        except:
            # Fallback to CSV count
            if os.path.exists(CSV_FILE):
                record_count = sum(1 for line in open(CSV_FILE)) - 1  # Subtract header row
    else:
        # Use CSV if MongoDB is not available
        if os.path.exists(CSV_FILE):
            record_count = sum(1 for line in open(CSV_FILE)) - 1  # Subtract header row
    
    return jsonify({
        'status': 'online',
        'time': time.time(),
        'timezone': TIMEZONE,
        'records_count': record_count,
        'database': 'mongodb' if MONGO_AVAILABLE else 'csv',
        'mongo_status': 'connected' if MONGO_AVAILABLE else 'disconnected',
        'twilio_status': 'connected' if TWILIO_AVAILABLE else 'disconnected'
    })

if __name__ == '__main__':
    initialize_csv()
    
    # Close MongoDB connection on exit
    if MONGO_AVAILABLE:
        def cleanup():
            print("Closing MongoDB connection...")
            mongo_client.close()
        
        # Register cleanup function to run on exit
        import atexit
        atexit.register(cleanup)
    
    print(f"Fall Detection API Server started. Current timezone: {TIMEZONE}")
    print(f"Access the dashboard at: http://[server-ip]:{PORT}")
    print(f"Database: {'MongoDB' if MONGO_AVAILABLE else 'CSV only (MongoDB unavailable)'}")
    print(f"SMS Alerts: {'Enabled via Twilio' if TWILIO_AVAILABLE else 'Disabled (Twilio unavailable)'}")
    
    app.run(host='0.0.0.0', port=PORT, debug=True)
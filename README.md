# Fall Detection System

A comprehensive IoT solution for real-time fall detection, monitoring, and alerting using ESP8266 microcontrollers with IMU sensors, Flask API backend, MongoDB Atlas database, and a Streamlit dashboard interface.

## Overview

This system is designed to detect falls among elderly or at-risk individuals using wearable devices. Upon detecting a fall, the system immediately sends alerts to registered caretakers via SMS and records the incident for future reference. Caretakers can monitor multiple users through a web-based dashboard.

### Components

1. **Hardware**
   - ESP8266 microcontroller
   - MPU6050/MPU9250 IMU sensor (accelerometer and gyroscope)
   - Battery power supply
   - 3D printed casing

2. **Backend**
   - Flask API for data ingestion and alert processing
   - MongoDB Atlas for cloud database storage
   - SMS service integration

3. **Frontend**
   - Streamlit dashboard for caretakers
   - User management interface
   - Incident visualization and history

## Features

- **Real-time fall detection** using machine learning algorithms
- **Instant SMS alerts** to caretakers when falls are detected
- **User management** to monitor multiple individuals
- **Historical data analysis** of movements and incidents
- **Battery status monitoring** of IoT devices
- **Secure cloud storage** of all detection data
- **Responsive web dashboard** for desktop and mobile access

## Setup and Installation

### Prerequisites

- Python 3.8+
- Arduino IDE
- MongoDB Atlas account
- SMS service API keys (Twilio recommended)
- Internet connection for IoT devices

### Hardware Setup

1. **ESP8266 & IMU Configuration**
   ```
   1. Connect the MPU6050/MPU9250 to the ESP8266:
      - VCC to 3.3V
      - GND to GND
      - SCL to D1
      - SDA to D2
   2. Flash the ESP8266 with the provided firmware
   3. Configure WiFi credentials in the code
   ```

2. **Power Supply**
   - Connect a 3.7V LiPo battery
   - Ensure proper charging circuit implementation

### Backend Setup

1. **Flask API**
   ```bash
   # Clone the repository
   git clone https://github.com/CodeWithAlvin/fallDetection
   cd fall-detection-system/backend
   
   # Create and activate virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Configure environment variables
   cp .env.example .env
   # Edit .env with your MongoDB and SMS service credentials
   
   # Run the Flask API
   python app.py
   ```

2. **MongoDB Atlas Configuration**
   - Create a cluster in MongoDB Atlas
   - Create a database named `fall_detection`
   - Create collections: `users`, `patients`, `fallDetection`
   - Configure network access for your API server

3. **SMS Service Setup**
   - Register for a Twilio account (or alternative SMS service)
   - Obtain API credentials
   - Add these credentials to your `.env` file

### Frontend Setup

1. **Streamlit Dashboard**
   ```bash
   cd fall-detection-system/frontend
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Run the Streamlit app
   streamlit run dashboard.py
   ```

## Usage

### Device Registration

1. Power on the ESP8266 device
2. The device will connect to WiFi and register with the backend
3. Log in to the Streamlit dashboard
4. Go to "Devices" and assign the new device to a user

### User Management

1. Navigate to "Users" section in the dashboard
2. Add new users with their details:
   - Name
   - Age
   - Contact information
   - Emergency contacts (for SMS alerts)
3. Assign devices to users

### Alert Monitoring

1. The dashboard will display:
   - Real-time status of all users
   - Recent alerts with severity levels
   - Fall history with timestamps and locations
   - Device battery status

2. SMS alerts will be automatically sent to registered caretakers when:
   - A fall is detected
   - Device battery is critically low
   - Device goes offline unexpectedly

## ESP8266 Firmware

The ESP8266 firmware includes:
- WiFi connection management
- IMU sensor data processing
- Fall detection algorithms
- HTTP communication with Flask API
- Power management routines


## Dashboard Features

1. **Home Screen**
   - Overview of all users
   - Active alerts
   - System health status

2. **User Management**
   - Add/Edit/Remove users
   - Assign devices to users
   - Manage emergency contacts

3. **Alert History**
   - Timeline of detected falls
   - Filtering by user, date, and severity
   - Export functionality for medical records

4. **Analytics**
   - Trends in user activity
   - Fall frequency analysis
   - Device performance metrics

## Troubleshooting

### Common Issues

1. **Device Not Connecting**
   - Check WiFi signal strength
   - Verify credentials in the firmware
   - Ensure backend API is running

2. **False Alerts**
   - Adjust sensitivity settings in the device configuration
   - Update firmware to latest version
   - Ensure device is worn correctly

3. **Missing SMS Alerts**
   - Verify SMS service credits and account status
   - Check phone numbers are in correct format (include country code)
   - Review API logs for error messages

## Contributing

Contributions to the project are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- [ESP8266 Community](https://github.com/esp8266/Arduino)
- [MPU6050 Library](https://github.com/jrowberg/i2cdevlib)
- [Flask](https://flask.palletsprojects.com/)
- [Streamlit](https://streamlit.io/)
- [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
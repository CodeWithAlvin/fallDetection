#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>

// WiFi credentials
const char* ssid = "alvin";         // Replace with your WiFi SSID
const char* password = "@blackmat2"; // Replace with your WiFi password

// API server details - hardcoded IP address instead of mDNS
const char* serverName = "falldetection-np7b.onrender.com";  // Server domain without https://
const char* apiEndpoint = "/fall_event";   // API endpoint for fall detection
const int httpsPort = 443;

// Device identifier
const char* deviceId = "falldetector01";

// Data collection interval (milliseconds)
const long interval = 10;  // Sample at 100Hz for better fall detection
unsigned long previousMillis = 0;

// Create MPU6050 object
Adafruit_MPU6050 mpu;

// Fall detection parameters
const float IMPACT_THRESHOLD = 3.5;      // Impact threshold in G's
const float FREEFALL_THRESHOLD = 0.6;    // Free fall threshold in G's
const float GYRO_THRESHOLD = 3.0;        // Rotation threshold in rad/s
const int IMPACT_WINDOW = 100;           // Impact detection window (samples)
const int MIN_FALL_DURATION = 15;        // Minimum fall duration (~150ms)
const int MAX_FALL_DURATION = 50;        // Maximum fall duration (~500ms)

// Detection variables
bool potentialFall = false;
bool fallDetected = false;
bool falseAlert = false;
int freefallStartIndex = 0;
int impactIndex = 0;
int sampleCount = 0;
unsigned long lastReportTime = 0;
const long REPORT_COOLDOWN = 10000;      // Minimum time between API reports (10 seconds)

// Circular buffers for historical data
const int BUFFER_SIZE = 200;             // 2 seconds at 100Hz
float accelBuffer[BUFFER_SIZE][3];       // x, y, z acceleration
float accelMagBuffer[BUFFER_SIZE];       // acceleration magnitude
float gyroMagBuffer[BUFFER_SIZE];        // angular velocity magnitude
int bufferIndex = 0;

// Orientation tracking
float initialAccel[3] = {0, 0, 0};
bool calibrated = false;
int calibrationCount = 0;

// Debug settings
const bool VERBOSE_OUTPUT = true;
unsigned long lastDebugOutput = 0;
const long DEBUG_INTERVAL = 500;  // Debug output every 500ms

void setup() {
  // Initialize serial communication
  Serial.begin(115200);
  
  // Initialize I2C communication
  Wire.begin(D2, D1);  // SDA, SCL pins for ESP8266 (D2=GPIO4, D1=GPIO5)
  
  Serial.println("Initializing");
  
  // Initialize WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Connected to WiFi, IP address: ");
  Serial.println(WiFi.localIP());
  Serial.print("Using server: ");
  Serial.println(serverName);

  // Initialize MPU6050
  if (!mpu.begin()) {
    Serial.println("Could not find a valid MPU6050 sensor, check wiring!");
    while (1) {
      delay(10);
    }
  }
  
  // Set accelerometer range - use 16G to capture strong impacts
  mpu.setAccelerometerRange(MPU6050_RANGE_16_G);
  
  // Set gyro range - use higher range for rapid rotations
  mpu.setGyroRange(MPU6050_RANGE_1000_DEG);
  
  // Set filter bandwidth - higher bandwidth for faster response
  mpu.setFilterBandwidth(MPU6050_BAND_44_HZ);
  
  Serial.println("MPU6050 initialized successfully!");
  Serial.println("Advanced fall detection algorithm started. Calibrating...");
  
  // Initialize buffers
  for (int i = 0; i < BUFFER_SIZE; i++) {
    accelMagBuffer[i] = 1.0;  // Initialize with 1G
    gyroMagBuffer[i] = 0.0;
    accelBuffer[i][0] = 0.0;
    accelBuffer[i][1] = 0.0;
    accelBuffer[i][2] = 1.0;  // Approximate gravity on Z
  }
}

// Helper functions
float calculateAccelMagnitude(float x, float y, float z) {
  return sqrt(x*x + y*y + z*z);
}

float calculateGyroMagnitude(float x, float y, float z) {
  return sqrt(x*x + y*y + z*z);
}

bool detectFreeFall(int currentIndex) {
  // Check for free-fall condition - significantly reduced acceleration
  int prevIndex = (currentIndex + BUFFER_SIZE - 1) % BUFFER_SIZE;
  int prevIndex2 = (currentIndex + BUFFER_SIZE - 2) % BUFFER_SIZE;
  
  return (accelMagBuffer[currentIndex] < FREEFALL_THRESHOLD && 
          accelMagBuffer[prevIndex] < FREEFALL_THRESHOLD &&
          accelMagBuffer[prevIndex2] < FREEFALL_THRESHOLD);
}

bool detectImpact(int currentIndex) {
  // Look for high acceleration impact after free-fall
  int prevIndex = (currentIndex + BUFFER_SIZE - 1) % BUFFER_SIZE;
  
  return (accelMagBuffer[currentIndex] > IMPACT_THRESHOLD && 
          accelMagBuffer[prevIndex] < IMPACT_THRESHOLD);
}

bool validateFall(int freefall_idx, int impact_idx) {
  // Calculate duration between freefall and impact
  int duration = 0;
  if (impact_idx >= freefall_idx) {
    duration = impact_idx - freefall_idx;
  } else {
    duration = BUFFER_SIZE - freefall_idx + impact_idx;
  }
  
  // Check if duration is within expected range
  if (duration < MIN_FALL_DURATION || duration > MAX_FALL_DURATION) {
    falseAlert = true;
    return false;
  }
  
  // Validate with gyroscope data - significant rotation should occur during fall
  float maxGyro = 0;
  int idx = freefall_idx;
  for (int i = 0; i < duration; i++) {
    maxGyro = max(maxGyro, gyroMagBuffer[idx]);
    idx = (idx + 1) % BUFFER_SIZE;
  }
  
  // Check orientation change after impact
  float beforeFall[3], afterImpact[3];
  int beforeIdx = (freefall_idx + BUFFER_SIZE - 5) % BUFFER_SIZE;
  int afterIdx = (impact_idx + 5) % BUFFER_SIZE;
  
  for (int i = 0; i < 3; i++) {
    beforeFall[i] = accelBuffer[beforeIdx][i];
    afterImpact[i] = accelBuffer[afterIdx][i];
  }
  
  // Calculate orientation change (dot product of normalized vectors)
  float magBefore = calculateAccelMagnitude(beforeFall[0], beforeFall[1], beforeFall[2]);
  float magAfter = calculateAccelMagnitude(afterImpact[0], afterImpact[1], afterImpact[2]);
  
  // Normalize vectors
  for (int i = 0; i < 3; i++) {
    beforeFall[i] /= magBefore;
    afterImpact[i] /= magAfter;
  }
  
  // Calculate dot product (smaller values indicate larger orientation change)
  float dotProduct = beforeFall[0]*afterImpact[0] + beforeFall[1]*afterImpact[1] + beforeFall[2]*afterImpact[2];
  
  // Fall should have significant rotation AND orientation change
  bool isValidFall = (maxGyro > GYRO_THRESHOLD && dotProduct < 0.7);
  
  // Set false alert flag if it doesn't meet criteria
  if (!isValidFall) {
    falseAlert = true;
  } else {
    falseAlert = false;
  }
  
  return isValidFall;
}

// Function to send fall event to server
void sendFallEvent(bool detected, bool isFalseAlert) {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected. Reconnecting...");
    WiFi.reconnect();
    return;
  }
  
  // Create JSON document
  StaticJsonDocument<256> jsonDoc;
  jsonDoc["detect"] = detected;
  jsonDoc["type"] = isFalseAlert ? "false alert" : "real alert";
  jsonDoc["device_id"] = deviceId;
  
  // Serialize JSON
  String jsonString;
  serializeJson(jsonDoc, jsonString);
  
  // Create secure WiFi client with insecure connection (skipping certificate validation)
  WiFiClientSecure client;
  client.setInsecure(); // Skip certificate validation
  
  Serial.print("Connecting to: ");
  Serial.println(serverName);
  
  if (!client.connect(serverName, httpsPort)) {
    Serial.println("Connection failed!");
    return;
  }
  
  // Create HTTP request
  String url = apiEndpoint;
  String request = String("POST ") + url + " HTTP/1.1\r\n" +
                  "Host: " + serverName + "\r\n" +
                  "Connection: close\r\n" +
                  "Content-Type: application/json\r\n" +
                  "Content-Length: " + jsonString.length() + "\r\n\r\n" +
                  jsonString;
  
  // Send the request
  client.print(request);
  
  // Wait for response
  unsigned long timeout = millis();
  while (client.available() == 0) {
    if (millis() - timeout > 5000) {
      Serial.println(">>> Client Timeout !");
      client.stop();
      return;
    }
  }
  
  // Read and print response
  Serial.println("Server response:");
  while (client.available()) {
    String line = client.readStringUntil('\r');
    Serial.print(line);
  }
  Serial.println();
  
  // Close connection
  client.stop();
}

void loop() {
  unsigned long currentMillis = millis();
  
  // Check if it's time to sample data
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;
    
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);
    
    // Convert acceleration to G's
    float accelX = a.acceleration.x / 9.8;
    float accelY = a.acceleration.y / 9.8;
    float accelZ = a.acceleration.z / 9.8;
    
    // Store acceleration components
    accelBuffer[bufferIndex][0] = accelX;
    accelBuffer[bufferIndex][1] = accelY;
    accelBuffer[bufferIndex][2] = accelZ;
    
    // Calculate and store magnitudes
    float accelMag = calculateAccelMagnitude(accelX, accelY, accelZ);
    float gyroMag = calculateGyroMagnitude(g.gyro.x, g.gyro.y, g.gyro.z);
    
    accelMagBuffer[bufferIndex] = accelMag;
    gyroMagBuffer[bufferIndex] = gyroMag;
    
    // Initial calibration
    if (!calibrated) {
      if (calibrationCount < 100) { // Take average of first 100 readings
        if (calibrationCount == 0) {
          initialAccel[0] = accelX;
          initialAccel[1] = accelY;
          initialAccel[2] = accelZ;
        } else {
          initialAccel[0] = (initialAccel[0] * calibrationCount + accelX) / (calibrationCount + 1);
          initialAccel[1] = (initialAccel[1] * calibrationCount + accelY) / (calibrationCount + 1);
          initialAccel[2] = (initialAccel[2] * calibrationCount + accelZ) / (calibrationCount + 1);
        }
        calibrationCount++;
      } else {
        calibrated = true;
        Serial.println("Calibration complete. Fall detection active.");
        Serial.print("Baseline acceleration: X=");
        Serial.print(initialAccel[0]);
        Serial.print(", Y=");
        Serial.print(initialAccel[1]);
        Serial.print(", Z=");
        Serial.println(initialAccel[2]);
        
        // Send initial connection message to server
        sendFallEvent(false, false);
      }
    } else {
      // Fall detection algorithm
      if (!fallDetected) {
        // Step 1: Look for free-fall condition
        if (!potentialFall && detectFreeFall(bufferIndex)) {
          potentialFall = true;
          freefallStartIndex = bufferIndex;
          Serial.println("Free-fall detected - potential fall event!");
        }
        
        // Step 2: Look for impact after free-fall
        if (potentialFall && detectImpact(bufferIndex)) {
          impactIndex = bufferIndex;
          
          // Step 3: Validate fall with additional criteria
          if (validateFall(freefallStartIndex, impactIndex)) {
            fallDetected = true;
            Serial.println("=============================");
            Serial.println("FALL DETECTED! Alert triggered!");
            Serial.println("=============================");
            
            // Send fall event to server if cooldown period has passed
            if (currentMillis - lastReportTime > REPORT_COOLDOWN) {
              sendFallEvent(true, false);
              lastReportTime = currentMillis;
            }
          } else {
            Serial.println("False alarm - event did not meet fall criteria");
            
            // Send false alarm to server if cooldown period has passed
            if (currentMillis - lastReportTime > REPORT_COOLDOWN) {
              sendFallEvent(true, true);
              lastReportTime = currentMillis;
            }
            
            potentialFall = false;
          }
        }
        
        // Timeout for potential fall detection
        if (potentialFall) {
          sampleCount++;
          if (sampleCount > IMPACT_WINDOW) {
            // Reset if no impact detected within window
            potentialFall = false;
            sampleCount = 0;
            Serial.println("Free-fall timeout - no impact detected");
          }
        }
      } else {
        // Reset fall detection after 5 seconds
        if (currentMillis - lastReportTime > 5000) {
          fallDetected = false;
          Serial.println("Fall detection reset - ready to detect new falls");
        }
      }
    }
    
    // Print debug information periodically
    if (VERBOSE_OUTPUT && (currentMillis - lastDebugOutput > DEBUG_INTERVAL)) {
      lastDebugOutput = currentMillis;
      
      Serial.print("Accel (G): X=");
      Serial.print(accelX);
      Serial.print(", Y=");
      Serial.print(accelY);
      Serial.print(", Z=");
      Serial.print(accelZ);
      Serial.print(" | Mag=");
      Serial.print(accelMag);
      Serial.print(" | Gyro Mag=");
      Serial.print(gyroMag);
      Serial.print(" | Status: ");
      if (fallDetected) {
        Serial.println("FALL DETECTED");
      } else if (potentialFall) {
        Serial.println("MONITORING POTENTIAL FALL");
      } else {
        Serial.println("NORMAL");
      }
      
      // Display server connection info
      Serial.print("Server: ");
      Serial.println(serverName);
    }
    
    // Increment buffer index
    bufferIndex = (bufferIndex + 1) % BUFFER_SIZE;
  }
}
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecureBearSSL.h>

// ===== SETTINGS =====
const char* ssid       = "divya.";
const char* password   = "jdev@bsnl";
const char* serverURL  = "https://prioribin.pythonanywhere.com/api/update_bin";
const char* wakeupURL  = "https://prioribin.pythonanywhere.com";
const char* BIN_ID     = "BIN-02";

// ===== Sensor Pins (NodeMCU) =====
const int TRIG_PIN = D5;
const int ECHO_PIN = D6;

// ===== Bin Dimensions =====
const float BIN_EMPTY_CM = 22.0;   // bin height
const float BIN_FULL_CM  = 2.0;    // distance when full
// ===== Edge Memory =====
int previous_fill_level = -1;

// ─────────────────────────────────────────

void wakeUpServer() {
  Serial.println("[Wake-Up] Pinging server...");
  
  std::unique_ptr<BearSSL::WiFiClientSecure> client(new BearSSL::WiFiClientSecure);
  client->setInsecure();

  HTTPClient http;
  http.setTimeout(15000);

  http.begin(*client, wakeupURL);
  int code = http.GET();

  Serial.println(code > 0 ? "[Wake-Up] Server awake!" : "[Wake-Up] Server slow, continuing...");
  http.end();
  delay(1000);
}

// ─────────────────────────────────────────

void setup() {

  Serial.begin(115200);
  delay(1000);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  Serial.println("--------------------------------");
  Serial.println("PRIORIBIN NODEMCU - " + String(BIN_ID));
  Serial.println("--------------------------------");

  Serial.print("Connecting to WiFi");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int attempts = 0;

  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nWiFi failed. Restarting...");
    delay(3000);
    ESP.restart();
    return;
  }

  Serial.println("\nWiFi connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  wakeUpServer();
}

// ─────────────────────────────────────────

float readDistanceCM() {

  float readings[7];
  int valid = 0;

  for (int i = 0; i < 7; i++) {

    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);

    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);

    digitalWrite(TRIG_PIN, LOW);

    long duration = pulseIn(ECHO_PIN, HIGH, 30000);

    if (duration > 0) {
      readings[valid] = (duration * 0.034) / 2.0;
      valid++;
    }

    delay(60);
  }

  if (valid == 0) return -1.0;

  // Bubble sort
  for (int i = 0; i < valid - 1; i++)
    for (int j = 0; j < valid - i - 1; j++)
      if (readings[j] > readings[j + 1]) {
        float temp = readings[j];
        readings[j] = readings[j + 1];
        readings[j + 1] = temp;
      }

  return readings[valid / 2];
}

// ─────────────────────────────────────────

int calculateFillLevel(float distance) {

  float range   = BIN_EMPTY_CM - BIN_FULL_CM;
  float filled  = BIN_EMPTY_CM - distance;
  float percent = (filled / range) * 100.0;

  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;

  return (int) percent;
}

// ─────────────────────────────────────────

void sendData(int fillLevel) {

  if (WiFi.status() != WL_CONNECTED) {

    Serial.println("WiFi dropped. Reconnecting...");
    WiFi.begin(ssid, password);

    int a = 0;

    while (WiFi.status() != WL_CONNECTED && a < 20) {
      delay(500);
      Serial.print(".");
      a++;
    }

    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("\nReconnect failed. Skipping.");
      return;
    }

    Serial.println("\nReconnected!");
  }

  String payload = "{\"bin_id\": \"" + String(BIN_ID) + "\", \"fill_level\": " + String(fillLevel) + "}";

  Serial.println("Sending: " + payload);

  int httpCode = -1;

  for (int attempt = 1; attempt <= 3; attempt++) {

    std::unique_ptr<BearSSL::WiFiClientSecure> client(new BearSSL::WiFiClientSecure);
    client->setInsecure();

    HTTPClient http;

    http.setTimeout(15000);
    http.begin(*client, serverURL);
    http.addHeader("Content-Type", "application/json");

    httpCode = http.POST(payload);

    http.end();

    if (httpCode > 0) {
      Serial.println("Sent! Code: " + String(httpCode));
      break;
    } else {
      Serial.println("Attempt " + String(attempt) + " failed. Retrying...");
      delay(3000);
    }
  }

  if (httpCode <= 0)
    Serial.println("All 3 attempts failed. Server offline.");
}

// ─────────────────────────────────────────

void loop() {

  float distance = readDistanceCM();

  if (distance <= 0) {
    Serial.println("Sensor error! Check wiring.");
    delay(2000);
    return;
  }

  int fillLevel = calculateFillLevel(distance);

  if (previous_fill_level == -1)
    previous_fill_level = fillLevel;

  if (fillLevel == 0 && previous_fill_level > 0) {
    Serial.println("[EVENT] Bin emptied by Collector!");
    previous_fill_level = 0;
  }

  Serial.println("--------------------------------------------------");
  Serial.println("BIN ID   : " + String(BIN_ID));
  Serial.println("Distance : " + String(distance, 1) + " cm");
  Serial.println("Fill     : " + String(fillLevel) + "%");

  if (fillLevel >= 90)
    Serial.println("STATUS   : CRITICAL - PRIORITY HIGH");
  else if (fillLevel >= 70)
    Serial.println("STATUS   : WARNING - PRIORITY MED");
  else
    Serial.println("STATUS   : Normal");

  sendData(fillLevel);

  previous_fill_level = fillLevel;

  Serial.println("Waiting 5 seconds...\n");

  delay(5000);
}

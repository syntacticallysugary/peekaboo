#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("========================================");
  Serial.println("ESP32-S3-EYE USB Test");
  Serial.println("========================================");
  Serial.println("If you can see this, the USB connection is working!");
  Serial.println("Press any key to reset...");
  
  while (!Serial.available()) {
    delay(100);
  }
}

void loop() {
  // Wait for input
  while (!Serial.available()) {
    delay(100);
  }
  
  // Reset on input
  Serial.println("Resetting...");
  delay(100);
  ESP.restart();
}

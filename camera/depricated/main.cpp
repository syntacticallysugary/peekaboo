// Minimal test to verify serial communication and LED control
#define LED_PIN 4

void setup() {
    Serial.begin(115200);
    delay(1000);  // Give serial time to initialize
    
    Serial.println("\n\n=== ESP32-CAM SERIAL TEST ===");
    Serial.println("If you see this, serial is working!");
    
    pinMode(LED_PIN, OUTPUT);
    Serial.println("LED pin configured");
}

void loop() {
    Serial.println("LED ON");
    digitalWrite(LED_PIN, HIGH);
    delay(1000);
    
    Serial.println("LED OFF");
    digitalWrite(LED_PIN, LOW);
    delay(1000);
}
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);

// Servo pulse limits (tune once)
#define SERVOMIN  110   // ~0Â°
#define SERVOMAX  500   // ~180Â°

int angleToPulse(int angle) {
  return map(angle, 0, 180, SERVOMIN, SERVOMAX);
}

void setup() {
  Serial.begin(9600);
  pwm.begin();
  pwm.setPWMFreq(50);  // Servo frequency
}

void loop() {
  if (Serial.available()) {
    String data = Serial.readStringUntil('\n');
    int comma = data.indexOf(',');

    if (comma > 0) {
      int channel = data.substring(0, comma).toInt();
      int angle   = data.substring(comma + 1).toInt();

      angle = constrain(angle, 0, 180);
      pwm.setPWM(channel, 0, angleToPulse(angle));
    }
  }
}
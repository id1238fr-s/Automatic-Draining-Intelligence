#include <Wire.h>
#include "HX711.h"


// --- PIN-KONFIGURATION ---
const int dirA = 12, dirB = 13, pwmA = 3, pwmB = 11, brakeA = 9, brakeB = 8;


// --- HÅRDVARA ---
HX711 scale;
const int DT_PIN = 4, SCK_PIN = 5;
const float myFactor = 997.27;


// --- REGLERINGSPARAMETRAR ---
const unsigned long hour_ms = 20000;
const float factor_P = 1500.0;
const float DEADBAND_PERCENT = 0.15;
const float PANIC_MULTIPLIER = 2.5;
const long MAX_ADJ_STEPS = 1400;
int stepDelay = 3;


// --- VARIABLER ---
float vol_goal = 15.0;
float total_drain = 0;
float current_default = 0;
int current_hour = 0;
unsigned long last_update = 0;
long current_pos_steps = 0;
float weight_at_start = 0;
bool systemActive = false;
bool isPaused = false;
int zero_drain_counter = 0;


// --- MOTORSTYRNING ---
void applyOutputs(bool aDir, int aPwm, bool bDir, int bPwm) {
  digitalWrite(dirA, aDir); digitalWrite(dirB, bDir);
  analogWrite(pwmA, aPwm);  analogWrite(pwmB, bPwm);
}


void stepSequence(int step) {
  switch (step) {
    case 0: applyOutputs(HIGH, 255, HIGH,   0); break;
    case 1: applyOutputs(HIGH, 255, HIGH, 255); break;
    case 2: applyOutputs(HIGH,   0, HIGH, 255); break;
    case 3: applyOutputs(LOW,  255, HIGH, 255); break;
    case 4: applyOutputs(LOW,  255, HIGH,   0); break;
    case 5: applyOutputs(LOW,  255, LOW,  255); break;
    case 6: applyOutputs(HIGH,   0, LOW,  255); break;
    case 7: applyOutputs(HIGH, 255, LOW,  255); break;
  }
}


void moveMotor(int steps, bool forward) {
  if (steps <= 0) return;
  digitalWrite(brakeA, LOW); digitalWrite(brakeB, LOW);


  for (int i = 0; i < steps; i++) {
    if (forward) current_pos_steps++;
    else current_pos_steps--;


    // Den robusta modulo-lösningen för stegsekvensen
    int s = (current_pos_steps % 8 + 8) % 8;
    stepSequence(s);
    delay(stepDelay);
  }
  analogWrite(pwmA, 0); analogWrite(pwmB, 0);
}


void setup() {
  Serial.begin(57600);
  pinMode(dirA, OUTPUT); pinMode(dirB, OUTPUT);
  pinMode(pwmA, OUTPUT); pinMode(pwmB, OUTPUT);
  pinMode(brakeA, OUTPUT); pinMode(brakeB, OUTPUT);
  scale.begin(DT_PIN, SCK_PIN);
  scale.set_scale(myFactor);
}


void loop() {
  // --- KOMMANDON FRÅN DATORN ---
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.startsWith("START:")) {
      int firstColon = input.indexOf(':');
      int secondColon = input.indexOf(':', firstColon + 1);
      if (secondColon == -1) {
          vol_goal = input.substring(firstColon + 1).toFloat();
      } else {
          vol_goal = input.substring(firstColon + 1, secondColon).toFloat();
      }
      current_hour = 0; total_drain = 0;
      current_default = vol_goal / 24.0;
      scale.tare();
      weight_at_start = scale.get_units(20);
      last_update = millis();
      systemActive = true;
      isPaused = false;
      Serial.println("T:0|Mal:0.00|Nu:0.00|Tryck:0.0|Status:STARTAR...");
    }
    else if (input == "PAUSE") { isPaused = true; Serial.println("SYS:PAUSAD"); }
    else if (input == "RESUME") { isPaused = false; last_update = millis(); Serial.println("SYS:ÅTERUPPTAGET"); }
    else if (input == "STOP") { systemActive = false; Serial.println("SYS:AVSTÄNGT"); }
  }


  // --- SJÄLVA REGLERINGEN ---
  if (systemActive && !isPaused) {
    if (current_hour < 24 && (millis() - last_update >= hour_ms)) {
      current_hour++;
      float weight_now = scale.get_units(15);
      float dranerat_nu = max(0.0, weight_now - weight_at_start);
     
      float error = dranerat_nu - current_default;
      float dynamic_deadband = max(0.02f, current_default * DEADBAND_PERCENT);
      float dynamic_panic = current_default * PANIC_MULTIPLIER;


      String status = "OK";
      bool do_move = false;
      bool move_up = false;
      long steps_to_move = 0;


      if (dranerat_nu < 0.005) {
          status = "NOLLFLÖDE";
          do_move = true; move_up = false;
          steps_to_move = (zero_drain_counter >= 1) ? 1500 : 800;
          zero_drain_counter++;
      }
      else if (dranerat_nu >= dynamic_panic) {
          status = "FLÖDESPIK";
          do_move = true; move_up = true;
          steps_to_move = MAX_ADJ_STEPS;
          zero_drain_counter = 0;
      }
      else if (abs(error) > dynamic_deadband) {
          do_move = true;
          steps_to_move = min((long)(abs(error) * factor_P), MAX_ADJ_STEPS);
          if (error > 0) { status = "HÖGT FLÖDE"; move_up = true; }
          else { status = "LÅGT FLÖDE"; move_up = false; }
          zero_drain_counter = 0;
      } else {
          status = "INOM DEADBAND";
          zero_drain_counter = 0;
      }


      // Kör motorn
      if (do_move) moveMotor(steps_to_move, move_up);


      // Beräkna mmHg för utskrift
      float currentmmHg = (current_pos_steps / 1000.0) / 1.36;


      // Rapportera i originalformatet
      Serial.print("T:");      Serial.print(current_hour);
      Serial.print("|Mal:");   Serial.print(current_default, 2);
      Serial.print("|Nu:");    Serial.print(dranerat_nu, 2);
      Serial.print("|Tryck:"); Serial.print(currentmmHg, 1);
      Serial.print("|Status:"); Serial.println(status);


      // Uppdatera mål inför nästa timme
      total_drain += dranerat_nu;
      int hours_left = 24 - current_hour;
      if (hours_left > 0) {
        current_default = constrain((vol_goal - total_drain) / (float)hours_left, 0.05, 20.0);
      }
      weight_at_start = scale.get_units(10);
      last_update = millis();
    }
  }
}




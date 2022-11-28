void setup() {
  pinMode(8,OUTPUT);
}

unsigned long previousMillis = 0; 
const long delayTime = 7200000;

void loop(){
    unsigned long currentMillis = millis(); // 현재시간 담기
    int level = digitalRead(7);// 수위센서 신호 측정.
    if(level == HIGH)          // 수위센서 액체 감지되면
    digitalWrite(8,HIGH);     // 8번 핀에 HIGH를 출력 릴레이 ON
    else                      // 그렇지 않고
    {
      if(currentMillis - previousMillis >= delayTime)
      {
        digitalWrite(8,LOW);      // 8번 핀에 LOW를 출력합니다 릴레이 OFF
        previousMillis = currentMillis;
      }
    } 
}

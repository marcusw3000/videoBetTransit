import cv2
import time
from ultralytics import YOLO

print("Carregando modelo YOLOv8m...")
model = YOLO("yolov8m.pt")
print("Modelo carregado!")

stream_url = "https://34.104.32.249.nip.io/SP125-KM093B/stream.m3u8"
print(f"Conectando ao stream: {stream_url}")
cap = cv2.VideoCapture(stream_url)

if not cap.isOpened():
    print("ERRO: Falha ao abrir stream.")
    exit(1)

print("Stream aberto! Processando frames...")
frame_count = 0
start_time = time.time()

while True:
    ret, frame = cap.read()
    if not ret:
        print("Fim do stream ou erro de leitura.")
        break
        
    frame_count += 1
    
    if frame_count % 30 == 0:
        results = model(frame, verbose=False, conf=0.25)
        boxes = results[0].boxes
        
        vehicles = 0
        for box in boxes:
            cls_id = int(box.cls[0].item())
            if cls_id in [2, 3, 5, 7]: # cars, motorcycles, bus, trucks
                vehicles += 1
                
        print(f"Frame {frame_count}: detectados {vehicles} veículos")
        
    if time.time() - start_time > 30:
        print("Teste de 30 segundos concluído.")
        break

cap.release()
print("Fim.")

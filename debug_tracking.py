"""
Script de diagnóstico rápido: testa se o stream, detecção e tracking estão
funcionando corretamente. Roda por ~15 segundos e imprime resultados.
"""
import time
import cv2
from ultralytics import YOLO

STREAM = "https://34.104.32.249.nip.io/SP125-KM093B/stream.m3u8"
MODEL = "yolov8s.pt"
TRACKER = "botsort_traffic.yaml"
CONF = 0.20
CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck

print("=" * 60)
print("DIAGNÓSTICO DE TRACKING")
print("=" * 60)

# 1. Carregar modelo
print(f"\n[1] Carregando modelo {MODEL}...")
model = YOLO(MODEL)
print("    OK")

# 2. Abrir stream
print(f"\n[2] Abrindo stream: {STREAM}")
cap = cv2.VideoCapture(STREAM, cv2.CAP_FFMPEG)
if not cap.isOpened():
    print("    ERRO: não conseguiu abrir o stream!")
    exit(1)
print("    OK")

# 3. Ler um frame para verificar dimensões
ret, frame = cap.read()
if not ret:
    print("    ERRO: não conseguiu ler o primeiro frame!")
    exit(1)

h, w = frame.shape[:2]
print(f"    Resolução do frame: {w}x{h}")

# 4. Testar detecção SEM tracking
print(f"\n[3] Testando detecção SEM tracking (conf={CONF})...")
results_detect = model(frame, conf=CONF, classes=CLASSES, verbose=False)
boxes_detect = results_detect[0].boxes
n_detect = len(boxes_detect) if boxes_detect is not None else 0
print(f"    Detecções sem tracking: {n_detect}")

if boxes_detect is not None and n_detect > 0:
    for i, box in enumerate(boxes_detect):
        cls_id = int(box.cls[0].item())
        conf_val = float(box.conf[0].item())
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
        print(f"    [{i}] cls={cls_id} conf={conf_val:.2f} bbox=({x1},{y1},{x2},{y2})")

# 5. Testar tracking
print(f"\n[4] Testando TRACKING com {TRACKER} por 10 segundos...")
cap.release()
cap = cv2.VideoCapture(STREAM, cv2.CAP_FFMPEG)

frame_count = 0
tracked_frames = 0
total_detections = 0
total_tracked = 0
start = time.time()

while time.time() - start < 15:
    ret, frame = cap.read()
    if not ret:
        continue

    frame_count += 1

    results = model.track(
        frame,
        persist=True,
        tracker=TRACKER,
        conf=CONF,
        classes=CLASSES,
        verbose=False,
    )

    boxes = results[0].boxes
    n_boxes = len(boxes) if boxes is not None else 0
    has_ids = boxes.id is not None if boxes is not None else False
    n_ids = len(boxes.id) if has_ids else 0

    total_detections += n_boxes

    if has_ids:
        tracked_frames += 1
        total_tracked += n_ids

    if frame_count % 15 == 0:
        print(
            f"    frame={frame_count:4d} | detecções={n_boxes:3d} | "
            f"tracked={n_ids:3d} | has_ids={has_ids}"
        )

cap.release()

print(f"\n{'=' * 60}")
print(f"RESULTADO:")
print(f"  Frames processados: {frame_count}")
print(f"  Total detecções: {total_detections}")
print(f"  Frames com track IDs: {tracked_frames}")
print(f"  Total objetos trackados: {total_tracked}")

if total_detections == 0:
    print("\n  ⚠ PROBLEMA: Nenhuma detecção! Verificar modelo/conf/classes/stream.")
elif total_tracked == 0:
    print("\n  ⚠ PROBLEMA: Detecções OK mas sem tracking! Verificar tracker YAML.")
else:
    print("\n  ✓ Tracking funcionando!")

print("=" * 60)

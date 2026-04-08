import argparse
import json
import os
from collections import Counter, defaultdict
from statistics import mean


def load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    index = (len(sorted_values) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = index - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def format_float(value: float) -> str:
    return f"{value:.2f}"


def summarize_cases(cases: list[dict], cfg: dict):
    print("=== Resumo Geral ===")
    print(f"Casos: {len(cases)}")
    print(f"Cameras: {', '.join(sorted({case.get('cameraId', '-') for case in cases})) or '-'}")
    print()

    print("=== Casos por Tipo ===")
    for case_type, count in Counter(case.get("caseType", "unknown") for case in cases).most_common():
        print(f"- {case_type}: {count}")
    print()

    print("=== Casos por Camera ===")
    for camera_id, count in Counter(case.get("cameraId", "unknown") for case in cases).most_common():
        print(f"- {camera_id}: {count}")
    print()

    detections_by_class = defaultdict(list)
    latest_cases = []

    for case in cases:
        latest_cases.append(
            {
                "savedAt": case.get("savedAt"),
                "frameId": case.get("frameId"),
                "caseType": case.get("caseType"),
                "imagePath": case.get("imagePath"),
                "detections": len(case.get("detections", [])),
            }
        )
        for det in case.get("detections", []):
            bbox = det.get("bbox", {})
            area = max(0, int(bbox.get("w", 0))) * max(0, int(bbox.get("h", 0)))
            detections_by_class[det.get("vehicleType", "unknown")].append(
                {
                    "confidence": float(det.get("confidence", 0.0)),
                    "area": area,
                    "counted": bool(det.get("counted", False)),
                    "insideRoi": bool(det.get("insideRoi", False)),
                    "crossedLine": bool(det.get("crossedLine", False)),
                    "hits": int(det.get("hits", 0)),
                }
            )

    print("=== Resumo por Classe ===")
    for vehicle_name in sorted(detections_by_class):
        rows = detections_by_class[vehicle_name]
        confidences = sorted(row["confidence"] for row in rows)
        areas = sorted(row["area"] for row in rows)
        hits = sorted(row["hits"] for row in rows)
        thresholds = cfg.get("class_thresholds", {}).get(vehicle_name, {})
        current_conf = float(thresholds.get("min_confidence", cfg.get("conf", 0.2)))
        current_area = int(thresholds.get("min_bbox_area", cfg.get("min_bbox_area", 100)))
        current_hits = int(thresholds.get("min_hits_to_count", cfg.get("min_hits_to_count", 4)))

        below_conf = sum(1 for row in rows if row["confidence"] < current_conf)
        below_area = sum(1 for row in rows if row["area"] < current_area)
        below_hits = sum(1 for row in rows if row["hits"] < current_hits)

        print(f"- {vehicle_name}")
        print(f"  deteccoes: {len(rows)} | counted: {sum(row['counted'] for row in rows)} | crossed: {sum(row['crossedLine'] for row in rows)} | inside_roi: {sum(row['insideRoi'] for row in rows)}")
        print(f"  conf atual: {format_float(current_conf)} | media: {format_float(mean(confidences))} | p25: {format_float(percentile(confidences, 0.25))} | mediana: {format_float(percentile(confidences, 0.50))} | p75: {format_float(percentile(confidences, 0.75))}")
        print(f"  area atual: {current_area} | media: {int(mean(areas))} | p25: {int(percentile(areas, 0.25))} | mediana: {int(percentile(areas, 0.50))} | p75: {int(percentile(areas, 0.75))}")
        print(f"  hits atual: {current_hits} | media: {format_float(mean(hits))} | p25: {format_float(percentile(hits, 0.25))} | mediana: {format_float(percentile(hits, 0.50))} | p75: {format_float(percentile(hits, 0.75))}")
        print(f"  abaixo do threshold atual -> conf: {below_conf}, area: {below_area}, hits: {below_hits}")
    print()

    print("=== Ultimos Casos ===")
    for case in sorted(latest_cases, key=lambda row: row.get("savedAt") or "", reverse=True)[:10]:
        print(
            f"- {case['savedAt']} | frame={case['frameId']} | tipo={case['caseType']} | "
            f"deteccoes={case['detections']} | {case['imagePath']}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Resume casos de calibracao salvos em calibration_review/cases.jsonl."
    )
    parser.add_argument(
        "--cases",
        default=os.path.join("calibration_review", "cases.jsonl"),
        help="Caminho do arquivo JSONL de casos de calibracao.",
    )
    parser.add_argument(
        "--config",
        default=os.path.join("vision-worker", "config.json"),
        help="Caminho do config.json oficial do worker.",
    )
    args = parser.parse_args()

    cases = load_jsonl(args.cases)
    if not cases:
        print(f"Nenhum caso encontrado em {args.cases}")
        return

    cfg = load_config(args.config)
    summarize_cases(cases, cfg)


if __name__ == "__main__":
    main()

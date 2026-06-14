import time
import cv2
import numpy as np
from ultralytics import YOLO
from boxmot.trackers.ocsort.ocsort import OcSort
from boxmot.trackers.bytetrack.bytetrack import ByteTrack
from boxmot.trackers.botsort.botsort import BotSort

# Analizar 1 de cada 5 frames del video original
FRAME_SKIP = 5

# Ancho máximo al que se redimensiona internamente el frame antes de pasarlo al modelo
MAX_WIDTH = 2560

# Margen relativo del borde del frame que se excluye del conteo
MARGEN_RELATIVO = 0.10

# Resolución del video anotado de salida (lo que ve el operador)
OUT_W, OUT_H = 1280, 720

# ── Tracker activo ──────────────────────────────────────────────
# Cambia esta línea para alternar entre trackers:
# TRACKER = "bytetrack"   # Rápido, ligero, bueno para movimiento fluido
# TRACKER = "botsort"     # Mayor precisión, mejor con muchas oclusiones
TRACKER = "ocsort"        # Robusto ante oclusiones largas


def _crear_tracker(tracker: str):
    if tracker == "botsort":
        return BotSort()
    elif tracker == "ocsort":
        return OcSort()
    else:
        return ByteTrack()


class ProcesadorVideoYOLO:
    def __init__(self, modelo_path: str = "best.pt"):
        self.model = YOLO(modelo_path)
        print("Clases del modelo:", self.model.names)

    def procesar(self, video_entrada_path: str, video_salida_path: str) -> dict:
        print(f"Iniciando procesamiento: {video_entrada_path}")
        t_inicio = time.time()

        cap = cv2.VideoCapture(video_entrada_path)
        if not cap.isOpened():
            raise Exception("Error al abrir el archivo de video.")

        width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps          = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        fps_salida = max(1, fps / FRAME_SKIP)

        scale  = min(1.0, MAX_WIDTH / width)
        proc_w = int(width  * scale)
        proc_h = int(height * scale)

        margen_x = int(proc_w * MARGEN_RELATIVO)
        margen_y = int(proc_h * MARGEN_RELATIVO)

        print(
            f"  Video original : {width}x{height} @ {fps:.1f}fps  ({total_frames} frames)\n"
            f"  Procesamiento  : {proc_w}x{proc_h} — 1 de cada {FRAME_SKIP} frames "
            f"(~{fps_salida:.1f}fps efectivos)\n"
            f"  Tracker        : {TRACKER}\n"
            f"  Frames a proc. : ~{total_frames // FRAME_SKIP}"
        )

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out    = cv2.VideoWriter(video_salida_path, fourcc, fps_salida, (OUT_W, OUT_H))

        tracker     = _crear_tracker(TRACKER)
        ids_unicos  = set()
        frames_proc = 0
        frame_idx   = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            if frame_idx % FRAME_SKIP != 0:
                continue

            frames_proc += 1

            if scale < 1.0:
                frame_proc = cv2.resize(frame, (proc_w, proc_h))
            else:
                frame_proc = frame

            # Detección con YOLO
            resultados = self.model.predict(
                frame_proc,
                verbose=False,
                conf=0.5,
                iou=0.5,
                imgsz=proc_w,
            )

            # Preparar detecciones para boxmot: Nx6 [x1,y1,x2,y2,conf,cls]
            dets = np.empty((0, 6))
            if resultados[0].boxes is not None and len(resultados[0].boxes):
                boxes = resultados[0].boxes.xyxy.cpu().numpy()
                confs = resultados[0].boxes.conf.cpu().numpy().reshape(-1, 1)
                clss  = resultados[0].boxes.cls.cpu().numpy().reshape(-1, 1)
                dets  = np.hstack([boxes, confs, clss])

            # Actualizar tracker → Nx8 [x1,y1,x2,y2,id,conf,cls,idx]
            tracks = tracker.update(dets, frame_proc)

            frame_anotado = frame_proc.copy()

            cv2.rectangle(
                frame_anotado,
                (margen_x, margen_y),
                (proc_w - margen_x, proc_h - margen_y),
                (255, 0, 0), 2,
            )

            if tracks is not None and len(tracks):
                for track in tracks:
                    x1, y1, x2, y2, track_id = (
                        int(track[0]), int(track[1]),
                        int(track[2]), int(track[3]),
                        int(track[4]),
                    )
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    dentro_roi = (
                        margen_x < cx < proc_w - margen_x
                        and margen_y < cy < proc_h - margen_y
                    )
                    if dentro_roi:
                        ids_unicos.add(track_id)

                    cv2.rectangle(frame_anotado, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(
                        frame_anotado,
                        f"ID {track_id}",
                        (x1, max(0, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 0), 2, cv2.LINE_AA,
                    )

            conteo_actual = len(ids_unicos)
            cv2.putText(
                frame_anotado,
                f"Melones: {conteo_actual}",
                (30, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2, (0, 255, 0), 3, cv2.LINE_AA,
            )

            frame_out = cv2.resize(frame_anotado, (OUT_W, OUT_H))
            out.write(frame_out)

            if frames_proc % 30 == 0:
                print(f"  Progreso: {frames_proc} frames procesados — {conteo_actual} melones únicos")

        cap.release()
        out.release()
        cv2.destroyAllWindows()

        tiempo_seg = int(time.time() - t_inicio)
        total      = len(ids_unicos)

        print(
            f"Procesamiento finalizado.\n"
            f"  Total melones: {total}\n"
            f"  Frames proc.: {frames_proc}\n"
            f"  Tiempo total: {tiempo_seg}s"
        )

        return {
            "total": total,
            "tiempo_segundos": tiempo_seg,
            "frames_procesados": frames_proc,
        }
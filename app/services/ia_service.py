import cv2
from ultralytics import YOLO


class ProcesadorVideoYOLO:
    def __init__(self, modelo_path: str = "best.pt"):
        self.model = YOLO(modelo_path)
        print("Clases del modelo:", self.model.names)

    def procesar(self, video_entrada_path: str, video_salida_path: str) -> dict:
        print(f"Iniciando procesamiento: {video_entrada_path}")

        cap = cv2.VideoCapture(video_entrada_path)
        if not cap.isOpened():
            raise Exception("Error al abrir el archivo de video.")

        width       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps         = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        # ── Parámetros de preprocesamiento ──────────────────────────
        TARGET_FPS   = 6          # frames efectivos a procesar por segundo
        FRAME_SKIP   = max(1, fps // TARGET_FPS)  # procesar 1 de cada N frames
        MAX_WIDTH    = 1920       # máximo ancho de procesamiento (1080p)
        scale        = min(1.0, MAX_WIDTH / width)
        proc_w       = int(width  * scale)
        proc_h       = int(height * scale)

        # ── VideoWriter a 720p para el video anotado ────────────────
        out_w, out_h = 1280, 720
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        out    = cv2.VideoWriter(video_salida_path, fourcc, TARGET_FPS, (out_w, out_h))

        ids_unicos    = set()
        frames_proc   = 0

        porcentaje_margen = 0.10
        margen_x = int(proc_w * porcentaje_margen)
        margen_y = int(proc_h * porcentaje_margen)

        resultados_track = self.model.track(
            source=video_entrada_path,
            persist=True,
            stream=True,
            verbose=False,
            conf=0.5,
            iou=0.5,
            tracker="bytetrack.yaml",
            vid_stride=FRAME_SKIP,   # submuestreo de frames
            imgsz=proc_w             # redimensionamiento interno del modelo
        )

        for resultado in resultados_track:
            frames_proc += 1

            frame_anotado = resultado.plot()

            # Dibujar región de interés
            cv2.rectangle(frame_anotado, (margen_x, margen_y),
                          (proc_w - margen_x, proc_h - margen_y),
                          (255, 0, 0), 2)

            if resultado.boxes.id is not None:
                cajas     = resultado.boxes.xyxy.cpu().numpy()
                track_ids = resultado.boxes.id.int().cpu().tolist()

                for caja, track_id in zip(cajas, track_ids):
                    x1, y1, x2, y2 = caja
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    if (margen_x < cx < proc_w - margen_x) and (margen_y < cy < proc_h - margen_y):
                        ids_unicos.add(track_id)

            conteo_actual = len(ids_unicos)
            cv2.putText(frame_anotado, f"Melones: {conteo_actual}",
                        (30, 60), cv2.FONT_HERSHEY_SIMPLEX,
                        1.2, (0, 255, 0), 3, cv2.LINE_AA)

            # Escalar a 720p antes de escribir
            frame_720 = cv2.resize(frame_anotado, (out_w, out_h))
            out.write(frame_720)

            if frames_proc % 30 == 0:
                print(f"Progreso: {frames_proc} frames procesados — {conteo_actual} melones únicos...")

        out.release()
        cv2.destroyAllWindows()

        total = len(ids_unicos)
        print(f"Procesamiento finalizado. Total melones: {total}")

        return {
            "total": total,
            "tiempo_segundos": 0  # TODO: medir tiempo real con time.time()
        }
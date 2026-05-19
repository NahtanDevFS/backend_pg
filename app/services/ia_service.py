import time
import cv2
from ultralytics import YOLO

# Analizar 1 de cada 5 frames del video original
FRAME_SKIP = 5

# Ancho máximo al que se redimensiona internamente el frame antes de pasarlo al modelo
MAX_WIDTH = 2560

# Margen relativo del borde del frame que se excluye del conteo (evita contar melones que entran/salen de cuadro a medias).
MARGEN_RELATIVO = 0.10

# Resolución del video anotado de salida (lo que ve el operador)
OUT_W, OUT_H = 1280, 720


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

        width    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps   = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        # FPS efectivos que tendrá el video anotado de salida
        fps_salida = max(1, fps / FRAME_SKIP)

        # Escala para no superar MAX_WIDTH (si el video ya es menor, scale=1.0)
        scale  = min(1.0, MAX_WIDTH / width)
        proc_w = int(width  * scale)
        proc_h = int(height * scale)

        # Márgenes en píxeles para la región de interés
        margen_x = int(proc_w * MARGEN_RELATIVO)
        margen_y = int(proc_h * MARGEN_RELATIVO)

        print(
            f"  Video original : {width}x{height} @ {fps:.1f}fps  ({total_frames} frames)\n"
            f"  Procesamiento  : {proc_w}x{proc_h} — 1 de cada {FRAME_SKIP} frames "
            f"(~{fps_salida:.1f}fps efectivos)\n"
            f"  Frames a proc. : ~{total_frames // FRAME_SKIP}"
        )

        # VideoWriter para el video anotado
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        out    = cv2.VideoWriter(video_salida_path, fourcc, fps_salida, (OUT_W, OUT_H))

        ids_unicos  = set()
        frames_proc = 0

        #Tracking con YOLO, vid_stride=FRAME_SKIP le indica a YOLO que salte 5-1 frames entre
        resultados_track = self.model.track(
            source=video_entrada_path,
            persist=True,
            stream=True,
            verbose=False,
            conf=0.5,
            iou=0.5,
            # tracker="bytetrack.yaml", #Rápido, ligero, bueno para movimiento fluido
            # tracker="botsort.yaml", #Mayor precisión, mejor con muchas oclusiones
            tracker="ocsort.yaml",  #Robusto ante oclusiones largas
            vid_stride=FRAME_SKIP,
            imgsz=proc_w,
        )

        for resultado in resultados_track:
            frames_proc += 1

            frame_anotado = resultado.plot()

            # Dibujar región de interés
            cv2.rectangle(
                frame_anotado,
                (margen_x, margen_y),
                (proc_w - margen_x, proc_h - margen_y),
                (255, 0, 0), 2,
            )

            if resultado.boxes.id is not None:
                cajas     = resultado.boxes.xyxy.cpu().numpy()
                track_ids = resultado.boxes.id.int().cpu().tolist()

                for caja, track_id in zip(cajas, track_ids):
                    x1, y1, x2, y2 = caja
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    dentro_roi = (
                        margen_x < cx < proc_w - margen_x
                        and margen_y < cy < proc_h - margen_y
                    )
                    if dentro_roi:
                        ids_unicos.add(track_id)

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

        out.release()
        cv2.destroyAllWindows()

        tiempo_seg = int(time.time() - t_inicio)
        total      = len(ids_unicos)

        print(
            f"Procesamiento finalizado.\n"
            f"  Total melones  : {total}\n"
            f"  Frames proc.   : {frames_proc}\n"
            f"  Tiempo total   : {tiempo_seg}s"
        )

        return {
            "total": total,
            "tiempo_segundos": tiempo_seg,
            "frames_procesados": frames_proc,
        }
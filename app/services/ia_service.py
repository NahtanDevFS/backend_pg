import cv2
from ultralytics import YOLO

class ProcesadorVideoYOLO:
    def __init__(self, modelo_path: str = "best.pt"):
        self.model = YOLO(modelo_path)
        print("Clases entrenadas en este modelo:", self.model.names)

    def procesar(self, video_entrada_path: str, video_salida_path: str) -> dict:
        print(f"Iniciando procesamiento de video: {video_entrada_path}")

        cap = cv2.VideoCapture(video_entrada_path)
        if not cap.isOpened():
            raise Exception("Error al abrir el archivo de video.")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        cuatrocc = cv2.VideoWriter_fourcc(*'avc1')
        out = cv2.VideoWriter(video_salida_path, cuatrocc, fps, (width, height))

        ids_melones_unicos = set()
        frames_procesados = 0

        porcentaje_margen = 0.10
        margen_x = int(width * porcentaje_margen)
        margen_y = int(height * porcentaje_margen)

        resultados_track = self.model.track(
            source=video_entrada_path,
            persist=True,
            stream=True,
            verbose=False,
            conf=0.5,
            iou=0.5,
            tracker="bytetrack.yaml"
        )

        for resultado in resultados_track:
            frames_procesados += 1

            frame_anotado = resultado.plot()

            cv2.rectangle(
                img=frame_anotado,
                pt1=(margen_x, margen_y),
                pt2=(width - margen_x, height - margen_y),
                color=(255, 0, 0),
                thickness=2
            )

            if resultado.boxes.id is not None:
                cajas = resultado.boxes.xyxy.cpu().numpy()
                track_ids = resultado.boxes.id.int().cpu().tolist()

                for caja, track_id in zip(cajas, track_ids):
                    x1, y1, x2, y2 = caja

                    centro_x = (x1 + x2) / 2
                    centro_y = (y1 + y2) / 2

                    if (margen_x < centro_x < (width - margen_x)) and (margen_y < centro_y < (height - margen_y)):
                        ids_melones_unicos.add(track_id)

            conteo_actual = len(ids_melones_unicos)
            texto_conteo = f"Melones Contados: {conteo_actual}"

            cv2.putText(
                img=frame_anotado,
                text=texto_conteo,
                org=(30, 60),
                fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                fontScale=1.2,
                color=(0, 255, 0),
                thickness=3,
                lineType=cv2.LINE_AA
            )

            out.write(frame_anotado)

            if frames_procesados % 30 == 0:
                print(f"Progreso: {frames_procesados}/{total_frames} frames procesados...")

        cap.release()
        out.release()
        cv2.destroyAllWindows()

        cantidad_total = len(ids_melones_unicos)
        print(f"Procesamiento finalizado. Melones únicos contados: {cantidad_total}")

        return {
            "maduros": cantidad_total,
            "inmaduros": 0,
            "tiempo_segundos": 0
        }
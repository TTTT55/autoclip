"""Lightweight content-aware horizontal framing for vertical clips.

The renderer ultimately needs a 9:16 window from a landscape source. This module
samples the source clip and estimates the visually important horizontal region
using OpenCV saliency plus face detection. It returns smoothed normalized crop
centers; rendering remains in FFmpeg.
"""

import os


def _clamp(value, low, high):
    return max(low, min(high, value))


def _fallback_points(duration):
    return [(0.0, 0.5), (max(0.0, float(duration)), 0.5)]


def find_reframe_points(video, start, end, sample_interval=1.0):
    """Return [(relative_time, normalized_x_center), ...] for a landscape clip."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return _fallback_points(end - start)

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        return _fallback_points(end - start)

    duration = max(0.0, float(end) - float(start))
    if duration <= 0:
        cap.release()
        return _fallback_points(duration)

    try:
        face_cascade = cv2.CascadeClassifier(
            os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        )
    except Exception:
        face_cascade = None

    # Fine-grained saliency is available in opencv-contrib-python. If unavailable,
    # use a lightweight contrast/edge saliency approximation below.
    saliency = None
    try:
        if hasattr(cv2, "saliency"):
            saliency = cv2.saliency.StaticSaliencyFineGrained_create()
    except Exception:
        saliency = None

    points = []
    t = 0.0
    while t < duration + 0.001:
        cap.set(cv2.CAP_PROP_POS_MSEC, (float(start) + t) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += sample_interval
            continue

        h, w = frame.shape[:2]
        if w <= h:
            points.append((t, 0.5))
            t += sample_interval
            continue

        target_x = 0.5
        confidence = 0.0

        # Face position gets strong priority for talking-head material.
        if face_cascade is not None:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, (640, max(1, int(640 * h / w))))
                faces = face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(32, 32)
                )
                if len(faces):
                    areas = [fw * fh for _, _, fw, fh in faces]
                    x, y, fw, fh = faces[int(np.argmax(areas))]
                    face_center = (x + fw / 2) / gray.shape[1]
                    target_x = float(face_center)
                    confidence = 1.0
            except Exception:
                pass

        # Saliency/contrast provides a useful cue when the important object is not
        # a face (e.g. a phone, product, screen, or object shown beside the speaker).
        try:
            small = cv2.resize(frame, (320, max(1, int(320 * h / w))))
            if saliency is not None:
                ok_sal, sal_map = saliency.computeSaliency(small)
                if ok_sal:
                    sal_map = cv2.GaussianBlur(sal_map, (0, 0), 3)
                else:
                    sal_map = None
            else:
                gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray_small, (0, 0), 9)
                sal_map = cv2.absdiff(gray_small, blur).astype("float32")
                sal_map = cv2.GaussianBlur(sal_map, (0, 0), 5)

            if sal_map is not None:
                sal_map = np.asarray(sal_map, dtype=np.float32)
                sal_map -= sal_map.min()
                max_value = float(sal_map.max())
                if max_value > 1e-6:
                    sal_map /= max_value
                    # Ignore weak background saliency.
                    sal_map[sal_map < 0.35] = 0
                    total = float(sal_map.sum())
                    if total > 1e-6:
                        xs = np.arange(sal_map.shape[1], dtype=np.float32)[None, :]
                        sal_x = float((sal_map * xs).sum() / total) / max(1, sal_map.shape[1] - 1)
                        if confidence >= 1.0:
                            target_x = 0.75 * target_x + 0.25 * sal_x
                        else:
                            target_x = sal_x
                            confidence = min(0.75, total / (sal_map.size * 0.15))
        except Exception:
            pass

        points.append((t, _clamp(target_x, 0.05, 0.95)))
        t += sample_interval

    cap.release()

    if len(points) < 2:
        return _fallback_points(duration)

    # Smooth movement so the crop behaves like a camera operator rather than
    # jumping between detections from frame to frame.
    smoothed = []
    previous = 0.5
    max_step = 0.16  # normalized frame width per second
    for i, (time, x) in enumerate(points):
        if i == 0:
            previous = x
        else:
            dt = max(0.1, time - points[i - 1][0])
            limit = max_step * dt
            x = _clamp(x, previous - limit, previous + limit)
            x = 0.65 * previous + 0.35 * x
            previous = x
        smoothed.append((time, _clamp(previous, 0.05, 0.95)))

    return smoothed

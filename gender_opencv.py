"""
Gender estimate via OpenCV DNN (Caffe gender net) + Haar face detection.
Downloads model files on first use (~500 KB total). Works without TensorFlow/DeepFace.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request

import cv2
import numpy as np

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "gender")
_PROTO = os.path.join(_DIR, "gender_deploy.prototxt")
_CAFFE = os.path.join(_DIR, "gender_net.caffemodel")
# Prototxt from LearnOpenCV repo; weights hosted on Dropbox (see AgeGender/README.md).
_PROTO_URL = (
    "https://raw.githubusercontent.com/spmallick/learnopencv/master/"
    "AgeGender/gender_deploy.prototxt"
)
_CAFFE_URL = "https://www.dropbox.com/s/iyv483wz7ztr9gh/gender_net.caffemodel?dl=1"

_MODEL_MEAN = (78.4263377603, 87.7689143744, 114.895847746)
_LABELS = ("Male", "Female")

_net = None
_cascade: cv2.CascadeClassifier | None = None


def _download(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "EmergencyAlert/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    if len(data) < 500:
        raise RuntimeError(f"Download too small from {url}")
    with open(dest, "wb") as f:
        f.write(data)


def _ensure_models() -> None:
    global _net, _cascade
    os.makedirs(_DIR, exist_ok=True)
    if not os.path.isfile(_PROTO):
        _download(_PROTO_URL, _PROTO)
    if not os.path.isfile(_CAFFE):
        _download(_CAFFE_URL, _CAFFE)
    if _net is None:
        _net = cv2.dnn.readNetFromCaffe(_PROTO, _CAFFE)
    if _cascade is None:
        path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        _cascade = cv2.CascadeClassifier(path)
        if _cascade.empty():
            raise RuntimeError("OpenCV Haar cascade missing")


def classify_gender_from_image_paths(paths: list[str]) -> str:
    if not paths:
        return "No images"

    try:
        _ensure_models()
    except (urllib.error.URLError, OSError, RuntimeError) as e:
        return f"Unavailable ({e})"

    assert _net is not None and _cascade is not None

    for path in paths:
        img = cv2.imread(path)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = _cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(48, 48))
        if len(faces) == 0:
            continue
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face = img[y : y + h, x : x + w]
        if face.size == 0:
            continue
        blob = cv2.dnn.blobFromImage(
            face, 1.0, (227, 227), _MODEL_MEAN, swapRB=False, crop=False
        )
        _net.setInput(blob)
        preds = _net.forward()
        idx = int(np.argmax(preds[0]))
        idx = max(0, min(idx, len(_LABELS) - 1))
        return _LABELS[idx]

    return "Unknown (no face detected)"

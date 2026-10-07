#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArUco 自動切り抜きキャプチャシステム（Android / Termux 版）
 - IP Webcam 等の MJPEG ストリームを受信（localhost:8080/video）
 - ArUco 4マーカー検出 → 透視変換で切り抜き → GAS 経由で Google Drive へ
 - Flask でステータス画面とライブプレビューを localhost:5000 で配信
起動:
    python main.py
ブラウザ:
    http://localhost:5000
"""

import base64
import datetime
import json
import threading
import time
import urllib.request

import cv2
import numpy as np
import requests
from flask import Flask, Response, jsonify, redirect, render_template_string

# ===================== 設定項目 =====================
GAS_URL = "https://script.google.com/macros/s/AKfycbyEUdak05s3S0VzILdb81tOL12qP46cpXgWyrYxYsFAWlsueCozfnheESTSyxR25lJf/exec"

# MJPEG ストリーム（IP Webcam の既定値。IP Webcam の設定画面で確認したURLに合わせる）
STREAM_URL = "http://127.0.0.1:8080/video"

# ステータス監視用のカメラID（同じスマホ内で重複しない値）
CAM_ID = "phone0"

MIN_INTERVAL = 5.0          # チャタリング防止（秒）
REQUIRED_STABLE_TIME = 1.0  # 4つ認識し続ける必要がある時間（秒）
OUTPUT_WIDTH = 800          # 切り抜き画像サイズ
OUTPUT_HEIGHT = 800
FLASK_PORT = 5000
PREVIEW_FPS_LIMIT = 2.0     # プレビューJPEGの更新頻度（枚/秒）

# ===================== 状態管理 =====================
status_store = {CAM_ID: "起動中（待機中）"}
status_lock = threading.Lock()


def update_status(text):
    with status_lock:
        status_store[CAM_ID] = text
    print(f"[status] {text}")


class FrameStore:
    """MJPEG 受信スレッドと処理スレッドの間で最新フレームを共有"""

    def __init__(self):
        self._lock = threading.Lock()
        self._frame = None
        self._ts = 0.0

    def set(self, frame):
        with self._lock:
            self._frame = frame
            self._ts = time.time()

    def get(self):
        with self._lock:
            if self._frame is None:
                return None, 0.0
            return self._frame.copy(), self._ts


frame_store = FrameStore()
preview_store = {"jpg": None, "ts": 0.0}
preview_lock = threading.Lock()


def set_preview(jpg_bytes):
    with preview_lock:
        preview_store["jpg"] = jpg_bytes
        preview_store["ts"] = time.time()


def get_preview():
    with preview_lock:
        return preview_store["jpg"]


# ===================== MJPEG 受信スレッド =====================
def stream_reader():
    """IP Webcam の MJPEG ストリームを純Pythonで受信し最新フレームを保持する"""
    while True:
        try:
            req = urllib.request.urlopen(STREAM_URL, timeout=10)
            update_status("映像ストリーム接続中...")
            buf = b""
            while True:
                chunk = req.read(4096)
                if not chunk:
                    raise ConnectionError("stream ended")
                buf += chunk
                # JPEG の SOI(FFD8) / EOI(FFD9) マーカーで切り出す
                while True:
                    start = buf.find(b"\xff\xd8")
                    if start == -1:
                        if len(buf) > 2_000_000:
                            buf = buf[-1:]
                        break
                    end = buf.find(b"\xff\xd9", start + 2)
                    if end == -1:
                        if start > 0:
                            buf = buf[start:]
                        if len(buf) > 10_000_000:
                            buf = buf[-2_000_000:]
                        break
                    jpg = buf[start:end + 2]
                    buf = buf[end + 2:]
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        frame_store.set(frame)
        except Exception:
            update_status("映像ストリーム未接続（IP Webcam を起動してください）")
            time.sleep(2)


# ===================== アップロード =====================
def upload_to_drive_via_gas(frame, file_name):
    print(f"[{file_name}] 切り抜き画像をアップロード中...")
    update_status("画像をアップロード中...")

    success, buffer = cv2.imencode(".jpg", frame)
    if not success:
        update_status("画像エンコード失敗")
        return

    base64_image = base64.b64encode(buffer).decode("utf-8")
    payload = {"image": base64_image, "filename": file_name}
    try:
        response = requests.post(
            GAS_URL, data=json.dumps(payload),
            headers={"Content-Type": "application/json"}, timeout=20,
        )
        if response.status_code == 200 and response.json().get("status") == "success":
            print(f"成功: Drive に保存されました: {response.json().get('file_name')}")
            update_status("アップロード完了！")
        else:
            print("GAS送信エラー")
            update_status("GAS送信エラー")
    except Exception as e:
        print(f"通信エラー: {e}")
        update_status(f"通信エラー: {e}")


# ===================== 画像処理 =====================
def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def crop_and_warp(frame, corners, ids):
    target_ids = [0, 1, 2, 3]
    pts = []
    for i in range(len(ids)):
        if ids[i][0] in target_ids:
            pts.append(np.mean(corners[i][0], axis=0))
    if len(pts) != 4:
        return None
    pts = np.array(pts, dtype="float32")
    rect = order_points(pts)
    dst = np.array([
        [0, 0],
        [OUTPUT_WIDTH - 1, 0],
        [OUTPUT_WIDTH - 1, OUTPUT_HEIGHT - 1],
        [0, OUTPUT_HEIGHT - 1],
    ], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(frame, M, (OUTPUT_WIDTH, OUTPUT_HEIGHT))


# ===================== 撮影ループ =====================
def capture_loop():
    if not hasattr(cv2, "aruco") or not hasattr(cv2.aruco, "ArucoDetector"):
        update_status("エラー: cv2.aruco がありません（opencv のバージョン確認）")
        return

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    aruco_params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    is_inside = False
    last_action_time = 0.0
    four_markers_start_time = None
    last_preview_ts = 0.0

    print(f"カメラ {CAM_ID}: 自動切り抜き監視システム起動中...")
    update_status("枠外（待機中）")

    while True:
        frame, _ = frame_store.get()
        if frame is None:
            time.sleep(0.3)
            continue

        clean_frame = frame.copy()
        corners, ids, _ = detector.detectMarkers(frame)

        valid_count = 0
        if ids is not None:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            for i in range(len(ids)):
                if ids[i][0] in [0, 1, 2, 3]:
                    valid_count += 1

        cv2.putText(frame, f"Targets: {valid_count}/4  Cam: {CAM_ID}",
                    (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)

        now = time.time()
        if now - last_preview_ts >= 1.0 / PREVIEW_FPS_LIMIT:
            ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                set_preview(enc.tobytes())
            last_preview_ts = now

        current_time = time.time()
        if valid_count == 4:
            if not is_inside:
                if four_markers_start_time is None:
                    four_markers_start_time = current_time
                    print("4つのマーカーを検出中...（維持してください）")
                    update_status("4つのマーカーを検出中...")

                if (current_time - four_markers_start_time) >= REQUIRED_STABLE_TIME:
                    if (current_time - last_action_time) > MIN_INTERVAL:
                        print("--- [条件達成] 1秒間4隅を維持しました。枠内を切り抜きます ---")
                        update_status("条件達成！切り抜き中...")

                        cropped_img = crop_and_warp(clean_frame, corners, ids)
                        if cropped_img is not None:
                            file_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S.jpg")
                            # アップロードは時間かかるのでスレッドで並行処理
                            threading.Thread(
                                target=upload_to_drive_via_gas,
                                args=(cropped_img, file_name),
                                daemon=True,
                            ).start()

                        last_action_time = current_time
                        is_inside = True
                        four_markers_start_time = None
        else:
            if four_markers_start_time is not None or is_inside:
                print("枠外に出たか、マーカーを見失いました。")
                update_status("枠外（待機中）")
            four_markers_start_time = None
            is_inside = False

        time.sleep(0.02)


# ===================== ステータスサーバー（Flask） =====================
app = Flask(__name__)

MONITOR_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>カメラ {{ cam_id }} モニター</title>
<script>
setInterval(async () => {
    try {
        let res = await fetch('/api/status/{{ cam_id }}');
        let data = await res.json();
        document.getElementById('status').innerText = data.status;
        let box = document.getElementById('status-box');
        if (data.status.includes('条件達成') || data.status.includes('アップロード') || data.status.includes('完了')) {
            box.style.backgroundColor = '#d4edda'; box.style.color = '#155724';
        } else if (data.status.includes('検出中')) {
            box.style.backgroundColor = '#fff3cd'; box.style.color = '#856404';
        } else if (data.status.includes('エラー') || data.status.includes('未接続')) {
            box.style.backgroundColor = '#f8d7da'; box.style.color = '#721c24';
        } else {
            box.style.backgroundColor = '#e2e3e5'; box.style.color = '#383d41';
        }
    } catch (e) {}
}, 500);

setInterval(() => {
    let img = document.getElementById('preview');
    if (img) img.src = '/preview.jpg?t=' + Date.now();
}, 500);

function toggleFullscreen() {
    document.getElementById('fullscreen-btn').style.display = 'none';
    let elem = document.documentElement;
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
        if (elem.requestFullscreen) elem.requestFullscreen();
        else if (elem.webkitRequestFullscreen) elem.webkitRequestFullscreen();
    } else {
        if (document.exitFullscreen) document.exitFullscreen();
        else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
    }
}
function showButton() { document.getElementById('fullscreen-btn').style.display = 'block'; }
function handleFullscreenChange() {
    document.getElementById('fullscreen-btn').style.display =
        (document.fullscreenElement || document.webkitFullscreenElement) ? 'none' : 'block';
}
document.addEventListener('fullscreenchange', handleFullscreenChange);
document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
</script>
<style>
html, body { height: 100%; margin: 0; padding: 0; background: #f8f9fa; overflow: hidden; }
body { font-family: sans-serif; display: flex; flex-direction: column; align-items: center; }
h1 { color: #333; margin: 8px 0 6px 0; font-size: 22px; }
#status-box { padding: 24px 16px; border-radius: 15px; font-size: 26px; font-weight: bold;
  width: 85%; max-width: 450px; box-shadow: 0 6px 12px rgba(0,0,0,0.15); text-align: center;
  box-sizing: border-box; margin-bottom: 12px; cursor: pointer; }
#preview { width: 92%; max-width: 640px; max-height: 45vh; object-fit: contain;
  border-radius: 10px; background: #222; box-shadow: 0 4px 10px rgba(0,0,0,0.2); }
.btn-fullscreen { margin-top: 10px; margin-bottom: 14px; padding: 10px 22px; font-size: 15px;
  font-weight: bold; background-color: #007bff; color: white; border: none; border-radius: 25px;
  cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
.btn-fullscreen:active { background-color: #0056b3; }
</style>
</head>
<body>
<h1>📷 カメラ 【{{ cam_id }}】</h1>
<div id="status-box" onclick="showButton()"><span id="status">{{ current_status }}</span></div>
<img id="preview" src="/preview.jpg?t=1" alt="プレビュー読込中...">
<button id="fullscreen-btn" class="btn-fullscreen" onclick="toggleFullscreen()"> 全画面表示に切り替え</button>
</body>
</html>
"""


@app.route("/")
def index():
    return redirect(f"/monitor/{CAM_ID}")


@app.route("/monitor/<cam_id>")
def monitor(cam_id):
    with status_lock:
        current = status_store.get(cam_id, "未登録のカメラIDです")
    return render_template_string(MONITOR_HTML, cam_id=cam_id, current_status=current)


@app.route("/api/status/<cam_id>")
def api_status(cam_id):
    with status_lock:
        return jsonify({"status": status_store.get(cam_id, "不明")})


@app.route("/preview.jpg")
def preview():
    jpg = get_preview()
    if jpg is None:
        return Response(b"", mimetype="image/jpeg")
    return Response(jpg, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store, max-age=0"})


def main():
    threading.Thread(target=stream_reader, daemon=True).start()
    threading.Thread(target=capture_loop, daemon=True).start()
    print(f"ステータス画面: http://localhost:{FLASK_PORT}  (CAM_ID={CAM_ID})")
    app.run(host="127.0.0.1", port=FLASK_PORT, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

#!/data/data/com.termux/files/usr/bin/bash
# Termux 環境セットアップスクリプト
# 使い方: bash install.sh
set -e

echo "=== パッケージ更新 ==="
pkg update -y

echo "=== リポジトリ追加（opencv-python に必要）==="
pkg install -y x11-repo

echo "=== Python / OpenCV / numpy ==="
pkg install -y python python-numpy opencv-python

echo "=== pip パッケージ ==="
pip install flask requests

echo ""
echo "=== 環境チェック ==="
python - <<'EOF'
import sys, numpy, cv2, flask, requests
from importlib.metadata import version
print("python     :", sys.version.split()[0])
print("numpy      :", numpy.__version__)
print("opencv     :", cv2.__version__)
print("flask      :", version("flask"))
print("requests   :", requests.__version__)
if hasattr(cv2, "aruco") and hasattr(cv2.aruco, "ArucoDetector"):
    print("cv2.aruco  : OK (ArucoDetector 使用可)")
else:
    print("cv2.aruco  : NG → pkg で入れた opencv を確認してください")
EOF

echo ""
echo "セットアップ完了。次:"
echo "  1. IP Webcam を起動して「Start server」を押す"
echo "  2. termux-wake-lock を実行する"
echo "  3. python main.py を実行する"
echo "  4. ブラウザで http://localhost:5000 を開く"

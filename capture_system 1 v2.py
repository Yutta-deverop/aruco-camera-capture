import cv2
import datetime
import time
import requests
import base64
import json
import numpy as np

# === 設定項目 ===
GAS_URL = "https://script.google.com/macros/s/AKfycbyEUdak05s3S0VzILdb81tOL12qP46cpXgWyrYxYsFAWlsueCozfnheESTSyxR25lJf/exec" # あなたのGASのURL
MIN_INTERVAL = 5.0  # チャタリング防止（秒）
REQUIRED_STABLE_TIME = 1.0  # ★追加：4つ認識し続ける必要がある時間（秒）

# 保存する切り抜き画像のサイズ
OUTPUT_WIDTH = 800
OUTPUT_HEIGHT = 800

# === 状態管理 ===
is_inside = False          
last_action_time = 0       
four_markers_start_time = None  # ★追加：4つのマーカーを認識し始めた時刻

def upload_to_drive_via_gas(frame, file_name):
    """画像をBase64に変換し、GAS経由でGoogle Driveへ保存する"""
    print(f"[{file_name}] 切り抜き画像をアップロード中...")
    success, buffer = cv2.imencode('.jpg', frame)
    if not success:
        return
        
    base64_image = base64.b64encode(buffer).decode('utf-8')
    payload = {"image": base64_image, "filename": file_name}
    
    try:
        response = requests.post(GAS_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=15)
        if response.status_code == 200 and response.json().get("status") == "success":
            print(f"成功: 切り抜き画像がDriveに保存されました: {response.json().get('file_name')}")
        else:
            print("GAS送信エラー")
    except Exception as e:
        print(f"通信エラー: {e}")

def order_points(pts):
    """4つの座標を [左上, 右上, 右下, 左下] の順番に整列する関数"""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)] # X+Yが最小 ➔ 左上
    rect[2] = pts[np.argmax(s)] # X+Yが最大 ➔ 右下
    
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] # Y-Xが最小 ➔ 右上
    rect[3] = pts[np.argmax(diff)] # Y-Xが最大 ➔ 左下
    return rect

def crop_and_warp(frame, corners, ids):
    """4つのマーカーで囲まれた範囲を検出し、真上からの長方形に変換・切り抜く"""
    target_ids = [0, 1, 2, 3]
    pts = []
    
    for i in range(len(ids)):
        if ids[i][0] in target_ids:
            center = np.mean(corners[i][0], axis=0)
            pts.append(center)
            
    if len(pts) != 4:
        return None
        
    pts = np.array(pts, dtype="float32")
    rect = order_points(pts)
    
    dst = np.array([
        [0, 0],
        [OUTPUT_WIDTH - 1, 0],
        [OUTPUT_WIDTH - 1, OUTPUT_HEIGHT - 1],
        [0, OUTPUT_HEIGHT - 1]
    ], dtype="float32")
    
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(frame, M, (OUTPUT_WIDTH, OUTPUT_HEIGHT))
    return warped

def main():
    global is_inside, last_action_time, four_markers_start_time
    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        print("カメラを起動できませんでした。")
        return

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    aruco_params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

    print("枠内限定・自動切り抜き監視システム起動中... 'q' キーで終了")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        clean_frame = frame.copy()
        corners, ids, _ = detector.detectMarkers(frame)
        
        valid_count = 0
        if ids is not None:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            for i in range(len(ids)):
                if ids[i][0] in [0, 1, 2, 3]:
                    valid_count += 1

        cv2.putText(frame, f"Targets: {valid_count}/4", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

        # 撮影ロジックの修正部分
        current_time = time.time()
        if valid_count == 4:
            if not is_inside:
                # 4つ見つかった瞬間にタイマーを開始
                if four_markers_start_time is None:
                    four_markers_start_time = current_time
                    print("4つのマーカーを検出中...（維持してください）")

                # 4つ認識し始めてから1秒以上経過したか判定
                if (current_time - four_markers_start_time) >= REQUIRED_STABLE_TIME:
                    # さらにチャタリング防止用のインターバル（5秒）をクリアしているかチェック
                    if (current_time - last_action_time) > MIN_INTERVAL:
                        print("--- [条件達成] 1秒間4隅を維持しました。枠内を切り抜きます ---")
                        
                        cropped_img = crop_and_warp(clean_frame, corners, ids)
                        if cropped_img is not None:
                            now = datetime.datetime.now()
                            file_name = now.strftime("%Y%m%d_%H%M%S.jpg")
                            
                            upload_to_drive_via_gas(cropped_img, file_name)
                            cv2.imshow("Last Cropped Image", cropped_img)
                            
                        last_action_time = current_time
                        is_inside = True  # 撮影完了。枠外に出るまで次の撮影をロック
                        four_markers_start_time = None  # タイマーリセット
                    else:
                        # 4つ揃っているが、前回の撮影から5秒経っていない場合は待機
                        pass
        else:
            # 1つでも見失ったら状態をすべてリセット
            four_markers_start_time = None
            if is_inside:
                print("枠外に出ました。")
                is_inside = False
                # 枠外に出たタイミングをインターバルの起点にしたい場合は有効化
                # last_action_time = current_time 

        cv2.imshow("ArUco Crop Monitor", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
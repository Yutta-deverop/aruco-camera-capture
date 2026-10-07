import cv2

def check_camera_id(max_tests=10):  # 仮想カメラはID番号が後ろの方にあることもあるので10まで拡張
    print("--- カメラ番号の確認を開始します ---")
    for camera_id in range(max_tests):
        # ★ ここを cv2.CAP_DSHOW または cv2.CAP_MSMF に変更してみる
        cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
        
        if not cap.isOpened():
            continue
            
        print(f"カメラ ID [{camera_id}] を起動しました。確認したら画面上で 'q' を押してください。")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                # 起動はできてもフレームが読めない場合の対策
                cv2.waitKey(100)
                continue
                
            cv2.putText(frame, f"CAMERA ID: {camera_id}", (30, 60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
            cv2.imshow(f"Test - Camera {camera_id}", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        cap.release()
        cv2.destroyAllWindows()
    
    print("--- すべてのカメラチェックが終了しました ---")

if __name__ == "__main__":
    check_camera_id()
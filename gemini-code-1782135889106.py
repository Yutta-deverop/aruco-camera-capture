import cv2

def check_camera_id(max_tests=5):
    print("--- カメラ番号の確認を開始します ---")
    for camera_id in range(max_tests):
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            # カメラが開かなければスキップ
            continue
            
        print(f"カメラ ID [{camera_id}] を起動しました。確認したら画面上で 'q' を押してください。")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # 画面の中に現在のIDを表示
            cv2.putText(frame, f"CAMERA ID: {camera_id}", (30, 60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
            
            cv2.imshow(f"Test - Camera {camera_id}", frame)
            
            # 'q' が押されたら次のカメラのチェックへ
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        cap.release()
        cv2.destroyAllWindows()
    
    print("--- すべてのカメラチェックが終了しました ---")

if __name__ == "__main__":
    check_camera_id()
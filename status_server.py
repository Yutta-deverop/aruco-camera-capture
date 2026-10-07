from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

statuses = {
    "0": "起動中（待機中）",
    "1": "起動中（待機中）",
    "2": "起動中（待機中）",
    "3": "起動中（待機中）",
    "4": "起動中（待機中）"
}

@app.route('/update', methods=['POST'])
def update():
    data = request.json
    cam_id = str(data.get("cam_id"))
    status_text = data.get("status")
    if cam_id in statuses:
        statuses[cam_id] = status_text
    return jsonify({"status": "success"})

@app.route('/monitor/<cam_id>')
def monitor(cam_id):
    if cam_id not in statuses:
        return "無効なカメラIDです", 404
        
    html = """
    <!DOCTYPE html>
    <html>
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
                    if(data.status.includes('条件達成') || data.status.includes('アップロード')) {
                        box.style.backgroundColor = '#d4edda'; box.style.color = '#155724';
                    } else if(data.status.includes('検出中')) {
                        box.style.backgroundColor = '#fff3cd'; box.style.color = '#856404';
                    } else {
                        box.style.backgroundColor = '#e2e3e5'; box.style.color = '#383d41';
                    }
                } catch(e) {}
            }, 500);

            // 指定した範囲（画面全体）を全画面表示にする関数
            function toggleFullscreen() {
                let elem = document.documentElement;
                
                // ★追加：ボタンが押されたら、全画面判定に関わらず即座にボタンを非表示にする
                document.getElementById('fullscreen-btn').style.display = 'none';
                
                if (!document.fullscreenElement && !document.webkitFullscreenElement) {
                    if (elem.requestFullscreen) {
                        elem.requestFullscreen();
                    } else if (elem.webkitRequestFullscreen) {
                        elem.webkitRequestFullscreen();
                    }
                } else {
                    if (document.exitFullscreen) {
                        document.exitFullscreen();
                    } else if (document.webkitExitFullscreen) {
                        document.webkitExitFullscreen();
                    }
                }
            }

            // ★追加：もし全画面を解除してボタンを再表示したくなったとき用の救済関数
            function showButton() {
                document.getElementById('fullscreen-btn').style.display = 'block';
            }

            // Android等で通常の全画面解除（戻るボタンなど）が起きたときの連動も残しておく
            function handleFullscreenChange() {
                let btn = document.getElementById('fullscreen-btn');
                if (document.fullscreenElement || document.webkitFullscreenElement) {
                    btn.style.display = 'none';
                } else {
                    btn.style.display = 'block';
                }
            }

            document.addEventListener('fullscreenchange', handleFullscreenChange);
            document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
        </script>
        <style>
            html, body { height: 100%; margin: 0; padding: 0; background: #f8f9fa; overflow: hidden; }
            body { font-family: sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; }
            h1 { color: #333; margin-bottom: 10px; font-size: 28px; }
            
            /* タップできることを示すため、boxにカーソル指定を追加 */
            #status-box { padding: 50px 20px; border-radius: 15px; font-size: 32px; font-weight: bold; width: 85%; max-width: 450px; box-shadow: 0 6px 12px rgba(0,0,0,0.15); text-align: center; box-sizing: border-box; margin-bottom: 20px; cursor: pointer; }
            
            .btn-fullscreen {
                padding: 12px 24px; font-size: 16px; font-weight: bold; background-color: #007bff; color: white; border: none; border-radius: 25px; cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }
            .btn-fullscreen:active { background-color: #0056b3; }
        </style>
    </head>
    <body>
        <h1> カメラ 【{{ cam_id }}】</h1>
        
        <div id="status-box" onclick="showButton()">
            <span id="status">{{ current_status }}</span>
        </div>
        
        <button id="fullscreen-btn" class="btn-fullscreen" onclick="toggleFullscreen()"> 全画面表示に切り替え</button>
    </body>
    </html>
    """
    return render_template_string(html, cam_id=cam_id, current_status=statuses[cam_id])

@app.route('/api/status/<cam_id>')
def api_status(cam_id):
    return jsonify({"status": statuses.get(cam_id, "不明")})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
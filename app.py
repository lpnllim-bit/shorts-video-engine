import os
import requests
import subprocess
import json
from flask import Flask, request, send_file, jsonify

app = Flask(__name__)

# 임시 저장 폴더
TEMP_IMG_DIR = "temp_images"
TEMP_AUDIO_DIR = "temp_audio"
TEMP_BG_DIR = "temp_bg"
OUTPUT_FILE = "output.mp4"

# 폴더 초기화 함수
def cleanup_files():
    for folder in [TEMP_IMG_DIR, TEMP_AUDIO_DIR, TEMP_BG_DIR]:
        if not os.path.exists(folder):
            os.makedirs(folder)
        for f in os.listdir(folder):
            os.remove(os.path.join(folder, f))
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

# 오디오 길이 측정 함수 (ffprobe)
def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 30.0

# 오디오 속도 변경 함수
def change_audio_speed(input_path, output_path, speed):
    # atempo 필터는 0.5 ~ 2.0 사이만 가능 (그 외에는 체인 연결 필요하지만 쇼츠용으론 충분)
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter:a", f"atempo={speed}",
        "-vn", output_path
    ]
    subprocess.run(cmd, check=True)

@app.route('/render', methods=['POST'])
def render_video():
    try:
        cleanup_files()
        
        data = request.json
        image_urls = data.get('images', [])
        audio_url = data.get('audio')
        background_url = data.get('background', None) # 배경 이미지 (선택)
        audio_speed = float(data.get('audio_speed', 1.0)) # 오디오 속도 (기본 1.0)

        if not image_urls or not audio_url:
            return jsonify({"error": "이미지 또는 오디오 URL이 없습니다."}), 400

        print(f"🎬 작업 시작: 이미지 {len(image_urls)}장, 배속 {audio_speed}")

        # 1. 오디오 다운로드 및 속도 조절
        original_audio_path = os.path.join(TEMP_AUDIO_DIR, "original.mp3")
        final_audio_path = os.path.join(TEMP_AUDIO_DIR, "final.mp3")
        
        with open(original_audio_path, 'wb') as f:
            f.write(requests.get(audio_url).content)
            
        if audio_speed != 1.0:
            change_audio_speed(original_audio_path, final_audio_path, audio_speed)
        else:
            os.rename(original_audio_path, final_audio_path)
        
        # 2. 변경된 오디오 길이로 시간 계산
        duration = get_audio_duration(final_audio_path)
        img_duration = duration / len(image_urls)
        print(f"🎵 최종 길이: {duration:.2f}초 / 이미지당: {img_duration:.2f}초")

        # 3. 이미지 다운로드 및 리스트 생성
        input_list_path = "inputs.txt"
        with open(input_list_path, 'w') as f:
            for i, url in enumerate(image_urls):
                img_path = os.path.join(TEMP_IMG_DIR, f"image_{i:03d}.png")
                with open(img_path, 'wb') as img_file:
                    img_file.write(requests.get(url).content)
                f.write(f"file '{img_path}'\n")
                f.write(f"duration {img_duration}\n")
            # 버그 방지용 마지막 프레임 반복
            f.write(f"file '{os.path.join(TEMP_IMG_DIR, f'image_{len(image_urls)-1:03d}.png')}'\n")

        # 4. 배경 이미지 처리 (있으면 다운로드)
        bg_cmd = ""
        filter_complex = ""
        
        if background_url:
            bg_path = os.path.join(TEMP_BG_DIR, "background.png")
            with open(bg_path, 'wb') as f:
                f.write(requests.get(background_url).content)
            
            # 배경이 있을 때: 배경을 밑에 깔고, 이미지를 중앙에 맞춤 (Overlay)
            # 입력 0: 슬라이드쇼, 입력 1: 오디오, 입력 2: 배경
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", input_list_path,
                "-i", final_audio_path,
                "-i", bg_path,
                "-filter_complex", 
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[img];[2:v]scale=1080:1920[bg];[bg][img]overlay=(W-w)/2:(H-h)/2[v]",
                "-map", "[v]", "-map", "1:a",
                "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-shortest",
                OUTPUT_FILE
            ]
        else:
            # 배경 없을 때: 그냥 꽉 차게 리사이즈
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", input_list_path,
                "-i", final_audio_path,
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p",
                "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-shortest",
                OUTPUT_FILE
            ]

        print("🔨 렌더링 중...")
        subprocess.run(ffmpeg_cmd, check=True)
        print("✅ 렌더링 완료!")

        return send_file(OUTPUT_FILE, mimetype='video/mp4')

    except Exception as e:
        print(f"❌ 에러 발생: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

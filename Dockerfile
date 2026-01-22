FROM python:3.9-slim

# FFmpeg 설치 (핵심 기술자)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean

WORKDIR /app

# 필요한 파이썬 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 복사
COPY app.py .

# 임시 폴더 생성
RUN mkdir -p temp_images temp_audio temp_bg

# 서버 실행
CMD ["python", "app.py"]

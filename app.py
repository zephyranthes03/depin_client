import os
import subprocess
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3

app = FastAPI()

# 저장 경로
DOWNLOAD_PATH = "./downloads/"
STREAM_PATH = "./streaming/"
LOG_DB = "./streaming_logs.db"

# 폴더 생성
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
os.makedirs(STREAM_PATH, exist_ok=True)

# SQLite 데이터베이스 초기화
conn = sqlite3.connect(LOG_DB)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS streaming_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_ip TEXT,
        video_name TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

class FileRequest(BaseModel):
    cid: str  # Filecoin/IPFS CID
    filename: str  # file name

@app.post("/download-content")
def download_content(file_request: FileRequest):
    """Filecoin (IPFS)에서 동영상을 다운로드"""
    file_path = os.path.join(DOWNLOAD_PATH, file_request.filename)

    # IPFS에서 파일 다운로드
    cmd = f"ipfs get {file_request.cid} -o {file_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="File download failed.")

    return {"message": "File downloaded successfully.", "file_path": file_path}

@app.post("/convert-to-hls")
def convert_to_hls(file_request: FileRequest):
    """다운로드한 동영상을 HLS 스트리밍 형식으로 변환"""
    input_file = os.path.join(DOWNLOAD_PATH, file_request.filename)
    output_folder = os.path.join(STREAM_PATH, file_request.filename.split('.')[0])
    os.makedirs(output_folder, exist_ok=True)
    
    # FFmpeg를 사용한 HLS 변환
    cmd = (
        f"ffmpeg -i {input_file} -profile:v baseline -level 3.0 -s 640x360 -start_number 0 "
        f"-hls_time 10 -hls_list_size 0 -f hls {output_folder}/video.m3u8"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="HLS conversion failed.")

    return {"message": "HLS conversion successful.", "stream_url": f"/stream/{file_request.filename.split('.')[0]}/video.m3u8"}

@app.get("/logs")
def get_logs():
    """스트리밍 로그 조회"""
    conn = sqlite3.connect(LOG_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM streaming_logs")
    logs = cursor.fetchall()
    conn.close()
    return {"logs": logs}

@app.get("/stream/{video_name}/{file_name}")
def stream_video(video_name: str, file_name: str):
    """HLS 스트리밍 파일 제공"""
    file_path = os.path.join(STREAM_PATH, video_name, file_name)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found.")
    
        # 클라이언트 IP 추출
    client_ip = request.client.host

    # 데이터베이스에 스트리밍 요청 로그 저장
    conn = sqlite3.connect(LOG_DB)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO streaming_logs (client_ip, video_name) VALUES (?, ?)", (client_ip, video_name))
    conn.commit()
    conn.close()

    return FileResponse(file_path, media_type="application/vnd.apple.mpegurl")

@app.get("/")
def home():
    return {"message": "Welcome to FastAPI Filecoin-Torrent service!"}


import os
import re
import subprocess
import shutil
import sqlite3
import requests
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js 클라이언트 주소
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],   # 모든 헤더 허용
)

# 저장 경로 설정
DOWNLOAD_PATH = "./downloads/"
STREAM_PATH = "./streaming/"
IPFS_GATEWAY = "https://ipfs.io/ipfs/"
GATEWAY_REGISTER_URL = "http://localhost:8000/register"  # 게이트웨이 등록 API
GATEWAY_METADATA_URL = "http://localhost:8000/meta/get_metadata/"  # 메타데이터 조회 API
STREAM_SEARCH_BY_WALLET_CID_URL = "http://localhost:8000/stream/get_stream_by_wallet_cid/"  # 게이트웨이 스트리밍 서버 조회 API
DEPIN_HOST_URI = "http://depinhost.com/api/record-view"  # DePIN Host의 API
GATEWAY_DEREGISTER_URL = "http://localhost:8000/deregister"  # Gateway API for deregistering stream
# SQLite 데이터베이스 설정
DB_PATH = "./depinc_metadata.db"

# EthStorage 설정
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "http://localhost:8545")
FLAT_DIRECTORY = os.getenv("FLAT_DIRECTORY")

# 폴더 생성
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
os.makedirs(STREAM_PATH, exist_ok=True)

app.mount("/streaming", StaticFiles(directory=STREAM_PATH), name="streaming")

# 콘텐츠 메타데이터 모델
class ContentClient(BaseModel):
    cid: str
    blockchain_address: str  # 블록체인 입금 주소

# Deregister Request Model
class DeregisterRequest(BaseModel):
    cid: str
    content_distributor_wallet: str  # Owner verification


## 20초 짜리 샘픔..
# curl -X 'POST' 'http://127.0.0.1:9000/register_web3' \
#       -H 'Content-Type: application/json' \
#       -d '{    "cid": "0x43659dACc5DF5284006df3a504562D6172063999",
#         "blockchain_address": "0xB9a3799106B0364331d4e154F5f76BFF7E62D4BC" }'


## 20초 짜리 샘픔..
# curl -X 'POST' 'http://127.0.0.1:9000/register_web3' \
#       -H 'Content-Type: application/json' \
#       -d '{    "cid": "0x43659dACc5DF5284006df3a504562D6172063999",
#         "blockchain_address": "0xB9a3799106B0364331d4e154F5f76BFF7E62D4BC" }'

@app.post("/register_web3")
def register(client: ContentClient):
    """IPFS에서 동영상을 다운로드하고, HLS 변환 후 게이트웨이에 등록"""
    
    # 1️⃣ 게이트웨이에서 메타데이터 가져오기
    response = requests.get(f"{GATEWAY_METADATA_URL}{client.cid}")
    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="메타데이터를 찾을 수 없습니다.")

    metadata = response.json()

    # 저장 디렉토리 (블록체인 입금주소/CID 구조로 관리)
    save_dir = os.path.join(DOWNLOAD_PATH, client.blockchain_address, client.cid)
    os.makedirs(save_dir, exist_ok=True)

    file_path = os.path.join(save_dir, metadata['video_name'])

    # 2️⃣ EthStorage에서 동영상 다운로드
    # 2️⃣ IPFS에서 동영상 다운로드
    # cmd = f"web3curl web3://{client.cid}/video.mp4 -o {file_path}"
    cmd = f"cd {save_dir} ; ethfs-cli download -f {metadata['video_name']} -a {FLAT_DIRECTORY} -c 11155111 -r {ETH_RPC_URL}"

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"IPFS 파일 다운로드 실패: {result.stderr}")

    """DePIN 스트리밍 서버 등록 및 HLS 변환 수행"""
    if metadata["creator_share"] + metadata["provider_share"] != 100:
        raise HTTPException(status_code=400, detail="리워드 합계가 100%가 아닙니다.")
    
    # 3️⃣ HLS 변환 실행
    input_file = file_path  # 수정: file_path를 그대로 사용
    output_folder = os.path.join(STREAM_PATH, client.blockchain_address, metadata["cid"])
    os.makedirs(output_folder, exist_ok=True)

    cmd = (
        f"ffmpeg -i {input_file} "
        f"-codec:v libx264 -preset veryfast -profile:v baseline -level 3.0 -s 1280x720 "
        f"-codec:a aac -b:a 128k -ac 2 "
        f"-hls_flags independent_segments+append_list "
        f"-hls_time 6 -hls_list_size 0 -hls_segment_type mpegts -hls_playlist_type vod "
        f"-hls_segment_filename \"{output_folder}/segment_%03d.ts\" " 
        f"-f hls {output_folder}/video.m3u8"
    )

    # For realtime streaming -hls_flags delete_segments : delete old segments,
    # -hls_playlist_type live : live streaming,
    # -hls_segment_filename "{output_folder}/segment_%03d.ts" : segment file name format
    # cmd = (f"ffmpeg -i {input_file} -profile:v baseline -level 3.0 -s 1280x720 -start_number 0 \
    #     -hls_time 6 -hls_list_size 6 -hls_flags delete_segments -hls_playlist_type live \
    #     -hls_segment_filename \"{output_folder}/segment_%03d.ts\" -f hls output/video.m3u8
    #     ")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"HLS 변환 실패: {result.stderr}")

    # 4️⃣ 스트리밍 서버 URL 생성
    stream_url = f"http://localhost:9000/streaming/{client.blockchain_address}/{client.cid}"

    # 5️⃣ 게이트웨이에 스트리밍 서버 등록 요청
    server_info = {
        "cid": client.cid,
        "stream_url": stream_url,
        "video_name": metadata["video_name"],
        "content_creator_wallet": metadata["content_creator_wallet"],
        "content_distributor_wallet": client.blockchain_address,
        "creator_share": metadata["creator_share"],
        "provider_share": metadata["provider_share"],
        "price": metadata["price"]
    }

    response = requests.post(GATEWAY_REGISTER_URL, json=server_info)
    
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"게이트웨이 등록 실패: {response.text}")

    return {
        "message": "파일 다운로드, 변환 및 스트리밍 서버 등록 완료",
        "stream_url": stream_url
    }


## 20초 짜리 샘픔..
# curl -X 'POST' 'http://127.0.0.1:9000/register' \
#       -H 'Content-Type: application/json' \
#       -d '{    "cid": "QmfAx8AhKrJSR7bnnp6NMguRXXXMgyXst14MPSJ4VdbH78",
#         "blockchain_address": "0xYourWalletAddress" }'


## 20초 짜리 샘픔..
# curl -X 'POST' 'http://127.0.0.1:9000/register' \
#       -H 'Content-Type: application/json' \
#       -d '{    "cid": "QmX7VzZ92ddg5ZqXs83W44NSyrSdcJ8wkHbdPaHcq3pAuA",
#         "blockchain_address": "0xYourWalletAddress" }'

@app.post("/register")
def register(client: ContentClient):
    """IPFS에서 동영상을 다운로드하고, HLS 변환 후 게이트웨이에 등록"""
    
    # 1️⃣ 게이트웨이에서 메타데이터 가져오기
    response = requests.get(f"{GATEWAY_METADATA_URL}{client.cid}")
    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="메타데이터를 찾을 수 없습니다.")

    metadata = response.json()

    # 저장 디렉토리 (블록체인 입금주소/CID 구조로 관리)
    save_dir = os.path.join(DOWNLOAD_PATH, client.blockchain_address, client.cid)
    os.makedirs(save_dir, exist_ok=True)

    file_path = os.path.join(save_dir, "video.mp4")

    # 2️⃣ IPFS에서 동영상 다운로드
    cmd = f"ipfs get {client.cid} -o {file_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"IPFS 파일 다운로드 실패: {result.stderr}")

    """DePIN 스트리밍 서버 등록 및 HLS 변환 수행"""
    if metadata["creator_share"] + metadata["provider_share"] != 100:
        raise HTTPException(status_code=400, detail="리워드 합계가 100%가 아닙니다.")
    
    # 3️⃣ HLS 변환 실행
    input_file = file_path  # 수정: file_path를 그대로 사용
    output_folder = os.path.join(STREAM_PATH, client.blockchain_address, metadata["cid"])
    os.makedirs(output_folder, exist_ok=True)

    cmd = (
        f"ffmpeg -i {input_file} -profile:v baseline -level 3.0 -s 1280x720 -start_number 0 "
        f"-hls_time 6 -hls_list_size 0 -hls_segment_filename \"{output_folder}/segment_%03d.ts\" " 
        f"-f hls {output_folder}/video.m3u8"
    )

    # For realtime streaming -hls_flags delete_segments : delete old segments,
    # -hls_playlist_type live : live streaming,
    # -hls_segment_filename "{output_folder}/segment_%03d.ts" : segment file name format
    # cmd = (f"ffmpeg -i {input_file} -profile:v baseline -level 3.0 -s 1280x720 -start_number 0 \
    #     -hls_time 6 -hls_list_size 6 -hls_flags delete_segments -hls_playlist_type live \
    #     -hls_segment_filename \"{output_folder}/segment_%03d.ts\" -f hls output/video.m3u8
    #     ")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"HLS 변환 실패: {result.stderr}")

    # 4️⃣ 스트리밍 서버 URL 생성
    stream_url = f"http://localhost:9000/stream/{client.blockchain_address}/{client.cid}"

    # 5️⃣ 게이트웨이에 스트리밍 서버 등록 요청
    server_info = {
        "cid": client.cid,
        "stream_url": stream_url,
        "video_name": metadata["video_name"],
        "content_creator_wallet": metadata["content_creator_wallet"],
        "content_distributor_wallet": client.blockchain_address,
        "creator_share": metadata["creator_share"],
        "provider_share": metadata["provider_share"],
        "price": metadata["price"]
    }

    response = requests.post(GATEWAY_REGISTER_URL, json=server_info)
    
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"게이트웨이 등록 실패: {response.text}")

    return {
        "message": "파일 다운로드, 변환 및 스트리밍 서버 등록 완료",
        "stream_url": stream_url
    }


# curl -X POST "http://localhost:8000/deregister" \
#      -H "Content-Type: application/json" \
#      -d '{
#            "cid": "QmfAx8AhKrJSR7bnnp6NMguRXXXMgyXst14MPSJ4VdbH78",
#            "content_distributor_wallet": "0xYourWalletAddress"
#          }'

# curl -X POST "http://localhost:8000/deregister" \
#      -H "Content-Type: application/json" \
#      -d '{
#            "cid": "QmX7VzZ92ddg5ZqXs83W44NSyrSdcJ8wkHbdPaHcq3pAuA",
#            "content_distributor_wallet": "0xYourWalletAddress"
#          }'

# curl -X POST "http://localhost:8000/deregister" \
#      -H "Content-Type: application/json" \
#      -d '{
#            "cid": "0x43659dACc5DF5284006df3a504562D6172063999",
#            "content_distributor_wallet": "0xB9a3799106B0364331d4e154F5f76BFF7E62D4BC"
#          }'


@app.post("/deregister")
def deregister(client: DeregisterRequest):
    """ 블록체인 주소 및 CID 기반으로 스트리밍 서버 제거 및 데이터 정리 """

    # 1️⃣ Retrieve stream metadata from the gateway
    response = requests.get(f"{STREAM_SEARCH_BY_WALLET_CID_URL}{client.content_distributor_wallet}/{client.cid}")
    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="메타데이터를 찾을 수 없습니다.")
    elif response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"게이트웨이 조회 실패: {response.text}")

    metadata = response.json()

    # 2️⃣ Verify ownership
    if metadata["content_distributor_wallet"] != client.content_distributor_wallet:
        raise HTTPException(status_code=403, detail="해당 스트리밍 서버를 제거할 권한이 없습니다.")

    # 3️⃣ Send deregistration request to the gateway
    remove_response = requests.post(GATEWAY_DEREGISTER_URL, json={"cid": client.cid, "content_distributor_wallet": client.content_distributor_wallet})
    if remove_response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"게이트웨이 제거 실패: {remove_response.text}")

    # 4️⃣ Delete downloaded original video file
    save_dir = os.path.join(DOWNLOAD_PATH, metadata["content_distributor_wallet"], client.cid)
    if os.path.exists(save_dir):
        shutil.rmtree(save_dir)  # Delete entire directory

    # 5️⃣ Delete HLS converted stream files
    stream_dir = os.path.join(STREAM_PATH, metadata["content_distributor_wallet"], client.cid)
    if os.path.exists(stream_dir):
        shutil.rmtree(stream_dir)  # Delete entire directory

    return {
        "message": "스트리밍 서버 제거 및 데이터 정리 완료",
        "cid": client.cid,
        "content_distributor_wallet": client.content_distributor_wallet
    }


@app.get("/stream_web/{blockchain_address}/{cid}")
def stream_video(
    blockchain_address: str,
    cid: str,
    request: Request,
    viewer_wallet: str = Query(default="")
):
    """
    블록체인 입금주소 및 CID 기반으로 스트리밍 파일 제공
    접근 기록을 DePIN Host의 API로 전송
    """
    file_name = "video.m3u8"
    file_path = os.path.join(STREAM_PATH, blockchain_address, cid, file_name)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    if not viewer_wallet:
        viewer_wallet = request.client.host  # viewer_wallet이 없으면 IP 주소로 대체

    # 1️⃣ DePIN Host API에 접근 기록 전송
    payload = {
        "cid": cid,
        "blockchain_address": blockchain_address,
        "viewer_wallet": viewer_wallet,
        "timestamp": datetime.utcnow().isoformat()
    }

    try:
        response = requests.post(DEPIN_HOST_URI, json=payload, timeout=5)
        response.raise_for_status()  # 오류 발생 시 예외 처리
    except requests.exceptions.RequestException as e:
        print(f"❌ DePIN Host API 요청 실패: {e}")

    # 2️⃣ 스트리밍 파일 반환
    return FileResponse(file_path, media_type="application/x-mpegURL")

@app.get("/stream/{blockchain_address}/{cid}")
def stream_video(
    blockchain_address: str,
    cid: str
):
    """
    블록체인 입금주소 및 CID 기반으로 스트리밍 파일 제공
    접근 기록을 DePIN Host의 API로 전송
    """
    file_name = "video.m3u8"
    file_path = os.path.join(STREAM_PATH, blockchain_address, cid, file_name)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # 2️⃣ 스트리밍 파일 반환
    return FileResponse(file_path, media_type="application/x-mpegURL")
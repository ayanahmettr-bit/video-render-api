from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import subprocess
import uuid
import os
import urllib.request

app = FastAPI()

class Clip(BaseModel):
    url: str
    aciklama: str
    rank: int

class VideoRequest(BaseModel):
    seri_adi: str
    clips: List[Clip]

def download_file(url: str, path: str):
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        with open(path, 'wb') as f:
            f.write(response.read())

@app.post("/render")
async def render_video(req: VideoRequest):
    job_id = str(uuid.uuid4())
    work_dir = f"/tmp/{job_id}"
    os.makedirs(work_dir, exist_ok=True)

    try:
        clips_sorted = sorted(req.clips, key=lambda x: x.rank, reverse=True)
        input_files = []

        for i, clip in enumerate(clips_sorted):
            ext = ".mp4"
            clip_path = f"{work_dir}/clip_{i}{ext}"
            download_file(clip.url, clip_path)
            input_files.append(clip_path)

        # Her klibi 5 saniyeye kırp ve 9:16 formatına getir
        processed = []
        for i, clip_path in enumerate(input_files):
            out = f"{work_dir}/proc_{i}.mp4"
            subprocess.run([
                "ffmpeg", "-i", clip_path,
                "-t", "6",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-an", "-y", out
            ], check=True, capture_output=True)
            processed.append(out)

        # Concat list oluştur
        concat_file = f"{work_dir}/concat.txt"
        with open(concat_file, "w") as f:
            for p in processed:
                f.write(f"file '{p}'\n")

        merged = f"{work_dir}/merged.mp4"
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", "-y", merged
        ], check=True, capture_output=True)

        # Overlay: başlık + sayılar + açıklamalar
        total_duration = 6 * len(processed)
        
        # Tüm sayıları sol tarafa yaz
        numbers_filter = ""
        for i, clip in enumerate(clips_sorted):
            y_pos = 200 + (i * 120)
            rank_num = clip.rank
            numbers_filter += f"drawtext=text='{rank_num}.':fontsize=55:fontcolor=white:x=40:y={y_pos}:enable='between(t,0,{total_duration})',"

        # Aktif sayı ve açıklama (her 6 saniyede bir)
        active_filter = ""
        for i, clip in enumerate(clips_sorted):
            start_t = i * 6
            end_t = start_t + 6
            y_pos = 200 + (i * 120)
            active_filter += f"drawtext=text='{clip.aciklama}':fontsize=32:fontcolor=yellow:x=110:y={y_pos+10}:enable='between(t,{start_t},{end_t})',"

        # Başlık
        title_filter = f"drawtext=text='{req.seri_adi}':fontsize=52:fontcolor=white:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:x=(w-tw)/2:y=60:box=1:boxcolor=black@0.5:boxborderw=10"

        full_filter = numbers_filter + active_filter + title_filter

        output = f"{work_dir}/final.mp4"
        subprocess.run([
            "ffmpeg", "-i", merged,
            "-vf", full_filter,
            "-c:v", "libx264", "-c:a", "aac",
            "-y", output
        ], check=True, capture_output=True)

        with open(output, "rb") as f:
            video_bytes = f.read()

        from fastapi.responses import Response
        return Response(content=video_bytes, media_type="video/mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

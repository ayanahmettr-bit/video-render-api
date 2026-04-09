from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional
import subprocess
import uuid
import os
import urllib.request
import urllib.parse
import json

app = FastAPI()

PEXELS_API_KEY = "7kkKD3fWLzWVn9WhAZ70vWYtNRwPWEKn8dZ4UbsVzLNeuEWRehPVLt1t"

class Clip(BaseModel):
    url: Optional[str] = None
    aciklama: str
    rank: int

class VideoRequest(BaseModel):
    seri_adi: str
    clips: List[Clip]

def get_pexels_video(keyword: str) -> str:
    url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(keyword)}&per_page=3&orientation=portrait"
    req = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    videos = data.get("videos", [])
    if not videos:
        url2 = f"https://api.pexels.com/videos/search?query=funny&per_page=1&orientation=portrait"
        req2 = urllib.request.Request(url2, headers={"Authorization": PEXELS_API_KEY})
        with urllib.request.urlopen(req2, timeout=30) as r2:
            data2 = json.loads(r2.read())
        videos = data2.get("videos", [])
    if not videos:
        raise Exception("Pexels video bulunamadi")
    files = videos[0].get("video_files", [])
    sd = next((f for f in files if f.get("quality") == "sd"), None)
    hd = next((f for f in files if f.get("quality") == "hd"), None)
    chosen = sd or hd or files[0]
    return chosen["link"]

def download_video(url: str, output_path: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.pexels.com/",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        with open(output_path, "wb") as f:
            f.write(r.read())

@app.post("/render")
async def render_video(req: VideoRequest):
    job_id = str(uuid.uuid4())
    work_dir = f"/tmp/{job_id}"
    os.makedirs(work_dir, exist_ok=True)

    try:
        clips_sorted = sorted(req.clips, key=lambda x: x.rank, reverse=True)
        processed = []

        for i, clip in enumerate(clips_sorted):
            video_url = get_pexels_video(clip.aciklama)
            raw_path = f"{work_dir}/raw_{i}.mp4"
            proc_path = f"{work_dir}/proc_{i}.mp4"

            download_video(video_url, raw_path)

            subprocess.run([
                "ffmpeg", "-i", raw_path,
                "-t", "6",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-an", "-y", proc_path
            ], check=True, capture_output=True)
            processed.append(proc_path)

        concat_file = f"{work_dir}/concat.txt"
        with open(concat_file, "w") as f:
            for p in processed:
                f.write(f"file '{p}'\n")

        merged = f"{work_dir}/merged.mp4"
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", "-y", merged
        ], check=True, capture_output=True)

        numbers_filter = ""
        for i, clip in enumerate(clips_sorted):
            y_pos = 200 + (i * 120)
            numbers_filter += f"drawtext=text='{clip.rank}.':fontsize=55:fontcolor=white:x=40:y={y_pos},"

        active_filter = ""
        for i, clip in enumerate(clips_sorted):
            start_t = i * 6
            end_t = start_t + 6
            y_pos = 200 + (i * 120)
            safe_text = clip.aciklama.replace("'", "").replace(":", "").replace(",", "")
            active_filter += f"drawtext=text='{safe_text}':fontsize=32:fontcolor=yellow:x=110:y={y_pos+10}:enable='between(t\\,{start_t}\\,{end_t})',"

        safe_title = req.seri_adi.replace("'", "")
        title_filter = f"drawtext=text='{safe_title}':fontsize=52:fontcolor=white:x=(w-tw)/2:y=60:box=1:boxcolor=black@0.5:boxborderw=10"

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

        return Response(content=video_bytes, media_type="video/mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

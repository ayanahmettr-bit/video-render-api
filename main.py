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
    api_url = "https://api.pexels.com/videos/search?query=" + urllib.parse.quote(keyword) + "&per_page=3&orientation=portrait"
    req = urllib.request.Request(api_url, headers={"Authorization": PEXELS_API_KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    videos = data.get("videos", [])
    if not videos:
        api_url2 = "https://api.pexels.com/videos/search?query=people&per_page=1&orientation=portrait"
        req2 = urllib.request.Request(api_url2, headers={"Authorization": PEXELS_API_KEY})
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

@app.post("/render")
async def render_video(req: VideoRequest):
    job_id = str(uuid.uuid4())
    work_dir = "/tmp/" + job_id
    os.makedirs(work_dir, exist_ok=True)

    try:
        clips_sorted = sorted(req.clips, key=lambda x: x.rank, reverse=True)
        processed = []

        for i, clip in enumerate(clips_sorted):
            video_url = get_pexels_video(clip.aciklama)
            proc_path = work_dir + "/proc_" + str(i) + ".mp4"

            result = subprocess.run([
                "ffmpeg",
                "-headers", "Referer: https://www.pexels.com/\r\nUser-Agent: Mozilla/5.0\r\n",
                "-i", video_url,
                "-t", "6",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264", "-an", "-y", proc_path
            ], capture_output=True, timeout=120)

            if result.returncode != 0:
                raise Exception("FFmpeg hatasi: " + result.stderr.decode())

            processed.append(proc_path)

        concat_file = work_dir + "/concat.txt"
        with open(concat_file, "w") as f:
            for p in processed:
                f.write("file '" + p + "'\n")

        merged = work_dir + "/merged.mp4"
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", "-y", merged
        ], check=True, capture_output=True)

        numbers_filter = ""
        for i, clip in enumerate(clips_sorted):
            y_pos = 200 + (i * 120)
            numbers_filter += "drawtext=text='" + str(clip.rank) + ".':fontsize=55:fontcolor=white:x=40:y=" + str(y_pos) + ","

        active_filter = ""
        for i, clip in enumerate(clips_sorted):
            start_t = i * 6
            end_t = start_t + 6
            y_pos = 200 + (i * 120)
            safe_text = clip.aciklama.replace("'", "").replace(":", "").replace(",", "")
            active_filter += "drawtext=text='" + safe_text + "':fontsize=32:fontcolor=yellow:x=110:y=" + str(y_pos + 10) + ":enable='between(t\\," + str(start_t) + "\\," + str(end_t) + ")',"

        safe_title = req.seri_adi.replace("'", "")
        title_filter = "drawtext=text='" + safe_title + "':fontsize=52:fontcolor=white:x=(w-tw)/2:y=60:box=1:boxcolor=black@0.5:boxborderw=10"

        full_filter = numbers_filter + active_filter + title_filter

        output = work_dir + "/final.mp4"
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

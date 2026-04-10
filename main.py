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

class Clip(BaseModel):
    url: Optional[str] = None
    aciklama: str
    rank: int

class VideoRequest(BaseModel):
    seri_adi: str
    clips: List[Clip]

def get_cobalt_url(original_url: str):
    try:
        req_body = json.dumps({
            "url": original_url,
            "videoQuality": "720",
            "downloadMode": "video"
        }).encode()
        req = urllib.request.Request(
            "https://api.cobalt.tools/",
            data=req_body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        if data.get("status") in ["redirect", "tunnel"]:
            return data.get("url")
        return None
    except:
        return None

def download_with_ytdlp(url: str, output_path: str) -> bool:
    result = subprocess.run([
        "yt-dlp",
        "-f", "best[height<=720][ext=mp4]/best[height<=720]/best",
        "-o", output_path,
        "--no-playlist",
        "--merge-output-format", "mp4",
        "--no-check-certificates",
        url
    ], capture_output=True, text=True, timeout=120)
    return result.returncode == 0

def make_fallback_clip(work_dir: str, index: int, output_path: str):
    colors = ["0x1a1a2e", "0x16213e", "0x0f3460", "0x1b1b2f", "0x2c2c54"]
    color = colors[index % len(colors)]
    subprocess.run([
        "ffmpeg", "-f", "lavfi",
        "-i", "color=c=" + color + ":size=1080x1920:rate=30",
        "-t", "6", "-c:v", "libx264", "-y", output_path
    ], check=True, capture_output=True)

@app.post("/render")
async def render_video(req: VideoRequest):
    job_id = str(uuid.uuid4())
    work_dir = "/tmp/" + job_id
    os.makedirs(work_dir, exist_ok=True)

    try:
        clips_sorted = sorted(req.clips, key=lambda x: x.rank, reverse=True)
        processed = []

        for i, clip in enumerate(clips_sorted):
            proc_path = work_dir + "/proc_" + str(i) + ".mp4"
            raw_path = work_dir + "/raw_" + str(i) + ".mp4"
            downloaded = False

            if clip.url and clip.url.strip() and clip.url.startswith("http"):
                # Cobalt deneyelim
                cobalt_url = get_cobalt_url(clip.url)
                if cobalt_url:
                    downloaded = download_with_ytdlp(cobalt_url, raw_path)

                # Cobalt basarisizsa yt-dlp ile direkt dene
                if not downloaded:
                    downloaded = download_with_ytdlp(clip.url, raw_path)

                # Video indirildiyse FFmpeg ile isle
                if downloaded and os.path.exists(raw_path):
                    r = subprocess.run([
                        "ffmpeg", "-i", raw_path,
                        "-t", "6",
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                        "-c:v", "libx264", "-an", "-y", proc_path
                    ], capture_output=True, timeout=120)
                    if r.returncode != 0:
                        downloaded = False

            if not downloaded:
                make_fallback_clip(work_dir, i, proc_path)

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
            numbers_filter += "drawtext=text='" + str(clip.rank) + ".':fontsize=60:fontcolor=white:x=40:y=" + str(y_pos) + ","

        active_filter = ""
        for i, clip in enumerate(clips_sorted):
            start_t = i * 6
            end_t = start_t + 6
            y_pos = 200 + (i * 120)
            safe_text = clip.aciklama.replace("'", "").replace(":", "").replace(",", "")
            active_filter += "drawtext=text='" + safe_text + "':fontsize=34:fontcolor=yellow:x=110:y=" + str(y_pos + 12) + ":enable='between(t\\," + str(start_t) + "\\," + str(end_t) + ")',"

        safe_title = req.seri_adi.replace("'", "")
        title_filter = "drawtext=text='" + safe_title + "':fontsize=54:fontcolor=white:x=(w-tw)/2:y=60:box=1:boxcolor=black@0.6:boxborderw=12"

        full_filter = numbers_filter + active_filter + title_filter

        output = work_dir + "/final.mp4"
        r2 = subprocess.run([
            "ffmpeg", "-i", merged,
            "-vf", full_filter,
            "-c:v", "libx264", "-y", output
        ], capture_output=True)

        if r2.returncode != 0:
            raise Exception("Overlay hatasi: " + r2.stderr.decode())

        with open(output, "rb") as f:
            video_bytes = f.read()

        return Response(content=video_bytes, media_type="video/mp4")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}

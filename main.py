from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List
import subprocess
import uuid
import os

app = FastAPI()

class Clip(BaseModel):
    url: str
    aciklama: str
    rank: int

class VideoRequest(BaseModel):
    seri_adi: str
    clips: List[Clip]

def download_video(url: str, output_path: str):
    result = subprocess.run([
        "yt-dlp",
        "-f", "best[height<=720]/best",
        "-o", output_path,
        "--no-playlist",
        "--merge-output-format", "mp4",
        url
    ], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise Exception(f"İndirme hatası: {result.stderr}")

@app.post("/render")
async def render_video(req: VideoRequest):
    job_id = str(uuid.uuid4())
    work_dir = f"/tmp/{job_id}"
    os.makedirs(work_dir, exist_ok=True)

    try:
        clips_sorted = sorted(req.clips, key=lambda x: x.rank, reverse=True)
        processed = []

        for i, clip in enumerate(clips_sorted):
            raw_path = f"{work_dir}/raw_{i}.mp4"
            proc_path = f"{work_dir}/proc_{i}.mp4"

            download_video(clip.url, raw_path)

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
            safe_text = clip.aciklama.replace("'", "")
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

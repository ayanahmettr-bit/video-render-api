from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional
import subprocess
import uuid
import os

app = FastAPI()

class Clip(BaseModel):
    url: Optional[str] = None
    aciklama: str
    rank: int

class VideoRequest(BaseModel):
    seri_adi: str
    clips: List[Clip]

@app.post("/render")
async def render_video(req: VideoRequest):
    job_id = str(uuid.uuid4())
    work_dir = "/tmp/" + job_id
    os.makedirs(work_dir, exist_ok=True)

    try:
        clips_sorted = sorted(req.clips, key=lambda x: x.rank, reverse=True)
        total_duration = len(clips_sorted) * 6

        bg_path = work_dir + "/bg.mp4"
        r = subprocess.run([
            "ffmpeg", "-f", "lavfi",
            "-i", "color=c=0x1a1a2e:size=1080x1920:rate=30",
            "-t", str(total_duration),
            "-c:v", "libx264", "-y", bg_path
        ], capture_output=True)
        if r.returncode != 0:
            raise Exception("BG hatasi: " + r.stderr.decode())

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
            "ffmpeg", "-i", bg_path,
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

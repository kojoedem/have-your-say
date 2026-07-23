import os
import subprocess
from pathlib import Path

VIDEO_ORIGINAL_DIR = Path("videos/original")
VIDEO_SEGMENT_DIR = Path("videos/segments")
VIDEO_THUMBNAIL_DIR = Path("videos/thumbnails")

# Create directories
VIDEO_ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

THUMBNAIL_FPS = 0.5  # 1 frame every 2 seconds (1/2 = 0.5 fps)

def get_video_duration(filepath: str) -> float:
    """
    Returns the duration of the video in seconds using ffprobe.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0.0

def process_video_segments_and_thumbnails(video_id: int, original_filename: str):
    """
    Processes the video:
    1. Splits the video into 60-second segments using FFmpeg.
    2. Generates timeline preview thumbnails at 2-second intervals (FPS = 0.5).
    """
    original_path = VIDEO_ORIGINAL_DIR / f"{video_id}_{original_filename}"
    if not original_path.exists():
        print(f"Original video not found: {original_path}")
        return False

    duration = get_video_duration(str(original_path))

    # 1. Split into 60-second chunks
    segment_output = VIDEO_SEGMENT_DIR / f"{video_id}_%03d.mp4"
    try:
        segment_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(original_path),
            "-c", "copy",
            "-map", "0",
            "-f", "segment",
            "-segment_time", "60",
            str(segment_output)
        ]
        subprocess.run(segment_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"Error segmenting video {video_id}: {e}")
        return False

    # Count generated segments
    segments_count = 0
    for file in VIDEO_SEGMENT_DIR.glob(f"{video_id}_*.mp4"):
        segments_count += 1

    # 2. Extract preview frame thumbnails (160x90 resolution, highly lightweight)
    thumbnail_output = VIDEO_THUMBNAIL_DIR / f"{video_id}_%03d.jpg"
    try:
        # fps=0.5 -> 1 frame every 2 seconds
        # scale=160:-1 -> preserve aspect ratio with width 160
        thumbnail_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(original_path),
            "-vf", f"fps={THUMBNAIL_FPS},scale=160:-1",
            "-q:v", "5",  # moderate quality to save storage
            str(thumbnail_output)
        ]
        subprocess.run(thumbnail_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"Error generating thumbnails for video {video_id}: {e}")

    # Update database metadata outside of here or return values
    return {
        "duration": duration,
        "segments_count": segments_count
    }

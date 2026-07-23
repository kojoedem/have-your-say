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

THUMBNAIL_FPS = 0.5  # 1 frame every 2 seconds

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

def trim_selected_video_frame(video_id: int, original_filename: str, frame_index: int):
    """
    Extracts ONLY the selected 60-second section (frame) of the video.
    Deletes the original video file immediately afterwards to conserve storage.
    Generates preview thumbnails from the trimmed 60-second clip.
    """
    original_path = VIDEO_ORIGINAL_DIR / f"{video_id}_{original_filename}"
    if not original_path.exists():
        print(f"Original video not found: {original_path}")
        return False

    # Calculate offset
    start_seconds = frame_index * 60

    # 1. Trim the selected 60-second section into segment 000
    trimmed_segment_path = VIDEO_SEGMENT_DIR / f"{video_id}_000.mp4"
    try:
        # Use -ss before -i for fast seeking
        trim_cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start_seconds),
            "-t", "60",
            "-i", str(original_path),
            "-c:v", "libx264",  # re-encode to ensure keyframe alignment and robust browser playback
            "-c:a", "aac",
            "-strict", "experimental",
            str(trimmed_segment_path)
        ]
        subprocess.run(trim_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"Error trimming video frame {video_id} (frame {frame_index}): {e}")
        return False

    # Get the duration of the extracted segment
    trimmed_duration = get_video_duration(str(trimmed_segment_path))

    # 2. Extract preview thumbnails from the trimmed 1-minute clip
    # This is fast, light, and optimized!
    thumbnail_output = VIDEO_THUMBNAIL_DIR / f"{video_id}_%03d.jpg"
    try:
        thumbnail_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(trimmed_segment_path),
            "-vf", f"fps={THUMBNAIL_FPS},scale=160:-1",
            "-q:v", "5",
            str(thumbnail_output)
        ]
        subprocess.run(thumbnail_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"Error generating thumbnails for trimmed video {video_id}: {e}")

    # 3. IMMEDIATELY delete the original heavy video file
    try:
        original_path.unlink()
        print(f"[video_processor] Successfully deleted original video {original_path}")
    except Exception as e:
        print(f"[video_processor] Error deleting original video: {e}")

    return {
        "duration": trimmed_duration,
        "segments_count": 1  # Only the single 60s selected segment is kept
    }

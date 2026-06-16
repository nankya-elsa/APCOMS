"""
Frame extraction script for YOLOv8 fine-tuning.

Walks every video in fine_tuning/raw_videos/ and extracts frames
at a configurable rate (default 2 frames per second). Frames are
saved to fine_tuning/extracted_frames/ with names like
'video1_frame_0001.jpg' so they sort sensibly and the source
video is traceable.

Usage:
    python extract_frames.py
    python extract_frames.py --fps 3
    python extract_frames.py --fps 1 --quality 90

The script is idempotent — re-running on the same videos
overwrites previous extractions cleanly, which is what we want
during iteration.
"""

import argparse
import os
from pathlib import Path

import cv2


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def extract_from_video(video_path, output_dir, target_fps, jpeg_quality):
    """
    Extract frames from a single video at the target frames-per-second.

    Returns the number of frames written.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  [SKIP] Could not open {video_path.name}")
        return 0

    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / source_fps

    # how many source frames to skip between each saved frame
    frame_interval = max(1, round(source_fps / target_fps))

    base_name = video_path.stem
    saved_count = 0
    frame_index = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_index % frame_interval == 0:
            saved_count += 1
            out_path = output_dir / f"{base_name}_frame_{saved_count:04d}.jpg"
            cv2.imwrite(
                str(out_path),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
            )

        frame_index += 1

    cap.release()
    print(
        f"  {video_path.name}: {saved_count} frames "
        f"(duration {duration_sec:.1f}s, source {source_fps:.1f}fps)"
    )
    return saved_count


def main():
    parser = argparse.ArgumentParser(
        description="Extract frames from videos for YOLO fine-tuning."
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=2.0,
        help="Frames to extract per second of source video (default: 2).",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="JPEG quality 0-100 (default: 95).",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    raw_videos_dir = script_dir / "raw_videos"
    output_dir = script_dir / "extracted_frames"

    if not raw_videos_dir.exists():
        print(f"ERROR: raw_videos folder not found at {raw_videos_dir}")
        return

    videos = sorted(
        p for p in raw_videos_dir.iterdir()
        if p.suffix.lower() in VIDEO_EXTENSIONS
    )

    if not videos:
        print(f"No videos found in {raw_videos_dir}")
        print(f"Supported extensions: {', '.join(sorted(VIDEO_EXTENSIONS))}")
        return

    print(f"Found {len(videos)} video(s). Extracting at {args.fps} fps...")
    total = 0
    for video in videos:
        total += extract_from_video(video, output_dir, args.fps, args.quality)

    print(f"\nDone. {total} frame(s) saved to {output_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# إعادة توليد الفيديو من الصفر (يحتاج ffmpeg + python3 + pillow + fonts في assets/../fonts)
set -e
python3 align.py                       # مزامنة الكلمات المصححة مع توقيت الصوت
python3 audio.py                       # التعليق + المؤثرات
python3 render.py full --out renders/video_raw.mp4
ffmpeg -y -i renders/video_raw.mp4 -i renders/soundtrack.m4a \
  -c:v libx264 -preset slow -b:v 1450k -pass 1 -passlogfile renders/pass -pix_fmt yuv420p -g 50 -an -f mp4 /dev/null
ffmpeg -y -i renders/video_raw.mp4 -i renders/soundtrack.m4a \
  -c:v libx264 -preset slow -b:v 1450k -pass 2 -passlogfile renders/pass -pix_fmt yuv420p \
  -profile:v high -level 4.1 -g 50 -c:a aac -b:a 96k -ac 1 -movflags +faststart -shortest final.mp4
echo "done: final.mp4"

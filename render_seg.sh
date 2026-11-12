#!/usr/bin/env bash
# رندر على مقاطع (الذاكرة محدودة: 2 جيجا بلا swap) ثم دمج بلا إعادة ترميز
set -e
cd /home/user/work
mkdir -p renders/segs
rm -f renders/segs/*.mp4 renders/segs/list.txt
I=0
for RANGE in "0 15" "15 30" "30 45" "45 60" "60 75" "75 90"; do
  set -- $RANGE
  OUT=$(printf "renders/segs/s%02d.mp4" $I)
  echo "== المقطع $I : $1 → $2"
  python3 render.py full --start $1 --end $2 --out "$OUT" --crf 23 --maxrate 1550k
  echo "file '$PWD/$OUT'" >> renders/segs/list.txt
  I=$((I+1))
done
echo "== الدمج"
ffmpeg -y -v error -f concat -safe 0 -i renders/segs/list.txt -c copy renders/video_v2.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 renders/video_v2.mp4
echo "== المزج مع الصوت"
ffmpeg -y -v error -i renders/video_v2.mp4 -i renders/mix_balanced.m4a \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 128k -ac 1 -t 90 -movflags +faststart renders/final_v2.mp4
ffprobe -v error -show_entries format=duration,size -of default=nw=1 renders/final_v2.mp4
echo "== تم"

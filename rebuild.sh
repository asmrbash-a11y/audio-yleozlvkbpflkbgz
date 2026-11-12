#!/usr/bin/env bash
# إعادة توليد الفيديو من الصفر على أي ملف تعليق
#   الاستعمال: bash rebuild.sh /path/to/voice.mp3 89.91
set -e
VOICE=${1:-VAHxPqaelNvcLSCW-1.mp3}
END=${2:-89.91}
python3 sfxgen.py assets/sfx3
python3 newalign.py "$VOICE" --end "$END" --out data/align_full.json
python3 rebuild_timeline.py --align data/align_full.json --end 90.0
python3 audio_new.py "$VOICE" --end "$END" --bed 20 --ceil 26 \
        --align data/align_full.json --out renders/mix_balanced.m4a
bash render_final.sh

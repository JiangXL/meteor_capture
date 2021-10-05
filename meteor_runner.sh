#!/bin/bash
dir="/home/pi/meteor_data"
timestamp=$(date '+%Y%m%d-%H%M')

cd /home/pi/meteor_capture
echo $timestamp >> meteor.log

# start indiserver
indiserver indi_qhy_ccd > "$dir/log/$timestamp-indi.log" 2>&1 &
sleep 1

# meteor capture 
python3 /home/pi/meteor_capture/main.py 2>&1 "$dir/log/$timestamp-main.log" 

# kill indiserver
pkill indiserver

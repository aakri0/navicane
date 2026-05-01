#!/bin/bash
echo "Stopping Blind Stick System..."
sudo systemctl stop blind-stick.service
touch /tmp/stop_blind_stick
echo "Blind Stick System stopped."
echo "Check logs: tail -f /home/pi/interdesciplinary/blind_stick.log"

#!/bin/bash
echo "Starting Blind Stick System..."
rm -f /tmp/stop_blind_stick
sudo systemctl start blind-stick.service
echo "Blind Stick System started."
echo "Check status: sudo systemctl status blind-stick.service"
echo "Check logs: tail -f /home/pi/interdesciplinary/blind_stick.log"

#!/bin/bash

# Startup script for Blind Stick System
echo "Starting Blind Stick System..." >> /home/pi/blind_stick.log

# Wait for system to fully boot
sleep 30

# Change to the correct directory
cd /home/pi

# Activate virtual environment if you're using one
# source myenv/bin/activate

# Set Python path
export PYTHONPATH=/home/pi/interdesciplinary/models:$PYTHONPATH

# Start the blind stick system
python3 /home/pi/interdesciplinary/models/final1.py >> /home/pi/blind_stick.log 2>&1

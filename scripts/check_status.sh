#!/bin/bash
echo "=== Blind Stick System Status ==="
echo "Service Status:"
sudo systemctl status blind-stick.service --no-pager
echo ""
echo "Recent Logs:"
tail -10 /home/pi/interdesciplinary/blind_stick.log
echo ""
echo "=== End Status ==="

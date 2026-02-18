#!/bin/bash
gnome-terminal -- bash -c 'echo "Starting MongoDB..." && sudo systemctl start mongod && echo "" && echo "MongoDB started successfully!" || echo "Failed to start MongoDB"; echo ""; read -p "Press Enter to close..."' 2>/dev/null || \
xfce4-terminal -e "bash -c 'echo "Starting MongoDB..." && sudo systemctl start mongod && echo "" && echo "MongoDB started successfully!" || echo "Failed to start MongoDB"; echo ""; read -p "Press Enter to close..."'" 2>/dev/null || \
konsole -e bash -c 'echo "Starting MongoDB..." && sudo systemctl start mongod && echo "" && echo "MongoDB started successfully!" || echo "Failed to start MongoDB"; echo ""; read -p "Press Enter to close..."' 2>/dev/null || \
xterm -e bash -c 'echo "Starting MongoDB..." && sudo systemctl start mongod && echo "" && echo "MongoDB started successfully!" || echo "Failed to start MongoDB"; echo ""; read -p "Press Enter to close..."' 2>/dev/null

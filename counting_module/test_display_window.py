import sys
import os
import time
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from display import DisplayComponent

display = DisplayComponent()
display.initialize_display()

# simulate some occupancy data
occupancy_data = {
    "passenger_count": 8,
    "available_seats": 12,
    "occupancy_status": "Available"
}

print("Showing display window for 5 seconds...")
print("Press any key to close")

# show the window for 5 seconds
start = time.time()
while time.time() - start < 5:
    display.show(occupancy_data, system_status="Active")

cv2.destroyAllWindows()
print("Done!")

import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)

class DisplayComponent:

    def __init__(self):
        self.font_size = 24
        self.screen_brightness = "auto"
        self.display_status = "inactive"
        self.window_name = "APCOMS - E-Shuttle Display"

    def initialize_display(self):
        """
        Initializes the display window for simulation using OpenCV.
        Sets display status to active on success.
        Logs success message when display is ready.
        """
        self.display_status = "active"
        logger.info("OLED display initialized successfully")

    def render_occupancy(self, occupancy_data):
        """
        Renders occupancy information for display on the OLED screen.
        Returns a dictionary containing formatted text and color codes
        for passenger count, available seats and occupancy status.
        """
        if occupancy_data is None:
            return None

        passenger_count = occupancy_data["passenger_count"]
        available_seats = occupancy_data["available_seats"]
        occupancy_status = occupancy_data["occupancy_status"]

        if occupancy_status == "Available":
            color = (0, 255, 0)        # green in BGR
            status_text = "AVAILABLE"
        elif occupancy_status == "Nearly Full":
            color = (0, 255, 255)      # yellow in BGR
            status_text = "NEARLY FULL"
        else:
            color = (0, 0, 255)        # red in BGR
            status_text = "FULL"

        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        return {
            "passengers_text": f"Passengers Onboard:  {passenger_count}",
            "available_text": f"Available Seats:     {available_seats}",
            "status_text": f"Occupancy Status:    {status_text}",
            "color": color,
            "timestamp": f"Last Updated:        {timestamp}"
        }

    def render_system_status(self, system_status):
        """
        Renders system status information for display on the OLED screen.
        Returns a dictionary containing formatted status text and message
        for Active, Calibrating and Error states.
        """
        if system_status is None:
            return None

        if system_status == "Active":
            status_text = "System: Active"
            message = "All systems operational"
        elif system_status == "Calibrating":
            status_text = "System: Calibrating"
            message = "Please wait..."
        else:
            status_text = "System: Error"
            message = "Check system logs"

        return {
            "status_text": status_text,
            "message": message
        }

    def auto_dim(self, ambient_light):
        """
        Adjusts screen brightness based on ambient light level.
        Reduces brightness when light is low to avoid glare in dark
        conditions and restores normal brightness in daylight.
        """
        low_threshold = 50

        if ambient_light < low_threshold:
            self.screen_brightness = "low"
        else:
            self.screen_brightness = "normal"

    def show(self, occupancy_data, system_status="Active"):
        """
        Renders and shows the OLED simulation window using OpenCV.
        Displays passenger count, available seats, occupancy status,
        current stop and system status with color coding.
        """
        rendered = self.render_occupancy(occupancy_data)
        status = self.render_system_status(system_status)

        if rendered is None:
            return

        # create black canvas simulating OLED screen
        canvas = __import__('numpy').zeros((400, 600, 3), dtype=__import__('numpy').uint8)

        color = rendered["color"]
        white = (255, 255, 255)
        gray = (150, 150, 150)

        cv2.putText(canvas, "APCOMS - E-Shuttle", (20, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, white, 2)
        cv2.line(canvas, (20, 55), (580, 55), gray, 1)

        cv2.putText(canvas, rendered["passengers_text"], (20, 100),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, white, 1)
        cv2.putText(canvas, rendered["available_text"], (20, 140),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, white, 1)
        cv2.putText(canvas, rendered["status_text"], (20, 180),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        cv2.line(canvas, (20, 200), (580, 200), gray, 1)

        cv2.putText(canvas, status["status_text"], (20, 240),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, white, 1)
        cv2.putText(canvas, rendered["timestamp"], (20, 280),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, gray, 1)

        cv2.imshow(self.window_name, canvas)
        cv2.waitKey(1)

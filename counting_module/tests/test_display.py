import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from display import DisplayComponent


class TestDisplayInitialization:

    def test_display_initializes_successfully(self):
        """
        Test that DisplayComponent initializes correctly so the system
        has a display ready to show occupancy information to shuttle
        operators and onboard passengers
        """
        display = DisplayComponent()
        assert display is not None

    def test_display_has_correct_default_font_size(self):
        """
        Test that font size defaults to 24 to ensure text on the OLED
        display is clearly readable by shuttle operators and passengers
        from inside the shuttle cabin as required by NFR-CM-7.1
        """
        display = DisplayComponent()
        assert display.font_size == 24

    def test_display_has_correct_default_brightness(self):
        """
        Test that screen brightness defaults to auto so the display
        automatically adjusts to ambient light conditions inside
        the shuttle cabin for optimal visibility
        """
        display = DisplayComponent()
        assert display.screen_brightness == "auto"

    def test_display_status_inactive_before_initialization(self):
        """
        Test that display status is inactive before initialize_display()
        is called to confirm the system is not rendering before it is
        explicitly started
        """
        display = DisplayComponent()
        assert display.display_status == "inactive"

    def test_display_status_active_after_initialization(self):
        """
        Test that display status changes to active after initialize_display()
        is called to confirm the OLED screen is ready to render occupancy
        information to shuttle operators and passengers
        """
        display = DisplayComponent()
        display.initialize_display()
        assert display.display_status == "active"

    def test_initialize_display_logs_success(self, caplog):
        """
        Test that initialize_display() logs a success message to confirm
        the OLED screen is ready and the System Monitor knows the
        display has started successfully
        """
        import logging
        display = DisplayComponent()
        with caplog.at_level(logging.INFO):
            display.initialize_display()
        assert "OLED display initialized successfully" in caplog.text


class TestOccupancyRendering:

    def test_render_occupancy_returns_formatted_string(self):
        """
        Test that render_occupancy() returns a formatted string so the
        display has content ready to render on the OLED screen
        """
        display = DisplayComponent()
        occupancy_data = {
            "passenger_count": 5,
            "available_seats": 15,
            "occupancy_status": "Available"
        }
        result = display.render_occupancy(occupancy_data)
        assert result is not None
        assert isinstance(result, dict)

    def test_rendered_output_contains_passenger_count(self):
        """
        Test that render_occupancy() includes passenger count in output
        so shuttle operators can see exactly how many people are onboard
        at any given time
        """
        display = DisplayComponent()
        occupancy_data = {
            "passenger_count": 5,
            "available_seats": 15,
            "occupancy_status": "Available"
        }
        result = display.render_occupancy(occupancy_data)
        assert "5" in result["passengers_text"]

    def test_rendered_output_contains_available_seats(self):
        """
        Test that render_occupancy() includes available seats in output
        so passengers can see exactly how many seats are left before
        deciding to go to the shuttle stop
        """
        display = DisplayComponent()
        occupancy_data = {
            "passenger_count": 5,
            "available_seats": 15,
            "occupancy_status": "Available"
        }
        result = display.render_occupancy(occupancy_data)
        assert "15" in result["available_text"]

    def test_rendered_output_contains_occupancy_status(self):
        """
        Test that render_occupancy() includes occupancy status in output
        so passengers can immediately understand the shuttle capacity
        situation at a glance
        """
        display = DisplayComponent()
        occupancy_data = {
            "passenger_count": 5,
            "available_seats": 15,
            "occupancy_status": "Available"
        }
        result = display.render_occupancy(occupancy_data)
        assert "AVAILABLE" in result["status_text"]

    def test_rendered_output_contains_timestamp(self):
        """
        Test that render_occupancy() includes last updated timestamp
        so operators can verify the display is showing live data
        and not stale information
        """
        display = DisplayComponent()
        occupancy_data = {
            "passenger_count": 5,
            "available_seats": 15,
            "occupancy_status": "Available"
        }
        result = display.render_occupancy(occupancy_data)
        assert "Last Updated" in result["timestamp"]

    def test_returns_green_color_for_available_status(self):
        """
        Test that render_occupancy() returns green color when status is
        Available so passengers can immediately identify the shuttle
        has plenty of seats at a glance
        """
        display = DisplayComponent()
        occupancy_data = {
            "passenger_count": 5,
            "available_seats": 15,
            "occupancy_status": "Available"
        }
        result = display.render_occupancy(occupancy_data)
        assert result["color"] == (0, 255, 0)

    def test_returns_yellow_color_for_nearly_full_status(self):
        """
        Test that render_occupancy() returns yellow color when status is
        Nearly Full so passengers know the shuttle is filling up and
        they should hurry to the stop
        """
        display = DisplayComponent()
        occupancy_data = {
            "passenger_count": 17,
            "available_seats": 3,
            "occupancy_status": "Nearly Full"
        }
        result = display.render_occupancy(occupancy_data)
        assert result["color"] == (0, 255, 255)

    def test_returns_red_color_for_full_status(self):
        """
        Test that render_occupancy() returns red color when status is
        Full so passengers immediately know not to go to the shuttle
        stop and should seek alternative transportation
        """
        display = DisplayComponent()
        occupancy_data = {
            "passenger_count": 20,
            "available_seats": 0,
            "occupancy_status": "Full"
        }
        result = display.render_occupancy(occupancy_data)
        assert result["color"] == (0, 0, 255)

    def test_handles_none_occupancy_data_gracefully(self):
        """
        Test that render_occupancy() handles None input gracefully to
        prevent the display from crashing when no occupancy data is
        available from the Counting Logic Component
        """
        display = DisplayComponent()
        result = display.render_occupancy(None)
        assert result is None


class TestSystemStatusRendering:

    def test_render_system_status_returns_formatted_string(self):
        """
        Test that render_system_status() returns a formatted string so
        the display has system status content ready to render on the
        OLED screen for maintenance verification
        """
        display = DisplayComponent()
        result = display.render_system_status("Active")
        assert result is not None
        assert isinstance(result, dict)

    def test_displays_active_indicator_correctly(self):
        """
        Test that render_system_status() correctly renders Active state
        so shuttle operators know the system is fully operational
        """
        display = DisplayComponent()
        result = display.render_system_status("Active")
        assert "Active" in result["status_text"]
        assert "operational" in result["message"]

    def test_displays_calibrating_indicator_correctly(self):
        """
        Test that render_system_status() correctly renders Calibrating
        state so operators know to wait while the system sets itself up
        """
        display = DisplayComponent()
        result = display.render_system_status("Calibrating")
        assert "Calibrating" in result["status_text"]
        assert "Please wait" in result["message"]

    def test_displays_error_indicator_correctly(self):
        """
        Test that render_system_status() correctly renders Error state
        so operators know to check the system logs for troubleshooting
        """
        display = DisplayComponent()
        result = display.render_system_status("Error")
        assert "Error" in result["status_text"]
        assert "Check system logs" in result["message"]

    def test_handles_none_system_status_gracefully(self):
        """
        Test that render_system_status() handles None input gracefully
        to prevent the display from crashing when no system status
        is available from the System Monitor Component
        """
        display = DisplayComponent()
        result = display.render_system_status(None)
        assert result is None


class TestAutoDim:

    def test_auto_dim_reduces_brightness_when_light_is_low(self):
        """
        Test that auto_dim() reduces screen brightness when ambient
        light is low to prevent the display from being too bright
        in dark conditions inside the shuttle cabin
        """
        display = DisplayComponent()
        display.auto_dim(ambient_light=10)
        assert display.screen_brightness == "low"

    def test_auto_dim_restores_brightness_when_light_is_normal(self):
        """
        Test that auto_dim() restores normal brightness when ambient
        light is sufficient to ensure the display remains clearly
        visible to operators and passengers during daytime operation
        """
        display = DisplayComponent()
        display.auto_dim(ambient_light=200)
        assert display.screen_brightness == "normal"

    def test_brightness_stays_within_valid_range(self):
        """
        Test that auto_dim() keeps brightness within valid range to
        prevent the display from becoming completely invisible or
        damagingly bright under any lighting conditions
        """
        display = DisplayComponent()
        display.auto_dim(ambient_light=10)
        assert display.screen_brightness in ["low", "normal", "auto"]

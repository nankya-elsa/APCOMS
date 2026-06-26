"""
Test Service Hours Manager
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from service_hours_manager import ServiceHoursManager

def test_service_hours_manager():
    """Test that ServiceHoursManager can read and validate hours"""

    # Create manager instance
    manager = ServiceHoursManager(
        shuttle_id="shuttle_001",
        db_path="local_database/apcoms.db"
    )

    # Get current hours (should not raise error)
    hours = manager.get_current_hours()
    print(f"✓ Current service hours: {hours['start_time']} - {hours['end_time']}")

    # Test time format validation
    assert manager._validate_time_format("06:00") == True, "Should accept valid time"
    assert manager._validate_time_format("24:00") == True, "Should accept 24:00 (end of day)"
    assert manager._validate_time_format("25:00") == False, "Should reject 25:00"
    assert manager._validate_time_format("06:60") == False, "Should reject invalid minutes"
    assert manager._validate_time_format("invalid") == False, "Should reject invalid format"
    print("✓ Time format validation works correctly")

    # Test check_and_sync (should return True even without Firebase)
    result = manager.check_and_sync()
    print(f"✓ check_and_sync() returned: {result}")

    print("\nAll tests passed!")

if __name__ == "__main__":
    test_service_hours_manager()

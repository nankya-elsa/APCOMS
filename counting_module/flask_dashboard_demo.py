from flask import Flask, render_template_string, redirect, url_for
import sqlite3
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from counting_logic import CountingLogic

app = Flask(__name__)


def get_db_data():
    """Reads current occupancy, recent events and system state from SQLite"""
    conn = sqlite3.connect("local_database/apcoms_demo.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM passenger_events
        ORDER BY event_id DESC
        LIMIT 20
    """)
    events = cursor.fetchall()

    cursor.execute("""
        SELECT passenger_count, available_seats, stop_location
        FROM passenger_events
        ORDER BY event_id DESC
        LIMIT 1
    """)
    latest = cursor.fetchone()

    cursor.execute("""
        SELECT value FROM system_state
        WHERE key='current_stop_index'
    """)
    stop_result = cursor.fetchone()
    conn.close()

    return events, latest, stop_result


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="5">
    <title>APCOMS - Shuttle Monitoring Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: #0f1117;
            color: #ffffff;
            min-height: 100vh;
            padding: 30px;
        }
        .header { text-align: center; margin-bottom: 40px; }
        .header h1 { font-size: 2rem; color: #00d4aa; margin-bottom: 5px; }
        .header p { color: #888; font-size: 0.9rem; }
        .cards {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 40px;
        }
        .card {
            background: #1a1d2e;
            border-radius: 16px;
            padding: 30px;
            text-align: center;
            border: 1px solid #2a2d3e;
        }
        .card .label {
            font-size: 0.85rem;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
        }
        .card .value { font-size: 3.5rem; font-weight: 700; }
        .card .value.green { color: #00d4aa; }
        .card .value.yellow { color: #ffd700; }
        .card .value.red { color: #ff4757; }
        .card .value.stop { font-size: 1.2rem; margin-top: 10px; color: #00d4aa; }
        .status-badge {
            display: inline-block;
            padding: 8px 24px;
            border-radius: 50px;
            font-size: 1rem;
            font-weight: 600;
            margin-top: 10px;
        }
        .badge-available { background: #00d4aa22; color: #00d4aa; border: 1px solid #00d4aa; }
        .badge-nearly { background: #ffd70022; color: #ffd700; border: 1px solid #ffd700; }
        .badge-full { background: #ff475722; color: #ff4757; border: 1px solid #ff4757; }
        .section-title {
            font-size: 1.1rem;
            color: #00d4aa;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #2a2d3e;
        }
        table { width: 100%; border-collapse: collapse; background: #1a1d2e; border-radius: 16px; overflow: hidden; }
        th {
            background: #2a2d3e;
            padding: 15px 20px;
            text-align: left;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #888;
        }
        td { padding: 15px 20px; border-bottom: 1px solid #2a2d3e; font-size: 0.9rem; }
        tr:last-child td { border-bottom: none; }
        .event-boarding { color: #00d4aa; font-weight: 600; }
        .event-alighting { color: #ff4757; font-weight: 600; }
        .event-reset { color: #888; font-weight: 600; }
        .system-info { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 40px; }
        .info-card {
            background: #1a1d2e;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2a2d3e;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .info-dot { width: 12px; height: 12px; border-radius: 50%; background: #00d4aa; flex-shrink: 0; }
        .info-text .title { font-size: 0.8rem; color: #888; }
        .info-text .status { font-size: 0.95rem; font-weight: 600; color: #00d4aa; }
        .footer { text-align: center; margin-top: 40px; color: #444; font-size: 0.8rem; }
        .refresh-note { text-align: right; color: #444; font-size: 0.75rem; margin-bottom: 10px; }
        .reset-btn {
            background: #ff475722;
            color: #ff4757;
            border: 1px solid #ff4757;
            padding: 10px 24px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
        }
        .reset-btn:hover { background: #ff475744; }
        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
    </style>
</head>
<body>

    <div class="header">
        <h1>APCOMS Monitoring Dashboard</h1>
        <p>AI-Powered Passenger Counting and Real-Time Occupancy Monitoring System</p>
        <p style="margin-top:5px; color: #555;">Makerere University Driverless E-Shuttle · BSE26-8</p>
    </div>

    <div style="display: flex; justify-content: flex-end; margin-bottom: 20px;">
        <form method="POST" action="/reset">
            <button type="submit" class="reset-btn">Reset Count</button>
        </form>
    </div>

    <div class="cards">
        <div class="card">
            <div class="label">Passengers Onboard</div>
            <div class="value {{ count_color }}">{{ passenger_count }}</div>
        </div>
        <div class="card">
            <div class="label">Available Seats</div>
            <div class="value {{ seats_color }}">{{ available_seats }}</div>
        </div>
        <div class="card">
            <div class="label">Occupancy Status</div>
            <div class="value" style="font-size:1.5rem; margin-top:15px;">
                <span class="status-badge {{ badge_class }}">{{ occupancy_status }}</span>
            </div>
        </div>
        <div class="card">
            <div class="label">Current Stop</div>
            <div class="value stop">{{ current_stop }}</div>
        </div>
    </div>

    <p class="section-title">System Status</p>
    <div class="system-info" style="margin-bottom:40px;">
        <div class="info-card">
            <div class="info-dot"></div>
            <div class="info-text">
                <div class="title">AI Detection</div>
                <div class="status">YOLOv8n · Active</div>
            </div>
        </div>
        <div class="info-card">
            <div class="info-dot"></div>
            <div class="info-text">
                <div class="title">Object Tracking</div>
                <div class="status">DeepSORT · Active</div>
            </div>
        </div>
        <div class="info-card">
            <div class="info-dot"></div>
            <div class="info-text">
                <div class="title">Local Database</div>
                <div class="status">SQLite · Connected</div>
            </div>
        </div>
        <div class="info-card">
            <div class="info-dot"></div>
            <div class="info-text">
                <div class="title">Cloud Sync</div>
                <div class="status">Firebase · Connected</div>
            </div>
        </div>
        <div class="info-card">
            <div class="info-dot"></div>
            <div class="info-text">
                <div class="title">Shuttle ID</div>
                <div class="status">shuttle_001</div>
            </div>
        </div>
        <div class="info-card">
            <div class="info-dot"></div>
            <div class="info-text">
                <div class="title">Total Capacity</div>
                <div class="status">20 Seats</div>
            </div>
        </div>
    </div>

    <p class="section-title">Recent Passenger Events</p>
    <div class="refresh-note">Auto-refreshes every 5 seconds</div>
    <table>
        <thead>
            <tr>
                <th>Event ID</th>
                <th>Shuttle ID</th>
                <th>Timestamp</th>
                <th>Stop Location</th>
                <th>Event Type</th>
                <th>Passenger Count</th>
                <th>Available Seats</th>
            </tr>
        </thead>
        <tbody>
            {% for event in events %}
            <tr>
                <td>{{ event['event_id'] }}</td>
                <td>{{ event['shuttle_id'] }}</td>
                <td>{{ event['timestamp'] }}</td>
                <td>{{ event['stop_location'] or 'N/A' }}</td>
                <td>
                    <span class="event-{{ event['event_type'] }}">
                        {{ event['event_type'].upper() }}
                    </span>
                </td>
                <td>{{ event['passenger_count'] }}</td>
                <td>{{ event['available_seats'] }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="footer">
        <p>APCOMS · BSE26-8 · Nankya Elsa & Musiimenta Cissylyn · Makerere University {{ year }}</p>
        <p style="margin-top:5px;">Last updated: {{ last_updated }}</p>
    </div>

</body>
</html>
"""


@app.route("/")
def dashboard():
    events, latest, stop_result = get_db_data()

    if latest:
        passenger_count = latest["passenger_count"]
        available_seats = latest["available_seats"]
    else:
        passenger_count = 0
        available_seats = 20

    if stop_result:
        stop_index = int(stop_result["value"])
        temp = CountingLogic(total_capacity=20)
        current_stop = temp.designated_stops_list[stop_index]
    elif latest and latest["stop_location"]:
        current_stop = latest["stop_location"]
    else:
        current_stop = "Western Gate"

    if available_seats > 5:
        occupancy_status = "Available"
        count_color = "green"
        seats_color = "green"
        badge_class = "badge-available"
    elif available_seats >= 1:
        occupancy_status = "Nearly Full"
        count_color = "yellow"
        seats_color = "yellow"
        badge_class = "badge-nearly"
    else:
        occupancy_status = "Full"
        count_color = "red"
        seats_color = "red"
        badge_class = "badge-full"

    return render_template_string(
        DASHBOARD_HTML,
        events=events,
        passenger_count=passenger_count,
        available_seats=available_seats,
        occupancy_status=occupancy_status,
        count_color=count_color,
        seats_color=seats_color,
        badge_class=badge_class,
        current_stop=current_stop,
        year=datetime.datetime.now().year,
        last_updated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@app.route("/reset", methods=["POST"])
def reset():
    """Resets passenger count to zero and stop index back to Western Gate"""
    conn = sqlite3.connect("local_database/apcoms_demo.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO passenger_events
        (shuttle_id, timestamp, event_type, passenger_count, available_seats, stop_location)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("shuttle_001", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          "reset", 0, 20, "Western Gate"))
    cursor.execute("""
        INSERT OR REPLACE INTO system_state (key, value)
        VALUES ('current_stop_index', '0')
    """)
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  APCOMS Flask Monitoring Dashboard")
    print("  Open your browser at: http://localhost:5000")
    print("="*60 + "\n")
    app.run(debug=True)

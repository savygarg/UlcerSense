from pathlib import Path
import logging
import threading
import time
import re
from flask import Flask, jsonify
from flask_cors import CORS
import joblib
import numpy as np
import serial

# CONFIG
BASE_DIR = Path(__file__).resolve().parent
SERIAL_PORT = "COM14"
SERIAL_BAUDRATE = 115200
DEFAULT_PRESSURE_DURATION = 120
DATA_TIMEOUT = 5 

app = Flask(__name__)
CORS(app)
app.logger.setLevel(logging.INFO)

data_lock = threading.Lock()
latest_sensor_data = {"status": "ERROR", "message": "Initializing system..."}
last_data_time = time.time()

# MODEL LOAD
def _load_first_available(candidates):
    for filename in candidates:
        path = BASE_DIR / filename
        if path.exists():
            print(f"Loaded: {path.name}")
            return joblib.load(path)
    raise FileNotFoundError(f"Missing model files: {candidates}")

model = _load_first_available(["final_smart_mattress_model.pkl", "smart_mattress_model.pkl"])
label_encoder = _load_first_available(["final_label_encoder.pkl", "label_encoder.pkl"])

# AI PREDICTION WITH GUARD LOGIC
def predict_risk(sensor_values):
    # Fix: Agar bed khali hai (Pressure aur FSR negligible hain), toh prediction skip karein
    if sensor_values["pressure"] < 0.5 and sensor_values["fsr1"] < 0.5 and sensor_values["fsr2"] < 0.5:
        return "NONE"

    try:
        features = np.array([[
            sensor_values["temperature"],
            sensor_values["pressure"],
            DEFAULT_PRESSURE_DURATION,
            sensor_values["spo2"],
            0.0, 0.0, 0.0
        ]])
        prediction = model.predict(features)
        return str(label_encoder.inverse_transform(prediction)[0])
    except:
        return "ERROR"

# SERIAL READER
def serial_reader():
    global latest_sensor_data, last_data_time
    pattern = r"FSR1:\s*([\d.]+)\s*\|\s*FSR2:\s*([\d.]+)\s*\|\s*Avg Pressure:\s*([\d.]+)\s*\|\s*Temp:\s*([\d.]+)\s*C\s*\|\s*SpO2:\s*([A-Za-z0-9. ]+)"

    while True:
        ser = None
        try:
            ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
            time.sleep(2)
            while True:
                raw_line = ser.readline().decode(errors="ignore").strip()
                if not raw_line: continue
                match = re.search(pattern, raw_line)
                if not match: continue

                last_data_time = time.time()
                fsr1 = float(match.group(1))
                fsr2 = float(match.group(2))
                pressure = float(match.group(3))
                temp = float(match.group(4))
                spo2_raw = match.group(5).strip()
                spo2 = 0 if spo2_raw.lower() == "no finger" else float(spo2_raw)

                sensor_values = {"fsr1": fsr1, "fsr2": fsr2, "pressure": pressure, "temperature": temp, "spo2": spo2}
                risk = predict_risk(sensor_values)

                with data_lock:
                    latest_sensor_data = {"status": "ACTIVE", **sensor_values, "risk_level": risk}
        except Exception as e:
            with data_lock:
                latest_sensor_data = {"status": "ERROR", "message": str(e)}
            time.sleep(2)
        finally:
            if ser and ser.is_open: ser.close()

def watchdog():
    global latest_sensor_data, last_data_time
    while True:
        time.sleep(1)
        if time.time() - last_data_time > DATA_TIMEOUT:
            with data_lock:
                latest_sensor_data = {"status": "INACTIVE", "message": "Disconnected"}

@app.route("/sensor-data")
def get_sensor_data():
    with data_lock: return jsonify(latest_sensor_data)

if __name__ == "__main__":
    threading.Thread(target=serial_reader, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
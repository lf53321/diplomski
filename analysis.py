from fastapi import APIRouter
from pymongo import MongoClient
import pandas as pd
from geopy.distance import geodesic
import os
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv("MONGO_URI")

router = APIRouter()

client = MongoClient(mongo_uri)
db = client.get_database("CarPulse")
drivers = db["Drivers"]
trips = db["Trips"]
obd_data = db["OdbData"]
drivers_review_trips = db["DriversReviewTrip"]
trip_summary_col = db["TripSummary"]
driver_summary_col = db["DriverSummary"]
avg_summary_col = db["AverageDriverData"]

def process_trip(trip):
    trip_id = trip["tripId"]

    raw_records = list(obd_data.find({"tripId": trip_id}))

    if not raw_records:
        return None

    seen_timestamps = set()
    unique_records = []

    for record in raw_records:
        timestamp_val = record.get("timestamp")
        if timestamp_val and isinstance(timestamp_val, dict) and "$numberLong" in timestamp_val:
            timestamp_val = int(timestamp_val["$numberLong"])
            if timestamp_val not in seen_timestamps:
                seen_timestamps.add(timestamp_val)
                record["int_timestamp"] = timestamp_val
                unique_records.append(record)
        elif isinstance(timestamp_val, (int, float)):
             if timestamp_val not in seen_timestamps:
                seen_timestamps.add(timestamp_val)
                record["int_timestamp"] = int(timestamp_val)
                unique_records.append(record)
        else:
            pass


    sorted_records = sorted(unique_records, key=lambda r: r["int_timestamp"])

    trip_obd_records = sorted_records

    if not trip_obd_records:
        return None
    trip_start_ts = trip.get('tripStartTimestamp')
    if isinstance(trip_start_ts, dict) and '$numberLong' in trip_start_ts:
        trip_start = int(trip_start_ts['$numberLong'])
    elif isinstance(trip_start_ts, (int, float)):
        trip_start = int(trip_start_ts)
    else:
        print(f"Skipping trip {trip_id} due to unexpected tripStartTimestamp format: {trip_start_ts}")
        return None


    trip_end = int(trip_obd_records[-1]["int_timestamp"])
    trip_duration_sec = (trip_end - trip_start) / 1000
    trip_duration_min = trip_duration_sec / 60

    total_distance_km = 0
    all_speeds = []
    last_location = None
    speed_limit_compliance_time = 0
    over_speeding_time = 0
    traffic_speeds = []
    vehicle_speeds = []
    rapid_accelerations = 0
    hard_decelerations = 0
    stop_and_go_count = 0
    last_speed = 0
    rpm_values = []
    idling_time = 0

    for record in trip_obd_records:
        if "locationData" in record and record["locationData"] is not None:
            current_location = (record["locationData"]["latitude"], record["locationData"]["longitude"])

            if last_location:
                total_distance_km += geodesic(last_location, current_location).km
            last_location = current_location

        if "obdData" in record and record["obdData"] is not None and record["obdData"].get("SPEED") not in ["NODATA", None]:
            try:
                current_speed = float(record["obdData"].get("SPEED", 0))
                all_speeds.append(current_speed)
                vehicle_speeds.append(current_speed)

                if "trafficData" in record and record["trafficData"] is not None and record["trafficData"].get("flowSegmentData", 0):
                    traffic_speed = record["trafficData"]["flowSegmentData"]["freeFlowSpeed"]
                    traffic_speeds.append(traffic_speed)

                    if current_speed <= traffic_speed:
                        speed_limit_compliance_time += 1
                    else:
                        over_speeding_time += 1

                if "obdData" in record and record["obdData"] is not None and record["obdData"].get("ENGINE_RPM") not in ["NODATA", None, 0]:
                    try:
                        rpm_values.append(int(record["obdData"]["ENGINE_RPM"]))
                    except ValueError:
                        pass


                if last_speed and current_speed - last_speed > 5:
                    rapid_accelerations += 1
                if last_speed and last_speed - current_speed > 5:
                    hard_decelerations += 1
                if current_speed < 5 and last_speed >= 5:
                    stop_and_go_count += 1
                if current_speed < 5:
                    idling_time += 1

                last_speed = current_speed
            except ValueError:
                continue


    max_speed = max(all_speeds) if all_speeds else 0
    avg_speed = sum(all_speeds) / len(all_speeds) if all_speeds else 0

    speed_limit_compliance_percent = (speed_limit_compliance_time / len(all_speeds)) * 100 if all_speeds else 0
    over_speeding_percent = (over_speeding_time / len(all_speeds)) * 100 if all_speeds else 0

    avg_traffic_speed = sum(traffic_speeds) / len(traffic_speeds) if traffic_speeds else 0
    avg_vehicle_speed = sum(vehicle_speeds) / len(vehicle_speeds) if vehicle_speeds else 0

    traffic_speed_diff = avg_traffic_speed - avg_vehicle_speed if avg_traffic_speed and avg_vehicle_speed else 0

    rpm_avg = sum(rpm_values) / len(rpm_values) if rpm_values else 0
    rpm_max = max(rpm_values) if rpm_values else 0

    idling_time_percent = (idling_time / len(all_speeds)) * 100 if all_speeds else 0

    return {
        "Trip ID": trip_id,
        "Trip Duration (min)": trip_duration_min,
        "Travel Distance (km)": total_distance_km,
        "Max Speed (km/h)": max_speed,
        "Average Speed (km/h)": avg_speed,
        "Rapid Accelerations": rapid_accelerations,
        "Hard Decelerations": hard_decelerations,
        "Speed Limit Compliance (%)": speed_limit_compliance_percent,
        "Over-Speeding Duration (%)": over_speeding_percent,
        "Traffic Speed vs. Vehicle Speed Difference": traffic_speed_diff,
        "Stop-and-Go Frequency": stop_and_go_count,
        "Max RPM": rpm_max,
        "Average RPM": rpm_avg,
        "Idling Time (%)": idling_time_percent
    }

def update_trip_summary(trip_id, summary):
    trip_summary_col.replace_one({"Trip ID": trip_id}, summary, upsert=True)

def update_driver_summary(email):
    trips_data = list(trips.find({"driverEmail": email}, {"tripId": 1}))
    trip_ids = [t["tripId"] for t in trips_data]

    summaries = list(trip_summary_col.find({"Trip ID": {"$in": trip_ids}}))
    if not summaries:
        return

    df = pd.DataFrame(summaries)

    summary = {
        "Email": email,
        "Number of Trips": len(df),
        "Total Distance (km)": df["Travel Distance (km)"].sum(),
        "Average Distance (km)": df["Travel Distance (km)"].mean(),
        "Total Duration (min)": df["Trip Duration (min)"].sum(),
        "Average Duration (min)": df["Trip Duration (min)"].mean(),
        "Max Speed (km/h)": df["Max Speed (km/h)"].max(),
        "Average Speed (km/h)": df["Average Speed (km/h)"].mean(),
        "Rapid Accelerations": df["Rapid Accelerations"].mean(),
        "Hard Decelerations": df["Hard Decelerations"].mean(),
        "Speed Limit Compliance (%)": df["Speed Limit Compliance (%)"].mean(),
        "Over-Speeding Duration (%)": df["Over-Speeding Duration (%)"].mean(),
        "Traffic Speed vs. Vehicle Speed Difference": df["Traffic Speed vs. Vehicle Speed Difference"].mean(),
        "Stop-and-Go Frequency": df["Stop-and-Go Frequency"].mean(),
        "Average RPM": df["Average RPM"].mean(),
        "Max RPM": float(df["Max RPM"].max()),
        "Idling Time (%)": df["Idling Time (%)"].mean(),
    }

    driver_summary_col.replace_one({"Email": email}, summary, upsert=True)

def update_average_summary():
    all_driver_summaries = list(driver_summary_col.find())
    if not all_driver_summaries:
        return

    df = pd.DataFrame(all_driver_summaries)
    numeric_df = df.select_dtypes(include=['float64', 'int64'])

    average_summary = numeric_df.mean().to_dict()
    avg_summary_col.delete_many({})
    avg_summary_col.insert_one(average_summary)


@router.post("/process-trip/{trip_id}")
def process_trip_api(trip_id: str):
    trip = trips.find_one({"tripId": trip_id})
    if not trip:
        return {"error": f"Trip ID {trip_id} not found."}
    summary = process_trip(trip)
    if not summary:
        return {"error": f"No summary generated for Trip ID {trip_id}."}
    update_trip_summary(trip_id, summary)
    update_driver_summary(trip["driverEmail"])
    update_average_summary()
    return {"message": f"Trip {trip_id} processed successfully."}

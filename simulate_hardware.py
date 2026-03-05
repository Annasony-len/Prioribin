import requests
import time
import random

# --- CONFIGURATION ---
BASE_URL = 'http://127.0.0.1:5000'
UPDATE_URL = f'{BASE_URL}/api/update_bin'
GET_BINS_URL = f'{BASE_URL}/api/get_all_bins'

def get_registered_bins():
    """Fetches real bins from the Admin Dashboard"""
    try:
        response = requests.get(GET_BINS_URL)
        if response.status_code == 200:
            return response.json() # Returns list of bins
    except:
        return []
    return []

print("----------------------------------------------------------------")
print("🚀 PRIORIBIN: Edge Intelligence Simulator (Event-Triggered)")
print("----------------------------------------------------------------")
print("Waiting for server...")

# Local memory to track previous state (simulating Edge memory)
bin_states = {}

try:
    while True:
        # 1. Fetch Active Bins from Server
        # We check this every loop so if you add a new bin in Admin, it appears here automatically.
        active_bins = get_registered_bins()
        
        if not active_bins:
            print("⚠️  No bins found in system. Please add a bin in Admin Dashboard.")
            time.sleep(15)
            continue

        # Hardware bins! These are completely ignored by the simulator.
        # Any other bin ID you create in the Admin Dashboard will automatically get simulated.
        IGNORED_BINS = ["BIN-01", "BIN-02"]

        simulated_count = 0
        for bin_data in active_bins:
            b_id = bin_data['bin_id']
            
            # Skip any bin that is reserved for real physical hardware
            if b_id in IGNORED_BINS:
                continue
                
            simulated_count += 1
            server_fill_level = bin_data['fill_level'] # The level currently in DB
            
            # Initialize local state if new
            if b_id not in bin_states:
                bin_states[b_id] = server_fill_level

            # 2. LOGIC: Check if Collector emptied it
            # If server says 0 but we thought it was 100, the collector cleaned it!
            if server_fill_level == 0 and bin_states[b_id] > 0:
                print(f"♻️  [EVENT] {b_id} was emptied by Collector. Resetting Edge Sensor.")
                bin_states[b_id] = 0
            
            # 3. LOGIC: Simulate Waste Accumulation
            current_level = bin_states[b_id]

            if current_level >= 100:
                # Bin is full. It CANNOT go down unless collected.
                new_level = 100
                status_msg = "🚨 CRITICAL: OVERFLOW DETECTED"
            else:
                # Simulate people throwing trash (random increase 5% to 15%)
                increase = random.randint(5, 15)
                new_level = min(current_level + increase, 100) # Cap at 100
                status_msg = "✅ Monitoring... (Filling Up)"

            # Update local memory
            bin_states[b_id] = new_level

            # 4. OUTPUT (Matches PDF concept of Edge Processing)
            print("-" * 50)
            print(f"📦 BIN ID: {b_id}")
            print(f"   Sensor Reading: {new_level} cm (converted to %)")
            
            if new_level >= 90:
                print("   [EDGE LOGIC] 🛑 Threshold Exceeded -> PRIORITY HIGH")
                print("   STATUS: CRITICAL (Needs Collector)")
            elif new_level >= 70:
                print("   [EDGE LOGIC] ⚠️ Threshold Approaching -> PRIORITY MED")
            else:
                print(f"   [EDGE LOGIC] Normal accumulation (+{new_level - current_level if new_level>current_level else 0}%)")

            # 5. Send to Server (Only if changed or critical to keep heartbeat)
            payload = {"bin_id": b_id, "fill_level": new_level}
            try:
                requests.post(UPDATE_URL, json=payload, timeout=1)
            except:
                print("   ❌ Network Error: Server Offline")

            time.sleep(1) # Short pause between bins

        print("\n⏳ Cycle complete. Waiting for next sensor reading...\n")
        time.sleep(15) # Wait 15 seconds before next batch

except KeyboardInterrupt:
    print("\n🛑 Simulation Stopped.")
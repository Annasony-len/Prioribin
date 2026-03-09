import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from models import db, WasteBin, BinHistory, Collector

app = Flask(__name__, instance_relative_config=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///prioribin.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev'
app.config['TEMPLATES_AUTO_RELOAD'] = True

db.init_app(app)

with app.app_context():
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    db.create_all()

# --- Logic ---
def calculate_status(fill_level):
    if fill_level >= 90: return "Critical"
    elif fill_level >= 70: return "Warning"
    return "Normal"

def log_event(bin_id, event_type, description, collector_name=None):
    new_log = BinHistory(
        bin_id=bin_id, 
        event_type=event_type, 
        description=description,
        collector_name=collector_name
    )
    db.session.add(new_log)

# --- Web Routes ---
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/admin')
def admin_dashboard():
    bins = WasteBin.query.order_by(WasteBin.fill_level.desc()).all()
    # Fetch active collectors for the new UI
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    active_collectors = Collector.query.filter(Collector.last_active >= cutoff).all()
    all_collectors = Collector.query.all()
    return render_template('admin.html', bins=bins, active_collectors=active_collectors, all_collectors=all_collectors)

@app.route('/history/<bin_id>')
def bin_history(bin_id):
    logs = BinHistory.query.filter_by(bin_id=bin_id).order_by(BinHistory.timestamp.desc()).limit(50).all()
    
    import json
    import re
    graph_labels = []
    graph_data = []
    
    for log in reversed(logs):
        if log.event_type == 'Collection':
            graph_labels.append(log.timestamp.strftime('%m-%d %H:%M'))
            graph_data.append(0)
        elif log.event_type in ['Critical Alert', 'Update']:
            match = re.search(r'Sensor: (\d+)%', log.description)
            level = int(match.group(1)) if match else 100
            graph_labels.append(log.timestamp.strftime('%m-%d %H:%M'))
            graph_data.append(level)
            
    return render_template('history.html', logs=logs, bin_id=bin_id, chart_labels=json.dumps(graph_labels), chart_data=json.dumps(graph_data))

# NEW: Collector Login Page
@app.route('/collector_login', methods=['GET', 'POST'])
def collector_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        collector = Collector.query.filter_by(username=username).first()
        if collector and collector.check_password(password):
            session['collector_id'] = collector.id
            session['collector_name'] = collector.name
            session['collector_username'] = collector.username
            collector.last_active = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('collector_dashboard'))
        else:
            flash('Invalid username or password', 'error')
            
    return render_template('collector_login.html')

@app.route('/collector_logout')
def collector_logout():
    session.pop('collector_id', None)
    session.pop('collector_name', None)
    session.pop('collector_username', None)
    return redirect(url_for('home'))

@app.route('/collector')
def collector_dashboard():
    if 'collector_id' not in session:
        return redirect(url_for('collector_login'))
    
    collector_id = session['collector_id']
    collector = Collector.query.get(collector_id)
    if collector:
        collector.last_active = datetime.utcnow()
        db.session.commit()

    priority_bins = WasteBin.query.filter(WasteBin.status.in_(['Warning', 'Critical'])).all()
    return render_template('collector.html', bins=priority_bins, collector_name=session.get('collector_name'), collector_username=session.get('collector_username'))

@app.route('/admin/register_collector', methods=['POST'])
def register_collector():
    name = request.form.get('name')
    username = request.form.get('username')
    password = request.form.get('password')
    
    if name and username and password:
        existing = Collector.query.filter_by(username=username).first()
        if not existing:
            new_collector = Collector(name=name, username=username)
            new_collector.set_password(password)
            db.session.add(new_collector)
            db.session.commit()
            flash(f'Collector {name} registered successfully!', 'success')
        else:
            flash('Username already exists.', 'error')
            
    return redirect(url_for('admin_dashboard'))

# --- Data Management Routes ---
@app.route('/add_bin', methods=['POST'])
def add_bin():
    bin_id = request.form.get('bin_id')
    lat = request.form.get('lat')
    lon = request.form.get('lon')
    if bin_id and lat and lon:
        if not WasteBin.query.filter_by(bin_id=bin_id).first():
            new_bin = WasteBin(bin_id=bin_id, location_lat=float(lat), location_lon=float(lon))
            db.session.add(new_bin)
            log_event(bin_id, "System", "Bin initialized")
            db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_bin/<bin_id>', methods=['POST'])
def delete_bin(bin_id):
    bin_obj = WasteBin.query.filter_by(bin_id=bin_id).first()
    if bin_obj:
        BinHistory.query.filter_by(bin_id=bin_id).delete()
        db.session.delete(bin_obj)
        db.session.commit()
    return redirect(url_for('admin_dashboard'))






# --- API Endpoints for Tracking ---

@app.route('/api/update_location', methods=['POST'])
def update_location():
    """Receives GPS from Collector Phone"""
    data = request.json
    username = data.get('username')  # Changed from name to username for unique lookup
    name = data.get('name') 
    lat = data.get('lat')
    lon = data.get('lon')

    if username:
        collector = Collector.query.filter_by(username=username).first()
    else:
        # Fallback for older apps temporarily
        collector = Collector.query.filter_by(name=name).first()

    if collector:
        if lat and lon: # only update if provided
            collector.lat = lat
            collector.lon = lon
        collector.last_active = datetime.utcnow()
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"error": "Collector not found"}), 404

@app.route('/api/get_collectors')
def get_collectors():
    """Sends list of active collectors to Admin Map"""
    # Only show collectors active in the last 5 minutes
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    active = Collector.query.filter(Collector.last_active >= cutoff).all()
    return jsonify([c.to_dict() for c in active])

@app.route('/api/update_bin', methods=['POST'])
def update_bin():
    """Hardware Simulation Endpoint"""
    data = request.json
    bin_obj = WasteBin.query.filter_by(bin_id=data['bin_id']).first()
    if bin_obj:
        new_level = int(data['fill_level'])
        new_status = calculate_status(new_level)
        
        # Log event if level has changed to ensure graph history
        if bin_obj.fill_level != new_level:
            if bin_obj.status != "Critical" and new_status == "Critical":
                log_event(bin_obj.bin_id, "Critical Alert", f"Sensor: {new_level}%")
            else:
                # Log regular update
                log_event(bin_obj.bin_id, "Update", f"Sensor: {new_level}%")

        bin_obj.fill_level = new_level
        bin_obj.status = new_status
        db.session.commit()
        return jsonify({"status": bin_obj.status}), 200
    return jsonify({"error": "Bin not found"}), 404

@app.route('/api/collect_bin/<bin_id>', methods=['POST'])
def collect_bin(bin_id):
    """Collector marked bin as cleaned"""
    # Get collector name from JSON body
    data = request.json
    collector_name = data.get('collector_name', 'Unknown')
    
    bin_obj = WasteBin.query.filter_by(bin_id=bin_id).first()
    if bin_obj:
        log_event(bin_id, "Collection", "Cleaned by collector", collector_name)
        bin_obj.fill_level = 0
        bin_obj.status = "Normal"
        db.session.commit()
        return jsonify({"success": True}), 200
    return jsonify({"error": "Bin not found"}), 404

# --- ADD THIS TO app.py ---

@app.route('/api/get_all_bins', methods=['GET'])
def get_all_bins():
    """Helper for Simulator to know which bins exist"""
    bins = WasteBin.query.all()
    # Convert list of objects to list of dictionaries
    return jsonify([b.to_dict() for b in bins])

if __name__ == '__main__':
    app.run(debug=True)
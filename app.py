from flask import Flask, jsonify, request
from datetime import datetime, timedelta
import json
import os
import threading
import time
import requests
import httpx
from threading import Thread

app = Flask(__name__)

# ========================== CONFIG ==========================

jwt_token = None

def get_jwt_token():
    global jwt_token
    url = "https://jwt-new-khaki.vercel.app/token?uid=4122992948&password=896F6C7EA0E34803C98B182BC9545237214EA7D696368B50A30155209F497D1F"
    try:
        response = httpx.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            if token:
                jwt_token = token
                print(" JWT Token updated")
            else:
                print(" Token key not found in response:", data)
        else:
            print(" JWT status code:", response.status_code)
    except httpx.RequestError as e:
        print(" Request error:", e)

# Refresh token every 8 hours
def token_refresher():
    while True:
        get_jwt_token()
        time.sleep(8 * 3600)

Thread(target=token_refresher, daemon=True).start()

# ======================= UID STORAGE ========================

STORAGE_FILE = 'uid_storage.json'
storage_lock = threading.Lock()

def ensure_storage_file():
    if not os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, 'w') as file:
            file.write('{}')

def load_uids():
    ensure_storage_file()
    with open(STORAGE_FILE, 'r') as file:
        try:
            data = file.read().strip()
            return json.loads(data) if data else {}
        except json.JSONDecodeError:
            print("⚠️ UID storage file is corrupted. Resetting...")
            return {}

def save_uids(uids):
    with open(STORAGE_FILE, 'w') as file:
        json.dump(uids, file, default=str)

# ======================= CLEANUP THREAD ========================

def cleanup_expired_uids():
    global jwt_token
    while True:
        with storage_lock:
            uids = load_uids()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            expired = [uid for uid, exp in uids.items() if exp != 'permanent' and exp <= now]
            for uid in expired:
                if jwt_token:
                    try:
                        url = f"https://chx-rem.vercel.app/remove_friend?token={jwt_token}&player_id={uid}"
                        r = requests.get(url, timeout=10)
                        print(f"🗑 Removed UID {uid}, response: {r.json()}")
                    except Exception as e:
                        print(f"❌ Failed to remove UID {uid}: {e}")
                else:
                    print(f"❌ JWT Token not available for UID {uid}")
                del uids[uid]
            save_uids(uids)
        time.sleep(1)

Thread(target=cleanup_expired_uids, daemon=True).start()

# ========================== ROUTES ==========================

@app.route('/add_uid', methods=['GET'])
def add_uid():
    uid = request.args.get('uid')
    time_value = request.args.get('time')
    time_unit = request.args.get('type')
    permanent = request.args.get('permanent', 'false').lower() == 'true'
    server_name = request.args.get('server_name', 'ind')

    if not uid:
        return jsonify({'error': 'Missing parameter: uid'}), 400

    if permanent:
        expiration_time = 'permanent'
    else:
        if not time_value or not time_unit:
            return jsonify({'error': 'Missing parameters: time or type'}), 400
        try:
            time_value = int(time_value)
        except ValueError:
            return jsonify({'error': 'Invalid time value'}), 400

        now = datetime.now()
        if time_unit == 'seconds':
            expiration_time = now + timedelta(seconds=time_value)
        elif time_unit == 'minutes':
            expiration_time = now + timedelta(minutes=time_value)
        elif time_unit == 'hours':
            expiration_time = now + timedelta(hours=time_value)
        elif time_unit == 'days':
            expiration_time = now + timedelta(days=time_value)
        elif time_unit == 'months':
            expiration_time = now + timedelta(days=time_value * 30)
        elif time_unit == 'years':
            expiration_time = now + timedelta(days=time_value * 365)
        else:
            return jsonify({
                'error': 'Invalid type. Use "seconds", "minutes", "hours", "days", "months", or "years".'
            }), 400
        expiration_time = expiration_time.strftime('%Y-%m-%d %H:%M:%S')

    try:
        spam_url = f"https://tcp-send.vercel.app/spam_request?uid={uid}&server_name={server_name}"
        res = requests.get(spam_url, timeout=10)
        spam_data = res.json()
    except Exception as e:
        return jsonify({'error': f'Failed to call spam_request: {e}'}), 500

    with storage_lock:
        uids = load_uids()
        uids[uid] = expiration_time
        save_uids(uids)

    return jsonify({
        'uid': uid,
        'expires_at': 'never' if permanent else expiration_time,
        'spam_response': spam_data
    })

@app.route('/get_time/<string:uid>', methods=['GET'])
def check_time(uid):
    with storage_lock:
        uids = load_uids()
        if uid not in uids:
            return jsonify({'error': 'UID not found'}), 404

        expiration = uids[uid]
        if expiration == 'permanent':
            return jsonify({'uid': uid, 'status': 'permanent', 'message': 'This UID will never expire.'})

        expiration_dt = datetime.strptime(expiration, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        if now > expiration_dt:
            return jsonify({'error': 'UID has expired'}), 400

        delta = expiration_dt - now
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        return jsonify({
            'uid': uid,
            'remaining_time': {
                'days': days,
                'hours': hours,
                'minutes': minutes,
                'seconds': seconds
            }
        })

# ========================== RUN ==========================

if __name__ == '__main__':
    ensure_storage_file()
    get_jwt_token()  # Initial token fetch
    time.sleep(2)  # small buffer
    app.run(host='0.0.0.0', port=9823, debug=True)

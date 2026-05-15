import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from flask import Flask, request, jsonify
from datetime import datetime
import struct

app = Flask(__name__)

freefire_version = "OB53"
key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
jwt_tokens = {}

# ===================== JWT TOKEN =====================
def get_access_token_sync(uid, password):
    try:
        url = f"https://uid-pass-to-jwt-token.onrender.com/api/token?uid={uid}&pass={password}"
        with httpx.Client(timeout=20.0) as client:
            r = client.get(url)
        if r.status_code != 200:
            return None, None
        data = r.json()
        if not data.get("success"):
            return None, None
        tokens = data.get("tokens", {})
        return tokens.get("jwt_token"), tokens.get("open_id")
    except Exception as e:
        print(f"Token error: {e}")
        return None, None

def ensure_token_sync(region):
    region = region.upper()
    if region in jwt_tokens and jwt_tokens[region]:
        return jwt_tokens[region]
    
    accounts = {
        "IND": ("4821491506", "ZAINUBYSTARGMR2PTJn2"),
        "BD": ("4558447129", "SEXTY_MODS_IND_QCZBNBQKO"),
        "BR": ("4627778236", "SEXTY_MODS_IND_O8ALMMBEF"),
        "US": ("3333333333", "xxx")
    }
    uid, pwd = accounts.get(region, accounts["IND"])
    token_val, _ = get_access_token_sync(uid, pwd)
    if token_val:
        jwt_tokens[region] = f"Bearer {token_val}"
        return jwt_tokens[region]
    return None

# ===================== BUILD PROTOBUF MANUALLY =====================
def build_my_data(clan_id):
    """Manually create protobuf for MyData { field1: clan_id, field2: 1 }"""
    result = bytearray()
    
    # field1 = 1 (tag: 1 << 3 | 0 = 8) = 0x08
    # Encode varint for clan_id
    n = int(clan_id)
    varint_bytes = bytearray()
    while n > 0:
        byte = n & 0x7F
        n >>= 7
        if n > 0:
            byte |= 0x80
        varint_bytes.append(byte)
    if not varint_bytes:
        varint_bytes.append(0)
    
    result.append(0x08)  # field1 tag
    result.extend(varint_bytes)
    
    # field2 = 2 (tag: 2 << 3 | 0 = 16) = 0x10
    result.append(0x10)  # field2 tag
    result.append(0x01)  # value 1
    
    return bytes(result)

# ===================== DECODE RESPONSE MANUALLY =====================
def decode_clan_response(data):
    """Extract clan info from response without protobuf"""
    result = {
        "clan_id": None,
        "clan_name": None,
        "created_at": None,
        "updated_at": None,
        "last_active": None,
        "level": None,
        "region": None,
        "welcome_message": None,
        "score": 0,
        "xp": 0,
        "status": "success"
    }
    
    try:
        # Convert to string and find readable text
        text = data.decode('utf-8', errors='ignore')
        
        # Find clan name (alphanumeric with possible special chars)
        import re
        matches = re.findall(r'[A-Za-z0-9_\-]{4,30}', text)
        for m in matches:
            if len(m) > 3 and m.isalnum():
                result["clan_name"] = m
                break
        
        # Find numbers that could be IDs
        numbers = re.findall(r'\d+', text)
        if numbers and not result["clan_id"]:
            result["clan_id"] = numbers[0]
            
    except Exception as e:
        print(f"Decode error: {e}")
    
    return result

# ===================== CLAN INFO ROUTE =====================
@app.route('/info', methods=['GET'])
def get_clan_info():
    clan_id = request.args.get('clan_id')
    region = request.args.get('region', 'IND').upper()

    if not clan_id:
        return jsonify({"error": "clan_id is required"}), 400

    token = ensure_token_sync(region)
    if not token:
        return jsonify({"error": "JWT not available"}), 503

    try:
        # Build protobuf manually
        data_bytes = build_my_data(clan_id)
        
        # AES Encrypt
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted_data = cipher.encrypt(pad(data_bytes, 16))

        # Region endpoints
        region_map = {
            "IND": "https://client.ind.freefiremobile.com/GetClanInfoByClanID",
            "BD": "https://clientbp.ggblueshark.com/GetClanInfoByClanID",
            "BR": "https://client.us.freefiremobile.com/GetClanInfoByClanID",
            "US": "https://client.us.freefiremobile.com/GetClanInfoByClanID",
        }
        url = region_map.get(region, region_map["IND"])
        host = url.split("//")[1].split("/")[0]

        headers = {
            "Authorization": token,
            "X-Unity-Version": "2018.4.11f1",
            "ReleaseVersion": freefire_version,
            "Content-Type": "application/octet-stream",
            "User-Agent": "Dalvik/2.1.0 (Linux; Android 11)",
            "Host": host,
        }

        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, headers=headers, content=encrypted_data)

        if response.status_code != 200:
            return jsonify({"error": f"HTTP {response.status_code}"}), 500

        result = decode_clan_response(response.content)
        result["clan_id"] = clan_id
        result["requested_region"] = region
        result["Api Owner"] = "@STAR_GMR"
        result["TG CHANNEL"] = "@STAR_METHODE"
        
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": "Server error", "details": str(e)}), 500

# ===================== HEALTH CHECK =====================
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "running",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

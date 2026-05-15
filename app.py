import httpx
import time
import re
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify
from datetime import datetime
import asyncio
import data_pb2
import encode_id_clan_pb2

# ===================== CONFIG =====================
app = Flask(__name__)
freefire_version = "OB53"
key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
jwt_tokens = {}  # Store tokens by region
# =================================================
USERAGENT = "Dalvik/2.1.0 (Linux; Android 11; Mobile)"
RELEASEVERSION = "OB53"
# ===================== REGION CONFIG =====================
def get_region_credentials(region):
    r = region.upper()
    if r == "IND":
        return "uid={}&password={}"
    elif r == "BD":
        return "uid={}&password={}"
    elif r in {"BR", "US", "SAC", "NA"}:
        return "uid={}&password={}"
    else:
        return "uid={}&password={}"

# ===================== ENCRYPT UID =====================
def Encrypt_ID(x):
    x = int(x)
    dec = [f'{i:02x}' for i in range(128, 256)]
    xxx = [f'{i:02x}' for i in range(0, 128)]

    parts = []
    while x > 0:
        parts.append(x % 128)
        x //= 128
    while len(parts) < 5:
        parts.append(0)
    parts.reverse()

    return ''.join(dec[parts[i]] if i > 0 else xxx[parts[i]] for i in range(5))

# ===================== AES ENCRYPT =====================
def encrypt_api(plain_text_hex):
    plain_text = bytes.fromhex(plain_text_hex)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(plain_text, 16)).hex()

# ===================== EMOTE ID EN/DE =====================
def Encrypt_id_emote(uid):
    result = []
    while uid > 0:
        byte = uid & 0x7F
        uid >>= 7
        if uid > 0:
            byte |= 0x80
        result.append(byte)
    return bytes(result).hex()

def Decrypt_id_emote(uidd):
    bytes_value = bytes.fromhex(uidd)
    r, shift = 0, 0
    for byte in bytes_value:
        r |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return r

# ===================== TIMESTAMP =====================
def convert_timestamp(ts):
    return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

# ===================== JWT TOKEN =====================
# ===================== JWT TOKEN =====================
import json
import os

jwt_tokens = {}
cached_tokens = {}


async def get_access_token(account):
    try:
        parts = dict(x.split("=") for x in account.split("&"))
        uid = parts.get("uid")
        password = parts.get("password")

        url = f"https://vk-boy-acc.vercel.app/guest_to_jwt?uid={uid}&password={password}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)

        if r.status_code != 200:
            print("[JWT API FAIL]", r.status_code, r.text[:100])
            return None, None

        data = r.json()

        # ✅ FIXED RESPONSE FIELDS
        jwt_token = data.get("jwt_token")
        open_id = data.get("open_id")

        return jwt_token, open_id

    except Exception as e:
        print("[JWT API ERROR]", e)
        return None, None


# ===================== CREATE JWT =====================
async def create_jwt(region):
    try:
        accounts = {
            "IND": "uid=4471767672&password=SEXTY_MODS_IND_REOPRZXEW",
            "BD": "uid=4558447129&password=SEXTY_MODS_IND_QCZBNBQKO",
            "BR": "uid=4627778236&password=SEXTY_MODS_IND_O8ALMMBEF",
            "US": "uid=3333333333&password=xxx"
        }

        account = accounts.get(region, accounts["IND"])

        token_val, open_id = await get_access_token(account)

        if not token_val or not open_id:
            print(f"[FAIL ACCESS] {region}")
            return

        jwt_tokens[region] = f"Bearer {token_val}"

        print(f"[OK] JWT READY {region}")

    except Exception as e:
        print("[JWT ERROR]", e)


async def ensure_token(region):
    region = region.upper()

    if jwt_tokens.get(region):
        return jwt_tokens[region]

    await create_jwt(region)
    return jwt_tokens.get(region)
# ===================== CLAN INFO ROUTE (SYNC) =====================
@app.route('/info', methods=['GET'])
def get_clan_info():
    clan_id = request.args.get('clan_id')
    region = request.args.get('region', 'IND').upper()

    if not clan_id:
        return jsonify({"error": "clan_id is required"}), 400

    # ✅ FIXED ASYNC LOOP
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        token = loop.run_until_complete(ensure_token(region))
        loop.close()
    except Exception as e:
        return jsonify({"error": "token init failed", "details": str(e)}), 503

    if not token:
        return jsonify({"error": "JWT not available"}), 503

    try:
        # ===== PROTOBUF =====
        my_data = encode_id_clan_pb2.MyData()
        my_data.field1 = int(clan_id)
        my_data.field2 = 1

        data_bytes = my_data.SerializeToString()

        # ===== AES ENCRYPT (OLD WORKING STYLE) =====
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted_data = cipher.encrypt(pad(data_bytes, 16))

        payload = encrypted_data

        # ===== REGION MAP =====
        region_map = {
            "IND": ("https://client.ind.freefiremobile.com/GetClanInfoByClanID", "client.ind.freefiremobile.com"),
            "BD": ("https://clientbp.ggblueshark.com/GetClanInfoByClanID", "clientbp.ggblueshark.com"),
            "BR": ("https://client.us.freefiremobile.com/GetClanInfoByClanID", "client.us.freefiremobile.com"),
            "SAC": ("https://client.us.freefiremobile.com/GetClanInfoByClanID", "client.us.freefiremobile.com"),
            "US": ("https://client.us.freefiremobile.com/GetClanInfoByClanID", "client.us.freefiremobile.com"),
            "NA": ("https://client.us.freefiremobile.com/GetClanInfoByClanID", "client.us.freefiremobile.com"),
        }

        url, host = region_map.get(region, region_map["IND"])

        headers = {
            "Expect": "100-continue",
            "Authorization": token if token.startswith("Bearer ") else f"Bearer {token}",
            "X-Unity-Version": "2018.4.11f1",
            "X-GA": "v1 1",
            "ReleaseVersion": freefire_version,
            "Content-Type": "application/octet-stream",
            "User-Agent": "Dalvik/2.1.0 (Linux; Android 11)",
            "Host": host,
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip"
        }

        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, headers=headers, content=payload)

        if response.status_code != 200:
            return jsonify({
                "error": f"HTTP {response.status_code}",
                "body": response.text[:200]
            }), 500

        # ===== PROTO DECODE =====
        resp = data_pb2.response()
        resp.ParseFromString(response.content)

        def ts(x):
            try:
                return datetime.fromtimestamp(int(x)).strftime("%Y-%m-%d %H:%M:%S")
            except:
                return None

        # =========================
        # 🔥 AUTO FIND CLAN INFO
        # =========================
        def auto_find_clan_info(obj):
            if hasattr(obj, "clanInfo") and obj.clanInfo:
                return obj.clanInfo

            for f in dir(obj):
                try:
                    val = getattr(obj, f)
                    if val and (
                        hasattr(val, "memberNum") or
                        hasattr(val, "capacity") or
                        hasattr(val, "captainBasicInfo")
                    ):
                        return val
                except:
                    pass
            return None

        clan_info = auto_find_clan_info(resp)

        # =========================
        # DEFAULT VALUES
        # =========================
        member_num = 0
        capacity = 50
        leader_uid = 0
        members_online = getattr(resp, "members_online", 0)

        # =========================
        # MEMBERS AUTO FIX
        # =========================
        if clan_info:

            def pick(fields):
                for f in fields:
                    if hasattr(clan_info, f):
                        v = getattr(clan_info, f)
                        if v is not None:
                            return v
                return 0

            member_num = pick(["memberNum", "memberCount", "members", "currentMembers"])
            capacity = pick(["capacity", "maxMembers", "memberLimit"])

            try:
                member_num = int(member_num or 0)
            except:
                member_num = 0

            try:
                capacity = int(capacity or 50)
            except:
                capacity = 50

            if capacity <= 0:
                capacity = 50

            # =========================
            # 🔥 LEADER AUTO FIX
            # =========================
            captain = getattr(clan_info, "captainBasicInfo", None)

            if captain:
                leader_uid = int(getattr(captain, "accountId", 0) or 0)

        # =========================
        # FINAL RESPONSE
        # =========================
        return jsonify({
            "clan_id": getattr(resp, "id", clan_id),
            "clan_name": getattr(resp, "special_code", None),

            "created_at": ts(getattr(resp, "timestamp1", 0)),
            "updated_at": ts(getattr(resp, "timestamp2", 0)),
            "last_active": ts(getattr(resp, "last_active", 0)),

            "level": getattr(resp, "rank", None),
            "region": getattr(resp, "region", region),

            "welcome_message": getattr(resp, "welcome_message", None),
            "score": getattr(resp, "score", 0),
            "xp": getattr(resp, "xp", 0),
            
            "Api Owner": "@STAR_GMR",
            "TG CHHANEL": "@STAR_METHODE",
            
            "status": "success",
            "requested_region": region
        })

    except Exception as e:
        return jsonify({
            "error": "Server error",
            "details": str(e)
        }), 500
        

# ===================== HEALTH CHECK =====================
@app.route('/health', methods=['GET'])
def health_check():
    regions_status = {}
    for region in ["IND", "BD", "BR", "US", "SAC", "NA"]:
        regions_status[region] = "ready" if region in jwt_tokens and jwt_tokens[region] else "not ready"
    
    return jsonify({
        "status": "running",
        "regions": regions_status,
        "timestamp": datetime.now().isoformat()
    })

# ===================== STARTUP =====================


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
    
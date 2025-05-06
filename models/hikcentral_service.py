# anpr_peage_manager/models/hikcentral_service.py
import threading
import requests
import time
import hmac
import hashlib
import base64
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

# Configuration Artemis
APP_KEY = '26838323'
APP_SECRET = 'xAuqYNE9gbiUnuyYvuKb'
ARTEMIS_URL = 'https://192.168.1.50'
SUBSCRIBE_ENDPOINT = '/artemis/api/eventService/v1/eventSubscriptionByEventTypes'
UNSUBSCRIBE_ENDPOINT = '/artemis/api/eventService/v1/eventUnSubscriptionByEventTypes'

EVENT_DEST_URL = 'https://192.168.1.69:8090/eventRcv'
EVENT_TYPES = [131622]
TOKEN = 'qscasd'

# Ignorer les warnings SSL auto-signé
requests.packages.urllib3.disable_warnings()

# ======= GÉNÉRER SIGNATURE AK/SK =======
def generate_headers(app_key, app_secret, method, path):
    timestamp = str(int(time.time() * 1000))
    string_to_sign = f"{method}\n*/*\napplication/json\nx-ca-key:{app_key}\nx-ca-timestamp:{timestamp}\n{path}"

    digest = hmac.new(app_secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode('utf-8')

    headers = {
        'Accept': '*/*',
        'Content-Type': 'application/json',
        'x-ca-key': app_key,
        'x-ca-signature': signature,
        'x-ca-timestamp': timestamp,
        'x-ca-signature-headers': 'x-ca-key,x-ca-timestamp'
    }
    return headers

# ======= DÉSABONNER =======
def unsubscribe_from_events():
    url = ARTEMIS_URL + UNSUBSCRIBE_ENDPOINT
    method = 'POST'
    headers = generate_headers(APP_KEY, APP_SECRET, method, UNSUBSCRIBE_ENDPOINT)
    payload = {"eventTypes": EVENT_TYPES}

    try:
        response = requests.post(url, headers=headers, json=payload, verify=False)
        _logger.info(f"📡 Unsubscribe Status: {response.status_code} | {response.text}")
    except Exception as e:
        _logger.error(f"❌ Error during unsubscribe: {e}")

# ======= S'ABONNER =======
def subscribe_to_events():
    url = ARTEMIS_URL + SUBSCRIBE_ENDPOINT
    method = 'POST'
    headers = generate_headers(APP_KEY, APP_SECRET, method, SUBSCRIBE_ENDPOINT)
    payload = {
        "eventTypes": EVENT_TYPES,
        "eventDest": EVENT_DEST_URL,
        "token": TOKEN,
        "passBack": 0,
        "srcIndexCodes": ["51"]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, verify=False)
        _logger.info(f"📡 Subscribe Status: {response.status_code} | {response.text}")
    except Exception as e:
        _logger.error(f"❌ Error during subscribe: {e}")

# ======= MAINTENANCE DE L'ABONNEMENT =======
def subscription_maintenance_loop():
    while True:
        _logger.info("🔄 Refresh de la subscription Artemis...")
        unsubscribe_from_events()
        time.sleep(1)
        subscribe_to_events()
        _logger.info("✅ Nouvelle subscription active.")
        time.sleep(120)  # 2 minutes

# ======= SERVICE PRINCIPAL ODOO =======
class HikcentralService(models.AbstractModel):
    _name = 'hikcentral.service'
    _description = "Service d'intégration Hikcentral ANPR"

    @api.model
    def start_hikcentral_listener(self):
        _logger.info("🚀 Début de la gestion des subscriptions Artemis...")

        # Lancer juste la boucle de subscription (PAS le serveur Flask)
        subscription_thread = threading.Thread(target=subscription_maintenance_loop)
        subscription_thread.daemon = True
        subscription_thread.start()

        _logger.info("✅ Service Artemis de subscription démarré.")
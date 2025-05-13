# anpr_peage_manager/models/hikcentral_service.py
import requests
import time
import hmac
import hashlib
import base64
import logging

from odoo import models, api

_logger = logging.getLogger(__name__)

requests.packages.urllib3.disable_warnings()

EVENT_TYPES = [131622]
SUBSCRIBE_ENDPOINT = '/artemis/api/eventService/v1/eventSubscriptionByEventTypes'
UNSUBSCRIBE_ENDPOINT = '/artemis/api/eventService/v1/eventUnSubscriptionByEventTypes'

def generate_headers(app_key, app_secret, method, path):
    timestamp = str(int(time.time() * 1000))
    string_to_sign = f"{method}\n*/*\napplication/json\nx-ca-key:{app_key}\nx-ca-timestamp:{timestamp}\n{path}"
    digest = hmac.new(app_secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode('utf-8')

    return {
        'Accept': '*/*',
        'Content-Type': 'application/json',
        'x-ca-key': app_key,
        'x-ca-signature': signature,
        'x-ca-timestamp': timestamp,
        'x-ca-signature-headers': 'x-ca-key,x-ca-timestamp'
    }

class HikcentralService(models.AbstractModel):
    _name = 'hikcentral.service'
    _description = "Service d'intégration Hikcentral ANPR"

    def _get_user_config(self):
        user = self.env.user
        return {
            'app_key': user.artemis_app_key,
            'app_secret': user.artemis_app_secret,
            'artemis_url': user.artemis_url,
            'event_dest_url': user.artemis_event_dest_url,
            'token': user.artemis_token,
            'src_codes': user.artemis_event_src_codes.split(",") if user.artemis_event_src_codes else [],
        }

    def unsubscribe_from_events(self, config):
        url = config['artemis_url'] + UNSUBSCRIBE_ENDPOINT
        headers = generate_headers(config['app_key'], config['app_secret'], 'POST', UNSUBSCRIBE_ENDPOINT)
        payload = {"eventTypes": EVENT_TYPES}
        try:
            response = requests.post(url, headers=headers, json=payload, verify=False)
            _logger.info(f"📡 Unsubscribe Status: {response.status_code} | {response.text}")
        except Exception as e:
            _logger.error(f"❌ Error during unsubscribe: {e}")

    def subscribe_to_events(self, config):
        url = config['artemis_url'] + SUBSCRIBE_ENDPOINT
        headers = generate_headers(config['app_key'], config['app_secret'], 'POST', SUBSCRIBE_ENDPOINT)
        payload = {
            "eventTypes": EVENT_TYPES,
            "eventDest": config['event_dest_url'],
            "token": config['token'],
            "passBack": 0,
            # "srcIndexCodes": config['src_codes']
        }
        try:
            response = requests.post(url, headers=headers, json=payload, verify=False)
            _logger.info(f"📡 Subscribe Status: {response.status_code} | {response.text}")
        except Exception as e:
            _logger.error(f"❌ Error during subscribe: {e}")

    @api.model
    def start_hikcentral_listener(self):
        try:
            config = self._get_user_config()
        except Exception as e:
            _logger.error(f"⚠️ Impossible de récupérer la configuration utilisateur : {e}")
            return

        _logger.info(f"🚀 Souscription Artemis pour l'utilisateur {self.env.user.name}...")

        self.unsubscribe_from_events(config)
        time.sleep(1)
        self.subscribe_to_events(config)

        _logger.info("✅ Souscription Artemis effectuée.")
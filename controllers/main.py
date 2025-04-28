# anpr_peage_manager\controllers\main.py
from odoo import http, fields
from odoo.http import request
import requests
import socket
import time
import serial
import logging
from .pay import generate_receipt_content

_logger = logging.getLogger(__name__)

DISPLAY_WIDTH = 20
SCROLL_DELAY = 0.2

class AnprPeageController(http.Controller):

    def print_receipt_to_printer(self, ip_address, port, content):
        try:
            s = socket.socket()
            s.settimeout(10)
            s.connect((ip_address, port))
            s.sendall(content)
            s.close()
            return True
        except Exception as e:
            return str(e)

    def scroll_vfd(self, raw_message, permanent=False):
        try:
            ser = serial.Serial("COM3", 9600, timeout=1)
            ser.write(b'\x0C')
            if permanent:
                message = raw_message.ljust(DISPLAY_WIDTH)[:DISPLAY_WIDTH]
                ser.write(message.encode('cp850', errors='replace'))
            else:
                text = raw_message.replace("\n", " ")
                buffer = text + " " * DISPLAY_WIDTH
                for i in range(len(buffer) - DISPLAY_WIDTH + 1):
                    window = buffer[i: i + DISPLAY_WIDTH]
                    ser.write(b'\x0C')
                    ser.write(window.encode('cp850', errors='replace'))
                    time.sleep(SCROLL_DELAY)
            ser.close()
            return True
        except Exception as e:
            _logger.warning("Afficheur non connecté ou inaccessible : %s", e)
            return str(e)

    @http.route('/anpr_peage/scroll_message', type='json', auth='public', csrf=False)
    def scroll_message(self, message, permanent=False):
        res = self.scroll_vfd(message, permanent)
        if res is True:
            return {'status': 'ok'}
        else:
            return {'status': 'error', 'message': res}

    @http.route('/anpr_peage/start_hikcentral', type='json', auth='user')
    def start_hikcentral_service(self):
        try:
            request.env['hikcentral.service'].sudo().start_hikcentral_listener()
            return {'status': 'success'}
        except Exception as e:
            _logger.error(f"❌ Erreur lors du lancement HikCentral Listener : {e}")
            return {'status': 'error', 'message': str(e)}

    # Nouvelle route pour récupérer la dernière plaque détectée
    @http.route('/anpr_peage/last_detected_plate', type='json', auth='public', csrf=False)
    def get_last_detected_plate(self):
        try:
            # Aller lire les données depuis le serveur Flask
            response = requests.get('https://127.0.0.1:8090/last_plate', verify=False, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return {
                    'status': 'success',
                    'plate': data.get('plate'),
                    'vehicle_type': data.get('vehicle_type')
                }
            else:
                return {'status': 'error', 'message': 'Erreur lecture Flask'}
        except Exception as e:
            _logger.error(f"❌ Erreur communication Flask Listener : {e}")
            return {'status': 'error', 'message': str(e)}


    @http.route('/anpr_peage/transactions', type="json", auth="user")
    def get_transactions(self):
        records = request.env['anpr.log'].sudo().search([], order="paid_at desc", limit=50)
        return [
            {
                'id': r.id,
                'operator': "Ogooué Technologies",
                'plate': r.plate,
                'date': r.paid_at.strftime("%d/%m/%Y") if r.paid_at else '',
                'time': r.paid_at.strftime("%H:%M") if r.paid_at else '',
                'amount': r.amount,
            }
            for r in records
        ]

    @http.route('/anpr_peage/pay_manuely', type='json', auth='user')
    def process_manual_payment(self, plate, vehicle_type, amount):
        try:
            ticket_number = request.env['ir.sequence'].sudo().next_by_code('anpr.ticket.sequence')

            request.env['anpr.log'].sudo().create({
                'plate': plate,
                'vehicle_type': vehicle_type,
                'amount': amount,
                'transaction_message': "Paiement manuel effectue",
                'payment_status': "success",
                'paid_at': fields.Datetime.now()
            })

            receipt = generate_receipt_content(
                plate, vehicle_type, numero="MANUEL", amount=amount,
                status_message="Paiement manuel effectue",
                ticket_number=ticket_number
            )

            result_print = self.print_receipt_to_printer("192.168.1.114", 9100, receipt)
            if result_print is not True:
                print(f"❌ Erreur impression POS : {result_print}")

            return {
                'payment_status': "success",
                'message': f"Paiement manuel enregistré avec le ticket {ticket_number}"
            }

        except Exception as e:
            return {
                'payment_status': "failed",
                'message': str(e)
            }

    @http.route('/anpr_peage/pay', type='json', auth='public', csrf=False)
    def process_payment(self, plate, vehicle_type, numero, amount):
        print("✅ Route /anpr_peage/pay appelée avec :", plate, vehicle_type, numero, amount)

        try:
            payload = {'numero': numero, 'amount': amount}
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            response = requests.post(
                'https://gytx.dev/api/airtelmoney-web.php',
                data=payload,
                headers=headers,
                timeout=30
            )

            try:
                result = response.json()
            except Exception as e:
                return {
                    'status': 'error',
                    'message': f"Erreur JSON : {e}",
                    'raw_response': response.text
                }

            status_message = result.get("status_message", "Aucune réponse").lower()

            if any(success in status_message for success in [
                "successfully processed",
                "a ete effectue avec success",
                "a été effectué avec succès"
            ]):
                payment_status = 'success'
            elif "annulee" in status_message or "cancelled" in status_message:
                payment_status = 'cancelled'
            else:
                payment_status = 'failed'

            ticket_number = request.env['ir.sequence'].sudo().next_by_code('anpr.ticket.sequence')

            if payment_status == 'success':
                request.env['anpr.log'].sudo().create({
                    'plate': plate,
                    'vehicle_type': vehicle_type,
                    'amount': amount,
                    'transaction_message': status_message,
                    'payment_status': payment_status,
                    'paid_at': fields.Datetime.now()
                })

                receipt = generate_receipt_content(
                    plate, vehicle_type, numero, amount, status_message, ticket_number
                )
                result_print = self.print_receipt_to_printer("192.168.1.114", 9100, receipt)
                if result_print is not True:
                    print(f"❌ Erreur impression POS : {result_print}")

            return {
                'status': 'success',
                'message': result.get("status_message", "Réponse inconnue"),
                'payment_status': payment_status
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f"Erreur API : {e}"
            }

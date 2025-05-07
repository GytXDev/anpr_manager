# anpr_peage_manager\controllers\main.py
from odoo import http, fields
from odoo.http import request
import requests
import socket
from pytz import timezone
from datetime import datetime, time
import serial
import logging
from .pay import generate_receipt_content

_logger = logging.getLogger(__name__)

DISPLAY_WIDTH = 20
SCROLL_DELAY = 0.2


def _today_range():
    today = fields.Date.today()
    start = datetime.combine(today, time.min)   # 00:00:00
    end   = datetime.combine(today, time.max)   # 23:59:59
    return start, end

def _totaux_all_time(env, domain_extra=None):
    """Renvoie (total_manual, total_mobile) sans filtrer par date."""
    base_domain = [
        ('payment_status', '=', 'success'),
        ('accounted', '=', True),  # Ne prendre que celles non comptabilisées
    ]

    if domain_extra:
        base_domain += domain_extra

    logs = env['anpr.log'].sudo().search(base_domain)
    t_manual = sum(l.amount for l in logs if l.payment_method == 'manual')
    t_mobile = sum(l.amount for l in logs if l.payment_method == 'mobile')
    return t_manual, t_mobile


def _totaux(env, domain_extra=None):
    """Renvoie (total_manual, total_mobile)."""
    start, end = _today_range()
    base_domain = [
        ('paid_at', '>=', start),
        ('paid_at', '<=', end),
        ('payment_status', '=', 'success'),
        ('accounted', '=', True),
    ]
    if domain_extra:
        base_domain += domain_extra

    logs = env['anpr.log'].sudo().search(base_domain)
    t_manual = sum(l.amount for l in logs if l.payment_method == 'manual')
    t_mobile = sum(l.amount for l in logs if l.payment_method == 'mobile')
    return t_manual, t_mobile

def now_gabon():
    return datetime.now(timezone("Africa/Libreville")).replace(tzinfo=None)

class AnprPeageController(http.Controller):

    def _create_account_move(self, amount, payment_method, plate, user_name):
        env = request.env
        journal_code = 'PEAGE' if payment_method == 'manual' else 'PEAGE_MM'
        debit_account_code = '512100'  # Banque
        credit_account_code = '706100'  # Produits Péage

        # Vérifie ou crée le journal
        journal = env['account.journal'].sudo().search([('code', '=', journal_code)], limit=1)
        if not journal:
            journal = env['account.journal'].sudo().create({
                'name': f'Péage {"Mobile" if payment_method == "mobile" else "Manuel"}',
                'code': journal_code,
                'type': 'cash',
                'company_id': env.company.id,
            })

        # Vérifie ou crée les comptes comptables
        debit_account = env['account.account'].sudo().search([('code', '=', debit_account_code)], limit=1)
        if not debit_account:
            debit_account = env['account.account'].sudo().create({
                'name': 'Banque (Péage)',
                'code': debit_account_code,
                'account_type': 'asset_cash',
            })

        credit_account = env['account.account'].sudo().search([('code', '=', credit_account_code)], limit=1)
        if not credit_account:
            credit_account = env['account.account'].sudo().create({
                'name': 'Produits Péage',
                'code': credit_account_code,
                'account_type': 'income',
            })

        # Création de la pièce comptable
        move = env['account.move'].sudo().create({
            'journal_id': journal.id,
            'ref': f'Paiement {plate} - {user_name}',
            'date': now_gabon().date(),
            'line_ids': [
                (0, 0, {
                    'name': f'Paiement péage {plate}',
                    'account_id': debit_account.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': f'Recette péage {plate}',
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })

        # ➜ Validation immédiate
        move.action_post()
        return move

    def print_receipt_to_printer(self, content):
        user = request.env.user
        ip_address = user.printer_ip
        port = int(user.printer_port or 9100)

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
        user = request.env.user
        flask_url = user.flask_url

        try:
            response = requests.get(f"{flask_url}/last_plate", verify=False, timeout=5)
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

    # Transactions de l'utilisateur 
    @http.route('/anpr_peage/transactions_user', type='json', auth='user')
    def transactions_user(self):
        uid = request.env.user.id
        recs = request.env['anpr.log'].sudo().search(
            [('user_id', '=', uid)],
            order='paid_at desc', limit=50
        )
        return [
            {
                'id': r.id,
                'operator': request.env.user.name,
                'plate': r.plate,
                'date': r.paid_at.strftime("%d/%m/%Y") if r.paid_at else '',
                'time': r.paid_at.strftime("%H:%M") if r.paid_at else '',
                'amount': r.amount,
            }
            for r in recs
        ]


    @http.route('/anpr_peage/pay_manuely', type='json', auth='user')
    def process_manual_payment(self, plate, vehicle_type, amount):
        try:
            # Mapper le label reçu vers la valeur interne
            valid_types = {
                'Car': 'car',
                '4x4': '4x4',
                'Bus': 'bus',
                'Camion': 'camion',
                'Autres': 'autres',
            }
            internal_type = valid_types.get(vehicle_type, 'autres')  

            ticket_number = request.env['ir.sequence'].sudo().next_by_code('anpr.ticket.sequence')

            request.env['anpr.log'].sudo().create({
                'user_id': request.env.user.id,
                'plate': plate,
                'vehicle_type': internal_type,
                'amount': amount,
                'transaction_message': "Paiement manuel effectué",
                'payment_status': "success",
                'payment_method': "manual",
                'paid_at': now_gabon()
            })

            self._create_account_move(amount, "manual", plate, request.env.user.name)

            receipt = generate_receipt_content(
                plate, internal_type, numero="MANUEL", amount=amount,
                status_message="Paiement manuel effectué",
                ticket_number=ticket_number
            )

            result_print = self.print_receipt_to_printer(receipt)
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
        user = request.env.user
        ip_address = user.printer_ip

        try:
            # 💡 Traduire le label reçu en valeur interne
            valid_types = {
                'Car': 'car',
                '4x4': '4x4',
                'Bus': 'bus',
                'Camion': 'camion',
                'Autres': 'autres',
            }
            internal_type = valid_types.get(vehicle_type, 'autres')  # fallback

            payload = {'numero': numero, 'amount': amount}
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            response = requests.post(
                payment_api_url,
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
                    'user_id': request.env.user.id,
                    'plate': plate,
                    'vehicle_type': internal_type,
                    'amount': amount,
                    'transaction_message': status_message,
                    'payment_status': payment_status,
                    'payment_method': "mobile",
                    'paid_at': now_gabon()
                })
                self._create_account_move(amount, "mobile", plate, request.env.user.name)

                receipt = generate_receipt_content(
                    plate, internal_type, numero, amount, status_message, ticket_number
                )
                result_print = self.print_receipt_to_printer(receipt)
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


    # Résumé de tout les paiements  
    @http.route('/anpr_peage/summary_user', type='json', auth='user')
    def summary_user(self):
        user_id = request.env.user.id

        # Totaux du jour
        t_manual_day, t_mobile_day = _totaux(request.env, [('user_id', '=', user_id)])

        # Totaux cumulés du caissier (tous les jours)
        t_manual_all, t_mobile_all = _totaux_all_time(request.env, [('user_id', '=', user_id)])

        return {
            'scope': 'user',
            'user_id': user_id,
            'manual_day': t_manual_day,
            'mobile_day': t_mobile_day,
            'total_day': t_manual_day + t_mobile_day,
            'manual_total': t_manual_all,
            'mobile_total': t_mobile_all,
            'total_all': t_manual_all + t_mobile_all,
        }


    @http.route('/anpr_peage/summary_global', type='json', auth='user')
    def summary_global(self):
        t_manual, t_mobile = _totaux(request.env)
        return {
            'scope': 'global',
            'manual': t_manual,
            'mobile': t_mobile,
            'overall': t_manual + t_mobile,
        }


    @http.route('/anpr_peage/get_current_user', type='json', auth='user', csrf=False)
    def get_current_user(self):
        try:
            info = request.env['anpr.log'].sudo().get_current_user_info()
            return info
        except Exception as e:
            # pour debug, renvoyer l’erreur
            return {'error': True, 'message': str(e)}

    
    # Status de la souscription ANPR
    @http.route('/anpr_peage/hikcentral_status', type='json', auth='user')
    def get_hikcentral_status(self):
        try:
            user = request.env.user
            config = {
                'app_key': user.artemis_app_key,
                'app_secret': user.artemis_app_secret,
                'artemis_url': user.artemis_url,
                'event_dest_url': user.artemis_event_dest_url,
                'token': user.artemis_token,
                'src_codes': user.artemis_event_src_codes,
            }

            missing = [k for k, v in config.items() if not v]
            if missing:
                return {
                    'status': 'error',
                    'message': f"Paramètres manquants : {missing}"
                }

            return {
                'status': 'ok',
                'message': f"Configuration Artemis OK pour {user.name}",
                'config': config
            }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/anpr_peage/flask_status', type='json', auth='user')
    def get_flask_status(self):
        try:
            user = request.env.user
            flask_url = user.flask_url

            if not flask_url:
                return {
                    'status': 'error',
                    'message': "Paramètre manquant : flask_url"
                }

            # Vérifie que le listener répond bien
            response = requests.get(f"{flask_url}/last_plate", verify=False, timeout=5)
            if response.status_code == 200:
                return {
                    'status': 'ok',
                    'message': f"Flask actif à {flask_url}",
                    'flask_url': flask_url
                }
            else:
                return {
                    'status': 'error',
                    'message': f"Flask ne répond pas correctement à {flask_url}"
                }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}
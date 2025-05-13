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
                'name': 'Caisse (Péage)',
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
        user = request.env.user 
        vfd_url = user.vfd_url
        try:
            payload = {
                "message": raw_message,
                "permanent": permanent
            }
            response = requests.post(vfd_url, json=payload, timeout=5)

            if response.status_code == 200:
                return True
            else:
                _logger.warning("Erreur lors de l'envoi au serveur VFD distant : %s", response.text)
                return False
        except Exception as e:
            _logger.warning("Impossible de contacter le serveur VFD distant : %s", e)
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
            response = requests.get(f"{flask_url}", verify=False, timeout=5)
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
                'payment_method': r.payment_method,
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
                'payment_method': r.payment_method,
            }
            for r in recs
        ]

    @http.route('/anpr_peage/pay_manuely', type='json', auth='user')
    def process_manual_payment(self, plate, vehicle_type, amount):
        user = request.env.user
        print_url = user.print_url
        try:
            # Validation des entrées
            if not all([plate, vehicle_type, amount]):
                return {
                    'payment_status': "failed",
                    'message': "Tous les champs sont requis."
                }

            valid_types = {
                'Car': 'car',
                '4x4': '4x4',
                'Bus': 'bus',
                'Camion': 'camion',
                'Autres': 'autres',
            }
            internal_type = valid_types.get(vehicle_type, 'autres')
            payment_method = "manual"
            transaction_message = "Paiement manuel effectué"

            ticket_number = request.env['ir.sequence'].sudo().next_by_code('anpr.ticket.sequence')

            log_entry = request.env['anpr.log'].sudo().create({
                'user_id': request.env.user.id,
                'plate': plate,
                'vehicle_type': internal_type,
                'amount': amount,
                'transaction_message': transaction_message,
                'payment_status': "success",
                'payment_method': payment_method,
                'paid_at': now_gabon()
            })

            self._create_account_move(amount, payment_method, plate, request.env.user.name)

            print_data = {
                "content": f"Plaque: {plate}, Type: {internal_type}, Montant: {amount}, Date: {now_gabon()}, Paiement: {payment_method}, Statut: {transaction_message}, Ticket: {ticket_number}"
            }
            
            response = requests.post(print_url, json=print_data)
            response.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP

            return {
                'payment_status': "success",
                'message': f"Paiement manuel enregistré avec le ticket {ticket_number}"
            }

        except requests.exceptions.RequestException as e:
            _logger.error("Erreur lors de l'envoi des données d'impression: %s", e)
            return {
                'payment_status': "failed",
                'message': "Erreur de communication avec le serveur d'impression."
            }
        except Exception as e:
            _logger.exception("Erreur lors du traitement du paiement manuel.")
            return {
                'payment_status': "failed",
                'message': str(e)
            }

    @http.route('/anpr_peage/pay', type='json', auth='public', csrf=False)
    def process_payment(self, plate, vehicle_type, numero, amount):
        print("✅ Route /anpr_peage/pay appelée avec :", plate, vehicle_type, numero, amount)
        user = request.env.user
        payment_api_url = user.payment_api_url
        print_url = user.print_url

        try:
            if not all([plate, vehicle_type, numero, amount]):
                return {
                    'status': 'error',
                    'message': "Tous les champs sont requis."
                }

            valid_types = {
                'Car': 'car',
                '4x4': '4x4',
                'Bus': 'bus',
                'Camion': 'camion',
                'Autres': 'autres',
            }
            internal_type = valid_types.get(vehicle_type, 'autres')

            payload = {'numero': numero, 'amount': amount}
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            response = requests.post(payment_api_url, data=payload, headers=headers, timeout=30)
            response.raise_for_status()  # Vérifie les erreurs de réponse

            result = response.json()
            status_message = result.get("status_message", "Aucune réponse").lower()
            payment_status = 'success' if "successfully processed" in status_message else 'failed'

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

                print_data = {
                    "content": f"Plaque: {plate}, Type: {internal_type}, Montant: {amount}, Date: {now_gabon()}, Numéro: {numero}, Paiement: mobile, Statut: {status_message}, Ticket: {ticket_number}"
                }
                
                print_response = requests.post(print_url, json=print_data)
                print_response.raise_for_status()  # Vérifie les erreurs lors de l'envoi

            return {
                'status': payment_status,
                'message': result.get("status_message", "Réponse inconnue"),
                'payment_status': payment_status
            }

        except requests.exceptions.RequestException as req_err:
            _logger.error(f"Erreur de requête : {req_err}")
            return {
                'status': 'error',
                'message': "Erreur de communication avec le serveur de paiement."
            }
        except Exception as e:
            _logger.exception("Erreur lors du traitement du paiement.")
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
    def get_flask_url(self):
        user = request.env.user
        return {
            'flask_url': user.flask_url or ''  # Retourne directement l'URL ou une chaîne vide si non définie
        }
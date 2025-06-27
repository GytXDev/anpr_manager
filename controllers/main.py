# anpr_peage_manager\controllers\main.py
from odoo import http, fields
from odoo.http import request
import requests
import socket
from io import BytesIO
from reportlab.pdfgen import canvas
import base64
from pytz import timezone
from datetime import datetime, time
import serial
import logging
from .pay import generate_receipt_content
from .open_drawer import open_cash_drawer
import xmlrpc.client

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
        ('accounted', '=', True),
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

    def _create_remote_log_entry(self, values):
        """
        Envoie un log de passage vers le serveur distant (modèle anpr.log),
        en liant le caissier via user_id et en ajoutant le prefix du site.
        """
        user = request.env.user
        remote_url = user.remote_odoo_url
        db = user.remote_odoo_db
        login = user.remote_odoo_login
        password = user.remote_odoo_password
        prefix = user.remote_odoo_prefix or "[DISTANT]"
        peage_id = user.peage_server_id

        if not all([remote_url, db, login, password]):
            _logger.warning("Paramètres de connexion au serveur distant incomplets.")
            return

        try:
            common = xmlrpc.client.ServerProxy(f"{remote_url}/xmlrpc/2/common")
            uid = common.authenticate(db, login, password, {})
            if not uid:
                raise Exception("Échec d’authentification sur le serveur distant.")

            models = xmlrpc.client.ServerProxy(f"{remote_url}/xmlrpc/2/object")

            if not peage_id:
                peage_id = models.execute_kw(db, uid, password, 'res.users', 'create', [{
                    'name': user.name,
                    'login': user.login,
                }])
                user.peage_server_id = peage_id

            log_data = {
                'plate': values.get('plate'),
                'vehicle_type': values.get('vehicle_type'),
                'amount': values.get('amount'),
                'transaction_message': f"{prefix} {values.get('transaction_message', 'Passage détecté')}",
                'payment_status': values.get('payment_status', 'success'),
                'payment_method': values.get('payment_method', 'manual'),
                'paid_at': values.get('paid_at'),
                'user_id': peage_id,
                'site_prefix': prefix,
            }

            models.execute_kw(db, uid, password, 'anpr.log', 'create', [log_data])
            _logger.info(f"[REMOTE] Log transmis pour {log_data['plate']} via {prefix} (User ID: {peage_id})")

        except Exception as e:
            _logger.error(f"[REMOTE] Erreur envoi log distant : {e}")
            request.env['anpr.remote.log.retry'].sudo().create({
                'plate': values.get('plate'),
                'vehicle_type': values.get('vehicle_type'),
                'amount': values.get('amount'),
                'transaction_message': values.get('transaction_message', 'Passage détecté'),
                'payment_status': values.get('payment_status', 'success'),
                'payment_method': values.get('payment_method', 'manual'),
                'paid_at': values.get('paid_at'),
                'user_id': user.id,
                'site_prefix': prefix,
                'state': 'pending',
            })

    def _send_to_remote_odoo(self, ref, date, amount, plate, journal_code, debit_code, credit_code):

        # Données de connexion vers le serveur distant
        user = request.env.user
        remote_url = user.remote_odoo_url
        db = user.remote_odoo_db
        login = user.remote_odoo_login
        password = user.remote_odoo_password
        prefix = request.env.user.remote_odoo_prefix or "[DISTANT]"
        
        common = xmlrpc.client.ServerProxy(f"{remote_url}/xmlrpc/2/common")
        uid = common.authenticate(db, login, password, {})

        if not uid:
            raise Exception("Échec d’authentification sur le serveur distant.")

        models = xmlrpc.client.ServerProxy(f"{remote_url}/xmlrpc/2/object")

        # Vérification / création du journal
        journal_ids = models.execute_kw(db, uid, password, 'account.journal', 'search', [[('code', '=', journal_code)]])
        if journal_ids:
            journal_id = journal_ids[0]
        else:
            journal_id = models.execute_kw(db, uid, password, 'account.journal', 'create', [{
                'name': {
                    'PEAGE': 'Péage Manuel',
                    'PEAGE_MM': 'Péage Mobile',
                    'PEAGE_SUB': 'Péage Abonnement',
                }.get(journal_code, 'Péage Inconnu'),
                'code': journal_code,
                'type': 'cash',
            }])
            _logger.info(f"[REMOTE] Journal {journal_code} créé automatiquement.")

        # Vérification / création du compte débit
        debit_ids = models.execute_kw(db, uid, password, 'account.account', 'search', [[('code', '=', debit_code)]])
        if debit_ids:
            debit_id = debit_ids[0]
        else:
            debit_id = models.execute_kw(db, uid, password, 'account.account', 'create', [{
                'name': 'Caisse (Péage)',
                'code': debit_code,
                'account_type': 'asset_cash',
            }])
            _logger.info(f"[REMOTE] Compte débit {debit_code} créé automatiquement.")

        # Vérification / création du compte crédit
        credit_ids = models.execute_kw(db, uid, password, 'account.account', 'search', [[('code', '=', credit_code)]])
        if credit_ids:
            credit_id = credit_ids[0]
        else:
            credit_id = models.execute_kw(db, uid, password, 'account.account', 'create', [{
                'name': 'Produits Péage',
                'code': credit_code,
                'account_type': 'income',
            }])
            _logger.info(f"[REMOTE] Compte crédit {credit_code} créé automatiquement.")

        # Création de l’écriture comptable
        move_id = models.execute_kw(db, uid, password, 'account.move', 'create', [{
            'journal_id': journal_id,
            'ref': ref,
            'date': date,
            'line_ids': [
                (0, 0, {
                    'name': f"{prefix} Paiement péage {plate}",
                    'account_id': debit_id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': f"{prefix} Recette péage {plate}",
                    'account_id': credit_id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ]
        }])

        # Validation de l’écriture
        models.execute_kw(db, uid, password, 'account.move', 'action_post', [[move_id]])
        _logger.info(f"[REMOTE] Écriture comptable postée avec succès (ID {move_id}).")

    def _create_account_move(self, amount, payment_method, plate, user_name):
        env = request.env
        if payment_method == 'manual':
            journal_code = 'PEAGE'
        elif payment_method == 'mobile':
            journal_code = 'PEAGE_MM'
        elif payment_method == 'subscription':
            journal_code = 'PEAGE_SUB'
        else:
            journal_code = 'PEAGE'  # fallback


        # Définir les codes des comptes
        debit_account_code = '531100'
        credit_account_code = '706100'
        
        # Création ou récupération du journal
        journal = env['account.journal'].sudo().search([('code', '=', journal_code)], limit=1)
        if not journal:
            journal_name = {
                'PEAGE': 'Péage Manuel',
                'PEAGE_MM': 'Péage Mobile',
                'PEAGE_SUB': 'Péage Abonnement',
            }.get(journal_code, 'Péage Inconnu')

            journal = env['account.journal'].sudo().create({
                'name': journal_name,
                'code': journal_code,
                'type': 'cash',
                'company_id': env.company.id,
            })


        # Création ou récupération du compte débit
        debit_account = env['account.account'].sudo().search([('code', '=', debit_account_code)], limit=1)
        if not debit_account:
            debit_account = env['account.account'].sudo().create({
                'name': 'Caisse (Péage)',
                'code': debit_account_code,
                'account_type': 'asset_cash',
            })

        # Création ou récupération du compte crédit
        credit_account = env['account.account'].sudo().search([('code', '=', credit_account_code)], limit=1)
        if not credit_account:
            credit_account = env['account.account'].sudo().create({
                'name': 'Produits Péage',
                'code': credit_account_code,
                'account_type': 'income',
            })

        # Création de l’écriture comptable locale
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

        move.action_post()

        # Envoi vers le serveur distant
        try:
            self._send_to_remote_odoo(
                ref=move.ref,
                date=str(move.date),
                amount=amount,
                plate=plate,
                journal_code=journal_code,
                debit_code=debit_account_code,
                credit_code=credit_account_code
            )
        except Exception as e:
            _logger.warning(f"[REMOTE BACKUP] Échec de l'envoi distant : {e}")
            env['failed.remote.move'].sudo().create({
                'ref': move.ref,
                'date': move.date,
                'amount': amount,
                'plate': plate,
                'journal_code': journal_code,
                'debit_code': debit_account_code,
                'credit_code': credit_account_code,
                'user_id': request.env.user.id,
                'error_message': str(e),
            })
            
        return move

    def print_receipt_to_printer(self, ip_address, port, plate, vehicle_type, numero, amount, status_message, ticket_number):
        
        try:
            # 1) Générer le buffer ESC/POS
            receipt_bytes = generate_receipt_content(
                plate=plate,
                vehicle_type=vehicle_type,
                numero=numero,
                amount=amount,
                status_message=status_message,
                ticket_number=ticket_number,
                open_drawer=True
            )
            s = socket.socket()
            s.settimeout(10)
            s.connect((ip_address, port))
            s.sendall(receipt_bytes)
            s.close()
            return True, None
        except Exception as e:
            return False, str(e)

    # Une méthode juste pour ouvrir la caisse via l'imprimante 
    def open_drawer_only(self, ip_address, port):
        try:
            success, error = open_cash_drawer(ip_address, port)
            if success:
                return True, None
            else:
                _logger.error("Erreur ouverture caisse : %s", error)
                return False, error
        except Exception as e:
            _logger.error("Exception lors de l'ouverture de la caisse : %s", e, exc_info=True)
            return False, str(e)


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
        """
        Route JSON pour paiement manuel :
        - Crée le log, la pièce comptable, puis imprime en local sur l’imprimante IP/port stockée sur l’utilisateur.
        """
        user = request.env.user
        try:
            if not all([plate, vehicle_type, amount]):
                return { 'payment_status': "failed", 'message': "Tous les champs sont requis." }

            valid_types = {
                'Car'    : 'car',
                '4x4'    : '4x4',
                'Bus'    : 'bus',
                'Camion' : 'camion',
                'Autres' : 'autres',
            }
            internal_type      = valid_types.get(vehicle_type, 'autres')
            payment_method     = "manual"
            transaction_message = "Paiement manuel effectué"
            ticket_number      = request.env['ir.sequence'].sudo().next_by_code('anpr.ticket.sequence')

            log_entry = request.env['anpr.log'].sudo().create({
                'user_id'             : user.id,
                'plate'               : plate,
                'vehicle_type'        : internal_type,
                'amount'              : amount,
                'transaction_message' : transaction_message,
                'payment_status'      : "success",
                'payment_method'      : payment_method,
                'paid_at'             : now_gabon(),
            })

            try:
                self._create_remote_log_entry({
                    'plate': plate,
                    'vehicle_type': internal_type,
                    'amount': amount,
                    'transaction_message': transaction_message,
                    'payment_status': "success",
                    'payment_method': payment_method,
                    'paid_at': now_gabon().strftime('%Y-%m-%d %H:%M:%S'),
                })
            except Exception as e:
                _logger.warning(f"Échec de l'envoi du log au serveur distant: {e}")

            self._create_account_move(amount, payment_method, plate, user.name)

            ip_addr = user.printer_ip
            port    = int(user.printer_port or 9100)
            success, err = self.print_receipt_to_printer(
                ip_address     = ip_addr,
                port           = port,
                plate          = plate,
                vehicle_type   = internal_type,
                numero         = "MANUEL",
                amount         = amount,
                status_message = transaction_message,
                ticket_number  = ticket_number
            )
            if not success:
                _logger.warning("Échec impression manuel (%s:%s) : %s", ip_addr, port, err)

            return {
                'payment_status': "success",
                'message': f"Paiement manuel enregistré avec le ticket {ticket_number}"
            }

        except Exception as e:
            _logger.exception("Erreur lors du traitement du paiement manuel.")
            return { 'payment_status': "failed", 'message': str(e) }


    @http.route('/anpr_peage/pay', type='json', auth='public', csrf=False)
    def process_payment(self, plate, vehicle_type, numero, amount):
        """
        Route JSON pour paiement Mobile Money :
        - Appelle l’API M-Money externe, génère log + écriture comptable,
          puis imprime directement sur l’imprimante du caissier.
        """
        user = request.env.user
        try:
            if not all([plate, vehicle_type, numero, amount]):
                return { 'status': 'error', 'message': "Tous les champs sont requis." }

            # 1) Préparer type interne
            valid_types = {
                'Car'    : 'car',
                '4x4'    : '4x4',
                'Bus'    : 'bus',
                'Camion' : 'camion',
                'Autres' : 'autres',
            }
            internal_type = valid_types.get(vehicle_type, 'autres')

            # 2) Appel à l’API Mobile Money externe
            payload = {'numero': numero, 'amount': amount}
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            resp = requests.post(user.payment_api_url, data=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            status_message = result.get("status_message", "Aucune réponse").lower()
            payment_status = 'success' if "successfully processed" in status_message else 'failed'

            ticket_number = request.env['ir.sequence'].sudo().next_by_code('anpr.ticket.sequence')

            if payment_status == 'success':
                # 3.1) Créer le log
                request.env['anpr.log'].sudo().create({
                    'user_id'             : user.id,
                    'plate'               : plate,
                    'vehicle_type'        : internal_type,
                    'amount'              : amount,
                    'transaction_message' : status_message,
                    'payment_status'      : payment_status,
                    'payment_method'      : "mobile",
                    'paid_at'             : now_gabon(),
                })

                try:
                    self._create_remote_log_entry({
                        'plate': plate,
                        'vehicle_type': internal_type,
                        'amount': amount,
                        'transaction_message': transaction_message,
                        'payment_status': "success",
                        'payment_method': payment_method,
                        'paid_at': now_gabon().strftime('%Y-%m-%d %H:%M:%S'),
                    })
                except Exception as e:
                    _logger.warning(f"Échec de l'envoi du log au serveur distant: {e}")

                # 3.2) Créer l’écriture comptable
                self._create_account_move(amount, "mobile", plate, user.name)

                # 3.3) Imprimer le reçu
                ip_addr = user.printer_ip
                port    = int(user.printer_port or 9100)
                success, err = self.print_receipt_to_printer(
                    ip_address     = ip_addr,
                    port           = port,
                    plate          = plate,
                    vehicle_type   = internal_type,
                    numero         = numero,
                    amount         = amount,
                    status_message = status_message,
                    ticket_number  = ticket_number
                )
                if not success:
                    _logger.warning("Échec impression mobile (%s:%s) : %s", ip_addr, port, err)

            return {
                'status'        : payment_status,
                'message'       : result.get("status_message", "Réponse inconnue"),
                'payment_status': payment_status
            }

        except requests.exceptions.RequestException as req_err:
            _logger.error(f"Erreur de requête : {req_err}")
            return { 'status': 'error', 'message': "Erreur de communication avec le serveur de paiement." }
        except Exception as e:
            _logger.exception("Erreur lors du traitement du paiement.")
            return { 'status': 'error', 'message': f"Erreur API : {e}" }

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


    @http.route('/anpr_peage/get_current_user', type='json', auth='user')
    def get_current_user(self):
        user = request.env.user.sudo()
        return {
            'id':           user.id,
            'name':         user.name,
            'avatar_url': f"/web/image/res.users/{user.id}/image_128",
            'flask_url':    user.flask_url,
            'payment_api_url': user.payment_api_url,
            'vfd_url':      user.vfd_url,
            'artemis_app_key':    user.artemis_app_key,
            'artemis_app_secret': user.artemis_app_secret,
            'artemis_url':        user.artemis_url,
            'artemis_token':      user.artemis_token,
            'artemis_event_dest_url': user.artemis_event_dest_url,
            'artemis_event_src_codes': user.artemis_event_src_codes,
            'printer_ip':   user.printer_ip,
            'printer_port': user.printer_port,
            # ** LES CHAMPS TVA + TARIFS HT ** 
            'tva_rate':     user.tva_rate,
            'price_autre':  user.price_autre,
            'price_car':    user.price_car,
            'price_camion': user.price_camion,
            'price_4x4':    user.price_4x4,
            'price_bus':    user.price_bus,
        }
    
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

    # Déconnecter l'utilisateur actuel 
    @http.route('/anpr_peage/logout_user', type='json', auth='user', csrf=False)
    def logout_user(self):
        try:
            request.session.logout()

            return {
                'status': 'success',
                'message': 'Caisse fermée, utilisateur déconnecté.'
            }

        except Exception as e:
            _logger.error("Erreur lors de la fermeture de caisse : %s", e)
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/anpr_peage/check_subscription', type='json', auth='user')
    def check_subscription(self, plate):
        """Vérifie si la plaque existe dans les abonnements et traite le passage."""
        user = request.env.user
        plate_clean = plate.upper().strip()

        subscription = request.env['anpr.subscription.pass'].sudo().search([
            ('plate', '=', plate_clean)
        ], limit=1)

        if not subscription:
            return {'exists': False}

        if subscription.balance >= subscription.cost_per_passage:
            try:
                # Débit du compte
                subscription.debit_passage()

                # Définition des variables nécessaires
                amount = subscription.cost_per_passage
                internal_type = subscription.vehicle_type
                transaction_message = "Passage via abonnement actif"
                payment_method = "subscription"

                # Création du log local
                log_entry = request.env['anpr.log'].sudo().create({
                    'user_id': user.id,
                    'plate': plate_clean,
                    'vehicle_type': internal_type,
                    'amount': 0.0,
                    'transaction_message': transaction_message,
                    'payment_status': "success",
                    'payment_method': payment_method,
                    'paid_at': now_gabon(),
                })

                # Création du log distant
                try:
                    self._create_remote_log_entry({
                        'plate': plate,
                        'vehicle_type': internal_type,
                        'amount': amount,
                        'transaction_message': transaction_message,
                        'payment_status': "success",
                        'payment_method': payment_method,
                        'paid_at': now_gabon().strftime('%Y-%m-%d %H:%M:%S'),
                    })
                except Exception as e:
                    _logger.warning(f"Échec de l'envoi du log au serveur distant: {e}")

                # Écriture comptable
                self._create_account_move(amount, payment_method, plate, user.name)

                # Ouverture de la caisse
                ip_addr = user.printer_ip
                port = int(user.printer_port or 9100)
                if ip_addr:
                    self.open_drawer_only(ip_addr, port)

                return {'exists': True}

            except Exception as e:
                _logger.error(f"Erreur lors du traitement du passage abonnement : {e}")
                return {'exists': False, 'error': str(e)}
        else:
            # Solde insuffisant, redirection vers paiement normal
            return {
                'exists': False,
                'insufficient_balance': True,
                'amount_due': subscription.cost_per_passage,
                'vehicle_type': subscription.vehicle_type
            }
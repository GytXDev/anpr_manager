# models/res_users.py
from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    artemis_app_key = fields.Char("Clé App Artemis")
    artemis_app_secret = fields.Char("Secret App Artemis")
    artemis_url = fields.Char("URL Artemis")
    artemis_token = fields.Char("Token Artemis")
    artemis_event_dest_url = fields.Char("URL Flask (eventDest)")
    artemis_event_src_codes = fields.Char("Liste caméras ANPR")
    flask_url = fields.Char("URL Serveur Flask") # Installer sur le vps
    payment_api_url = fields.Char("URL API Mobile Money")
    printer_ip = fields.Char("IP Imprimante POS")
    printer_port = fields.Integer("Port Imprimante POS")
    vfd_url = fields.Char("URL Serveur VFD")
    # print_url = fields.Char("URL Serveur de commande d'impressions")
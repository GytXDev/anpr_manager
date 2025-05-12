# models/res_config_settings.py
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    artemis_app_key = fields.Char(string="Clé App Artemis")
    artemis_app_secret = fields.Char(string="Secret App Artemis")
    artemis_url = fields.Char(string="URL Artemis")
    artemis_token = fields.Char(string="Token")
    artemis_event_dest_url = fields.Char(string="URL Flask (eventDest)")
    artemis_event_src_codes = fields.Char(string="Liste caméras ANPR")
    flask_url = fields.Char(string="URL Serveur Flask")
    payment_api_url = fields.Char(string="URL API Mobile Money")
    printer_ip = fields.Char(string="IP Imprimante POS")
    printer_port = fields.Integer(string="Port Imprimante POS")
    vfd_url = fields.Char(string="URL Serveur VFD")

    def get_values(self):
        res = super().get_values()
        user = self.env.user
        res.update({
            'artemis_app_key': user.artemis_app_key,
            'artemis_app_secret': user.artemis_app_secret,
            'artemis_url': user.artemis_url,
            'artemis_token': user.artemis_token,
            'artemis_event_dest_url': user.artemis_event_dest_url,
            'artemis_event_src_codes': user.artemis_event_src_codes,
            'flask_url': user.flask_url,
            'payment_api_url': user.payment_api_url,
            'printer_ip': user.printer_ip,
            'printer_port': user.printer_port,
            'vfd_url': user.vfd_url,
            # 'print_url': user.print_url,
        })
        return res

    def set_values(self):
        super().set_values()
        user = self.env.user
        user.write({
            'artemis_app_key': self.artemis_app_key,
            'artemis_app_secret': self.artemis_app_secret,
            'artemis_url': self.artemis_url,
            'artemis_token': self.artemis_token,
            'artemis_event_dest_url': self.artemis_event_dest_url,
            'artemis_event_src_codes': self.artemis_event_src_codes,
            'flask_url': self.flask_url,
            'payment_api_url': self.payment_api_url,
            'printer_ip': self.printer_ip,
            'printer_port': self.printer_port,
            'vfd_url': self.vfd_url,
            # 'print_url': self.print_url,
        })

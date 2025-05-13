# models/res_config_settings.py
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    artemis_app_key = fields.Char("Clé App Artemis")
    artemis_app_secret = fields.Char("Secret App Artemis")
    artemis_url = fields.Char("URL Artemis")
    artemis_token = fields.Char("Token")
    artemis_event_dest_url = fields.Char("URL Flask (eventDest)")
    artemis_event_src_codes = fields.Char("Liste caméras ANPR")
    flask_url = fields.Char("URL Serveur Flask")
    payment_api_url = fields.Char("URL API Mobile Money")
    vfd_url = fields.Char("URL Serveur VFD")
    print_url = fields.Char("URL Serveur d’impression")

    def get_values(self):
        res = super().get_values()
        user = self.env.user.sudo()

        # Protection dynamique
        for field_name in [
            'artemis_app_key', 'artemis_app_secret', 'artemis_url', 'artemis_token',
            'artemis_event_dest_url', 'artemis_event_src_codes', 'flask_url',
            'payment_api_url', 'vfd_url', 'print_url'
        ]:
            if field_name in user._fields:
                res[field_name] = getattr(user, field_name)

        return res

    def set_values(self):
        super().set_values()
        user = self.env.user.sudo()

        for field_name in [
            'artemis_app_key', 'artemis_app_secret', 'artemis_url', 'artemis_token',
            'artemis_event_dest_url', 'artemis_event_src_codes', 'flask_url',
            'payment_api_url', 'vfd_url', 'print_url'
        ]:
            if field_name in self._fields and field_name in user._fields:
                user[field_name] = getattr(self, field_name)
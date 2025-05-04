# anpr_peage_manager/models/account_patch.py

from odoo import models

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super().action_post()

        for move in self:
            if move.ref and "Paiement" in move.ref:
                # Exemple : ref = "Paiement TR123ABC - John Doe"
                ref_parts = move.ref.split(" ")
                if len(ref_parts) >= 2:
                    plate = ref_parts[1]  # ex: TR123ABC

                    # On cherche la transaction correspondante non encore comptabilisée
                    anpr_log = self.env['anpr.log'].search([
                        ('plate', '=', plate),
                        ('accounted', '=', False),
                        ('payment_status', '=', 'success')
                    ], order='paid_at desc', limit=1)

                    if anpr_log:
                        anpr_log.accounted = True

        return res

    def button_draft(self):
        res = super().button_draft()

        for move in self:
            if move.ref and "Paiement" in move.ref:
                ref_parts = move.ref.split(" ")
                if len(ref_parts) >= 2:
                    plate = ref_parts[1]  # ex: TR123ABC

                    # On cherche la transaction liée
                    anpr_log = self.env['anpr.log'].search([
                        ('plate', '=', plate),
                        ('accounted', '=', True),
                        ('payment_status', '=', 'success')
                    ], order='paid_at desc', limit=1)

                    if anpr_log:
                        anpr_log.accounted = False

        return res
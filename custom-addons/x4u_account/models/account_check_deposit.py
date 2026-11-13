from odoo import Command, _, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date


class AccountCheckDeposit(models.Model):
    _inherit = "account.check.deposit"

    def _x4u_not_due(self):
        """Cheque lines dated after the deposit date: the bank would refuse them (spec §12 K3)."""
        self.ensure_one()
        return self.check_payment_ids.filtered(
            lambda line: line.payment_id.x4u_cheque_date and line.payment_id.x4u_cheque_date > self.deposit_date
        )

    def get_all_checks(self):
        res = super().get_all_checks()
        for deposit in self:
            deposit._x4u_not_due().write({"check_deposit_id": False})
        return res

    def validate_deposit(self):
        for deposit in self:
            not_due = deposit._x4u_not_due()
            if not_due:
                raise UserError(
                    _(
                        "These cheques are dated after %(date)s and cannot be deposited yet: %(cheques)s",
                        date=format_date(self.env, deposit.deposit_date),
                        cheques=", ".join(
                            "%s (%s)" % (line.payment_id.x4u_cheque_number, format_date(self.env, line.payment_id.x4u_cheque_date))
                            for line in not_due
                        ),
                    )
                )
        return super().validate_deposit()

    def _prepare_move_vals(self):
        """One bank line per cheque instead of one for the total (spec §12 K4): the bank clears each
        cheque on its own day, the statement line meets its cheque, and a bounce reverses only that one."""
        vals = super()._prepare_move_vals()
        bank_side = [cmd for cmd in vals["line_ids"] if cmd[2].get("debit")]
        if len(bank_side) != 1:
            return vals
        bank_vals = bank_side[0][2]
        lines = [cmd for cmd in vals["line_ids"] if cmd is not bank_side[0]]
        for line in self.check_payment_ids:
            pay = line.payment_id
            lines.append(
                Command.create(
                    {
                        "account_id": bank_vals["account_id"],
                        "partner_id": line.partner_id.id,
                        "name": _("Cheque %(number)s - %(partner)s", number=pay.x4u_cheque_number or line.name,
                                  partner=line.partner_id.display_name),
                        "debit": line.debit,
                        "currency_id": bank_vals.get("currency_id"),
                        "amount_currency": line.amount_currency,
                        "x4u_deposit_payment_id": pay.id,
                    }
                )
            )
        vals["line_ids"] = lines
        return vals

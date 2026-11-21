from odoo import _, fields, models
from odoo.exceptions import UserError

from ..hooks import USD_PER_AED_PEG

# Spec §18: the ECB publishes no dirham rate, so GBP (and any other ECB currency) comes from the
# ECB against the dollar, then through the peg (spec §8 Q1). USD itself stays at the peg.
SERVICE = "X4U_ECB_USD_PEG"


class ResCurrencyRateProvider(models.Model):
    _inherit = "res.currency.rate.provider"

    service = fields.Selection(
        selection_add=[(SERVICE, "ECB via the USD peg (AED)")],
        ondelete={SERVICE: "set default"},
    )

    def _x4u_ecb(self):
        return self.new({"service": "ECB", "company_id": self.company_id.id})

    def _get_supported_currencies(self):
        self.ensure_one()
        if self.service != SERVICE:
            return super()._get_supported_currencies()
        return [name for name in self._x4u_ecb()._get_supported_currencies() if name != "USD"]

    def _obtain_rates(self, base_currency, currencies, date_from, date_to):
        self.ensure_one()
        if self.service != SERVICE:
            return super()._obtain_rates(base_currency, currencies, date_from, date_to)
        if base_currency != "AED":
            raise UserError(_("%(provider)s works for a company in AED only.", provider=self.name))
        wanted = [name for name in currencies if name not in ("AED", "USD")]
        # Units of each currency per 1 USD, then per 1 AED (1 AED = 1 / 3.6725 USD).
        per_usd = self._x4u_ecb()._obtain_rates("USD", list(wanted), date_from, date_to) or {}
        return {
            day: {name: str(float(rate) / USD_PER_AED_PEG) for name, rate in rates.items() if name in wanted}
            for day, rates in per_usd.items()
        }

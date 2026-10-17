# Odoo 18 + extra Python deps required by OCA modules (e.g. mis_builder -> openupgradelib)
FROM odoo:18.0-20261015
USER root
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt
USER odoo

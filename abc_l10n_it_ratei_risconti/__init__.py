# -*- coding: utf-8 -*-
from . import models
from . import wizard


def post_init_hook(env):
    """Disattiva i differimenti nativi di Odoo: generazione manuale per tutte le societa'.
    I menu dei report nativi sono nascosti da ir.ui.menu._load_menus_blacklist."""
    env['res.company'].search([])._abc_rr_disable_native()

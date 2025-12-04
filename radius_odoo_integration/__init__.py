# -*- coding: utf-8 -*-
from . import models
from . import wizards
from .models.ir_ui_view_fix import disable_problematic_views


def post_init_hook(env):
    """
    Hook that runs after module installation/upgrade.
    Disables problematic views from uninstalled modules.
    """
    disable_problematic_views(env)

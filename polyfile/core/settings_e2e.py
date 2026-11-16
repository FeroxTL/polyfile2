"""Django settings used by the browser end-to-end test suite.

This module inherits the production/development settings and tweaks a few
values so that a live server can be started cleanly for Playwright:

* disable the debug toolbar completely
* redirect to the SPA after login
* keep ALLOWED_HOSTS permissive for ephemeral test server ports
"""

from polyfile.core.settings import *

DEBUG_TOOLBAR_ENABLED = False
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]
MIDDLEWARE = [
    middleware
    for middleware in MIDDLEWARE
    if middleware != "debug_toolbar.middleware.DebugToolbarMiddleware"
]
LOGIN_REDIRECT_URL = "/files/"
AXES_ENABLED = False

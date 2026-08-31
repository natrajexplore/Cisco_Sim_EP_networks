"""Connectors package.

Silence the noisy InsecureRequestWarning: the DevNet sandboxes present
internal-CA / self-signed certificates and are accessed with verify=False by
design. This is a lab tool talking to public practice sandboxes, not production.
"""

from __future__ import annotations

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

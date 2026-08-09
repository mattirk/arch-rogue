# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# Deploy health probe: exit 0 once 127.0.0.1:$PORT accepts a TCP connection,
# exit 1 if it never does within the deadline. Used by deploy-server.yml.

from __future__ import annotations

import os
import socket
import sys
import time


def main() -> int:
    port = int(os.environ["PORT"])
    deadline = time.monotonic() + float(os.environ.get("PROBE_DEADLINE", "10"))
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.5):
                return 0
        except OSError:
            time.sleep(0.5)
    return 1


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Server-side facade over the canonical shared wire protocol.

The server must consume the exact same ``arch_rogue_protocol`` package the
game client re-exports through ``arch_rogue.net.protocol`` — never a vendored
or copied module — so client and server can never drift. When the package is
not installed (running straight from a repo checkout), the sibling ``src/``
tree is added to ``sys.path`` and the same canonical files are imported from
there.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import arch_rogue_protocol as _protocol
except ModuleNotFoundError:  # pragma: no cover - repo-checkout convenience
    _src = Path(__file__).resolve().parent.parent / "src"
    if (_src / "arch_rogue_protocol").is_dir():
        sys.path.insert(0, str(_src))
        import arch_rogue_protocol as _protocol
    else:
        raise

from arch_rogue_protocol import *  # noqa: F401,F403,E402
from arch_rogue_protocol import __all__ as _protocol_all  # noqa: E402

__all__ = list(_protocol_all)

assert _protocol is not None

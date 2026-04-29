"""Language-aware structural extractors for baseline diff analysis.

Each extractor produces PatternMatch objects that describe trackable
code patterns (auth conditions, function signatures, route metadata, etc.)
for a specific language ecosystem.

The extractors are FACT PRODUCERS — they extract what exists in code.
Policy rules in codegate.policies.security consume these facts to make
governance decisions.
"""

from codegate.analysis.structural_extractors.typescript import (
    extract_typescript_patterns,
)
from codegate.analysis.structural_extractors.rust import (
    extract_rust_patterns,
)

__all__ = [
    "extract_typescript_patterns",
    "extract_rust_patterns",
]

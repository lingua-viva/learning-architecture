"""
Governed External Research Gateway

Three layers of governance:
1. Ontology gate: blocks_external = True → nothing leaves. Period.
2. PII sanitizer: 3-layer detection strips sensitive data.
3. Targeted query: formulated using node name + local knowledge gaps.
"""

from .sanitizer import Sanitizer
from .perplexity import PerplexityGateway, PerplexityResult

__all__ = ["Sanitizer", "PerplexityGateway", "PerplexityResult"]

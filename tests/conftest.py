"""Tests import the package from this checkout. evalcore comes from the installed geo-eval dependency; a local
checkout of geo-eval can be used instead by setting GEO_EVAL_REPO to its path."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("GEO_EVAL_REPO"):
    sys.path.insert(0, os.environ["GEO_EVAL_REPO"])

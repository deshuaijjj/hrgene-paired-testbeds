"""Import the benchmark's oracle builder without duplicating it."""
import importlib.util
import os

_p = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "benchmark", "v4", "build", "oracle.py"))
_spec = importlib.util.spec_from_file_location("hrgene_oracle", _p)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
oracle_bundle = _mod.oracle_bundle
oracle_bridge_oracle_bundle = oracle_bundle

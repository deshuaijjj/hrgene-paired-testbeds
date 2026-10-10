"""hrgene — executable expert-rule contracts for evidence-bounded HR review packets (HRgene v4).

Standard library only. Modules:
  schema_lite  minimal JSON-schema (draft 2020-12 subset) validator used for the output contract
  lexicons     bilingual term families + numeric normalisation
  textmatch    term / family / number matching with negation windows
  rules        rule registry (canonical-rules.v2.json): activation (tau) and obligation rendering (d)
  bundle       traversal helpers for PairedReviewBundle v2 outputs
  detectors    the nine detectors (phi) -> findings
  validator    run detectors, aggregate ACCEPT / HUMAN_REVIEW / BLOCK
  repair       bounded deterministic repair (rho) + repair log
  pipeline     C3 (validate & report) / C4 (validate, repair, <=1 regeneration)
"""
__version__ = "2.0.0"

"""
MFA Study

This is a revision of the prototype 'mfa_models' framework for building a nested LCA study with an observed
MFA at its core.

The NestedLcaStudy creates a three-tier system with a study container, a logistics container, and an activity
container, which is terminated to the study driver (nominally an MFA fragment).  The NestedLcaStudy includes
tools to build "routes" that attach to the logistics / study containers to link MFA flows to LCA models.  This is
done with an explicit mapping of flow to route.

In fact, the flow is supposed to plug into a MARKET of routes.
"""
from .lc_mfa_study import NestedLcaStudy
from .dynamic_unit_study import DynamicUnitLcaStudy, DynamicUnitSpec
from .observed_mfa_study import ObservedMfaStudy, StudySpec

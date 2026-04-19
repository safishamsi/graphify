"""Pure local oracles used by the verifier."""

from depos.analysis.oracles.advisory_db import lookup as advisory_lookup
from depos.analysis.oracles.json_schema import lookup as json_schema_lookup
from depos.analysis.oracles.lockfile_resolver import lookup as lockfile_lookup
from depos.analysis.oracles.openapi_lookup import lookup as openapi_lookup
from depos.analysis.oracles.pep440 import lookup as pep440_lookup
from depos.analysis.oracles.semver import lookup as semver_lookup

ORACLES = {
    "advisory_db": advisory_lookup,
    "json_schema": json_schema_lookup,
    "lockfile_resolver": lockfile_lookup,
    "openapi_lookup": openapi_lookup,
    "pep440": pep440_lookup,
    "semver": semver_lookup,
}

__all__ = ["ORACLES"]

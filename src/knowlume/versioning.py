from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TypedDict

from knowlume.constants import (
    CONFIGURATION_VERSION,
    DISTRIBUTION_NAME,
    INTERFACE_VERSION,
    LOCATOR_VERSION,
    OBJECT_CONTRACT_VERSION,
    PARSER_VERSION,
    PROJECTION_VERSION,
    RELATION_SCHEMA_VERSION,
    TRANSACTION_VERSION,
)


class VersionReport(TypedDict):
    package: str
    object_contract: int
    locator: int
    relation_schema: int
    interface: int
    projection: int
    parser: int
    configuration: int
    transaction: int


def package_version() -> str:
    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "0+unknown"


def version_report() -> VersionReport:
    return {
        "package": package_version(),
        "object_contract": OBJECT_CONTRACT_VERSION,
        "locator": LOCATOR_VERSION,
        "relation_schema": RELATION_SCHEMA_VERSION,
        "interface": INTERFACE_VERSION,
        "projection": PROJECTION_VERSION,
        "parser": PARSER_VERSION,
        "configuration": CONFIGURATION_VERSION,
        "transaction": TRANSACTION_VERSION,
    }


def format_version_report() -> str:
    report = version_report()
    return (
        f"Knowlume {report['package']} "
        f"(object={report['object_contract']}, locator={report['locator']}, "
        f"relation={report['relation_schema']}, interface={report['interface']}, "
        f"projection={report['projection']}, parser={report['parser']}, "
        f"configuration={report['configuration']}, transaction={report['transaction']})"
    )

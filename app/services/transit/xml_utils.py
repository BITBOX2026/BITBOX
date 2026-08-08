"""Hardened XML parsing helpers for external transit API responses."""

from typing import Any

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException


XML_ELEMENT_TYPE = type(ElementTree.fromstring("<root />"))
XML_PARSE_ERRORS = (ElementTree.ParseError, DefusedXmlException)


def parse_untrusted_xml(value: str) -> Any:
    """Parse external XML while rejecting DTD and entity expansion features."""
    return ElementTree.fromstring(value)

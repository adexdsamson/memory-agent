"""Conformance test suite for MNEMA backend adapters.

Each sub-module defines a contract test against a specific port Protocol.
Tests in this package run across multiple backend implementations via
parametrized fixtures defined in conftest.py.

Local-always backends run in every CI environment without credentials.
Cloud/Postgres backends are gated by MNEMA_TEST_* environment variables
and skip cleanly when unavailable.
"""

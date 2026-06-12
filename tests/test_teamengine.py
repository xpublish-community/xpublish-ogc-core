"""Tests for the TeamEngine (CITE) harness shipped for downstream OGC plugins.

These cover the offline pieces of the harness; ``test_cite.py`` runs an
actual suite against this plugin, and the full standard-specific suites run
in the plugin repos that compose ogc-core with a data plugin (xpublish-edr,
xpublish-tiles).
"""

from xpublish_ogc_core.teamengine import free_port, parse_testng_results

TESTNG_RESULTS = """<?xml version="1.0" encoding="UTF-8"?>
<testng-results ignored="0" total="4" passed="1" failed="1" skipped="1">
  <suite name="ogcapi-example-1.0" duration-ms="100">
    <test name="example">
      <class name="org.opengis.cite.example.Conformance">
        <test-method status="PASS" name="setUp" is-config="true" signature="setUp()"/>
        <test-method status="PASS" name="validateConformance" signature="validateConformance()"/>
        <test-method status="FAIL" name="apiDefinitionValidation" signature="apiDefinitionValidation()">
          <exception class="java.lang.AssertionError">
            <message><![CDATA[API definition is not valid]]></message>
          </exception>
        </test-method>
        <test-method status="SKIP" name="validateLocations" signature="validateLocations()"/>
      </class>
    </test>
  </suite>
</testng-results>
"""


def test_parse_testng_results():
    result = parse_testng_results(TESTNG_RESULTS)

    assert result.passed == 1
    assert result.failed == 1
    assert result.skipped == 1


def test_configuration_methods_are_ignored():
    result = parse_testng_results(TESTNG_RESULTS)

    assert result.passed == 1, "is-config methods should not be counted"


def test_failures_carry_test_name_and_message():
    result = parse_testng_results(TESTNG_RESULTS)

    assert result.failure_names() == {"Conformance.apiDefinitionValidation"}

    failure = result.failures[0]
    assert failure.message == "API definition is not valid"


def test_summary_points_at_failures():
    result = parse_testng_results(TESTNG_RESULTS)

    summary = result.summary()
    assert "1 passed, 1 failed, 1 skipped" in summary
    assert "Conformance.apiDefinitionValidation" in summary


def test_free_port_is_usable():
    port = free_port()

    assert 0 < port < 65536

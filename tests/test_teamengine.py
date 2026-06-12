"""Tests for the TeamEngine (CITE) harness shipped for downstream OGC plugins.

These cover the offline pieces of the harness; ``test_cite.py`` runs an
actual suite against this plugin, and the full standard-specific suites run
in the plugin repos that compose ogc-core with a data plugin (xpublish-edr,
xpublish-tiles).
"""

from pathlib import Path

from xpublish_ogc_core.teamengine import (
    free_port,
    parse_testng_results,
    report_subtests,
)

# a real ets-ogcapi-edr10 run against the core+edr app: 9 passed, 2 failed,
# 11 skipped (see the testng-results header in the fixture)
EDR_CITE_RESULTS = (Path(__file__).parent / "fixtures" / "edr_cite_results.xml").read_text()

# the two methods that fail in that run, for use as a known-failures set
EDR_KNOWN_FAILURES = {
    "ApiDefinition.apiDefinitionValidation",
    "Conformance.validateConformanceOperationAndResponse",
}

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


def test_parses_a_real_suite_run():
    result = parse_testng_results(EDR_CITE_RESULTS)

    assert (result.passed, result.failed, result.skipped) == (9, 2, 11)
    assert result.failure_names() == EDR_KNOWN_FAILURES


def test_records_every_test_method_not_just_failures():
    result = parse_testng_results(EDR_CITE_RESULTS)

    # the parser now keeps passes and skips too, so report_subtests can show
    # one subtest per method
    assert len(result.tests) == 22
    statuses = {test.status for test in result.tests}
    assert statuses == {"PASS", "FAIL", "SKIP"}


def test_report_subtests_passes_when_all_failures_are_known(subtests):
    result = parse_testng_results(EDR_CITE_RESULTS)

    # every failure is expected and the suite ran enough passes: this should
    # complete without failing the test (the failures show up as xfails)
    report_subtests(
        result,
        subtests,
        known_failures=EDR_KNOWN_FAILURES,
        expected_passed=9,
    )


def _run_report(pytester, *, known_failures, expected_passed):
    """Drive report_subtests in an isolated pytest run and return the result."""
    fixture = Path(__file__).parent / "fixtures" / "edr_cite_results.xml"
    pytester.makepyfile(
        f"""
        from pathlib import Path

        from xpublish_ogc_core.teamengine import parse_testng_results, report_subtests

        def test_cite(subtests):
            result = parse_testng_results(Path({str(fixture)!r}).read_text())
            report_subtests(
                result,
                subtests,
                known_failures={known_failures!r},
                expected_passed={expected_passed},
            )
        """,
    )
    return pytester.runpytest("-rA")


def test_report_subtests_flags_unexpected_failures(pytester):
    result = _run_report(pytester, known_failures=set(), expected_passed=0)

    assert result.ret != 0
    out = result.stdout.str()
    assert "SUBFAILED" in out
    # both real failures are surfaced as their own subtests
    assert "ApiDefinition.apiDefinitionValidation" in out
    assert "Conformance.validateConformanceOperationAndResponse" in out


def test_report_subtests_flags_known_failures_that_now_pass(pytester):
    # a method that actually passes in the fixture, wrongly listed as known
    stale = EDR_KNOWN_FAILURES | {"ApiDefinition.openapiDocumentRetrieval"}
    result = _run_report(pytester, known_failures=stale, expected_passed=9)

    assert result.ret != 0
    out = result.stdout.str()
    assert "known_failures now pass" in out
    assert "ApiDefinition.openapiDocumentRetrieval" in out


def test_report_subtests_enforces_expected_passed(pytester):
    result = _run_report(pytester, known_failures=EDR_KNOWN_FAILURES, expected_passed=99)

    assert result.ret != 0
    assert "at least 99 tests passed" in result.stdout.str()

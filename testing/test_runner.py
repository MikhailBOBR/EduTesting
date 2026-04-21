import re
import time
import unittest
import warnings

from django.core.management.color import color_style, no_style
from django.test.runner import DebugSQLTextTestResult, DiscoverRunner, PDBDebugResult


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


class PrettyTextTestResult(unittest.TextTestResult):
    progress_width = 28

    def __init__(self, stream, descriptions, verbosity, total_tests=0, style=None):
        super().__init__(stream, descriptions, verbosity)
        self.total_tests = total_tests
        self.style = style or no_style()
        self.inline_progress = self.dots and getattr(stream, "isatty", lambda: False)()
        self.last_progress_length = 0
        self.progress_started = False

    def startTestRun(self):
        super_method = getattr(super(), "startTestRun", None)
        if callable(super_method):
            super_method()
        if self.dots:
            self.stream.writeln("")
            self.stream.writeln(self._paint("MIGRATE_HEADING", "=" * 62))
            self.stream.writeln(self._paint("MIGRATE_HEADING", "EduTesting Test Run"))
            if self.total_tests:
                self.stream.writeln(f"Total tests: {self.total_tests}")
            self.stream.writeln(self._paint("HTTP_INFO", "-" * 62))
            self.stream.flush()

    def startTest(self, test):
        super(unittest.TextTestResult, self).startTest(test)

    def addSuccess(self, test):
        super(unittest.TextTestResult, self).addSuccess(test)
        self._report("OK", "SUCCESS", test)

    def addError(self, test, err):
        super(unittest.TextTestResult, self).addError(test, err)
        self._report("ERROR", "ERROR", test)

    def addFailure(self, test, err):
        super(unittest.TextTestResult, self).addFailure(test, err)
        self._report("FAIL", "ERROR", test)

    def addSkip(self, test, reason):
        super(unittest.TextTestResult, self).addSkip(test, reason)
        self._report(f"SKIP ({reason})", "WARNING", test)

    def addExpectedFailure(self, test, err):
        super(unittest.TextTestResult, self).addExpectedFailure(test, err)
        self._report("EXPECTED FAIL", "WARNING", test)

    def addUnexpectedSuccess(self, test):
        super(unittest.TextTestResult, self).addUnexpectedSuccess(test)
        self._report("UNEXPECTED SUCCESS", "ERROR", test)

    def printErrors(self):
        self.finish_progress()
        super().printErrors()

    def finish_progress(self):
        if self.inline_progress and self.progress_started:
            self.stream.writeln("")
            self.stream.flush()
            self.progress_started = False
            self.last_progress_length = 0

    def _report(self, label, style_name, test):
        if self.showAll:
            status = self._paint(style_name, f"[{label}]")
            self.stream.writeln(f"{status} {self.getDescription(test)}")
            self.stream.flush()
            return
        if not self.dots:
            return
        if self.inline_progress:
            line = self._build_progress_line(label, style_name)
            visible_length = len(self._strip_ansi(line))
            padding = max(0, self.last_progress_length - visible_length)
            self.stream.write("\r" + line + (" " * padding))
            self.stream.flush()
            self.progress_started = True
            self.last_progress_length = visible_length
            return
        if self._should_emit_checkpoint(label):
            self.stream.writeln(self._build_progress_line(label, style_name))
            self.stream.flush()

    def _should_emit_checkpoint(self, label):
        if label not in {"OK", "EXPECTED FAIL"}:
            return True
        if self.testsRun == 1:
            return True
        if self.total_tests and self.testsRun == self.total_tests:
            return True
        return self.testsRun % 10 == 0

    def _build_progress_line(self, label, style_name):
        status = self._paint(style_name, label)
        if not self.total_tests:
            return f"Progress: {self.testsRun} [{status}]"
        filled = int((self.testsRun / self.total_tests) * self.progress_width)
        bar = "#" * filled + "-" * (self.progress_width - filled)
        return f"Progress [{bar}] {self.testsRun}/{self.total_tests} [{status}]"

    def _paint(self, style_name, text):
        formatter = getattr(self.style, style_name, None)
        if callable(formatter):
            return formatter(text)
        return text

    @staticmethod
    def _strip_ansi(text):
        return ANSI_ESCAPE_RE.sub("", text)


class PrettyTextTestRunner(unittest.TextTestRunner):
    resultclass = PrettyTextTestResult

    def __init__(self, *args, total_tests=0, style=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_tests = total_tests
        self.style = style or color_style()

    def _makeResult(self):
        if self.resultclass is None:
            resultclass = PrettyTextTestResult
        else:
            resultclass = self.resultclass
        try:
            return resultclass(
                self.stream,
                self.descriptions,
                self.verbosity,
                total_tests=self.total_tests,
                style=self.style,
            )
        except TypeError:
            return resultclass(self.stream, self.descriptions, self.verbosity)

    def run(self, test):
        result = self._makeResult()
        unittest.registerResult(result)
        result.failfast = self.failfast
        result.buffer = self.buffer
        result.tb_locals = self.tb_locals
        with warnings.catch_warnings():
            if self.warnings:
                warnings.simplefilter(self.warnings)
                if self.warnings in ["default", "always"]:
                    warnings.filterwarnings(
                        "module",
                        category=DeprecationWarning,
                        message=r"Please use assert\w+ instead.",
                    )
            start_time = time.perf_counter()
            start_test_run = getattr(result, "startTestRun", None)
            if start_test_run is not None:
                start_test_run()
            try:
                test(result)
            finally:
                stop_test_run = getattr(result, "stopTestRun", None)
                if stop_test_run is not None:
                    stop_test_run()
            stop_time = time.perf_counter()

        time_taken = stop_time - start_time
        finish_progress = getattr(result, "finish_progress", None)
        if callable(finish_progress):
            finish_progress()
        result.printErrors()

        failed = len(result.failures)
        errored = len(result.errors)
        skipped = len(getattr(result, "skipped", []))
        expected_failures = len(getattr(result, "expectedFailures", []))
        unexpected_successes = len(getattr(result, "unexpectedSuccesses", []))
        passed = max(
            0,
            result.testsRun - failed - errored - skipped - expected_failures - unexpected_successes,
        )

        self.stream.writeln(self._paint("HTTP_INFO", "-" * 62))
        self.stream.writeln(f"Total  : {result.testsRun}")
        status_label = "OK" if result.wasSuccessful() else "FAILED"
        status_style = "SUCCESS" if result.wasSuccessful() else "ERROR"
        self.stream.writeln(f"Result : {self._paint(status_style, status_label)}")
        self.stream.writeln(f"Passed : {passed}")
        self.stream.writeln(f"Failed : {failed}")
        self.stream.writeln(f"Errors : {errored}")
        if skipped:
            self.stream.writeln(f"Skipped: {skipped}")
        if expected_failures:
            self.stream.writeln(f"Expected failures : {expected_failures}")
        if unexpected_successes:
            self.stream.writeln(f"Unexpected successes: {unexpected_successes}")
        self.stream.writeln(f"Time   : {time_taken:.3f}s")
        self.stream.writeln(self._paint("MIGRATE_HEADING", "=" * 62))
        self.stream.flush()
        return result

    def _paint(self, style_name, text):
        formatter = getattr(self.style, style_name, None)
        if callable(formatter):
            return formatter(text)
        return text


class PrettyDiscoverRunner(DiscoverRunner):
    test_runner = PrettyTextTestRunner

    def get_resultclass(self):
        if self.debug_sql:
            return DebugSQLTextTestResult
        if self.pdb:
            return PDBDebugResult
        return PrettyTextTestResult

    def run_suite(self, suite, **kwargs):
        runner = self.test_runner(
            total_tests=suite.countTestCases(),
            style=color_style(),
            **self.get_test_runner_kwargs(),
        )
        try:
            return runner.run(suite)
        finally:
            if self._shuffler is not None:
                seed_display = self._shuffler.seed_display
                self.log(f"Used shuffle seed: {seed_display}")

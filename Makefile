# omarchy-pdf — canonical entry points.
# `make test` runs every kind (incl. the slow mutation pass);
# `make check` is the fast policy + unit + regression gate for a pre-push hook.

.PHONY: test check policy unit regression integration e2e shell mutation

test:
	bash tools/run_tests.sh

check: policy unit regression

policy:
	python3 tools/policy_check.py

unit:
	python3 -m unittest discover -s tests -p 'test_unit_*.py' -q

regression:
	python3 -m unittest discover -s tests -p 'test_regression_*.py' -q

integration:
	QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s tests -p 'test_integration_*.py' -q

e2e:
	bash tests/e2e/test_viewer_e2e.sh

shell:
	bash tests/shell/test_omarchy_pdf.sh

mutation:
	python3 tools/mutator.py

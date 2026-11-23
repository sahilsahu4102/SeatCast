# Unix shortcut. On Windows run: python -m seatcast.run <step>
all day0 ingest match flows load checks gps note serve:
	python -m seatcast.run $@
test:
	python -m pytest -q
.PHONY: all day0 ingest match flows load checks gps note serve test

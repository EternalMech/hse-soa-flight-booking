PYTHON ?= python3
CODEGEN_PYTHON := .venv-codegen/bin/python

.PHONY: generate run stop

generate: .venv-codegen/.installed
	mkdir -p build/generated
	$(CODEGEN_PYTHON) -m grpc_tools.protoc \
		-I proto \
		--python_out=build/generated \
		--pyi_out=build/generated \
		--grpc_python_out=build/generated \
		proto/flight/v1/flight.proto

.venv-codegen/.installed: requirements-codegen.txt
	$(PYTHON) -m venv .venv-codegen
	$(CODEGEN_PYTHON) -m pip install -r requirements-codegen.txt
	touch $@

run:
	docker compose up --build -d --wait

stop:
	docker compose down

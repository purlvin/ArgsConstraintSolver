ROOT?=$(shell git rev-parse --show-toplevel)
include $(ROOT)/infra/common.mk

CONSTRAINTS_SOLVER = $(ROOT)/out/pub/constraints_solver.sv 
.PHONY: gen
gen: args_constraint_solver.py
	mkdir -p $(ROOT)/out/pub
	mkdir -p $(ROOT)/out/sim
	mkdir -p $(ROOT)/out/run
	python3 args_constraint_solver.py --yml=test.yml --out=$(CONSTRAINTS_SOLVER)
	$(foreach svh, $(wildcard *.svh), ln -sf ${CURDIR}/${svh} $(ROOT)/out/pub/${svh};)
	#printf "$(CONSTRAINTS_SOLVER) $(SUCCESS_STRING)\n" | $(PRETTY_2_COL)

.PHONY: clean
clean:
	rm -rf $(ROOT)/out


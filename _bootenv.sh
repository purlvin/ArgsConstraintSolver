#!/usr/bin/env bash

alias bootenv='export ROOT=`git rev-parse --show-toplevel`;'
alias run_test="$ROOT/src/hardware/tb_tensix/meta/run_test.py";

# Common
alias h="history"
alias g="gvim -p"
alias findex="find . -type f | grep $@"

# GO alias
alias go="cd $ROOT"; 
alias go_pub='cd ${ROOT}/out/pub'
alias go_sim='cd ${ROOT}/out/sim'
alias go_run='cd ${ROOT}/out/run/$1'


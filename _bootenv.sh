#!/usr/bin/env bash

alias bootenv='export ROOT=`git rev-parse --show-toplevel`;'
function run_test() { mv $ROOT/out $ROOT/out.old && mkdir $ROOT/out && python3 $ROOT/src/hardware/tb_tensix/meta/run_test.py $@ | tee $ROOT/out/run_test.log; }

# Common
alias h="history"
alias g="gvim -p"
alias findex="find . -type f | grep $@"

# GO alias
alias go="cd $ROOT"; 
alias go_test='cd ${ROOT}/src/hardware/tb_tensix/tests'
alias go_tb='cd ${ROOT}/src/t6ifc/vcs-core'
alias go_pub='cd ${ROOT}/out/pub'
alias go_sim='cd ${ROOT}/out/sim'
alias go_run='cd ${ROOT}/out/run/$1'


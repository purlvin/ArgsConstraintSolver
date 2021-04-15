#!/usr/bin/env python3
import os
import yaml
import re
import argparse
import random
import args_constraint_solver

def get_tests(yml):
    spec = {}
    # Load all .yml
    cfg = yaml.load(open(yml), Loader=yaml.FullLoader)
    for inc in cfg.get("testsuites", []):
        spec.update(yaml.load(open(inc), Loader=yaml.FullLoader))

    # Load constraint groups per test
    tests = {"groups": {}, "cases": {}}
    for test in spec:
        if re.search("^__.*_t$", test):
            continue
        test_hash = spec[test]
        def flatten_list(irregular_list):
            return [element for item in irregular_list for element in flatten_list(item)] if type(irregular_list) is list else [irregular_list]
        for constr_grp in flatten_list(test_hash["_constr_grps"]):
            k, v = [i.strip() for i in constr_grp.split("=")]
            cfg = [i.strip() for i in constr_grp.split("=")]
            (len(cfg) == 1) and cfg.append(1)
            if (test not in tests["cases"]): tests["cases"][test] = []
            if (int(cfg[1])>0): tests["cases"][test].append(cfg[0].replace('.', '_inst.'))
        for group in flatten_list(test_hash["_when"]):
            if group not in tests["groups"]: tests["groups"][group] = {}
            tests["groups"][group][test] = test_hash["_clones"] if ("_clones" in test_hash) else 1
    return tests



if __name__ == "__main__":
    # Construct the argument parser
    ap = argparse.ArgumentParser()
    ap.add_argument("test", nargs='?', help="Test name")
    ap.add_argument("-w", "--when", help="When groups nane", default="quick")
    ap.add_argument("-s", "--seed", help="Seed")
    args = vars(ap.parse_args())
    print("> Input Args ")
    for k,v in args.items():
        if (v): print("  {} : {}".format(k, v))
    
    #USAGE = "Wrong argument number!\n  USAGE:  {0} <TEST_CASE|WHEN> [SEED]".format(sys.argv[0])
    #raise ValueError(USAGE)
    
    # Seed
    if (args["seed"]): random.seed(args["seed"])
    
    # Test list
    test_list = {}
    yml       = "test.yml"
    tests     = get_tests(yml)
    if (args["test"]) :
        if args["test"] not in tests['cases']: raise ValueError("Invalid test name '{}'!".format(args["test"])) 
        val = args["test"]
        test_list[val] = val 
    else :
        if args["when"] not in tests['groups']: raise ValueError("Invalid when tag '{}'!".format(args["when"]))
        val = tests['groups'][args["when"]]
        for k,v in val.items():
            for i in range(v):
                test_list[k+"_"+str(i)] = k
    print("> Found tests: \n  " + str(sorted(test_list.keys())))
  
    # Gen constrints_solver.sv
    print('\nSTEP 1: Gen constrints_solver.sv')
    outdir = os.path.join(os.getcwd(), "out")
    os.makedirs(outdir, exist_ok=True)
    sv = os.path.join(outdir, "constraints_solver.sv")
    args_constraint_solver.GenConstrintsSolver(sv)
    
    # VCS build
    print('\nSTEP 2: VCS compile')
    cmd = "vcs {} tb.sv -sverilog -o {}/args_constraint_simv -l {}/args_constraint_simv_comp.log".format(sv, outdir, outdir)
    print(cmd)
    ret = os.system(cmd)
    
#    owd = os.getcwd()
#    os.chdir(rundir)
#    print('\nSTEP 2: VCS run')
#    cmd = "{}/args_constraint_simv +ntb_random_seed={} +test={}".format(outdir, seed, test)
#    print(cmd)
#    ret = os.system(cmd)
#    os.chdir(owd)
    
    # VCS run
    for rundir,test in sorted(test_list.items()):
        print('STEP 3: VCS run test: {}'.format(rundir))
        seed = random.getrandbits(32)
        rundir = os.path.join(outdir, rundir)
        os.makedirs(rundir, exist_ok=True)
        os.chdir(rundir)
        cmd = "{}/args_constraint_simv +ntb_random_seed={} +test={}".format(outdir, seed, test)
        ret = os.system(cmd)



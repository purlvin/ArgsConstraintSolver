#!/usr/bin/env python3
import os
import yaml
import re
import argparse
import random
import args_constraint_solver

def get_test_list(yml, tgt_test, tgt_group):
    spec      = {}
    test_list = {}
    # Load all .yml
    cfg = yaml.load(open(yml), Loader=yaml.FullLoader)
    for inc in cfg.get("testsuites", []):
        inc = os.path.join(os.path.dirname(yml),inc)
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
    
    # Generate test list 
    if (tgt_test) :
        if tgt_test not in tests['cases']: raise ValueError("Invalid tgt_test name '{}'!".format(tgt_test)) 
        val = tgt_test
        test_list[val] = val 
    else :
        if tgt_group not in tests['groups']: raise ValueError("Invalid when tag '{}'!".format(tgt_group))
        val = tests['groups'][tgt_group]
        for k,v in val.items():
            for i in range(v):
                test_list[k+"_"+str(i)] = k
   
    return test_list

# Hierarchy:
#   ROOT
#     -> out
#         -> pub
#           -> constraints_solver.sv
#           -> test_generator.so?
#         -> sim
#           -> design.f
#         -> run
#           -> <TEST_x>
#             -> ttx_args.cfg

if __name__ == "__main__":
    root    = os.getcwd()
    testdir = os.path.join(root,   ".")
    outdir  = os.path.join(root,   "out")
    pubdir  = os.path.join(outdir, "pub")
    simdir  = os.path.join(outdir, "sim")
    rundir  = os.path.join(outdir, "run")
    os.makedirs(pubdir, exist_ok=True)
    os.makedirs(simdir, exist_ok=True)
    os.makedirs(rundir, exist_ok=True)
    
    # Construct the argument parser
    ap = argparse.ArgumentParser()
    ap.add_argument("test", nargs='?', help="Test name")
    ap.add_argument("-w", "--when", help="When groups nane", default="quick")
    ap.add_argument("-s", "--seed", help="Seed")
    args = vars(ap.parse_args())
    print("> Input Args ")
    for k,v in args.items():
        if (v): print("  {} : {}".format(k, v))
    
    # Seed
    seed = random.getrandbits(32) if (not args["seed"]) else args["seed"]
    random.seed(args["seed"])
    print("> Seed: " + str(seed))
    
    # Test list
    yml       = os.path.join(testdir, "test.yml")
    test_list = get_test_list(yml, args["test"], args["when"])
    print("> Found tests: \n  " + str(sorted(test_list.keys())))
  
    # STEP 1: Source publish
    os.chdir(pubdir)
    print('\n>> STEP 1: Source publish')
    sv = os.path.join(pubdir, "constraints_solver.sv")
    print('     -> Gen {}'.format(sv))
    args_constraint_solver.GenConstrintsSolver(yml, sv)
    
    # STEP 2: VCS build
    os.chdir(simdir)
    print('\n>> STEP 2: VCS compile')
    cmd = "vcs {} {}/tb.sv -sverilog -o simv -l vcs_compile.log".format(sv, testdir)
    print(cmd)
    ret = os.system(cmd)
    
    # STEP 3: VCS run
    count = 0
    for inst,test in sorted(test_list.items()):
        print('\n>> STEP 3[{}]: VCS run test - {}'.format(count, inst))
        seed = random.getrandbits(32)
        test_rundir = os.path.join(rundir, inst)
        os.makedirs(test_rundir, exist_ok=True)
        os.chdir(test_rundir)
        cmd = "{}/simv +ntb_random_seed={} +test={}".format(simdir, seed, test)
        ret = os.system(cmd)
        count += 1


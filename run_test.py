#!/usr/bin/env python3
import glob, shutil, os
import yaml
import re
import argparse
import random
import args_constraint_solver

# -------------------------------
# Path variables
root    = os.environ.get("ROOT")
metadir = os.path.join(root,   "src/hardware/tb_tensix/meta")
testdir = os.path.join(root,   "src/hardware/tb_tensix/tests")
tbdir   = os.path.join(root,   "src/t6ifc/vcs-core")
outdir  = os.path.join(root,   "out")
pubdir  = os.path.join(outdir, "pub")
simdir  = os.path.join(outdir, "sim")
rundir  = os.path.join(outdir, "run")

# -------------------------------
def get_test_list(yml, tgt_test, tgt_group):
    spec      = {}
    test_list = {}
    # Load all .yml
    #FIXME: cfg = yaml.load(open(yml), Loader=yaml.FullLoader)
    cfg = yaml.safe_load(open(yml))
    for inc in cfg.get("testsuites", []):
        inc = os.path.join(os.path.dirname(yml),inc)
        #FIXME: spec.update(yaml.load(open(inc), Loader=yaml.FullLoader))
        spec.update(yaml.safe_load(open(inc)))

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

# -------------------------------
def  env_cleanup():
    outdir = "{0}/out".format(root)
    if os.path.exists(outdir): shutil.rmtree(outdir)
    outdir = "{0}/out".format(testdir)
    if os.path.exists(outdir): shutil.rmtree(outdir)
    outdir = "{0}/tvm_tb/out".format(tbdir)
    if os.path.exists(outdir): shutil.rmtree(outdir)
    os.makedirs(pubdir, exist_ok=True)
    os.makedirs(simdir, exist_ok=True)
    os.makedirs(rundir, exist_ok=True)

    
# -------------------------------
def ln_sf(src, dst):
    if os.path.exists(dst): os.remove(dst)
    #os.symlink(src, dst)
    os.system("ln -f {} {}".format(src, dst))
def source_publish():
    os.chdir(pubdir)
    # Gen constraints_solver.sv
    sv = os.path.join(pubdir, "constraints_solver.sv")
    print('     -> Gen {}'.format(sv))
    args_constraint_solver.GenConstrintsSolver(yml, sv)
    # Soft-link metadir
    print('     -> Publish source files')
    for type in ('*.sv', '*.svh'):
        for file in glob.glob(os.path.join(metadir,type)):
            ln_sf(file, os.path.basename(file))
    # Prebuild libraries
    print('     -> Prebuild libraries (tvm_tb.so)')
    cmd = " make -C {}/tvm_tb -j8 SIM=vcs &> publish.log".format(tbdir)
    print(cmd)
    ret = os.system(cmd)

# -------------------------------
def vsc_compile():
    os.chdir(tbdir)
    sv = os.path.join(pubdir, "constraints_solver.sv")
    #cmd = "./vcs-docker -fsdb -kdb -lca +vcs+lic+wait +define+ECC_ENABLE -xprop=tmerge +define+MAILBOX_TARGET=6 {}/tvm_tb/out/tvm_tb.so -f vcs.f  +incdir+{} {} +define+NOVEL_ARGS_CONSTRAINT_TB -sverilog -full64 -l vcs_compile.log -timescale=1ns/1ps -error=PCWM-W +lint=TFIPC-L -o {}/simv -assert disable_cover -CFLAGS -LDFLAGS -lboost_system -L{}/vendor/yaml-cpp/build -lyaml-cpp -lsqlite3 -lz -debug_acc+dmptf -debug_region+cell+encrypt -debug_access &> vcs_compile.log".format(tbdir, pubdir, sv, simdir, root)
    cmd = "vcs +incdir+{0} {1} {2}/tb.sv -sverilog -o {3}/simv -l vcs_compile.log".format(pubdir, sv, testdir, simdir)
    print(cmd)
    ret = os.system(cmd)

# -------------------------------
def vsc_run(test_list):
    count = 0
    for inst,test in sorted(test_list.items()):
        print('   -> [{}]: VCS run test - {}'.format(count, inst))
        seed = random.getrandbits(32)
        test_rundir = os.path.join(rundir, inst)
        os.makedirs(test_rundir, exist_ok=True)
        os.chdir(test_rundir)
        #cmd = "{}/simv +testdef={}/{}/core.ttx +tvm_verbo=high '+event_db=1 +data_reg_mon_enable=1' +ntb_random_seed={} +test={} &> vcs_run.log".format(simdir, rundir, test, seed, test)
        cmd = "{}/simv +ntb_random_seed={} +test={}".format(simdir, seed, test)
        print(cmd)
        ret = os.system(cmd)
        count += 1


# -------------------------------
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
#
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
    
    # Seed
    seed = random.getrandbits(32) if (not args["seed"]) else args["seed"]
    random.seed(args["seed"])
    print("> Seed: " + str(seed))
    
    # Test list
    yml       = os.path.join(metadir, "test.yml")
    test_list = get_test_list(yml, args["test"], args["when"])
    print("> Found tests: \n  " + str(sorted(test_list.keys())))
  
    # STEP 0: Env cleanup
    print('\n>> STEP 0: Env cleanup')
    env_cleanup()

    # STEP 1: Source publish
    print('\n>> STEP 1: Source publish')
    source_publish()

    # STEP 2: VCS compile
    print('\n>> STEP 2: VCS compile')
    vsc_compile()
    
    # STEP 3: VCS run
    print('\n>> STEP 3: VCS run')
    vsc_run(test_list)

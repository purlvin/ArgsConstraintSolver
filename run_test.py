#!/usr/bin/env python3
import glob, shutil, os
from multiprocessing import Process
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
    spec = yaml.load(open(yml), Loader=yaml.SafeLoader)
    # Load constraint groups per test
    tests = {"groups": {}, "cases": {}, "ttx": {}}
    for test in spec:
        if re.search("^__.*_t$", test):
            continue
        test_hash = spec[test]
        tests["ttx"][test] = test_hash["_ttx"] 
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
    
    test_list = {}
    # Generate test list 
    if (tgt_test) :
        if tgt_test not in tests['ttx'].keys(): raise ValueError("Invalid test name '{}'!".format(tgt_test)) 
        test_list[tgt_test] = tests['ttx'][tgt_test] 
    else :
        if tgt_group not in tests['groups']: raise ValueError("Invalid when tag '{}'!".format(tgt_group))
        val = tests['groups'][tgt_group]
        for k,v in val.items():
            for i in range(v):
                test_list[k+"_"+str(i)] = tests['ttx'][k]
   
    return test_list

# -------------------------------
def env_cleanup():
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
def source_publish(test_list):
    os.chdir(pubdir)
    
    cmd = '''\
export ROOT={0}
echo -e "-- STAGE build_tools --"
cd $ROOT/ && make -j 64
cd $ROOT/src/software/assembler && make -j 64
cd $ROOT/src/software/command_assembler && make -j 64
cd $ROOT/src/test_ckernels/ckti && make -j 64
cd $ROOT/src/test_ckernels/gen && make -j 64
cd $ROOT/src/test_ckernels/src && make -j 64
cd $ROOT/src/t6ifc/vcs-core/tvm_tb && make SIM=vcs -j 64
echo -e "-- STAGE build_firmware --"
cd $ROOT/ && make -j 64 -f src/hardware/tb_tensix/tests/firmware.mk TENSIX_GRID_SIZE_X=1 TENSIX_GRID_SIZE_Y=1 OUTPUT_DIR=$ROOT/out/pub/fw/GRID-1x1
echo -e "-- STAGE build_test_generator --"
'''.format(root)
    for ttx in list(set(test_list.values())):
    	cmd += "cd $ROOT/src/hardware/tb_tensix/tests && make -j 64 OUTPUT_DIR=$ROOT/out/pub/ttx/{ttx} TEST={ttx} generator firmware".format(ttx=ttx)
    sh = os.path.join(pubdir, "tb_build.sh")
    f = open(sh, "w")
    f.write(cmd)
    f.close()
    print('     -> Building testbench : {0}'.format(sh), flush=True)
    cmd = "   source {0} &> {1}/publish.log ".format(sh, pubdir)
    print(cmd, flush=True)
    ret = os.system(cmd)


    ## Soft-link metadir
    #print('     -> Publish source files', flush=True)
    #for type in ('*.sv', '*.svh'):
    #    for file in glob.glob(os.path.join(metadir,type)):
    #        ln_sf(file, os.path.basename(file))
    # Prebuild libraries
    #print('     -> Prebuild libraries (tvm_tb.so)', flush=True)
    ##cmd = " make -C {0}/tvm_tb -j8 SIM=vcs &> publish.log; make -j8 -C {1} TEST_OUT=conv_basic TEST=single-core-conv GENARGS='--inline_halo --conv=3x3s1 --filters=16' compile_test &>> publish.log".format(tbdir, testdir)
    #cmd = " make -C {0}/tvm_tb -j8 SIM=vcs &> publish.log; ".format(tbdir, testdir)
    #print(cmd)
    #ret = os.system(cmd)


# -------------------------------
def vsc_compile():
    os.chdir(tbdir)
    sv = os.path.join(pubdir, "constraints_solver.sv")
    cmd = "./vcs-docker -fsdb -kdb -lca +vcs+lic+wait +define+ECC_ENABLE -xprop=tmerge +define+MAILBOX_TARGET=6 {0}/tvm_tb/out/tvm_tb.so -f vcs.f  +incdir+{1} {2} +define+NOVEL_ARGS_CONSTRAINT_TB -sverilog -full64 -l vcs_compile.log -timescale=1ns/1ps -error=PCWM-W +lint=TFIPC-L -o {3}/simv -assert disable_cover -CFLAGS -LDFLAGS -lboost_system -L{4}/vendor/yaml-cpp/build -lyaml-cpp -lsqlite3 -lz -debug_acc+dmptf -debug_region+cell+encrypt -debug_access &> {3}/vcs_compile.log".format(tbdir, pubdir, sv, simdir, root)
    print(cmd)
    ret = os.system(cmd)

# -------------------------------
def testRunInParallel(id, test, ttx):
    print('   -> [{}]: VCS run test - {}'.format(id, test))
    seed = random.getrandbits(32)
    test_rundir = os.path.join(rundir, test)
    os.makedirs(test_rundir, exist_ok=True)
    os.chdir(test_rundir)
    cmd = "{0}/simv +testdef={1}/{2}/{4}.ttx +tvm_verbo=high '+event_db=1 +data_reg_mon_enable=1' +ntb_random_seed={3} +test={2} &> {1}/vcs_run.log".format(simdir, rundir, test, seed, ttx)
    print(cmd)
    ret = os.system(cmd)
def vsc_run(test_list):
    id = 0
    proc = []
    for test,ttx in sorted(test_list.items()):
        p = Process(target=testRunInParallel, args=(id, test, ttx))
        p.start()
        proc.append(p)
        id += 1
    for p in proc:
        p.join()


# -------------------------------


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
    print(" (Seed: " + str(seed) + ")")
    
    # STEP 0: Env cleanup
    print('\n>> STEP 0: Env cleanup', flush=True)
    env_cleanup()
    # STEP 0+: Test list
    cmd = " cd {0} && make gen".format(metadir)
    #print(cmd)
    ret = os.system(cmd)
    yml       = os.path.join(pubdir, "test_expanded.yml")
    test_list = get_test_list(yml, args["test"], args["when"])
    print("> Found tests: \n  " + str(sorted(test_list.keys())))

    # STEP 1: Source publish
    print('\n>> STEP 1: Source publish', flush=True)
    source_publish(test_list)
    
    # STEP 2: VCS compile
    print('\n>> STEP 2: VCS compile', flush=True)
    vsc_compile()
    
    # STEP 3: VCS run
    print('\n>> STEP 3: VCS run', flush=True)
    vsc_run(test_list)

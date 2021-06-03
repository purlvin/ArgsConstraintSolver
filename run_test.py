#!/usr/bin/env python3
import glob, shutil, os, sys, signal
from multiprocessing import Process
import yaml
import re
import argparse
import random
import time
import logging;
from datetime import datetime

# -------------------------------
# Path variables
root        = os.environ.get("ROOT")
metadir     = os.path.join(root,    "src/hardware/tb_tensix/meta")
testdir     = os.path.join(root,    "src/hardware/tb_tensix/tests")
tbdir       = os.path.join(root,    "src/t6ifc/vcs-core")
outdir      = os.path.join(root,    "out")
pubdir      = os.path.join(outdir,  "pub")
simdir      = os.path.join(outdir,  "sim")
rundir      = os.path.join(outdir,  "run")
start_time  = time.time()
logger      = logging.getLogger()
log         = os.path.join(outdir,  "run_test.log")
proc        = []


# -------------------------------
class Colors:
    """ ANSI color codes """
    BLACK           = "\033[0;30m"
    RED             = "\033[0;31m"
    GREEN           = "\033[0;32m"
    BROWN           = "\033[0;33m"
    BLUE            = "\033[0;34m"
    PURPLE          = "\033[0;35m"
    CYAN            = "\033[0;36m"
    LIGHT_GRAY      = "\033[0;37m"
    DARK_GRAY       = "\033[1;30m"
    LIGHT_RED       = "\033[1;31m"
    LIGHT_GREEN     = "\033[1;32m"
    YELLOW          = "\033[1;33m"
    LIGHT_BLUE      = "\033[1;34m"
    LIGHT_PURPLE    = "\033[1;35m"
    LIGHT_CYAN      = "\033[1;36m"
    LIGHT_WHITE     = "\033[1;37m"
    BOLD            = "\033[1m"
    FAINT           = "\033[2m"
    ITALIC          = "\033[3m"
    UNDERLINE       = "\033[4m"
    BLINK           = "\033[5m"
    NEGATIVE        = "\033[7m"
    CROSSED         = "\033[9m"
    END             = "\033[0m"
class ColorFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""
    formatter = "[%(relativeCreated)8.2f] %(levelname)s - %(message)s".format(time.time()-start_time)
    FORMATS = {
        logging.DEBUG:      "", 
        logging.INFO:       Colors.BLUE + formatter + Colors.END,
        logging.WARNING:    Colors.YELLOW + formatter + Colors.END,
        logging.ERROR:      Colors.LIGHT_RED + formatter + Colors.END,
        logging.CRITICAL:   Colors.RED + formatter + Colors.END,
    }
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        record.relativeCreated /= 1000
        return formatter.format(record)

# -------------------------------
def get_test_list(yml, tgt_test, tgt_group):
    spec = yaml.load(open(yml), Loader=yaml.SafeLoader)
    # Load constraint groups per test
    tests = {"groups": {}, "ttx": {}, "args": {}}
    for test,test_hash in spec["testcases"].items():
        def flatten_list(irregular_list):
            return [element for item in irregular_list for element in flatten_list(item)] if type(irregular_list) is list else [irregular_list]
        tests["ttx"][test]  = test_hash["_ttx"]
        tests["args"][test] = " ".join(flatten_list(test_hash["_args"]))
        for group in flatten_list(test_hash["_when"]):
            if group not in tests["groups"]: tests["groups"][group] = {}
            tests["groups"][group][test] = test_hash["_clones"] if ("_clones" in test_hash) else 1
    
    test_list = {"base": {}, "ttx": {}, "args": {}}
    # Generate test list 
    if (tgt_test) :
        if tgt_test not in tests['ttx'].keys(): 
          logger.error("Invalid test name '{}'!".format(tgt_test)) 
          raise "Die run_test.py!"
        test_list["base"][tgt_test] = tgt_test
        test_list["ttx"][tgt_test]  = tests['ttx'][tgt_test]
        test_list["args"][tgt_test] = tests['args'][tgt_test]
    else :
        if tgt_group not in tests['groups']: 
          logger.error("Invalid when tag '{}'!".format(tgt_group))
          raise "Die run_test.py!"
        val = tests['groups'][tgt_group]
        for k,v in val.items():
            for i in range(v):
                test_list["base"][k+"_"+str(i)] = k
                test_list["ttx"][k+"_"+str(i)]  = tests['ttx'][k]
                test_list["args"][k+"_"+str(i)] = tests['args'][k]
    return test_list

# -------------------------------
def env_cleanup():
    outdir = "{0}/out".format(root)
    for d in ['pub', 'sim', 'run']:
        dir =  os.path.join(outdir, d)
        if os.path.exists(dir): shutil.rmtree(dir)
        os.makedirs(dir, exist_ok=True)
    outdir = "{0}/out".format(testdir)
    if os.path.exists(outdir): shutil.rmtree(outdir)
    outdir = "{0}/tvm_tb/out".format(tbdir)
    if os.path.exists(outdir): shutil.rmtree(outdir)

# -------------------------------
def source_publish(test_list):
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
cd $ROOT/ && make -j 64 -f src/hardware/tb_tensix/tests/firmware.mk TENSIX_GRID_SIZE_X=1 TENSIX_GRID_SIZE_Y=1 OUTPUT_DIR=$ROOT/out/pub/fw
echo -e "-- STAGE build_test_generator --"
'''.format(root)
    for ttx in list(set(test_list["ttx"].values())):
    	cmd += "cd $ROOT/src/hardware/tb_tensix/tests && make -j 64 OUTPUT_DIR=$ROOT/out/pub/ttx/{ttx} TEST={ttx} generator firmware\n".format(ttx=ttx)
    sh = os.path.join(pubdir, "tb_build.sh")
    f = open(sh, "w")
    f.write(cmd)
    f.close()
    logger.debug('  -> Building testbench : {0}'.format(sh))
    cmd = "  source {0} &> {1}/publish.log ".format(sh, pubdir)
    logger.debug(cmd)
    ret = os.system(cmd)
    if ret != 0: 
      logger.error("Source publish failed! \n  CMD: {0}".format(cmd)) 
      raise "Die run_test.py!"

# -------------------------------
def vsc_compile():
    sv = os.path.join(pubdir, "constraints_solver.sv")
    cmd = "  cd {0}; ./vcs-docker -fsdb -kdb -lca +vcs+lic+wait +define+ECC_ENABLE -xprop=tmerge +define+MAILBOX_TARGET=6 {0}/tvm_tb/out/tvm_tb.so -f vcs.f  +incdir+{1} {2} +define+NOVEL_ARGS_CONSTRAINT_TB -sverilog -full64 -l vcs_compile.log -timescale=1ns/1ps -error=PCWM-W +lint=TFIPC-L -o {3}/simv -assert disable_cover -CFLAGS -LDFLAGS -lboost_system -L{4}/vendor/yaml-cpp/build -lyaml-cpp -lsqlite3 -lz -debug_acc+dmptf -debug_region+cell+encrypt -debug_access &> {3}/vcs_compile.log".format(tbdir, pubdir, sv, simdir, root)
    #logger.debug(cmd)
    ret = os.system(cmd)
    if ret != 0:
      logger.error("VCS compile failed! \n  CMD: {0}".format(cmd)) 
      raise "Die run_test.py!"

# -------------------------------
def testRunInParallel(id, test, base, ttx, args):
    logger.info('  -> [{}]: {}'.format(id, test))
    seed = random.getrandbits(32)
    test_rundir = os.path.join(rundir, test)
    os.makedirs(test_rundir, exist_ok=True)
    cmd = "  cd {0}; {1}/simv +testdef={0}/{4}.ttx +tvm_verbo=high '+event_db=1 +data_reg_mon_enable=1' +ntb_random_seed={3} +test={2} {5}&> {0}/vcs_run.log".format(test_rundir, simdir, base, seed, ttx, args)
    logger.debug(cmd)
    ret = os.system(cmd)
def vsc_run(test_list, args):
    id = 0
    for test,ttx in sorted(test_list["ttx"].items()):
        if (args["dump"]):  test_list["args"][test] += " --vcdfile=waveform.vcd"
        if (args["debug"]): test_list["args"][test] += " +event_db=1 +data_reg_mon_enable=1 +tvm_verbo=high"
        p = Process(target=testRunInParallel, args=(id, test, test_list["base"][test], ttx, test_list["args"][test]))
        p.start()
        proc.append(p)
        id += 1
    for p in proc:
        p.join()

# -------------------------------
def result_report(test_list):
    results = {}
    id = 0
    for test in sorted(test_list["ttx"].keys()):
        results[test] = Colors.RED + "FAIL" + Colors.END
        run_log = os.path.join(rundir, test, "vcs_run.log")
        if ("<TEST-PASSED>" in open(run_log).read()): results[test] =  Colors.GREEN + "PASS" + Colors.END
        logger.debug("  {0:-3} - {1:30}: {2} {3}".format(id, test, results[test], "" if "PASS" in results[test] else "(run_log: {0})".format(run_log))) 
        id += 1

# -------------------------------
def signal_handler(sig, frame):
    for p in proc: p.terminate()
def main():
    os.makedirs(outdir, exist_ok=True)
    if os.path.exists(log): shutil.move(log, log+".old")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log, mode="w", encoding=None, delay=False)
    ch = logging.StreamHandler()
    fh.setFormatter(logging.Formatter(ColorFormatter.formatter))
    ch.setFormatter(ColorFormatter())
    logger.addHandler(fh)
    logger.addHandler(ch)

    # Construct the argument parser
    ap = argparse.ArgumentParser()
    ap.add_argument("test", nargs='?', help="Test name")
    ap.add_argument("-w", "--when", help="When groups nane")
    ap.add_argument("-s", "--seed", help="Seed")
    ap.add_argument("-clean", "--clean",  action="store_true", help="Remove out directories")
    ap.add_argument("-dbg", "--debug", action="store_true", help="Simplify TTX data")
    ap.add_argument("-dp", "--dump", action="store_true", help="Dump FSDB waveform")
    ap.add_argument("-jsb", "--j_sim_build", action="store_true", help="Jump to sim build")
    ap.add_argument("-jsr", "--j_sim_run", action="store_true", help="Jump to sim run")
    args = vars(ap.parse_args())
    if not (args["test"] or args["when"]): args["when"] = "sanity"
    logger.debug(" <Input Args>: " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))
    for k,v in args.items():
        if (v): logger.debug("  {} : {}".format(k, v))
    if args["j_sim_run"] : args["j_sim_build"] = True

    # Seed
    seed = random.getrandbits(32) if (not args["seed"]) else args["seed"]
    random.seed(args["seed"])
    logger.debug(" (Seed: " + str(seed) + ")")
   
    # STEP 0: Env cleanup
    if (not args["j_sim_build"]):
      logger.info(' STEP 0: Env cleanup')
      if (args["clean"]):
        env_cleanup()
    # STEP 0+: Test list
    cmd = " cd {0} && make gen DEBUG={1}".format(metadir, int(args["debug"]))
    #logger.info(cmd)
    ret = os.system(cmd)
    yml       = os.path.join(pubdir, "test_expanded.yml")
    test_list = get_test_list(yml, args["test"], args["when"])
    logger.info(" Found tests: " + str(sorted(test_list["ttx"].keys())))

    # STEP 1: Source publish
    if (not args["j_sim_build"]):
      logger.info(' STEP 1: Source publish')
      source_publish(test_list)
    
    # STEP 2: VCS compile
    if (not args["j_sim_run"]):
      logger.info(' STEP 2: VCS compile')
      vsc_compile()
   
    # STEP 3: VCS run
    logger.info(' STEP 3: VCS run')
    signal.signal(signal.SIGINT, signal_handler)
    vsc_run(test_list, args)

    # STEP 4: Result report
    logger.info(' STEP 4: Result report')
    result_report(test_list)


if __name__ == "__main__":
    main()


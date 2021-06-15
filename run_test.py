#!/usr/bin/env python3
import glob, shutil, psutil, os, sys, signal
from multiprocessing import Process
import subprocess
import yaml
import re
import argparse
import random
import time
import logging;
from enum import Enum   
from pprint import pprint
from datetime import datetime
from lib_email  import send_email

# -------------------------------
# Path variables
root        = os.environ.get("ROOT")
metadir     = os.path.join(root,    "src/hardware/tb_tensix/meta")
testdir     = os.path.join(root,    "src/hardware/tb_tensix/tests")
tbdir       = os.path.join(root,    "src/t6ifc/vcs-core")
outdir      = os.path.join(root,    "out")
pubdir      = os.path.join(outdir,  "pub")
simdir      = os.path.join(outdir,  "sim")
simdir_stg1 = os.path.join(simdir,  "stg1")
rundir      = os.path.join(outdir,  "run")
logger      = logging.getLogger()
log         = os.path.join(outdir,  "run_test.log")


# -------------------------------
class Meta:
    STG      = Enum('STG', 'PREBUILD SIM_BUILD_1 SIM_BUILD_2 SIM_RUN')
    TEST_STG = Enum('TEST_STG', 'VCS_RUN_1 TTX_GEN CKTI VCS_RUN_2')
    
    proc        = []
    start_time  = time.time()
    stages      = {} # {test: {current: "", stages: [{stage: "", status: ""}]}}
    test_stages = {} # {test: {current: "", stages: [{stage: "", status: ""}]}}
    def __init__(self, test_spec):
        self.id = random.getrandbits(32)
        self.stages            = {"current": "OVERALL", "stages": [{"stage": "OVERALL", "status": "FAIL", "duration": "N/A", "log": os.path.join(outdir,  "run_test.log")}]}
        self.stages["stages"] += [{"stage": stage.name, "status": "N/A", "duration": "N/A"} for stage in self.STG]
        for test,spec in sorted(test_spec.items()): 
            self.test_stages[test]            = {"current": "N/A", "stages": [{"stage": "OVERALL", "status": "FAIL", "suite": spec["suite"], "duration": "N/A", "log": os.path.join(rundir, test, "test_run.log")}]} 
            self.test_stages[test]["stages"] += [{"stage": stage.name, "status": "N/A", "duration": "N/A"} for stage in self.TEST_STG]
    def id(self):
        return self.id
    def cmdline(self):
        process = psutil.Process(os.getpid())
        cmdline = process.cmdline()
        return " ".join(cmdline)
    def run_subprocess(self, cmd):
        ret = {}
        p = subprocess.Popen(cmd, shell=True)
        self.proc.append(p.pid)
        ret["stdout"], ret["stderr"] = p.communicate()
        ret["returncode"] = p.returncode
        print(cmd, ret, self.proc)
        return ret
    def start_stage(self, stage, log):
        self.stages["current"] = stage
        i = self.update_status("RUNNING")
        self.stages["stages"][i]["log"] = log
    def update_status(self, status):
        i = [self.stages["stages"].index(stage) for stage in self.stages["stages"] if stage['stage'] == self.stages["current"]][0]
        self.stages["stages"][i]["status"]   = status
        self.stages["stages"][i]["duration"] = time.strftime('%H:%M:%S', time.gmtime(time.time()-self.start_time))
        if (status == "FAIL"): 
            self.stages["stages"][0]["status"]   = status
            self.stages["stages"][0]["duration"] = self.stages["stages"][i]["duration"]
        return i
    def stage_status(self, stage):
        status = [s["status"] for s in self.stages["stages"] if s["stage"] == stage][0]
        return status
    def start_test_stage(self, test, stage, log):
        self.test_stages[test]["current"] = stage
        i = self.update_test_status(test, "RUNNING")
        self.test_stages[test]["stages"][i]["log"] = log
    def update_test_status(self, test, status):
        if (test not in self.test_stages): raise ValueError("FAIL to find {_test} in meta({_list})".format(_test=test, _list=self.test_stages.keys()))
        i = [self.test_stages[test]["stages"].index(stage) for stage in self.test_stages[test]["stages"] if stage['stage'] == self.test_stages[test]["current"]][0]
        self.test_stages[test]["stages"][i]["status"]   = status
        self.test_stages[test]["stages"][i]["duration"] = time.strftime('%H:%M:%S', time.gmtime(time.time()-self.start_time))
        if (status == "FAIL"): 
            self.test_stages[test]["stages"][0]["status"] = status
            self.test_stages[test]["stages"][0]["status"] = self.test_stages[test]["stages"][i]["duration"]
        return i
    def test_stage_status(self, test, stage):
        if (test not in self.test_stages): raise ValueError("FAIL to find {_test} in meta({_list})".format(_test=test, _list=self.test_stages.keys()))
        status = [s["status"] for s in self.test_stages[test]["stages"] if s['stage'] == stage][0]
        return status



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
    formatter = "[%(relativeCreated)8.2f] %(levelname)s - %(message)s".format(time.time()-Meta.start_time)
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
def get_test_spec(yml, tgt_test, tgt_group):
    spec = yaml.load(open(yml), Loader=yaml.SafeLoader)
    # Load constraint groups per test
    test_spec = {}
    for test,test_hash in spec["testcases"].items():
        def flatten_list(irregular_list):
            return [element for item in irregular_list for element in flatten_list(item)] if type(irregular_list) is list else [irregular_list]
        info = {
            "base":     test,
            "suite":    test_hash["_suite"],
            "ttx":      test_hash["_ttx"],
            "args":     flatten_list(test_hash["_args"]),
        }
        if ((tgt_test) and (tgt_test.split("__")[0] == test)):
            test_spec[tgt_test] = info
        elif (tgt_group in flatten_list(test_hash["_when"])):
            test_spec[test] = info
            for i in range(test_hash["_clones"]): test_spec["{}__{}".format(test,i+1)] = info
    return test_spec

# -------------------------------
def env_cleanup():
    outdir = "{0}/out".format(root)
    for dir in [pubdir, simdir, simdir_stg1, rundir]:
        if os.path.exists(dir): shutil.rmtree(dir)
        os.makedirs(dir, exist_ok=True)
    outdir = "{0}/out".format(testdir)
    if os.path.exists(outdir): shutil.rmtree(outdir)
    outdir = "{0}/tvm_tb/out".format(tbdir)
    if os.path.exists(outdir): shutil.rmtree(outdir)

# -------------------------------
def prebuild(test_spec):
    log = "{_pubdir}/prebuild.log".format(_pubdir=pubdir) 
    meta.start_stage(meta.STG.PREBUILD.name, log)
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
    for ttx in list(set([spec["ttx"] for test,spec in test_spec.items()])):
    	cmd += "cd $ROOT/src/hardware/tb_tensix/tests && make -j 64 OUTPUT_DIR=$ROOT/out/pub/ttx/{ttx} TEST={ttx} generator firmware\n".format(ttx=ttx)
    sh = os.path.join(pubdir, "tb_build.sh")
    f = open(sh, "w")
    f.write(cmd)
    f.close()
    logger.debug('  -> Building testbench : {0}'.format(sh))
    cmd = "  source {0} &> {1} ".format(sh, log)
    logger.debug(cmd)
    ret = meta.run_subprocess(cmd)["returncode"]
    if ret != 0: 
      logger.error("Prebuild failed! \n  CMD: {0}".format(cmd)) 
      meta.update_status("FAIL")
      raise Exception("Die run_test.py!")
    meta.update_status("PASS")

# -------------------------------
def vsc_compile():
    for dir in [simdir, simdir_stg1]:
      os.makedirs(dir, exist_ok=True)
    # Stage 1 VCS compile
    log = "{_simdir_stg1}/vcs_compile.log".format(_simdir_stg1=simdir_stg1) 
    meta.start_stage(meta.STG.SIM_BUILD_1.name, log)
    logger.info('   --> Stage 1 VCS compile')
    sv = os.path.join(pubdir, "constraints_solver.sv")
    cmd = "  cd {0}; {1}/vcs-docker -fsdb -kdb -lca +vcs+lic+wait +incdir+{2} {3} -sverilog -full64 -o {0}/simv &> {4}".format(simdir_stg1, tbdir, pubdir, sv, log)
    ret = meta.run_subprocess(cmd)["returncode"]
    if ret != 0:
      logger.error("Stage 1 VCS compile failed! \n  CMD: {0}".format(cmd)) 
      meta.update_status("FAIL")
      raise Exception("Die run_test.py!")
    meta.update_status("PASS")
    # Stage 2 VCS compile
    log = "{_simdir}/vcs_compile.log".format(_simdir=simdir) 
    meta.start_stage(meta.STG.SIM_BUILD_2.name, log)
    logger.info('   --> Stage 2 VCS compile')
    cmd = "  cd {0}; ./vcs-docker -fsdb -kdb -lca +vcs+lic+wait +define+ECC_ENABLE -xprop=tmerge +define+MAILBOX_TARGET=6 {0}/tvm_tb/out/tvm_tb.so -f vcs.f  +incdir+{1} +define+NOVEL_ARGS_CONSTRAINT_TB -sverilog -full64 -l vcs_compile.log -timescale=1ns/1ps -error=PCWM-W +lint=TFIPC-L -o {3}/simv -assert disable_cover -CFLAGS -LDFLAGS -lboost_system -L{4}/vendor/yaml-cpp/build -lyaml-cpp -lsqlite3 -lz -debug_acc+dmptf -debug_region+cell+encrypt -debug_access &> {5}".format(tbdir, pubdir, sv, simdir, root, log)
    ret = meta.run_subprocess(cmd)["returncode"]
    if ret != 0:
      logger.error("Stage 2 VCS compile failed! \n  CMD: {0}".format(cmd)) 
      meta.update_status("FAIL")
      raise Exception("Die run_test.py!")
    meta.update_status("PASS")

# -------------------------------
def testRunInParallel(id, test, seed, spec, args):
    (base, ttx, j_sim_run) = (spec["base"], spec["ttx"], args["j_sim_run"])
    cfg_args = {}
    cfg_hash = {}
    test_rundir = os.path.join(rundir, test)
    os.makedirs(test_rundir, exist_ok=True)
    run_log_file = open(os.path.join(rundir, test, "test_run.log"), "w")   

    # Stage 1 VCS run
    if (not j_sim_run):
      log = os.path.join(test_rundir, "stg1_vcs_run.log")
      meta.start_test_stage(test, meta.TEST_STG.VCS_RUN_1.name, log)
      msg = '   --> [{}: {}] Stage 1 VCS run(seed: {})'.format(id, test, seed)
      logger.info(msg)
      run_log_file.write(msg+"\n");
      cmd = "  cd {0}; {1}/simv +test={2} +ntb_random_seed={3} &> {4}".format(test_rundir, simdir_stg1, base, seed, log)
      ret  = meta.run_subprocess(cmd)["returncode"]
      ret |= 1 if ("Error" in open(log).read()) else 0
      if ret != 0:
        msg = " [{}]: {} : Stage 1 VCS run failed! \n  CMD: {}".format(id, test, cmd) 
        logger.error(msg) 
        meta.update_test_status(test, "FAIL")
        run_log_file.write(msg+"\n");
        run_log_file.close()
        raise Exception("Die run_test.py!")
      meta.update_test_status(test, "PASS")
    # Paring .cfg files
    for x in ["genargs", "plusargs"] :
        cfg = os.path.join(test_rundir, x + "_rnd.cfg")
        f = open(cfg, "r")
        cfg_args[x] = f.read().strip().split("\n")
        cfg_hash[x] = {}
    cfg_args["plusargs"] += args
    for k,v in cfg_args.items():
        k = k.split(".")[0]
        for x in v:
            a = x.split("=")
            cfg_hash[k][a[0]] = a[1] if len(a)>1 else None
        cfg_args[k] = ""
        for kk,vv in cfg_hash[k].items():
            cfg_args[k] += " {}={}".format(kk,vv) if vv != None else " {}".format(kk)
    # TTX generation
    log = os.path.join(test_rundir, "ttx_gen.log")
    meta.start_test_stage(test, meta.TEST_STG.TTX_GEN.name, log)
    msg = '   --> [{}: {}] TTX Generation'.format(id, test)
    logger.info(msg)
    run_log_file.write(msg+"\n");
    cmd = "  cd {0}; ln -sf {1}/fw . && {1}/ttx/{2}/{2} {3} &> {0}/ttx_gen.log".format(test_rundir, pubdir, ttx, cfg_args["genargs"], root)
    ret  = meta.run_subprocess(cmd)["returncode"]
    if ret != 0:
      msg = " [{}]: {} : TTX generation failed! \n  CMD: {}".format(id, test, cmd) 
      logger.error(msg) 
      meta.update_test_status(test, "FAIL")
      run_log_file.write(msg+"\n");
      run_log_file.close()
      raise Exception("Die run_test.py!")
    meta.update_test_status(test, "PASS")
    # CKTI
    log = os.path.join(test_rundir, "ckti.log")
    meta.start_test_stage(test, meta.TEST_STG.CKTI.name, log)
    msg = '   --> [{}: {}] CKTI'.format(id, test)
    logger.info(msg)
    run_log_file.write(msg+"\n");
    cmd = "  cd {4}/src/test_ckernels/ckti && out/ckti --dir={0} --test={2} &> {5}".format(test_rundir, pubdir, ttx, cfg_args["genargs"], root, log)
    ret  = meta.run_subprocess(cmd)["returncode"]
    if ret != 0:
      msg = " [{}]: {} : CKTI failed! \n  CMD: {}".format(id, test, cmd) 
      logger.error(msg) 
      meta.update_test_status(test, "FAIL")
      run_log_file.write(msg+"\n");
      run_log_file.close()
      raise Exception("Die run_test.py!")
    meta.update_test_status(test, "PASS")
    # Stage 2 VCS run
    log = os.path.join(test_rundir, "vcs_run.log")
    meta.start_test_stage(test, meta.TEST_STG.VCS_RUN_2.name, log)
    msg = '   --> [{}: {}] Stage 2 VCS run'.format(id, test)
    logger.info(msg)
    run_log_file.write(msg+"\n");
    vcs_run_log = os.path.join(test_rundir, "vcs_run.log")
    cmd  = "  cd {0}; {1}/simv +testdef={0}/{4}.ttx +tvm_verbo=none '+event_db=1 +data_reg_mon_enable=1' +ntb_random_seed={3} +test={2} {5} &> {6}".format(test_rundir, simdir, base, seed, ttx, cfg_args["plusargs"], log)
    ret  = meta.run_subprocess(cmd)["returncode"]
    ret |= 0 if ("<TEST-PASSED>" in open(vcs_run_log).read()) else 1
    if ret != 0:
      msg = " [{}]: {} : Stage 2 VCS run failed! \n  CMD: {}".format(id, test, cmd) 
      logger.error(msg) 
      meta.update_test_status(test, "FAIL")
      run_log_file.write(msg+"\n");
      run_log_file.close()
      raise Exception("Die run_test.py!")
    meta.update_test_status(test, "PASS")
    run_log_file.write("<TEST-PASSED>");
    run_log_file.close()
def vsc_run(test_spec, args):
    id = 0
    for test,spec in sorted(test_spec.items()):
        log = os.path.join(rundir, test, "test_run.log")
        meta.start_stage(meta.STG.SIM_RUN.name, log)
        meta.update_status("FAIL")
        if (args["dump"]):  spec["args"] += " --vcdfile=waveform.vcd"
        if (args["debug"]): spec["args"] += " +event_db=1 +data_reg_mon_enable=1 +tvm_verbo=high"
        seed = args["seed"] if (args["seed"]) else 88888888 if (args["when"] == "sanity") else random.getrandbits(32)
        #p = Process(target=testRunInParallel, name=test, args=(id, test, spec["base"], ttx, seed, spec["args"], args['j_sim_run']))
        p = Process(target=testRunInParallel, name=test, args=(id, test, seed, spec, args))
        p.start()
        meta.proc.append(p)
        id += 1
    for p in meta.proc:
        p.join()

# -------------------------------
def result_report(test_spec):
    results = {}
    id = 0
    stage_status = "PASS"
    for test in sorted(test_spec.keys()):
        results[test] = Colors.RED + "FAIL" + Colors.END
        run_log = os.path.join(rundir, test, "test_run.log")
        if ("<TEST-PASSED>" in open(run_log).read()): 
            results[test] =  Colors.GREEN + "PASS" + Colors.END
            logger.debug("  {0:-3} - {1:30}: {2} {3}".format(id, test, results[test], "")) 
        else:
            logger.debug("  {0:-3} - {1:30}: {2} {3}".format(id, test, results[test], "(run_log: {0})".format(run_log)))
            #meta.update_test_status(test, "FAIL")
            stage_status = "FAIL"
        id += 1
    meta.update_status(stage_status)

# -------------------------------
def signal_handler(sig, frame):
    for p in proc: 
      logger.info("\n  Killing process '{}'({})".format(p.name, p.pid))
      p.terminate()
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
    ap.add_argument("test", nargs='?',       help="Test name")
    ap.add_argument("-w",   "--when",        help="When groups nane")
    ap.add_argument("-s",   "--seed",        help="Seed")
    ap.add_argument('-ga',  "--genargs",     type=str, nargs='*', default=[], help="TTX args example: -a +<ARG1>=<VALUE> +<ARG2>=<VALUE>")
    ap.add_argument('-pa',  "--plusargs",    type=str, nargs='*', default=[], help="Sim run args example: -a +<ARG1>=<VALUE> +<ARG2>=<VALUE>")
    ap.add_argument("-c",   "--clean",       action="store_true", help="Remove out directories")
    ap.add_argument("-dbg", "--debug",       action="store_true", help="Simplify TTX data")
    ap.add_argument("-dp",  "--dump",        action="store_true", help="Dump FSDB waveform")
    ap.add_argument("-jsb", "--j_sim_build", action="store_true", help="Jump to sim build")
    ap.add_argument("-jsr", "--j_sim_run",   action="store_true", help="Jump to sim run")
    global args
    args = vars(ap.parse_args())
    if not (args["test"] or args["when"]): args["when"] = "sanity"
    logger.debug(" <Input Args>: " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))
    for k,v in args.items():
        if (v): logger.debug("  {} : {}".format(k, v))
    if args["j_sim_run"] : args["j_sim_build"] = True

    # STEP 0: Env cleanup
    if (not args["j_sim_build"]):
      if (args["clean"]):
        logger.info(' STEP 0: Env cleanup')
        env_cleanup()
    # STEP 0+: Test list
    cmd = " cd {0} && make gen DEBUG={1}".format(metadir, int(args["debug"]))
    ret = os.system(cmd)
    yml       = os.path.join(pubdir, "test_expanded.yml")
    test_spec = get_test_spec(yml, args["test"], args["when"])
    logger.info(" Found tests: " + str(sorted(test_spec.keys())))
    # STEP 0+: Update meta
    global meta
    meta = Meta(test_spec)

    # STEP 1: Prebuild libraries
    if (not args["j_sim_build"]):
      logger.info(' STEP 1: Prebuild libraries')
      prebuild(test_spec)
    
    # STEP 2: VCS compile
    if (not args["j_sim_run"]):
      logger.info(' STEP 2: VCS compile')
      vsc_compile()
   
    # STEP 3: VCS run
    logger.info(' STEP 3: VCS run')
    signal.signal(signal.SIGINT, signal_handler)
    vsc_run(test_spec, args)

    # STEP 4: Result report
    logger.info(' STEP 4: Result report')
    result_report(test_spec)


if __name__ == "__main__":
    try:
        main()
    finally:
        logger.info(' Sending Email...')
        send_email(meta)

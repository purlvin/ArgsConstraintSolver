#!/usr/bin/env python3
import glob, shutil, os, sys 
import multiprocessing, subprocess
from multiprocessing.pool import ThreadPool
import shlex
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
srcdir      = os.path.join(root,    "src")
logger      = logging.getLogger()
log         = os.path.join(outdir,  "run_test.log")

# -------------------------------
global manager 
manager = multiprocessing.Manager()
class Meta:
    STG      = Enum('STG', 'PREBUILD SIM_BUILD_1 SIM_BUILD_2 SIM_RUN')
    TEST_STG = Enum('TEST_STG', 'VCS_RUN_1 TTX_GEN CKTI VCS_RUN_2')

    start_time          = time.time()
    passrate_threshold  = 97
    pool_results        = {}
    proc                = []
    test_spec           = {}
    args                = None
    passrate            = 0.0
    stages              = {} # {test: {current: "", stages: [{stage: "", status: ""}]}}
    test_stages         = manager.dict() # {test: {current: "", stages: [{stage: "", status: ""}]}}
    def __init__(self, test_spec, args):
        self.id                = random.getrandbits(32)
        self.test_spec         = test_spec
        self.args              = args
        self.passrate          = manager.Value('d', 0.0)
        self.stages            = {"current": "OVERALL", "stages": [{"stage": "OVERALL", "status": "FAIL", "duration": "N/A", "log": os.path.join(outdir,  "run_test.log")}]}
        self.stages["stages"] += [{"stage": stage.name, "status": "N/A", "duration": "N/A"} for stage in self.STG]
        for test,spec in sorted(test_spec.items()): 
            self.test_stages[test]            = manager.dict({"seed": "N/A", "current": "N/A", "stages": manager.list([manager.dict({"stage": "OVERALL", "status": "FAIL", "suite": spec["suite"], "duration": "N/A", "log": os.path.join(rundir, test, "test.log")})])}) 
            self.test_stages[test]["stages"] += manager.list([manager.dict({"stage": stage.name, "status": "N/A", "duration": "N/A"}) for stage in self.TEST_STG])
        if (args["passrate_threshold"]): self.passrate_threshold = args["passrate_threshold"]
    def id(self):
        return self.id
    def cmdline(self):
        cmdline = sys.argv
        return " ".join(cmdline)
    def exec_subprocess(self, cmd):
        ret = {}
        p = subprocess.Popen(cmd, shell=True)
        self.proc.append(p)
        ret["stdout"], ret["stderr"] = p.communicate()
        ret["returncode"] = p.returncode
        return ret
    def start_stage(self, stage, log):
        self.stages["current"] = stage
        i = self.update_status("RUNNING")
        self.stages["stages"][i]["log"] = log
    def update_status(self, status):
        i = [self.stages["stages"].index(stage) for stage in self.stages["stages"] if stage['stage'] == self.stages["current"]][0]
        self.stages["stages"][i]["status"]   = status
        self.stages["stages"][i]["duration"] = time.strftime('%H:%M:%S', time.gmtime(time.time()-self.start_time))
        if (status == "FAIL"): self.stages["stages"][0]["status"]   = status
        self.stages["stages"][0]["duration"] = self.stages["stages"][i]["duration"]
        return i
    def current_stage(self):
        return self.stages["current"]
    def stage_status(self, stage):
        status = [s["status"] for s in self.stages["stages"] if s["stage"] == stage][0]
        return status
    def start_test_stage(self, test, stage, log):
        self.test_stages[test]["current"] = stage
        i = self.update_test_status(test, "RUNNING")
        self.test_stages[test]["stages"][i]["log"] = log
    def update_test_status(self, test, status):
        if (test not in self.test_stages): raise ValueError("FAIL to find {_test} in meta({_list})".format(_test=test, _list=self.test_stages.keys()))
        test_stages = dict(self.test_stages[test])
        i = [ stage["stage"] for stage in test_stages["stages"] ].index(test_stages["current"])
        self.test_stages[test]["stages"][i]["status"]   = status
        self.test_stages[test]["stages"][i]["duration"] = time.strftime('%H:%M:%S', time.gmtime(time.time()-self.start_time))
        if (status == "FAIL"): self.test_stages[test]["stages"][0]["status"] = status
        self.test_stages[test]["stages"][0]["duration"] = self.test_stages[test]["stages"][i]["duration"]
        results = [test_hash["stages"][0]["status"] for test,test_hash in self.test_stages.items()]
        self.passrate.value = results.count("PASS")/len(results)*100
        return i
    def test_current_stage(self, test):
        return self.test_stages[test]["current"]


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
            "id":       None,
            "base":     test,
            "seed":     test_hash["_seed"] if ("_seed" in test_hash) else None,
            "suite":    test_hash["_suite"],
            "fw":       test_hash["_fw"],
            "ttx":      test_hash["_ttx"],
            "args":     flatten_list(test_hash["_args"]),
        }
        groups = flatten_list(test_hash["_when"])
        if (len([grp for grp in groups if ("NEVER" == grp.upper())])>0): continue;
        if ((tgt_test) and (tgt_test.split("__")[0] == test)):
            test_spec[tgt_test] = info
        elif (tgt_group in groups):
            test_spec[test] = info
            if ("_clones" in test_hash): 
                for i in range(test_hash["_clones"]): 
                    test_spec["{}__{}".format(test,i+1)] = info.copy()
    id = 0
    for test,spec in sorted(test_spec.items()):
        test_spec[test]["id"] = id
        id                   += 1
    if (not test_spec): raise ValueError("FAIL to find {_type} '{_name}'!".format(_type="test" if tgt_test else "suite", _name=tgt_test if tgt_test else tgt_group))
    return test_spec

# -------------------------------
def env_cleanup():
  for path, dirs, files in os.walk(srcdir) :
    if ("out" in dirs):
      dir = os.path.join(path, "out")
      if os.path.exists(dir): os.system("mv {0} {0}.old && rm -rf {0}.old &".format(dir))
    for dir in [pubdir, simdir, simdir_stg1, rundir]:
        os.makedirs(dir, exist_ok=True)
  os.system("cd {0} && make clean ".format(root))
  os.system("mv {0} {0}.old && mkdir {0} && rm -rf {0}.old &".format(rundir))
  os.system("mv {0} {0}.old && mkdir {0} && rm -rf {0}.old &".format(pubdir))
  os.system("mv {0} {0}.old && mkdir {0} && rm -rf {0}.old &".format(simdir))

# -------------------------------
def prebuild(meta):
    (test_spec) = (meta.test_spec)
    log = "{_pubdir}/prebuild.log".format(_pubdir=pubdir) 
    meta.start_stage(meta.STG.PREBUILD.name, log)
    f = open(log, "w")
    # Serialized tasks
    pool = ThreadPool(1)
    #   -> $ROOT
    path = "{0}".format(root); name = "Build {0}".format(path); cmd  = "cd {1} && make -j 64 &>> {2}".format(name, path, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> $ROOT/src/test_ckernels/gen
    path = "{0}/src/test_ckernels/gen".format(root); name = "Build {0}".format(path); cmd  = "cd {1} && make -j 64 &>> {2}".format(name, path, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    pool.close()
    pool.join()
    # Parallelized tasks
    pool = ThreadPool(os.cpu_count())
    #   -> $ROOT/src/software/assembler
    path = "{0}/src/software/assembler".format(root); name = "Build {0}".format(path); cmd  = "cd {1} && make -j 64 &>> {2}".format(name, path, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> $ROOT/src/software/command_assembler
    path = "{0}/src/software/command_assembler".format(root); name = "Build {0}".format(path); cmd  = "cd {1} && make -j 64 &>> {2}".format(name, path, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> $ROOT/src/test_ckernels/ckti
    path = "{0}/src/test_ckernels/ckti".format(root); name = "Build {0}".format(path); cmd  = "cd {1} && make -j 64 &>> {2}".format(name, path, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> $ROOT/src/test_ckernels/src
    path = "{0}/src/test_ckernels/src".format(root); name = "Build {0}".format(path); cmd  = "cd {1} && make -j 64 &>> {2}".format(name, path, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> $ROOT/src/t6ifc/vcs-core/tvm_tb
    path = "{0}/src/t6ifc/vcs-core/tvm_tb".format(root); name = "Build {0}".format(path); cmd  = "cd {1} && make SIM=vcs -j 64 &>> {2}".format(name, path, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> firmware
    name = "Build firmware".format(path); cmd  = "cd {1}/src/hardware/tb_tensix/tests && make -j 64 -f firmware.mk TENSIX_GRID_SIZE_X=1 TENSIX_GRID_SIZE_Y=1 OUTPUT_DIR={1}/out/pub/fw/main &>> {2}".format(name, root, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> firmware/single-core-synth-ckernel-mailbox
    name = "Build firmware/single-core-synth-ckernel-mailbox".format(path); cmd  = "cd {1}/src/hardware/tb_tensix/tests/single-core-synth-ckernel-mailbox/fw && make -j 64 -f Makefile TENSIX_GRID_SIZE_X=1 TENSIX_GRID_SIZE_Y=1 OUTPUT_DIR={1}/out/pub/fw/single-core-synth-ckernel-mailbox &>> {2}".format(name, root, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> firmware/single-core-reset-1
    name = "Build firmware/single-core-reset-1".format(path); cmd  = "cd {1}/src/hardware/tb_tensix/tests && export FW_DEFINES='-DENABLE_TENSIX_TRISC_RESET'; export OUTPUT_DIR={1}/out/pub/fw/single-core-reset-1 && make -j 64 -f single-core-reset/test.mk  &>> {2} && make -C {1}/src/firmware/riscv/targets/ncrisc  &>> {2}".format(name, root, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> firmware/single-core-reset-2
    name = "Build firmware/single-core-reset-2".format(path); cmd  = "cd {1}/src/hardware/tb_tensix/tests && export FW_DEFINES='-DENABLE_TENSIX_TRISC_RESET -DENABLE_TENSIX_TRISC_RESE'; export OUTPUT_DIR={1}/out/pub/fw/single-core-reset-2 && make -j 64 -f single-core-reset/test.mk  &>> {2} && make -C {1}/src/firmware/riscv/targets/ncrisc  &>> {2}".format(name, root, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> firmware/single-core-reset-3
    name = "Build firmware/single-core-reset-3".format(path); cmd  = "cd {1}/src/hardware/tb_tensix/tests && export FW_DEFINES='-DENABLE_TENSIX_TRISC_PC_OVERRIDE'; export OUTPUT_DIR={1}/out/pub/fw/single-core-reset-3 && make -j 64 -f single-core-reset/test.mk &>> {2} && make -C {1}/src/firmware/riscv/targets/ncrisc  &>> {2}".format(name, root, log)
    f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
    meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    #   -> ttx
    for ttx in list(set([spec["ttx"] for test,spec in test_spec.items()])):
        name = "Build ttx/{0}".format(ttx); cmd  = "cd {1}/src/hardware/tb_tensix/tests && make -j 64 OUTPUT_DIR={1}/out/pub/ttx/{3} TEST={3} generator firmware &>> {2}".format(name, root, log, ttx)
        f.writelines("\n->> {0} \n  CMD: {1}\n".format(name, cmd));  f.flush()
        meta.pool_results[name] = pool.apply_async(meta.exec_subprocess, (cmd,))
    f.close
    # Poll results
    status_pass = True
    timeout = int(args["timeout"]) - int(time.time()-Meta.start_time) if args["timeout"] else 14400
    pending_tasks = list(meta.pool_results.keys())
    while (timeout>0):
        for name,p in meta.pool_results.items():
            if ((name in pending_tasks) and (p.ready())): 
                ret          = p.get()["returncode"]
                status_pass &= (0==ret)
                logger.debug("   --> {0:100} : {1}".format(name, "PASS" if (0==ret) else "FAIL")) 
                pending_tasks.remove(name)
        if (not pending_tasks): break
        time.sleep(1)
        timeout -= 1
    if (timeout==0):
        status_pass = False
        logger.error(' Timeout triggered!')
        logger.warning('  ->> Pending Task: {}'.format(pending_tasks))
    if not status_pass: 
      logger.error("Prebuild failed! (Log: {0})".format(log)) 
      meta.update_status("FAIL")
      raise Exception("Die run_test.py!")
    meta.update_status("PASS")

# -------------------------------
def vsc_compile():
    global meta
    for dir in [simdir, simdir_stg1]:
      os.makedirs(dir, exist_ok=True)
    # Stage 1 VCS compile
    log = "{_simdir_stg1}/vcs_compile.log".format(_simdir_stg1=simdir_stg1) 
    meta.start_stage(meta.STG.SIM_BUILD_1.name, log)
    logger.info('   --> Stage 1 VCS compile')
    sv = os.path.join(pubdir, "constraints_solver.sv")
    cmd = "  cd {0}; {1}/vcs-docker -fsdb -kdb -lca +vcs+lic+wait +incdir+{2} {3} -sverilog -full64 -o {0}/simv &> {4}".format(simdir_stg1, tbdir, pubdir, sv, log)
    ret = meta.exec_subprocess(cmd)["returncode"]
    if ret != 0:
      logger.error("Stage 1 VCS compile failed! \n  CMD: {0}".format(cmd)) 
      meta.update_status("FAIL")
      raise Exception("Die run_test.py!")
    meta.update_status("PASS")
    # Stage 2 VCS compile
    log = "{_simdir}/vcs_compile.log".format(_simdir=simdir) 
    meta.start_stage(meta.STG.SIM_BUILD_2.name, log)
    logger.info('   --> Stage 2 VCS compile')
    cmd = "  cd {0}; ./vcs-docker -fsdb -kdb -lca +vcs+lic+wait +define+ECC_ENABLE +define+NOVEL_ARGS_CONSTRAINT_TB -xprop=tmerge +define+MAILBOX_TARGET=6 {0}/tvm_tb/out/tvm_tb.so -f vcs.f  +incdir+{1} +define+SIM=vcs -sverilog -full64 -l vcs_compile.log -timescale=1ns/1ps -error=PCWM-W +lint=TFIPC-L -o {3}/simv -assert disable_cover -CFLAGS -LDFLAGS -lboost_system -L{4}/vendor/yaml-cpp/build -lyaml-cpp -lsqlite3 -lz -debug_acc+dmptf -debug_region+cell+encrypt -debug_access &> {5}".format(tbdir, pubdir, sv, simdir, root, log)
    ret = meta.exec_subprocess(cmd)["returncode"]
    if ret != 0:
      logger.error("Stage 2 VCS compile failed! \n  CMD: {0}".format(cmd)) 
      meta.update_status("FAIL")
      raise Exception("Die run_test.py!")
    meta.update_status("PASS")

# -------------------------------
def testRunInParallel(test, seed, meta):
    try: 
        (id, suite, base, fw, ttx, spec_args)  = (meta.test_spec[test]["id"], meta.test_spec[test]["suite"], meta.test_spec[test]["base"], meta.test_spec[test]["fw"], meta.test_spec[test]["ttx"], meta.test_spec[test]["args"])
        (genargs, plusargs)         = (meta.args["genargs"], meta.args["plusargs"])
        cfg_args = {}
        cfg_hash = {}
        test_rundir = os.path.join(rundir, test)
        os.makedirs(test_rundir, exist_ok=True)
        test_log = os.path.join(rundir, test, "test.log")
        f_test_log = open(test_log, "w")   

        # Stage 1 VCS run
        log = os.path.join(test_rundir, "stg1_vcs_run.log")
        meta.start_test_stage(test, meta.TEST_STG.VCS_RUN_1.name, log)
        msg = '   --> [{0:3}: {1:30} : {2}] : Executing {3}'.format(id, test, os.getpid(), meta.test_current_stage(test))
        logger.info(msg)
        f_test_log.write(msg+"\n");
        cmd = "  cd {0}; {1}/simv +test={2} +ntb_random_seed={3} &> {4}".format(test_rundir, simdir_stg1, base, seed, log)
        f_test_log.write(cmd+"\n");
        ret  = meta.exec_subprocess(cmd)["returncode"]
        ret |= 1 if ("Error" in open(log).read()) else 0
        if ret != 0: raise Exception("Die run_test.py!")
        meta.update_test_status(test, "PASS")
        # Paring .cfg files
        for x in ["genargs", "plusargs"] :
            cfg = os.path.join(test_rundir, x + ".cfg")
            f = open(cfg, "r")
            cfg_args[x] = f.read().strip().split("\n")
            cfg_hash[x] = {}
            f.close
        cfg_args["genargs"]  += genargs + ["--ttx={}".format(ttx)] 
        cfg_args["plusargs"] += spec_args + plusargs
        for k,v in cfg_args.items():
            k = k.split(".")[0]
            for x in v:
                a = x.split("=")
                cfg_hash[k][a[0]] = a[1] if len(a)>1 else None
            cfg_args[k] = ""
            for kk,vv in sorted(cfg_hash[k].items()):
                if ((vv) and (vv.upper() == "REMOVE")) : continue
                cfg_args[k] += " {}={}".format(kk,vv) if vv != None else " {}".format(kk)
        for x in ["genargs", "plusargs"] :
            cfg = os.path.join(test_rundir, x + ".cfg")
            f = open(cfg, "w")
            f.writelines(cfg_args[x].strip().replace(" ", "\n"));
            f.close

        # TTX generation
        log = os.path.join(test_rundir, "ttx_gen.log")
        meta.start_test_stage(test, meta.TEST_STG.TTX_GEN.name, log)
        msg = '   --> [{0:3}: {1:30} : {2}] : Executing {3}'.format(id, test, os.getpid(), meta.test_current_stage(test))
        logger.info(msg)
        f_test_log.write(msg+"\n");
        cmd = "  cd {0}; ln -sf {1}/fw/{2} fw && {1}/ttx/{3}/{3} {4} &> {0}/ttx_gen.log".format(test_rundir, pubdir, fw, ttx, cfg_args["genargs"])
        f_test_log.write(cmd+"\n");
        ret  = meta.exec_subprocess(cmd)["returncode"]
        if ret != 0: raise Exception("Die run_test.py!")
        meta.update_test_status(test, "PASS")
        # CKTI
        log = os.path.join(test_rundir, "ckti.log")
        meta.start_test_stage(test, meta.TEST_STG.CKTI.name, log)
        msg = '   --> [{0:3}: {1:30} : {2}] : Executing {3}'.format(id, test, os.getpid(), meta.test_current_stage(test))
        logger.info(msg)
        f_test_log.write(msg+"\n");
        cmd = "  cd {4}/src/test_ckernels/ckti && out/ckti --dir={0} --test={2} &> {5}".format(test_rundir, pubdir, ttx, cfg_args["genargs"], root, log)
        f_test_log.write(cmd+"\n");
        ret  = meta.exec_subprocess(cmd)["returncode"]
        if ret != 0: raise Exception("Die run_test.py!")
        meta.update_test_status(test, "PASS")
        # Stage 2 VCS run
        log = os.path.join(test_rundir, "vcs_run.log")
        f = open(log, "w")
        info = '''\
<BUILDARGS> TEST={_test} SUITE={_suite} SEED={_seed} 
<GENARGS> {_genargs} 
<SIMARGS>
<PLUSARGS> {_plusargs}
<TAG> {_id} 
<RERUN-COMMAND> N/A
'''.format(_test=test, _suite=suite, _seed=seed, _genargs=cfg_args["genargs"], _plusargs=cfg_args["plusargs"], _id=id, _cmd=meta.cmdline())
        f.writelines(info + "\n")
        f.flush()
        f.close
        #  -> run vcs
        meta.start_test_stage(test, meta.TEST_STG.VCS_RUN_2.name, log)
        msg = '   --> [{0:3}: {1:30} : {2}] : Executing {3}'.format(id, test, os.getpid(), meta.test_current_stage(test))
        logger.info(msg)
        f_test_log.write(msg+"\n")
        vcs_run_log = os.path.join(test_rundir, "vcs_run.log")
        cmd  = "  cd {0}; trap 'echo kill -9 $PID; kill -9 $PID' SIGINT SIGTERM; {1}/simv +testdef={0}/{4}.ttx +ntb_random_seed={3} +test={2} {5} &>> {6} & PID=$!; wait $PID; EXIT_STATUS=$?".format(test_rundir, simdir, base, seed, ttx, cfg_args["plusargs"], log)
        f_test_log.write(cmd+"\n")
        sys.stdout.flush()
        ret  = meta.exec_subprocess(cmd)["returncode"]
        ret |= 0 if ("<TEST-PASSED>" in open(vcs_run_log).read()) else 1
        if ret != 0: raise Exception("Die run_test.py!")
        meta.update_test_status(test, "PASS")
        f_test_log.write("\n<TEST-PASSED>");
        f_test_log.flush()
        f_test_log.close()
    except KeyboardInterrupt:
        msg = '   --> [{0:3}: {1:30} : {2}] : Received Ctrl-C'.format(id, test, os.getpid())
        logger.error(msg) 
        f_test_log.close()
        pass
    except Exception:
        msg = '   --> [{0:3}: {1:30} : {2}] : Failed to exec {3}'.format(id, test, os.getpid(), meta.test_current_stage(test))
        logger.error(msg) 
        meta.update_test_status(test, "FAIL")
        f_test_log.write(msg+"\n");
        f_test_log.close()
        
        log = os.path.join(test_rundir, "vcs_run.log")
        if not os.path.exists(log): 
          f = open(log, "w")
          info = '''\
<BUILDARGS> TEST={_test} SUITE={_suite} SEED={_seed} 
<GENARGS> {_genargs} 
<SIMARGS>
<PLUSARGS> {_plusargs}
<TAG> {_id} 
<RERUN-COMMAND> N/A
'''.format(_test=test, _suite=suite, _seed=seed, _genargs=cfg_args["genargs"] if ("genargs" in cfg_args) else "--CONSTRAINT_RANDOM=FAIL", _plusargs=cfg_args["plusargs"] if ("genargs" in cfg_args) else "N/A", _id=id, _cmd=meta.cmdline())
          f.writelines(info + "\n")
          f.flush()
          f.close
        pass
def vsc_run(meta):
    (test_spec, args) = (meta.test_spec, meta.args)
    meta.start_stage(meta.STG.SIM_RUN.name, "")
    iterable = []
    mproc   = int(args["mproc"])
    timeout = int(args["timeout"]) - int(time.time()-Meta.start_time) if args["timeout"] else 14400
    logger.info(' [{}] : Kicking off {} processes in parallel(timeout: {})'.format(os.getpid(), mproc, "{} s".format(timeout) if timeout else None))
    pool = multiprocessing.Pool(mproc)
    meta.proc.append(pool)
    for test,spec in sorted(test_spec.items()):
        if (args["dump"]):  
          spec["args"] += ["+FSDB_DUMP_DISABLE=0"] 
        else: 
          spec["args"] += ["+FSDB_DUMP_DISABLE=1"]
        if (args["debug"]): spec["args"] += ["+event_db=1", "+data_reg_mon_enable=1", "+tvm_verbo=high"]
        seed = args["seed"] if (args["seed"]) else 88888888 if (args["when"] == "quick") else spec["seed"] if (None != spec["seed"]) else random.getrandbits(32)
        meta.test_stages[test]["seed"] = seed
        meta.test_stages[test]["stages"][0]['status'] = "PASS"
        iterable.append((test, seed, meta))
    p = pool.starmap_async(testRunInParallel, iterable)
    p.get(timeout)
    pool.terminate()

# -------------------------------
def result_report(meta):
    (test_spec, args) = (meta.test_spec, meta.args)
    stage_status = "PASS"
    for test,spec in sorted(test_spec.items()):
        test_status = Colors.RED + "FAIL" + Colors.END
        run_log = os.path.join(rundir, test, "test.log")
        if not os.path.exists(run_log): 
          os.makedirs(os.path.join(rundir, test), exist_ok=True)
          tmplog = os.path.join(rundir, test, "test.log")
          f = open(tmplog, "w")
          f.writelines("NOT STARTED!\n")
          f.flush()
          f.close
          tmplog = os.path.join(rundir, test, "vcs_run.log")
          f = open(tmplog, "w")
          info = '''\
<BUILDARGS> TEST={_test} SUITE={_suite} SEED={_seed} 
<GENARGS> {_genargs} 
<SIMARGS>
<PLUSARGS> {_plusargs}
<TAG> {_id} 
<RERUN-COMMAND> N/A
'''.format(_test=test, _suite=spec["suite"], _seed=spec["seed"], _genargs="--CONSTRAINT_RANDOM=NOT_RUN", _plusargs="N/A", _id=spec["id"])
          f.writelines(info + "\n")
          f.flush()
          f.close
        if ("<TEST-PASSED>" in open(run_log).read()): 
            test_status =  Colors.GREEN + "PASS" + Colors.END
            logger.debug("  {0:-3} - {1:30} (seed={4}) : {2} {3}".format(spec["id"], test, test_status, "", meta.test_stages[test]["seed"])) 
        else:
            logger.debug("  {0:-3} - {1:30} (seed={4}) : {2} {3}".format(spec["id"], test, test_status, "(run_log: {0})".format(run_log), meta.test_stages[test]["seed"]))
            stage_status = "FAIL"
    meta.update_status(stage_status)
    meta.start_stage("OVERALL", log)
    meta.update_status(stage_status)
    # Upload to mongo db
    if (args["upload_db"]):
        msg = ' --> Upload result to database'.format()
        logger.info(msg)
        cmd = "  python3 {0}/lib_db.py --indir {1} --testname --limit_ttx_run_size 300 ".format(metadir, rundir)
        ret = meta.exec_subprocess(cmd)["returncode"]
        if ret != 0: 
          logger.error("Upload to database failed! \n  CMD: {0}".format(cmd)) 
          raise Exception("Die run_test.py!")


# -------------------------------
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
    ap.add_argument("test", nargs='?',              help="Test name")
    ap.add_argument("-w",   "--when",               help="When groups nane")
    ap.add_argument("-s",   "--seed",               help="Seed")
    ap.add_argument('-ga',  "--genargs",            help="TTX args example: -ga='--<ARG1>=<VALUE> --<ARG2>=<VALUE>'")
    ap.add_argument('-pa',  "--plusargs",           help="Sim run args example: -pa='+<ARG1>=<VALUE> --<ARG2>=<VALUE>'")
    ap.add_argument("-tmo", "--timeout",            help="Set timeout in seconds, default no timeout")
    ap.add_argument("-prt", "--passrate_threshold", type=float, help="Set tests passrate threshold")
    ap.add_argument("-m",   "--mproc",              default=os.cpu_count()/2, help="Set maximum parallel processes, default max number of CPUs")
    ap.add_argument("-c",   "--clean",              action="store_true", help="Remove out directories")
    ap.add_argument("-sl",  "--show_list",          action="store_true", help="Print test list")
    ap.add_argument("-dbg", "--debug",              action="store_true", help="Simplify TTX data")
    ap.add_argument("-dp",  "--dump",               action="store_true", help="Dump FSDB waveform")
    ap.add_argument("-udb", "--upload_db",          action="store_true", help="Upload result to database")
    ap.add_argument("-jsb", "--j_sim_build",        action="store_true", help="Jump to sim build")
    ap.add_argument("-jsr", "--j_sim_run",          action="store_true", help="Jump to sim run")
    global args
    args = vars(ap.parse_args())
    if not (args["test"] or args["when"]): args["when"] = "quick"
    args["genargs"] = args["genargs"].split(" ") if (args["genargs"]) else []
    args["plusargs"] = args["plusargs"].split(" ") if (args["plusargs"]) else []
    logger.debug(" <Input Args>: " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))
    for k,v in args.items():
        if (v): logger.debug("  {} : {}".format(k, v))
    if args["j_sim_run"] : args["j_sim_build"] = True
    if (args["upload_db"]): os.system("mv {0} {0}.old && mkdir {0} && rm -rf {0}.old ".format(rundir))

    # STEP 0: Env cleanup
    if (not args["j_sim_build"]):
      if (args["clean"]):
        logger.info(' STEP 0: Env cleanup')
        env_cleanup()
    # STEP 0+: Test list
    cmd = " cd {0} && make gen DEBUG={1}".format(metadir, int(args["debug"]))
    ret = os.system(cmd)
    if ret != 0: 
      logger.error("Failed to generate constraints_solver.sv! \n  CMD: {0}".format(cmd)) 
      raise Exception("Die run_test.py!")
    yml       = os.path.join(pubdir, "test_expanded.yml")
    test_spec = get_test_spec(yml, args["test"], args["when"])
    if (args["show_list"]):
      logger.info(" Found tests: ")
      id = 0
      for test in sorted(test_spec.keys()):
        print("{:10}".format(id), ":", test)
        id += 1
      exit(0) 
    logger.info(" Found tests: " + str(sorted(test_spec.keys())))
    # STEP 0+: Update meta
    global meta
    meta = Meta(test_spec, args)

    # STEP 1: Prebuild libraries
    if (not args["j_sim_build"]):
      logger.info(' STEP 1: Prebuild libraries')
      prebuild(meta)
    
    # STEP 2: VCS compile
    if (not args["j_sim_run"]):
      logger.info(' STEP 2: VCS compile')
      vsc_compile()
   
    # STEP 3: VCS run
    logger.info(' STEP 3: VCS run')
    vsc_run(meta)

    # STEP 4: Result report
    logger.info(' STEP 4: Result report')
    result_report(meta)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("")
        logger.error('[Main] Ctrl-C triggered')
        for p in meta.proc: 
          logger.error("   Killing process: {}".format(p))
          p.terminate()
    except multiprocessing.TimeoutError:
        sys.stdout.flush()
        logger.error('[Main] Timeout triggered')
        logger.info(' STEP 4: Result report')
        result_report(meta)
    finally:
        if 'meta' in globals():
            status = "PASS" if (meta.passrate.value >= meta.passrate_threshold) else "FAIL" 
            if (status == "FAIL"): 
              logger.info(' Sending Email...')
              send_email(meta, status)


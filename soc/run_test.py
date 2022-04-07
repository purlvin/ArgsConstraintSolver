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
from lib_email import send_email
from lib_spec import get_yml_spec

# -------------------------------
# Path variables
root        = os.environ.get("ROOT")
#FIXME: metadir     = os.path.join(root,    "src/hardware/tb_tensix/meta")
#FIXME: testdir     = os.path.join(root,    "src/hardware/tb_tensix/tests")
#FIXME: tbdir       = os.path.join(root,    "src/t6ifc/vcs-core")
metadir     = os.path.join(root,    ".")
testdir     = os.path.join(root,    ".")
tbdir       = os.path.join(root,    ".")
outdir      = os.path.join(root,    "out")
pubdir      = os.path.join(outdir,  "pub")
simdir      = os.path.join(outdir,  "sim")
rundir      = os.path.join(outdir,  "run")
srcdir      = os.path.join(root,    "src")
logger      = logging.getLogger()
log         = os.path.join(outdir,  "run_test.log")

# -------------------------------
global manager 
manager = multiprocessing.Manager()
class Meta:
    STG      = Enum('STG', 'PREBUILD SIM_BUILD SIM_RUN')
    TEST_STG = Enum('TEST_STG', 'VCS_RUN')

    start_time          = time.time()
    passrate_threshold  = 97
    pool_results        = {}
    proc                = []
    yml_spec           = {}
    args                = None
    passrate            = 0.0
    stages              = {} # {test: {current: "", stages: [{stage: "", status: ""}]}}
    test_stages         = {} # {test: {current: "", stages: [{stage: "", status: ""}]}}
    def __init__(self, yml_spec, args):
        self.id                = random.getrandbits(32)
        self.yml_spec         = yml_spec
        self.args              = args
        self.passrate          = manager.Value('d', 0.0)
        self.stages            = {"current": "OVERALL", "stages": [{"stage": "OVERALL", "status": "FAIL", "duration": "N/A", "log": os.path.join(outdir,  "run_test.log")}]}
        self.stages["stages"] += [{"stage": stage.name, "status": "N/A", "duration": "N/A"} for stage in self.STG]
        for test,spec in sorted(yml_spec["tests"].items()): 
            self.test_stages[test]            = {"seed": "N/A", "current": "N/A", "stages": [{"stage": "OVERALL", "status": "FAIL", "suite": spec["suite"], "duration": "N/A", "log": os.path.join(rundir, test, "test.log")}]} 
            self.test_stages[test]["stages"] += [{"stage": stage.name, "status": "N/A", "duration": "N/A"} for stage in self.TEST_STG]
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
        print("purlvin - 1:", self.test_stages[test], stage,  self.test_stages[test]["current"])#FIXME:
        self.test_stages[test]["current"] = stage
        print("purlvin - 1:", self.test_stages[test], stage,  self.test_stages[test]["current"])#FIXME:
        i = self.update_test_status(test, "RUNNING")
        self.test_stages[test]["stages"][i]["log"] = log
    def update_test_status(self, test, status):
        if (test not in self.test_stages): raise ValueError("FAIL to find {_test} in meta({_list})".format(_test=test, _list=self.test_stages.keys()))
        test_stages = dict(self.test_stages[test])
        print(test, test_stages)#FIXME:
        print(test_stages["stages"],   test_stages["current"])#FIXME:
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
def env_cleanup():
  for path, dirs, files in os.walk(srcdir) :
    if ("out" in dirs):
      dir = os.path.join(path, "out")
      if os.path.exists(dir): os.system("mv {0} {0}.old && rm -rf {0}.old &".format(dir))
  os.system("cd {0} && make clean ".format(root))
  os.system("mv {0} {0}.old && mkdir {0} && rm -rf {0}.old &".format(rundir))
  os.system("mv {0} {0}.old && mkdir {0} && rm -rf {0}.old &".format(pubdir))
  os.system("mv {0} {0}.old && mkdir {0} && rm -rf {0}.old &".format(simdir))

# -------------------------------
def prebuild(meta):
    (yml_spec) = (meta.yml_spec)
    prebuild_log = "{_pubdir}/prebuild.log".format(_pubdir=pubdir) 
    meta.start_stage(meta.STG.PREBUILD.name, prebuild_log)
    f = open(prebuild_log, "w")
    logdir = "{_pubdir}/prebuild".format(_pubdir=pubdir)
    os.makedirs(logdir, exist_ok=True)
    def add_pool_task(dir, name, margs):
        log = os.path.join(logdir, name.replace(root,"ROOT").replace("/","_")+".log");
        cmd  = "cd {0} && make -j 64 {1} &> {2}".format(dir, margs.replace("#log#",log), log)
        f.writelines("\n->> Build {0} ({1})\n  CMD: {2}\n".format(name, log, cmd));  f.flush()
        meta.pool_results[name] = [pool.apply_async(meta.exec_subprocess, (cmd,)), log]
    # Serialized tasks
    pool = ThreadPool(1)
    #   -> $ROOT
    dir = root; name = dir; margs = "";
    add_pool_task(dir, name, margs)
    #   -> $ROOT/src/test_ckernels/gen
    dir = "{0}/src/test_ckernels/gen".format(root); name = dir; margs = "";
    add_pool_task(dir, name, margs)
    pool.close()
    pool.join()
    # Parallelized tasks
    pool = ThreadPool(os.cpu_count())
    #   -> $ROOT/src/software/assembler
    dir = "{0}/src/software/assembler".format(root); name = dir; margs = "";
    add_pool_task(dir, name, margs)
    #   -> $ROOT/src/software/command_assembler
    dir = "{0}/src/software/command_assembler".format(root); name = dir; margs = "";
    add_pool_task(dir, name, margs)
    #   -> $ROOT/src/test_ckernels/ckti
    dir = "{0}/src/test_ckernels/ckti".format(root); name = dir; margs = "";
    add_pool_task(dir, name, margs)
    #   -> $ROOT/src/test_ckernels/src
    dir = "{0}/src/test_ckernels/src".format(root); name = dir; margs = "";
    add_pool_task(dir, name, margs)
    #   -> $ROOT/src/t6ifc/vcs-core/tvm_tb
    dir = "{0}/src/t6ifc/vcs-core/tvm_tb".format(root); name = dir; margs = "SIM=vcs";
    add_pool_task(dir, name, margs)
    #   -> firmware
    dir = "{0}/src/hardware/tb_tensix/tests".format(root); name = "firmware"; margs = "-f firmware.mk TENSIX_GRID_SIZE_X=1 TENSIX_GRID_SIZE_Y=1 OUTPUT_DIR={0}/out/pub/fw/main".format(root);
    add_pool_task(dir, name, margs)
    #   -> firmware/single-core-synth-ckernel-mailbox
    dir = "{0}/src/hardware/tb_tensix/tests/single-core-synth-ckernel-mailbox/fw".format(root); name = "firmware/single-core-synth-ckernel-mailbox"; margs = "-f Makefile TENSIX_GRID_SIZE_X=1 TENSIX_GRID_SIZE_Y=1 OUTPUT_DIR={0}/out/pub/fw/single-core-synth-ckernel-mailbox".format(root);
    add_pool_task(dir, name, margs)
    #   -> firmware/single-core-reset-1
    dir = "{0}/src/hardware/tb_tensix/tests && export FW_DEFINES='-DENABLE_TENSIX_TRISC_RESET' OUTPUT_DIR={0}/out/pub/fw/single-core-reset-1".format(root); name = "firmware/single-core-reset-1"; margs = "-f single-core-reset/test.mk  &> #log# && make -C {0}/src/firmware/riscv/targets/ncrisc".format(root);
    add_pool_task(dir, name, margs)
    #   -> firmware/single-core-reset-2
    dir = "{0}/src/hardware/tb_tensix/tests && export FW_DEFINES='-DENABLE_TENSIX_TRISC_RESET -DENABLE_TENSIX_TRISC_RESE' OUTPUT_DIR={0}/out/pub/fw/single-core-reset-2".format(root); name = "firmware/single-core-reset-2"; margs = "-f single-core-reset/test.mk  &> #log# && make -C {0}/src/firmware/riscv/targets/ncrisc".format(root);
    add_pool_task(dir, name, margs)
    #   -> firmware/single-core-reset-3
    dir = "{0}/src/hardware/tb_tensix/tests && export FW_DEFINES='-DENABLE_TENSIX_TRISC_PC_OVERRIDE' OUTPUT_DIR={0}/out/pub/fw/single-core-reset-3".format(root); name = "firmware/single-core-reset-3"; margs = "-f single-core-reset/test.mk  &> #log# && make -C {0}/src/firmware/riscv/targets/ncrisc".format(root);
    add_pool_task(dir, name, margs)
    f.close
    # Poll results
    status_pass = True
    timeout = int(args["timeout"]) - int(time.time()-Meta.start_time) if args["timeout"] else 14400
    pending_tasks = list(meta.pool_results.keys())
    while (timeout>0):
        for name,[p,log] in meta.pool_results.items():
            if ((name in pending_tasks) and (p.ready())): 
                ret          = p.get()["returncode"]
                status_pass &= (0==ret)
                logger.debug("   --> {0:100} : {1}".format(name, "PASS" if (0==ret) else "FAIL ({0})".format(log))) 
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
def vsc_compile(meta):
    (config_spec) = (meta.yml_spec["configs"])
    build_log = os.path.join(simdir,"build.log")
    f = open(build_log, "w")
    meta.start_stage(meta.STG.SIM_BUILD.name, build_log)
    pool = ThreadPool(os.cpu_count())
    for config,spec in sorted(config_spec.items()):
        dir = os.path.join(simdir,config)
        os.makedirs(dir, exist_ok=True)
        logger.info("   --> VCS compile: config '{_cfg}'".format(_cfg=config))
        log = "{_dir}/vcs_compile.log".format(_dir=dir)
        cmd  = "  cd {0}; ./vcs-docker -top {1} ".format(tbdir, spec["_top"])
        cmd += " ".join(spec["_args"])
        cmd += "".join(map(lambda x: " +define+"+x, spec["_defines"]))
        cmd += "".join(map(lambda x: " -f "+x, spec["_flist"]))
        cmd += " -o {0}/simv -l {1}".format(dir, log)
        f.writelines("\n->> Build {0} ({1})\n  CMD: {2}\n".format(config, log, cmd));  f.flush()
        meta.pool_results[config] = [pool.apply_async(meta.exec_subprocess, (cmd,)), log]
    f.close
    # Poll results
    status_pass = True
    timeout = int(args["timeout"]) - int(time.time()-Meta.start_time) if args["timeout"] else 14400
    pending_tasks = list(meta.pool_results.keys())
    while (timeout>0):
        for name,[p,log] in meta.pool_results.items():
            if ((name in pending_tasks) and (p.ready())): 
                ret          = p.get()["returncode"]
                status_pass &= (0==ret)
                logger.debug("   --> {0:100} : {1}".format(name, "PASS" if (0==ret) else "FAIL ({0})".format(log))) 
                pending_tasks.remove(name)
        if (not pending_tasks): break
        time.sleep(1)
        timeout -= 1
    if (timeout==0):
        status_pass = False
        logger.error(' Timeout triggered!')
        logger.warning('  ->> Pending Task: {}'.format(pending_tasks))
    if not status_pass: 
      logger.error("Sim build failed! (Log: {0})".format(build_log)) 
      meta.update_status("FAIL")
      raise Exception("Die run_test.py!")
    meta.update_status("PASS")

# -------------------------------
#def testRunInParallel(test, seed, meta):
#    try: 
#        (id, suite, base, fw, spec_args)  = (meta.yml_spec['tests'][test]["id"], meta.yml_spec['tests'][test]["suite"], meta.yml_spec['tests'][test]["base"], meta.yml_spec['tests'][test]["fw"], meta.yml_spec['tests'][test]["args"])
#        cfg_args = {}
#        cfg_hash = {}
#        test_rundir = os.path.join(rundir, test)
#        os.makedirs(test_rundir, exist_ok=True)
#        test_log = os.path.join(rundir, test, "test.log")
#        f_test_log = open(test_log, "w")   
#
#        # verdi_command.txt
#        with open(os.path.join(test_rundir, "verdi_command.txt"), "w") as f:
#            f.write("$VERDI_HOME/bin/verdi -sv -L out -f {0}/vcs.f -vtop verdi_vtop.map +define+ECC_ENABLE -ssf {1}/dump_rtl_ecc.fsdb &".format(tbdir, test_rundir))
#        ## VCS run
#        log = os.path.join(test_rundir, "vcs_run.log")
#        f = open(log, "w")
#        info = '''\
#<BUILDARGS> TEST={_test} SUITE={_suite} SEED={_seed} 
#<SIMARGS>
#<TAG> {_id} 
#<RERUN-COMMAND> N/A
#'''.format(_test=test, _suite=suite, _seed=seed, _id=id, _cmd=meta.cmdline())
#        f.writelines(info + "\n")
#        f.flush()
#        f.close
#        #  -> run vcs
#        print("purlvin - 0:", test)#FIXME:
#        meta.start_test_stage(test, meta.TEST_STG.VCS_RUN.name, log)
#        print("purlvin - 2:", test)#FIXME:
#        msg = '   --> [{0:3}: {1:30} : {2}] : Executing {3}'.format(id, test, os.getpid(), meta.test_current_stage(test))
#        logger.info(msg)
#        f_test_log.write(msg+"\n")
#        vcs_run_log = os.path.join(test_rundir, "vcs_run.log")
#        cmd  = "  cd {0}; trap 'echo kill -9 $PID; kill -9 $PID' SIGINT SIGTERM; {1}/simv +ntb_random_seed={3} +test={2} {5} &>> {6} & PID=$!; wait $PID; EXIT_STATUS=$?".format(test_rundir, simdir, base, seed, cfg_args["plusargs"], log)
#        f_test_log.write(cmd+"\n")
#        f_test_log.flush()
#        sys.stdout.flush()
#        ret  = meta.exec_subprocess(cmd)["returncode"]
#        ret |= 0 if ("<TEST-PASSED>" in open(vcs_run_log).read()) else 1
#        if ret != 0: raise Exception("Die run_test.py!")
#        meta.update_test_status(test, "PASS")
#        f_test_log.write("\n<TEST-PASSED>");
#        f_test_log.flush()
#        f_test_log.close()
#    except KeyboardInterrupt:
#        msg = '   --> [{0:3}: {1:30} : {2}] : Received Ctrl-C'.format(id, test, os.getpid())
#        logger.error(msg) 
#        f_test_log.close()
#        pass
#    except Exception:
#        msg = '   --> [{0:3}: {1:30} : {2}] : Failed to exec {3}'.format(id, test, os.getpid(), meta.test_current_stage(test))
#        logger.error(msg) 
#        meta.update_test_status(test, "FAIL")
#        f_test_log.write(msg+"\n");
#        f_test_log.close()
#        
#        log = os.path.join(test_rundir, "vcs_run.log")
#        if not os.path.exists(log): 
#          f = open(log, "w")
#          info = '''\
#<BUILDARGS> TEST={_test} SUITE={_suite} SEED={_seed} 
#<SIMARGS>
#<TAG> {_id} 
#<RERUN-COMMAND> N/A
#'''.format(_test=test, _suite=suite, _seed=seed, _id=id, _cmd=meta.cmdline())
#          f.writelines(info + "\n")
#          f.flush()
#          f.close
#        pass
#def vsc_run(meta):
#    (yml_spec, args) = (meta.yml_spec["tests"], meta.args)
#    meta.start_stage(meta.STG.SIM_RUN.name, "")
#    # Kick off simv
#    iterable = []
#    mproc   = int(args["mproc"])
#    timeout = int(args["timeout"]) - int(time.time()-Meta.start_time) if args["timeout"] else 14400
#    logger.info(' [{}] : Kicking off {} processes in parallel(timeout: {})'.format(os.getpid(), mproc, "{} s".format(timeout) if timeout else None))
#    pool = multiprocessing.Pool(mproc)
#    meta.proc.append(pool)
#    for test,spec in sorted(yml_spec.items()):
#        if (args["dump"]):  
#          spec["args"] += ["+FSDB_DUMP_DISABLE=0"] 
#        else: 
#          spec["args"] += ["+FSDB_DUMP_DISABLE=1"]
#        if (args["debug"]): spec["args"] += ["+event_db=1", "+data_reg_mon_enable=1", "+tvm_verbo=high"]
#        seed = args["seed"] if (args["seed"]) else 88888888 if (args["when"] == "quick") else spec["seed"] if (None != spec["seed"]) else random.getrandbits(32)
#        meta.test_stages[test]["seed"] = seed
#        meta.test_stages[test]["stages"][0]['status'] = "PASS"
#        iterable.append((test, seed, meta))
#    p = pool.starmap_async(testRunInParallel, iterable)
#    p.get(timeout)
#    pool.terminate()

# -------------------------------
def vsc_run(meta):
    (test_spec, args) = (meta.yml_spec["tests"], meta.args)
    run_log = os.path.join(rundir,"run.log")
    f = open(run_log, "w")
    meta.start_stage(meta.STG.SIM_BUILD.name, run_log)
    pool = ThreadPool(int(args["mproc"]))
    for test,spec in sorted(test_spec.items()):
        dir = os.path.join(rundir,test)
        os.makedirs(dir, exist_ok=True)
        seed = args["seed"] if (args["seed"]) else 88888888 if (args["when"] == "quick") else spec["seed"] if (None != spec["seed"]) else random.getrandbits(32)
        meta.test_stages[test]["seed"] = seed
        meta.test_stages[test]["stages"][0]['status'] = "PASS"
        # verdi_command.txt
        with open(os.path.join(dir, "verdi_command.txt"), "w") as fv:
            fv.write("$VERDI_HOME/bin/verdi -sv -L out -f {0}/vcs.f -vtop verdi_vtop.map +define+ECC_ENABLE -ssf {1}/dump_rtl_ecc.fsdb &".format(tbdir, dir))
        # vcs run        
        config = spec["config"]
        logger.info("   --> VCS run: {_test}({_cfg})".format(_test=test, _cfg=config))
        log = "{_dir}/vcs_run.log".format(_dir=dir)
        cmd  = "  cd {_dir}; {_dir}/simv ".format(_dir=os.path.join(simdir,config))
        cmd += " ".join(spec["args"])
        cmd += " {_fw} ".format(_fw=spec["fw"])
        cmd += "".join(map(lambda x: " +define+"+x, spec["defines"]))
        cmd += " -l {_log}".format(_log=log)
        f.writelines("\n->> Run {0} ({1})\n  CMD: {2}\n".format(test, log, cmd));  f.flush()
        meta.pool_results[test] = [pool.apply_async(meta.exec_subprocess, (cmd,)), log]
    f.close
    # Poll results
    status_pass = True
    timeout = int(args["timeout"]) - int(time.time()-Meta.start_time) if args["timeout"] else 14400
    pending_tasks = list(meta.pool_results.keys())
    try: 
        while (timeout>0):
            for name,[p,log] in meta.pool_results.items():
                if ((name in pending_tasks) and (p.ready())): 
                    ret          = p.get()["returncode"]
                    status_pass &= (0==ret)
                    logger.debug("   --> {0:100} : {1}".format(name, "PASS" if (0==ret) else "FAIL ({0})".format(log))) 
                    pending_tasks.remove(name)
            if (not pending_tasks): break
            time.sleep(1)
            timeout -= 1
    except KeyboardInterrupt:
        msg = '   --> [SIM_RUN] : Received Ctrl-C'.format()
        logger.error(msg) 
        status_pass = False
        pass
    if (timeout==0):
        status_pass = False
        logger.error(' Timeout triggered!')
        logger.warning('  ->> Pending Task: {}'.format(pending_tasks))
    if not status_pass: 
      logger.error("Sim run failed! (Log: {0})".format(run_log)) 
      meta.update_status("FAIL")
      raise Exception("Die run_test.py!")
    meta.update_status("PASS")

# -------------------------------
def result_report(meta):
    (yml_spec, args) = (meta.yml_spec["tests"], meta.args)
    stage_status = "PASS"
    for test,spec in sorted(yml_spec.items()):
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
<SIMARGS>
<TAG> {_id} 
<RERUN-COMMAND> N/A
'''.format(_test=test, _suite=spec["suite"], _seed=spec["seed"], _id=spec["id"])
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
    ap.add_argument("test", nargs='?',                  help="Test name")
    ap.add_argument("-w",   "--when",                   help="When groups nane")
    ap.add_argument("-s",   "--seed",                   help="Seed")
    ap.add_argument("-tmo", "--timeout",                help="Set timeout in seconds, default no timeout")
    ap.add_argument("-prt", "--passrate_threshold",     type=float, help="Set tests passrate threshold")
    ap.add_argument("-m",   "--mproc",                  default=os.cpu_count()/2, help="Set maximum parallel processes, default max number of CPUs")
    ap.add_argument("-c",   "--clean",                  action="store_true", help="Remove out directories")
    ap.add_argument("-sl",  "--show_list",              action="store_true", help="Print test list")
    ap.add_argument("-dr",  "--disable_randomization",  action="store_true", help="Disable gen/plus args output from randomization")
    ap.add_argument("-dbg", "--debug",                  action="store_true", help="Simplify TTX data")
    ap.add_argument("-dp",  "--dump",                   action="store_true", help="Dump FSDB waveform")
    ap.add_argument("-udb", "--upload_db",              action="store_true", help="Upload result to database")
    ap.add_argument("-jsb", "--j_sim_build",            action="store_true", help="Jump to sim build")
    ap.add_argument("-jsr", "--j_sim_run",              action="store_true", help="Jump to sim run")
    global args
    args = vars(ap.parse_args())
    if not (args["test"] or args["when"]): args["when"] = "quick"
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
    for dir in [pubdir, simdir, rundir]:  os.makedirs(dir, exist_ok=True)
    # STEP 0+: Test list
    yml_spec = get_yml_spec(os.path.join(metadir, "test.yml"), args["test"], args["when"], pubdir)
    if (args["show_list"]):
      logger.info(" Found tests: ")
      id = 0
      for test in sorted(yml_spec["tests"].keys()):
        print("{:10}".format(id), ":", test)
        id += 1
      exit(0) 
    logger.info(" Found tests: " + str(sorted(yml_spec["tests"].keys())))
    # STEP 0+: Update meta
    global meta
    meta = Meta(yml_spec, args)

    # STEP 1: Prebuild libraries
    #FIXME: if (not args["j_sim_build"]):
    #FIXME:   logger.info(' STEP 1: Prebuild libraries')
    #FIXME:   prebuild(meta)
    
    # STEP 2: VCS compile
    if (not args["j_sim_run"]):
      logger.info(' STEP 2: VCS compile')
      vsc_compile(meta)
   
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
        logger.error('[Main] Timeout triggered')
        for p in meta.proc: 
          logger.error("   Killing process: {}".format(p))
          p.terminate()
        sys.stdout.flush()
        for test,spec in meta.yml_spec.items():
          if (test, meta.test_stages[test]["current"] != "VCS_RUN"):
             meta.test_stages[test]["stages"][0]['status'] = "FAIL"
        results = [test_hash["stages"][0]["status"] for test,test_hash in meta.test_stages.items()]
        meta.passrate.value = results.count("PASS")/len(results)*100
        logger.info(' STEP 4: Result report')
        result_report(meta)
    finally:
        if 'meta' in globals():
            status = "PASS" if (meta.passrate.value >= meta.passrate_threshold) else "FAIL" 
            if (status == "FAIL"): 
              logger.info(' Sending Email...')
              send_email(meta, status)


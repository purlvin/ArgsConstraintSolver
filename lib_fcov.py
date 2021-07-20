#!/usr/bin/env python3
import os, platform
import shlex, subprocess
from subprocess import Popen
from datetime import datetime
from pathlib import Path
from pprint import pprint

class FCov:
    procs               = []
    def __init__(self, root, mproc):
        curdir  = Path(__file__).parent.resolve()
        outdir  = "{0}/out".format(root)
        self.fcov_merge_tool    = "{0}/vendor/fc4sc/tools/coverage_merge/merge.py".format(root)
        self.fcov_report_tool   = "{0}/fcov_report.py".format(curdir)
        self.fcov_upload_tool   = "{0}/upload_fcov.py".format(curdir)
        self.fcov_dir           = "{0}/fcov".format(outdir)
        self.fcov_input_dir     = "{0}/run".format(outdir)
        self.watchdog_stop_file = "{0}/TEST_DONE".format(self.fcov_dir)
        self.fcov_merged_xml    = "{0}/FCOV_MERGE_{1}.xml".format(self.fcov_dir, datetime.now().strftime("%Y-%m-%d_%H:%M:%S"))
        self.fcov_grade_file    = "{0}/fcov_grade.yaml".format(curdir)
        self.watchdog_merge_notification_interval = -10
        self.watchdog_merge_procs                 = (mproc+7)/8
        Path(self.fcov_dir).mkdir(parents=True, exist_ok=True)

    # -------------------------------
    def start_fcov_watchdog(self):
      cmd = "python3 {0} --watchdog {1} --watchdog_merge_notification_interval {2} --watchdog_stop_file {3} --watchdog_merge_procs {4} --merge_to_db {5} ".format(self.fcov_merge_tool, self.fcov_input_dir, self.watchdog_merge_notification_interval, self.watchdog_stop_file, self.watchdog_merge_procs, self.fcov_merged_xml)
      self.procs.append(subprocess.Popen(shlex.split(cmd)))

    # -------------------------------
    def stop_fcov_watchdog(self):
        # Stop wathchdog
        open(self.watchdog_stop_file, 'a').close()
        for p in self.procs:
            p.wait()
        self.procs.clear()

        # Generate and upload fcov report
        report = ""
        # Report fcov_grade_*_full.txt
        for grade in range(3,0,-1):
            report = "{0}/fcov_grade_{1}_full.txt".format(self.fcov_dir, grade)
            cmd = "python3 {0} --xml_report {1} --report --report_grade {2} --apply_grade_file {3} --report_misses --report_hits > {4} ".format(self.fcov_report_tool, self.fcov_merged_xml, grade, self.fcov_grade_file, report)
            self.procs.append(subprocess.Popen(shlex.split(cmd)))
        # Report fc4sc_yaml
        fc4sc_yaml = "{1}.yaml ".format(self.fcov_merged_xml)
        cmd = "python3 {0} --xml_report {1} --apply_grade_file {2} --yaml_out {3} ".format(self.fcov_report_tool, self.fcov_merged_xml, self.fcov_grade_file, fc4sc_yaml)
        self.procs.append(subprocess.Popen(shlex.split(cmd)))
        for p in self.procs:
            p.wait()
        self.procs.clear()
        # Upload
        cmd = "python3 {0} --input_fc4sc_yaml {1} --description 'Blockhole TB Tensix Jenkin FCOV run' --scope 'tb-tensix'".format(self.fcov_upload_tool, fc4sc_yaml)
        self.procs.append(subprocess.Popen(shlex.split(cmd)))
        for p in self.procs:
            p.wait()

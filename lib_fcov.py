#!/usr/bin/env python3
import os, sys, platform
import shlex, subprocess, multiprocessing
import time
import yaml
from subprocess import Popen
from datetime import datetime
from pathlib import Path
from pprint import pprint
from pymongo import MongoClient

# -------------------------------
class FCov:
    MERGE_BATCH_SIZE = 10
    procs            = []
    pool             = multiprocessing.Pool(int(os.cpu_count()/2))

    def __init__(self, root, mproc):
        curdir  = Path(__file__).parent.resolve()
        outdir  = "{0}/out".format(root)
        self.merged_xml_list    = []
        self.fcov_merge_tool    = "{0}/vendor/fc4sc/tools/coverage_merge/merge.py".format(root)
        self.fcov_report_tool   = "{0}/fcov/fcov_report.py".format(curdir)
        self.fcov_upload_tool   = "{0}/fcov/upload_fcov.py".format(curdir)
        self.fcov_grade_file    = "{0}/fcov/fcov_grade.yaml".format(curdir)
        self.fcov_dir           = "{0}/run/fcov".format(outdir)
        self.fcov_input_dir     = "{0}/run".format(outdir)
        self.watchdog_stop_file = "{0}/TEST_DONE".format(self.fcov_dir)
        self.fcov_merged_xml    = "{0}/FCOV_MERGED.xml".format(self.fcov_dir, datetime.now().strftime("%Y-%m-%d_%H:%M:%S"))
        self.watchdog_merge_notification_interval = 10
        self.watchdog_merge_procs                 = int((mproc+7)/8)
        os.system("rm -rf {0} && mkdir -p {0}".format(self.fcov_dir))

    # -------------------------------
    def fcov_collection_daemon(self):
        id    = 0
        pool  = multiprocessing.Pool(int(os.cpu_count()/2))
        while True:
            xml_queue = [str(p) for p in Path(self.fcov_input_dir).glob("**/*_fc4sc_results.xml") if (str(p) not in self.merged_xml_list)]
            if ((os.path.exists(self.watchdog_stop_file)) and (len(xml_queue)<=1)):
              for p in self.procs:
                  p.wait()
              if (len(xml_queue)==1):
                os.remve(self.fcov_merged_xml) if os.path.exists(self.fcov_merged_xml) else None
                os.symlink(xml_queue[0], self.fcov_merged_xml)
              break
            while (len(xml_queue) > 1):
                id   += 1
                merged_xml = "{0}/merge_{1}_fc4sc_results.xml ".format(self.fcov_dir, id)
                log = merged_xml.replace(".xml", ".log")
                cmd = "python {0} --merge_to_db {1}".format(self.fcov_merge_tool, merged_xml)
                count = 0
                xml_list = []
                while (count<self.MERGE_BATCH_SIZE):
                    xml_list.append(xml_queue.pop(0))
                    count += 1
                    if (0==len(xml_queue)): break
                cmd += " ".join(xml_list)
                self.merged_xml_list += xml_list
                print("FCOV_DEBUG:", id, ":", cmd) #FIXME: remove it
                self.procs.append(pool.apply_async(os.system, (cmd,)))
            time.sleep(self.watchdog_merge_notification_interval)


    # -------------------------------
    def upload_fcov_yaml(self, fc4sc_yaml, scope, description):
      git_branch  = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip().decode("utf-8")
      ci_build    = os.environ["CI_BUILD_NAME"]       if "CI_BUILD_NAME" in os.environ else "Unknown CI_BUILD_NAME"
      ci_pipe     = os.environ["CI_PIPELINE_ID"]      if "CI_PIPELINE_ID" in os.environ else "Unknown CI_PIPELINE_ID"
      branch      = os.environ["CI_COMMIT_REF_NAME"]  if "CI_COMMIT_REF_NAME" in os.environ else git_branch

      print ('         -> Connecting to fcov MongoDB...')
      sys.stdout.flush()

      mongoclient = MongoClient('mongodb://zlogger:zlogger@nextstep:30002/zversim', serverSelectionTimeoutMS=5000)
      db = mongoclient.zversim
      collection = db.fcov4
      with open(fc4sc_yaml,"r") as yml:
          upload_docs = [ { 'scope'       : scope,
                            'data'        : d,
                            'ci-build'    : ci_build,
                            'ci-pipe'     : ci_pipe,
                            'git-branch'  : branch,
                          # 'env' : safe_env,
                            'description' : description
                            } for d in yaml.load(yml) ]
          try:
              res = collection.insert_many(upload_docs)
              print("Uploaded %d docs for branch(%s)" % (len(res.inserted_ids),branch))
          except pymongo.errors.ServerSelectionTimeoutError as e:
              print ("Warning - the fcov result might not be in the DB due to the following exception:")
              print (e)


    # -------------------------------
    def start_fcov_watchdog(self):
        p = multiprocessing.Process(target=self.fcov_collection_daemon, args=())
        p.start()
        self.procs.append(p)

    # -------------------------------
    def stop_fcov_watchdog(self):
        # Stop wathchdog
        open(self.watchdog_stop_file, 'a').close()
        for p in self.procs:
            p.join()
        self.procs.clear()

        # Generate and upload fcov .txt report
        print("         -> Generate fcov report")
        report = ""
        # Report fcov_grade_*_full.txt
        for grade in range(3,0,-1):
            report = "{0}/fcov_grade_{1}_full.txt".format(self.fcov_dir, grade)
            cmd = "python3 {0} --xml_report {1} --report --report_grade {2} --apply_grade_file {3} --report_misses --report_hits > {4} ".format(self.fcov_report_tool, self.fcov_merged_xml, grade, self.fcov_grade_file, report)
            self.procs.append(self.pool.apply_async(os.system, (cmd,)))
        # Report fc4sc_yaml
        print("         -> Generate fcov final .yaml report")
        fc4sc_yaml = "{0}.yaml".format(self.fcov_merged_xml)
        cmd = "python3 {0} --xml_report {1} --apply_grade_file {2} --yaml_out {3} ".format(self.fcov_report_tool, self.fcov_merged_xml, self.fcov_grade_file, fc4sc_yaml)
        print(cmd)
        self.procs.append(self.pool.apply_async(os.system, (cmd,)))
        for p in self.procs:
            p.wait()
        self.procs.clear()
        # Upload
        print("         -> Upload fcov final .yaml report")
        self.upload_fcov_yaml(fc4sc_yaml, 'tb-tensix', 'Blockhole TB Tensix Jenkin FCOV run')


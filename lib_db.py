#! /usr/bin/env python3

import argparse
import re
import os, sys, platform
import pymongo
import collections
from pprint import pprint
import operator
import hashlib
import subprocess
import datetime
from pymongo import MongoClient
from statistics import mean
from pathlib import Path

ROOT = subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).decode().strip('\n')
sys.path.append(os.path.join(ROOT, 'infra'))

TIME_ME=False  # Set to 'True' to log time each step takes
TIME_ME_TS=None
TIME_ME_CURRENT_STEP=None

def time_me(starting="", done=False):
    global TIME_ME, TIME_ME_TS, TIME_ME_CURRENT_STEP
    if not TIME_ME:
        return
    ts = datetime.datetime.now()
    if TIME_ME_TS is None:
        print("TIME_ME: [start time] %s" % (ts))
    else:
        print("TIME_ME: [%s] took: %s" % (TIME_ME_CURRENT_STEP, ts-TIME_ME_TS))
    if not done:
        print("TIME_ME: [%s] starting" % (starting))
        TIME_ME_TS=ts
        TIME_ME_CURRENT_STEP=starting

time_me(starting="Initialization")

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

sys.path.append(os.path.join(os.path.dirname(__file__)))

def get_safe_env():
    safe_vars = {
        "CI_PROJECT_PATH",            # :       "tensix",
        "CI_PIPELINE_SOURCE",         # :  "CI_Trigger",
        "CI_JOB_STAGE",               # :       "post-commit",
        "GITLAB_USER_LOGIN",          # :       "ihamer",
        "CI_BUILD_STAGE",             # :       "post-commit",
        "CI_PIPELINE_ID",             # :       "5556",
        "USER",                       # :  "Runner",
        "CI_COMMIT_SHA",              # :  "Commit",
        "CI_COMMIT_AUTHOR",           # :  "Commit Author"
        "SHELL",                      # :       "/bin/bash",
        "CI_COMMIT_REF_NAME",         # :  "CI Branch",
        "CI_JOB_ID",                  # :       "14225",
        "CI_BUILD_ID",                # :       "14225",
        "CI_PROJECT_PATH_SLUG",       # :       "tensix",
        "CI_JOB_NAME",                # :  "CI Job Name",
        "CI_RUNNER_DESCRIPTION",      # :       "kozmo",
        "CI_BUILD_NAME",              # :       "post-commit",
        # The ones below are added by us (ie. they are not part of OS environment or Gitlabs vars)
        "CI_ZVERSIM_JOB_DESCRIPTION", # : "Description"
        "CI_ZVERSIM_SCRIPT"
    }
    env = { }
    for var in os.environ:
        if var in safe_vars:
            env[var] = os.environ[var]
    return env

parser = argparse.ArgumentParser(description='Test output parser 0.1. This program parses output of tests and reports the stats.')
parser.add_argument('--indir', help="The path to the output of test runs.", required=True)
parser.add_argument('--nodb', action='store_true', default=False, help="Will not write results to db.", required=False)
parser.add_argument('--genargs', action='store_true', default=False, help="Prints genargs of each failed signature.", required=False)
parser.add_argument('--testname', action='store_true', default=False, help="Prints run ids grouped by test name for each signature.", required=False)
parser.add_argument('--ignore_incomplete', dest="ignore_incomplete", action='store_true', default=False, help="Ignore incomplete tests", required=False)
parser.add_argument('--test_pass_pct', help="Check that test pass % is greater than given pct or exit non-zero", type=float, required=False )
parser.add_argument('--rm_passing_ttx', help="Remove TTX files of passing tests", action='store_true', required=False )
parser.add_argument('--rm_passing_log', help="Remove log files of passing tests", action='store_true', required=False )
parser.add_argument('--tag_ovrd', help="additional tag that overrides error sig detection", type=str, required=False )
parser.add_argument('--limit_ttx_run_size', type=int, help='Trims ttx file to be under argument size in MB', required=False)
parser.add_argument('--rm_passing_gen',help='Remove gen files of passing tests',action='store_true',required=False)
parser.add_argument('--clean_fcov_merge',help='Remove intermediate merge files',action='store_true',required=False)
args = parser.parse_args()

all_tags_matcher = re.compile ('[<][^>]*[>](.*)')
notatag_matcher = re.compile ('notatag')


run_id_to_metrics = { }  # for storing SIM-CYCLES-PER-SECOND , etc

tag_descriptors = {
    "SIM-CYCLES" : {
        'help' : 'Total number of clk cycles in test',
        'custom_matcher' : { 'target' : run_id_to_metrics,
                             're' : all_tags_matcher,
                             'extractor' : lambda re: int(re.group(1)) }
    },
    "SIM-WALLTIME-SECONDS" : {
        'help' : 'Total walltime for the test',
        'custom_matcher' : { 'target' : run_id_to_metrics,
                             're' : all_tags_matcher,
                             'extractor' : lambda re: float(re.group(1)) }
    },
    "SIM-CYCLES-PER-SECOND" : {
        'help' : 'Average clk cycles per second',
        'custom_matcher' : { 'target' : run_id_to_metrics,
                             're' : all_tags_matcher,
                             'extractor' : lambda re: int(re.group(1)) }
    },
    "TEST-FAILED" : {
        'help' : 'Presence of this tag indicates that the run has failed'
    },
    "TEST-PASSED" : {
        'help' : 'Presence of this tag indicates that the run was successful'
    },
    "BUILDARGS" : {
        'help' : 'Arguments passed to the build stage',
        'arg_matcher' : all_tags_matcher,
        'custom_matcher': [{ 're' : re.compile('\\bTEST=(\\S+)'),
                            'extractor' : lambda re: re.group(1),
                            'tag' : 'TEST',
                            'target' : run_id_to_metrics },
                           { 're' : re.compile('\\bSUITE=(\\S+)'),
                             'extractor' : lambda re: re.group(1),
                             'tag' : 'SUITE',
                             'target' : run_id_to_metrics },
                           { 're' : re.compile('\\bSIM=(\\S+)'),
                             'extractor' : lambda re: re.group(1),
                             'tag' : 'SIM',
                             'target' : run_id_to_metrics },
                           { 're' : re.compile('\\bTENSIX_GRID_SIZE=(\\S+)'),
                             'extractor' : lambda re: re.group(1),
                             'tag' : 'TENSIX_GRID_SIZE',
                             'target' : run_id_to_metrics } ]
    },
    "GENARGS" : {
        'help' : 'Arguments passed to generator',
        'arg_matcher' : all_tags_matcher
    },
    "SIMARGS" : {
        'help' : 'Arguments passed to simulator',
        'arg_matcher' : all_tags_matcher
    },
    "PLUSARGS" : {
        'help' : 'Arguments passed to simulator and passed on to Verilog runtime',
        'arg_matcher' : all_tags_matcher
    },
    "TESTDEF" : {
        'help' : 'The test definition file',
        'arg_matcher' : all_tags_matcher
    }
}

def DEBUG (s):
    # print (s)
    return

def strhash (s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def isahexdigit(char):
    if char == '0':
        return 1
    if char == '1':
        return 1
    if char == '2':
        return 1
    if char == '3':
        return 1
    if char == '4':
        return 1
    if char == '5':
        return 1
    if char == '6':
        return 1
    if char == '7':
        return 1
    if char == '8':
        return 1
    if char == '9':
        return 1
    if char == 'a':
        return 1
    if char == 'b':
        return 1
    if char == 'c':
        return 1
    if char == 'd':
        return 1
    if char == 'e':
        return 1
    if char == 'f':
        return 1
    return 0

#Determine if hash is in EXIT-SIG or not
#returns the proper hash depending on whether or not it is in the exit-sig
def calchash (s):
    if s.find('<EXIT-SIG>') != -1:
        exit = s.find('<EXIT-SIG>')
    if s.find('ASSERTION FAILED') != -1:
        exit = s.find('ASSERTION FAILED')
    if s.find('<EXIT-SIG>') == -1 and s.find('ASSERTION FAILED') == -1:
        return strhash(s)
    start = exit + 10
    while s[start] != '<':
        if s[start] == '\n' or start == len(s) - 1:
            return strhash(s)
        start += 1
    if start != exit:
        if isahexdigit(s[start + 1]):
            end = start
            while s[end] != '>':
                end += 1
            return s[start+1:end]
    return strhash(s)

# If we have never seen the tag
known_tags = set()
def unrecognized_tag (tag):
    if not tag in known_tags:
        known_tags.add (tag)
        DEBUG ("Warning (onetime): unrecognized tag: %s" % (tag))

tag_to_run_id_map = { }

set_of_all_run_ids = set()

def process_tag (tag, run_id):
    if tag    not in tag_to_run_id_map: tag_to_run_id_map[tag]    = set()
    tag_to_run_id_map[tag].add (run_id)

    if tag not in tag_descriptors:
        unrecognized_tag (tag)



NUM_SIG_LINES = 7
run_id_to_run_signature = { }
run_id_to_timestamp_of_first_exit_signature = { }
run_id_to_args = { }  # for storing GENARGS, SIMARGS, PLUSARGS

# Match tags in form of <mytag>
tag_matcher = re.compile('[<]([^>]*)[>]')
if args.tag_ovrd is not None:
    tag_matcher_ovrd = re.compile(args.tag_ovrd)

sig_remove_timestamp_matcher_1 = re.compile('\\s\[(\d+)\]\\s')   # Example match: " [12500] " 
sig_remove_timestamp_matcher_2 = re.compile('\\bt[.](\d+)')      # Example match: "t.12500"
sig_remove_timestamp_matcher_3 = re.compile('Time: \d+')         # Example match: "Time: 12500"
sig_remove_coreid_matcher      = re.compile('\[\d+-\d+\]')       # Example match: "[0-3]"
sig_remove_txnid_matcher       = re.compile('\(\d+\)')           # Example match: "(123)"
sig_remove_testid_matcher      = re.compile('id->\d+')           # Example match: "id->19"
sig_remove_timeout_matcher     = re.compile('timeout at [0-9]+') # Example match: "due to timeout at 90000 cycles"
sig_remove_match_ratio         = re.compile('match_ratio\((\d+).(\d+)\)')     # Example match: "match_ratio(99.4567)"
sig_remove_min_match_ratio     = re.compile('min_match_ratio\((\d+).(\d+)\)') # Example match: "min_match_ratio(99.4567)"
sig_remove_bin_counts          = re.compile('Count: (\d+) \((\d+).(\d+)\%\)') # Example match: "Count: 428 (5.22%)"
sig_remove_lsb_counts          = re.compile('lsb corrections:\s*\d+')  # Example match: "1-lsb corrections:	55"
sig_remove_flt_counts          = re.compile('float corrections:\s*\d+')  # Example match: "infinity == BIG float corrections:	126"
sig_remove_pointer             = re.compile('pointer to [a-f0-9]+')    # Example match: "read pointer to 0 and write pointer to 4b0"
sig_remove_assign              = re.compile('(?<!>|<)=\s*[_xa-f0-9]+') # Example match: "= 16", "= 0b1001", = 0x40c01000"
sig_remove_num                 = re.compile('[#][xa-f0-9]+')     # Example match: "#123"
sig_remove_hex                 = re.compile('0x[_a-f0-9x]+')      # Example match: "= 16", "= 0b1001", = 0x40c01000"
sig_remove_txn                 = re.compile('\[txn[_a-f0-9]+\]') # Example match: "txn_123", "t0"
sig_remove_hash                = re.compile('[a-f0-9]{64}')
sig_remove_log_info            = re.compile('.*(TVM_NONE|TVM_LOW|TVM_MED|TVM_HIGH|TVM_FULL|LOG -|EVENT -).*')   # Example match: "[  @45001] TVM_LOW ..."

# Filters out irrelevant stuff from the exit signature 
def filter_sig_line (l):
    nl = sig_remove_timestamp_matcher_1.sub(' t.-- ', l)
    nl = sig_remove_timestamp_matcher_2.sub('t.--', nl)
    nl = sig_remove_coreid_matcher.sub ('[x-y]', nl)
    nl = sig_remove_txnid_matcher.sub ('(--)', nl)
    nl = sig_remove_testid_matcher.sub ('id->--', nl)
    nl = sig_remove_timeout_matcher.sub ('timeout at --', nl)
    nl = sig_remove_timestamp_matcher_3.sub ('Time: --', nl)
    nl = sig_remove_bin_counts.sub ('Count: -- (--)', nl)
    nl = sig_remove_lsb_counts.sub ('lsb corrections: --', nl)
    nl = sig_remove_flt_counts.sub ('float corrections: --', nl)
    nl = sig_remove_pointer.sub ('pointer to --', nl)
    nl = sig_remove_log_info.sub ('', nl)
    nl = sig_remove_assign.sub ('=...', nl)
    nl = sig_remove_num.sub ('...', nl)
    nl = sig_remove_hex.sub ('0x...', nl)
    nl = sig_remove_txn.sub ('[txn--]', nl)
    nl = sig_remove_hash.sub ('--hash--', nl)
    nl = sig_remove_match_ratio.sub('match_ratio(--.---)', nl)
    nl = sig_remove_min_match_ratio.sub('min_match_ratio(--.---)', nl)

    ratio = sig_remove_match_ratio.search(nl)
    if ratio:
        ratio_value = int(ratio.group(1))
        val = str(ratio_value - ratio_value%10)
        if ratio_value <= 30:
            val = "below 30"
        elif ratio_value <= 80:
            val = "below 80"

    return nl

def get_timestamp (l):
    timestamp = -1
    m = sig_remove_timestamp_matcher_1.search (l)
    if m:
        timestamp = int(m.group (1))
    m = sig_remove_timestamp_matcher_2.search (l)
    if m:
        timestamp = int(m.group (1))
    return timestamp

def get_testname (l):
    t = "undefined"
    for setting in l.split(' '):
        testarg = re.compile('TEST=')
        m = testarg.search(setting)
        if m:
            t = testarg.sub('', setting)
    return t.strip()

def get_arg_match (l, p):
    for setting in l.split(' '):
        m = re.match(p,setting)
        if m:
            return True

exit_sig_lines = collections.deque(maxlen=NUM_SIG_LINES)
previous_lines  = collections.deque(maxlen=2)

# Skip first four ('run_') and last four (".log") chars
# sorted_filename_list = sorted (os.listdir(args.indir), key = lambda x: int(x[4:][:-4]))

time_me(starting="Log parsing")

run_id = -1 
for filename in [str(p) for p in Path(args.indir).rglob("vcs_run.log")]:
    with open(filename) as f:
        run_id += 1
        set_of_all_run_ids.add(run_id)

        #print ("filename = "+ filename + " run_id = " + str(run_id))
        line_num = 0
        timestamp_of_first_exit_sign = -1
        last_timestamp = -1
        properly_exited = False   # with test-passed or test-failed
        run_id_to_args[run_id] = {}
        run_id_to_metrics[run_id] = { 'run_id' : run_id }
        for line in f:
            line_num = line_num + 1
            notatag = False
            m = tag_matcher.search (line)
            if args.tag_ovrd is not None:
                ovrd = tag_matcher_ovrd.search (line)
            else:
                ovrd = False
            if m:
                notatag = notatag_matcher.search(line)
            if (m or ovrd) and not notatag:
                if (m):
                    tag = m.group (1)
                else:
                    tag = ovrd.group (1)
                #print ("processing tag: " + tag)
                process_tag (tag, run_id)
                timestamp = get_timestamp(line)
                if timestamp >= 0:
                  last_timestamp = timestamp

                # Check for exit signature and grab some data about it
                if (tag == "EXIT-SIG" or ovrd) and timestamp_of_first_exit_sign == -1:
                    #print ("found EXIT-SIG on line: " + line.rstrip('\n') )
                    # Get timestamp of sig
                    timestamp_of_first_exit_sign = int (get_timestamp (line) if timestamp_of_first_exit_sign == -1 else timestamp_of_first_exit_sign)
                    if timestamp_of_first_exit_sign == -1:
                      timestamp_of_first_exit_sign = last_timestamp # get last seen timestamp if we don't have one in this line

                    # Append the line to the exit_sig together with past few lines if not already there
                    for pl in previous_lines:
                        if pl not in exit_sig_lines:
                            exit_sig_lines.append (filter_sig_line(pl))
                    nl = filter_sig_line (line)
                    if nl != '':
                        exit_sig_lines.append (nl)
                    #for exit_lines in exit_sig_lines:
                        #print ("        exit_sig_lines:       "+exit_lines.rstrip('\n'))

                # Check if properly exited
                if tag == "TEST-PASSED" or tag == "TEST-FAILED":
                    properly_exited = True

                #for mytag in tag_descriptors:
                #    print ("FoundTags: " + mytag)
                # Check if the tag contains the arguments (genargs, simargs...)
                if tag in tag_descriptors and 'arg_matcher' in tag_descriptors[tag]:
                    arg_matcher = tag_descriptors[tag]['arg_matcher']
                    m = arg_matcher.search (line)
                    if m:
                        tag_arg = m.group (1)
                        run_id_to_args[run_id][tag] = tag_arg.strip()

                # Check if the tag contains metrics
                if tag in tag_descriptors and 'custom_matcher' in tag_descriptors[tag]:
                    matchers = tag_descriptors[tag]['custom_matcher']
                    if not isinstance(matchers, list):
                        matchers = [matchers]
                    for matcher in matchers:
                        m = matcher['re'].search(line)
                        if m:
                            tag_arg = matcher['extractor'](m)
                            if 'tag' in matcher:
                                tag = matcher['tag']
                            matcher['target'][run_id][tag] = tag_arg
                            #print("tty2:"+ matcher['target'][run_id][tag])
            else:
                if line != '':
                    previous_lines.append (line)

        #if properly_exited:
        #    print ("properly_exited")
        if not properly_exited  and not args.ignore_incomplete:
            #print ('TEST DID NOT PROPERTLY EXITEDDD')
            process_tag ('TEST-FAILED', run_id)  # Attach a failed tag
            process_tag ('EXIT-SIG', run_id)  # Attach a failed tag
            #exit_sig_lines = previous_lines.copy()
            # Can't copy previous lines like this, or the maxlen will be copied, too... need to transfer one by one
            for pl in previous_lines:
              cpu_time = "CPU Time"
              date_vcs = r"\w\w\w \w\w\w \d\d? \d\d?:\d\d?:\d\d? \d\d\d\d"
              if re.search(cpu_time, pl) == None:
                if re.search(date_vcs, pl) == None:
                    if filter_sig_line(pl) not in exit_sig_lines:
                      exit_sig_lines.append(filter_sig_line(pl))
            exit_sig_lines.append("<EXIT-SIG> Crashed")
            #for exit_lines in exit_sig_lines:
            #  print ("        FINAL exit_sig_lines:       "+exit_lines.rstrip('\n'))

        #print(run_id_to_metrics[run_id])

        
        run_id_to_run_signature[run_id] = exit_sig_lines.copy()
        #run_id_to_run_signature[run_id] = sorted(exit_sig_lines).copy()
        run_id_to_timestamp_of_first_exit_signature[run_id] = timestamp_of_first_exit_sign
        exit_sig_lines.clear()

time_me(starting="Signature processing")

passed_test_ids = tag_to_run_id_map.get ("TEST-PASSED", set())
failed_test_ids = tag_to_run_id_map.get ("TEST-FAILED", set())

#print ("passed test: "+str(len(passed_test_ids)))
#print ("failed test: "+str(len(failed_test_ids)))

# See if there are any tests that did not print the PASS/FAIL tag
properly_exited_tests = passed_test_ids.copy()
properly_exited_tests.update (failed_test_ids)
properly_exited_tests = [i for i in properly_exited_tests]

not_properly_exited_tess = set_of_all_run_ids.difference (properly_exited_tests)

# Not necessary with summary now reporting crash/impcomplete
# for test_id in not_properly_exited_tess:
#     print ("Warning: Test %d did not exit with TEST-PASSED or TEST-FAILED tag" % test_id)

# Find tests that failed without exit signature
proper_exit_sig_tests = tag_to_run_id_map.get ("EXIT-SIG", {})
for test_id in failed_test_ids.difference (proper_exit_sig_tests):
    print ("Warning: Test %d FAILED without EXIT-SIG" % test_id)

# Collect fail signatures and hashes
hash_to_failed_run_ids = dict()
hash_to_signature = dict()
for id in proper_exit_sig_tests:
    sig = run_id_to_run_signature[id]
    sig_str = ''.join (sig)
    hsh = calchash(sig_str)
    if hsh not in hash_to_failed_run_ids:
        hash_to_failed_run_ids[hsh] = set ()
        hash_to_signature[hsh] = sig_str
    hash_to_failed_run_ids[hsh].add (id)

SEPARATOR = "======================================================================================================"
print (SEPARATOR)

# Print the signature information
sig_id = 1
for hsh in sorted (hash_to_failed_run_ids):
    sig = hash_to_signature[hsh]
    failed_list = [str(i) for i in hash_to_failed_run_ids[hsh] ]
    numfail = len(hash_to_failed_run_ids[hsh])
    summary_msg = "Exit signature #%d hash: %s\n" % (sig_id, hsh)
    if numfail == 1:
        summary_msg += "Exit signature #%d occured once. Showing run_id with timestamp:" % sig_id
    else:
        summary_msg += "Exit signature #%d occured %d times. Showing a list of run_ids and timestamps sorted in order of increasing timestamp:" % (sig_id, numfail)

    timestamp_sorted_run_id_list = sorted(run_id_to_timestamp_of_first_exit_signature.items(), key=operator.itemgetter(1))
    timestamped_run_id_str = ""
    testname_to_run_id_str = { }

    print (summary_msg)
    for i in timestamp_sorted_run_id_list:
        if i[0] in hash_to_failed_run_ids[hsh]:
            timestamped_run_id_str = timestamped_run_id_str + "%d(t.%d) " % (i[0], i[1] )
            testname = get_testname(run_id_to_args[int(i[0])].get('BUILDARGS', ''))

            # Temporarily parse stream arg during bringup
            if get_arg_match(run_id_to_args[int(i[0])].get('GENARGS', ''), '--stream'):
                testname = testname + "(stream)"

            testname_to_run_id_str[testname] = testname_to_run_id_str.get(testname, "") + "%d(t.%d) " % (i[0], i[1] )

    if args.testname:
        for i in testname_to_run_id_str:
            testname_str = i + "\t " + testname_to_run_id_str[i]
            print (bcolors.OKGREEN + testname_str.expandtabs(30) + bcolors.ENDC)
    else:
        print (bcolors.OKGREEN + timestamped_run_id_str + bcolors.ENDC)

    # Print the Genargs of each failed run
    if args.genargs:
        for run_id in hash_to_failed_run_ids[hsh]:
            print ("Failed run %4d genargs: %s" % (run_id, run_id_to_args[run_id]['GENARGS']))

    print ("")
    print (bcolors.FAIL + sig.rstrip() + bcolors.ENDC)
    print (SEPARATOR)
    sig_id = sig_id + 1

# Hash to signature dict
hashed_exit_signatures = { }
signature_hash_to_run_ids = { }
for hsh in hash_to_failed_run_ids:
    sig = hash_to_signature[hsh]
    hashed_exit_signatures[hsh] = sig
    signature_hash_to_run_ids[hsh] = list(sorted(hash_to_failed_run_ids[hsh]))

if args.rm_passing_gen:
    for id in passed_test_ids:
        path = "out/gen/gen_%s.log" % id
        if os.path.exists(path):
            os.remove(path)

if args.clean_fcov_merge:
    path = "out/reports/"
    if os.path.exists(path):
        for file in os.listdir(path):
            if file.find('.xml_proc') != -1:
                filepath = path + file
                if os.path.exists(filepath):
                    os.remove(filepath)

if args.rm_passing_ttx:
    for id in passed_test_ids:
        if id in run_id_to_args and "TESTDEF" in run_id_to_args[id]:
            td = "%s.ttx" % (run_id_to_args[id]["TESTDEF"])
            if os.path.exists(td):
                os.remove(td)

if args.rm_passing_log:
    for id in passed_test_ids:
        path = "out/run/run_%s.log" % id
        if os.path.exists(path):
            os.remove(path)

run_id_to_ttx_size = { }
run_id_to_run_size = { }
if args.limit_ttx_run_size:
    max_size = args.limit_ttx_run_size * 1048576
    #calcualte total size
    total_size_MB = 0
    for id in set_of_all_run_ids:
        if id in run_id_to_args and "TESTDEF" in run_id_to_args[id]:
            td = "%s.ttx" % (run_id_to_args[id]["TESTDEF"])
            if os.path.exists(td):
                run_id_to_ttx_size[id] = os.path.getsize(td)
                total_size_MB += os.path.getsize(td)
        path = "out/run/run_%s.log" % id
        if os.path.exists(path):
            run_id_to_run_size[id] = os.path.getsize(path)
            total_size_MB += os.path.getsize(path)

    #if total size is too big, shave it
    if total_size_MB > max_size:
        #first try to trim passed tests, by test size
        #sort passed test by size
        if not args.rm_passing_ttx:
            sorted_passed_tests_size = list()
            for id in passed_test_ids:
                if id in run_id_to_args and "TESTDEF" in run_id_to_args[id]:
                    td = "%s.ttx" % (run_id_to_args[id]["TESTDEF"])
                    if os.path.exists(td):
                        if len(sorted_passed_tests_size) == 0:
                            sorted_passed_tests_size.append(id)
                        else:
                            i = 0
                            while i < len(sorted_passed_tests_size):
                                if (run_id_to_ttx_size[sorted_passed_tests_size[i]] + run_id_to_run_size[sorted_passed_tests_size[i]]) > (run_id_to_ttx_size[id] + run_id_to_run_size[id]):
                                    i += 1
                                else:
                                    sorted_passed_tests_size.insert(i,id)
                            if i == len(sorted_passed_tests_size):
                                sorted_passed_tests_size.append(id)
            #remove passed tests until all are gone or size is small enough
            for id in sorted_passed_tests_size:
                if total_size_MB > max_size:
                    if id in run_id_to_args and "TESTDEF" in run_id_to_args[id]:
                        td = "%s.ttx" % (run_id_to_args[id]["TESTDEF"])
                        if os.path.exists(td):
                            os.remove(td)
                            total_size_MB -= run_id_to_ttx_size[id]
                    path = "out/run/run_%s.log" % id
                    if os.path.exists(path):
                        os.remove(path)
                        total_size_MB -= run_id_to_run_size[id]
                else:
                    break
        #if still too big
        if total_size_MB > max_size:
            #sort failed IDs based on exit time and size
            sorted_failed_tests = { }
            for id in failed_test_ids:
                if id in run_id_to_args and "TESTDEF" in run_id_to_args[id]:
                    td = "%s.ttx" % (run_id_to_args[id]["TESTDEF"])
                    if os.path.exists(td):
                        buildargs = run_id_to_args[id]['BUILDARGS']
                        index = buildargs.find('TEST=') + 5
                        i = index
                        while buildargs[i] != ' ':
                            i += 1
                        test_name = buildargs[index:i]
                        if test_name not in sorted_failed_tests:
                            sorted_failed_tests[test_name] = list()
                            sorted_failed_tests[test_name].append(id)
                        else:
                            i = 0
                            while i < len(sorted_failed_tests[test_name]):
                                if run_id_to_timestamp_of_first_exit_signature[id] < run_id_to_timestamp_of_first_exit_signature[sorted_failed_tests[test_name][i]]:
                                    i += 1
                                elif run_id_to_timestamp_of_first_exit_signature[id] == run_id_to_timestamp_of_first_exit_signature[sorted_failed_tests[test_name][i]]:
                                    if (run_id_to_ttx_size[id] + run_id_to_run_size[id]) < (run_id_to_ttx_size[sorted_failed_tests[test_name][i]] + run_id_to_run_size[sorted_failed_tests[test_name][i]]):
                                        i += 1
                                    else:
                                        sorted_failed_tests[test_name].insert(i,id)
                                        break
                                else:
                                    sorted_failed_tests[test_name].insert(i,id)
                                    break
                            if i == len(sorted_failed_tests[test_name]):
                                sorted_failed_tests[test_name].append(id)
                    else: #if failed log file doesn't have corresponding ttx, remove them
                        path = "out/run/run_%s.log" % id
                        if os.path.exists(path):
                            os.remove(path)
            #remove failed tests until size is small enough
            while total_size_MB > max_size:
                most_entries = 'start'
                for test_name in sorted_failed_tests:
                    if most_entries == 'start':
                        most_entries = test_name
                    elif len(sorted_failed_tests[test_name]) > len(sorted_failed_tests[most_entries]):
                        most_entries = test_name
                if len(sorted_failed_tests[most_entries]) == 0:
                    print('Warning: Had to remove all files')
                    break
                id = sorted_failed_tests[most_entries][0]
                if id in run_id_to_args and "TESTDEF" in run_id_to_args[id]:
                    td = "%s.ttx" % (run_id_to_args[id]["TESTDEF"])
                    if os.path.exists(td):
                        os.remove(td)
                        total_size_MB -= run_id_to_ttx_size[id]
                        sorted_failed_tests[most_entries].pop(0)
                path = "out/run/run_%s.log" % id
                if os.path.exists(path):
                    os.remove(path)
                    total_size_MB -= run_id_to_run_size[id]

time_me(starting="Metrics pre-processing")

#
# SUMMARY
#
summary = {
    'passed' : len (passed_test_ids),
    'failed' : len (failed_test_ids),
    'exit_signature_counts' : { key: len (hash_to_failed_run_ids[key]) for key in hash_to_failed_run_ids }
}

#
# METRICS
#
metrics_unique_suites = list(set(d['SUITE'] for d in run_id_to_metrics.values() if 'SUITE' in d))


def mean_with_key(dicts, key):
    items = [d[key] for d in dicts if key in d]
    if not items:
        return 0
    return mean(items)

metrics = {
  'overall' : {
      'avg-cycles-per-second': mean_with_key(run_id_to_metrics.values(), 'SIM-CYCLES-PER-SECOND'),
      'avg-walltime-seconds': mean_with_key(run_id_to_metrics.values(), 'SIM-WALLTIME-SECONDS'),
      'avg-cycles': mean_with_key(run_id_to_metrics.values(), 'SIM-CYCLES'),
      'total-passed': len(passed_test_ids),
      'total-failed': len(failed_test_ids),
      'total-tests': len(set_of_all_run_ids),
      'total-crash': len(not_properly_exited_tess),
      'pct-pass': (100*len(passed_test_ids))/float(len(set_of_all_run_ids)),
      'pct-fail': (100*len(failed_test_ids))/float(len(set_of_all_run_ids)),
      'pct-crash': (100*len(not_properly_exited_tess))/float(len(set_of_all_run_ids)),
  },
  'by-suite' : {}
}

def color_pass_pct(pass_pct,thing=None):
    """ Returns colored string """
    if(pass_pct >= 100.0):
        color = bcolors.OKGREEN
    elif(pass_pct >= 80.0):
        color = bcolors.OKBLUE
    elif(pass_pct >= 50.0):
        color = bcolors.WARNING
    else:
        color = bcolors.FAIL
    if(thing==None):
        thing = "%6.2f%%" % (pass_pct)
    return color + thing + bcolors.ENDC


results_by_test_by_param_value = {}


def param_record(test,type,name,val,result):
    param_name_value = "%s__%s__%s" % (type,name,val)
    if result not in ['pass','fail','crash']:
       return # TODO: Print warning
    if name in [ "seed" ]:
        return None
    if test not in results_by_test_by_param_value:
        results_by_test_by_param_value[test] = {}
    if param_name_value not in results_by_test_by_param_value[test]:
        results_by_test_by_param_value[test][param_name_value] = {
            'param-name' : name,
            'param-value' : val,
            'param-name-value' : param_name_value,
            'pass' : 0,
            'fail' : 0,
            'crash': 0 }
    results_by_test_by_param_value[test][param_name_value][result] += 1
    return param_name_value

for suite in metrics_unique_suites:
    tests = [d for d in run_id_to_metrics.values() if d.get('SUITE','') == suite]
    tests_passed = [d for d in tests if d['run_id'] in passed_test_ids]
    tests_failed = [d for d in tests if d['run_id'] in failed_test_ids]
    num_tests_not_properly_exited = len(tests) - (len(tests_passed)+len(tests_failed))
    metrics['by-suite'][suite] = { 'avg-cycles-per-second': mean_with_key(tests, 'SIM-CYCLES-PER-SECOND'),
                                 'avg-walltime-seconds': mean_with_key(tests, 'SIM-WALLTIME-SECONDS'),
                                 'avg-cycles': mean_with_key(tests, 'SIM-CYCLES'),
                                 'total-passed': len(tests_passed),
                                 'total-failed': len(tests_failed),
                                 'total-tests': len(tests),
                                 'total-crash': num_tests_not_properly_exited,
                                 'pct-of-total-runs': (100*len(tests))/float(len(set_of_all_run_ids)),
                                 'pct-pass': (100*len(tests_passed))/float(len(tests)),
                                 'pct-fail': (100*len(tests_failed))/float(len(tests)),
                                 'pct-crash': (100*num_tests_not_properly_exited)/float(len(tests)),
                                 'runs' : {}}
    mbt = metrics['by-suite'][suite]
    for test in tests:
        run_id = test['run_id']
        res = "crash"
        if run_id in [t['run_id'] for t in tests_passed]:
            res = "pass"
        elif  run_id in [t['run_id'] for t in tests_failed]:
            res = "fail"
        rid_metrics = {
            'result' : res,
            'genargs' : []
        }
        for m in ['SIM-CYCLES-PER-SECOND',
                  'SIM-WALLTIME-SECONDS',
                  'SIM-CYCLES']:
            if m in test:
                rid_metrics[m] = test[m]
        mbt['runs'][run_id] = rid_metrics
        # Gather genargs
        if "GENARGS" in run_id_to_args[run_id]:
            for setting in run_id_to_args[run_id]["GENARGS"].split(' '):
                m = re.match("--(\S+)=(\S+)",setting)
                if m:
                    param_name_value=param_record(test=test['TEST'], type="genarg",name=m.group(1),val=m.group(2),result=res)
                    if param_name_value is not None:
                        rid_metrics["genargs"].append(( m.group(1), m.group(2), param_name_value ))


print ('')
print (bcolors.UNDERLINE + 'Summary By Suite:' + bcolors.ENDC)
print ('')
metrics_unique_suites.sort()
for suite in metrics_unique_suites:
    print (' %s:     Passed: %5d (%s)   Failed: %5d (%6.2f%%)   Total: %5d (%6.2f%%)   Crashed: %5d (%6.2fd%%)  Average CPS: %4d   Average Cycles:   %8d   Average Walltime: %6d (seconds)'
           % (color_pass_pct(metrics['by-suite'][suite]['pct-pass'],"%20s"%(suite)),
              metrics['by-suite'][suite]['total-passed'], color_pass_pct(metrics['by-suite'][suite]['pct-pass']),
              metrics['by-suite'][suite]['total-failed'], metrics['by-suite'][suite]['pct-fail'],
              metrics['by-suite'][suite]['total-tests'], metrics['by-suite'][suite]['pct-of-total-runs'],
              metrics['by-suite'][suite]['total-crash'], metrics['by-suite'][suite]['pct-crash'],
              metrics['by-suite'][suite]['avg-cycles-per-second'],
              metrics['by-suite'][suite]['avg-cycles'],
              metrics['by-suite'][suite]['avg-walltime-seconds']))
print ('')
print (bcolors.UNDERLINE + 'Summary:' + bcolors.ENDC)
print ('')
print ('  Total:            %d' % (metrics['overall']['total-tests']))
print ('  Passed:           %d (%s)' % (summary['passed'], color_pass_pct(metrics['overall']['pct-pass'])))
print ('  Failed:           %d (%6.2f%%)' % (summary['failed'], metrics['overall']['pct-fail']) )
print ('  Crash:            %d (%6.2f%%)' % (metrics['overall']['total-crash'], metrics['overall']['pct-crash']) )
print ('  Average CPS:      %d' % metrics['overall']['avg-cycles-per-second'])
print ('  Average Cycles:   %d' % metrics['overall']['avg-cycles'])
print ('  Average Walltime: %d (seconds)' % metrics['overall']['avg-walltime-seconds'])
print ('')
print ("Number of distinct fail signatures: %d" % len(summary['exit_signature_counts']))
print ('')

def flatten_metrics_for_kibana(metrics, safe_env):
    time_me(starting="Metrics flattening")
    import tensix.workspace
    import datetime
    import getpass
    import platform
    # http://api.mongodb.com/python/current/examples/datetimes.html
    utc_time = datetime.datetime.utcnow()
    username = getpass.getuser()
    plat_sys = platform.system()
    host = platform.node()
    # When running under CI we are on a detached head and can get the branch
    # via normal means so use CI_COMMIT_REF_NAME.
    if "CI_COMMIT_REF_NAME" in safe_env:
        branch = safe_env["CI_COMMIT_REF_NAME"]
    else:
        try:
            branch = tensix.workspace.current_git_branch()
        except Exception as e:
            print(e)
            pass

    if "CI_BUILD_NAME" in safe_env:
        ci_build = safe_env["CI_BUILD_NAME"]
    else:
        ci_build = "unknown-build"

    if "CI_PIPELINE_ID" in safe_env:
        ci_pipe = safe_env["CI_PIPELINE_ID"]
    else:
        ci_pipe = "unknown-pipe"

    om = metrics['overall'].copy()
    om['metric-type'] = 'run-overall'
    om['branch'] = branch
    om['ci-build'] = ci_build
    om['ci-pipe'] = ci_pipe
    om['uct_time'] = utc_time
    om['user'] = username
    om['system'] = plat_sys
    om['host'] = host
    res = [ om ]
    for test_name, test_metrics in metrics['by-suite'].items():
        tm = test_metrics.copy()
        runs = tm.pop('runs') # We'll flatten these below into their own items
        tm['metric-type'] = 'test-overall'
        tm['branch'] = branch
        tm['uct_time'] = utc_time
        tm['test-name'] = test_name
        tm['user'] = username
        tm['host'] = host
        tm['system'] = plat_sys
        res.append(tm)
        if len(results_by_test_by_param_value) > 0:
            for pnv, d in results_by_test_by_param_value[test_name].items():
                pm = d.copy()
                total = d['pass'] + d['fail'] + d['crash']
                pm['metric-type'] = 'param-test-overall'
                pm['uct_time'] = utc_time
                pm['test-name'] = test_name
                pm['param-name'] = d['param-name']
                pm['param-value'] = d['param-value']
                pm['param-name-value'] = pnv
                pm['pct-fail'] = (100*d['fail'])/total
                pm['pct-pass'] = (100*d['pass'])/total
                pm['pct-crash'] = (100*d['crash'])/total
                pm['count'] = d['fail'] + d['pass'] + d['crash']
                pm['branch'] = branch
                pm['user'] = username
                pm['system'] = plat_sys
                pm['host'] = host
                res.append(pm)
            for run_id, rid_metric in runs.items():
                rm = rid_metric.copy()
                genargs = rm.pop('genargs') # We'll flatten below
                rm['metric-type'] = 'test-run'
                rm['run-id'] = run_id
                rm['uct_time'] = utc_time
                rm['test-name'] = test_name
                rm['branch'] = branch
                rm['user'] = username
                rm['system'] = plat_sys
                rm['host'] = host
                res.append(rm)
                for arg, value, param_name_value in genargs:
                    pm = {
                        'metric-type' : 'param',
                        'param-type' : 'genarg',
                        'branch' : branch,
                        'uct_time' : utc_time,
                        'test-name' : test_name,
                        'run-id' : run_id,
                        'result' : rm['result'],
                        'param-name' : arg,
                        'param-value' : value,
                        'param-name-value' : param_name_value,
                        'user' : username
                    }
                    for k in ['SIM-WALLTIME-SECONDS']:
                        if k in rm:
                            pm[k] = rm[k]
                    res.append(pm)
    return res


#
# DB
#
if not args.nodb:
    time_me(starting="Results uploading")
    print ('Connecting to DB...')
    sys.stdout.flush()

    mongoclient = MongoClient('mongodb://zlogger:zlogger@nextstep:30002/zversim', serverSelectionTimeoutMS=5000)
    db = mongoclient.zversim
    results_collection = db.results
    exit_signatures_collection = db.exit_signatures
    metrics_collection = db.metrics

    metrics['overall'].pop('total-passed')
    metrics['overall'].pop('total-failed')

    all_passed = len(failed_test_ids) == 0
    try:
        import datetime
        # 1. Store results
        exit_signatures = [ ]
        for sighash in signature_hash_to_run_ids:
            exit_sig = {
                'hash' : sighash,
                'runs' : [ {
                    'run_id'   : run_id,
                    'args'     : run_id_to_args[run_id],
                    'clk_time' : run_id_to_timestamp_of_first_exit_signature[run_id]
                } for run_id in signature_hash_to_run_ids[sighash] ]
            }
            exit_sig['runs'].sort (key=lambda x: x['clk_time'])
            exit_signatures.append (exit_sig)

        env = get_safe_env()

        # http://api.mongodb.com/python/current/examples/datetimes.html
        dt = datetime.datetime.utcnow()

        results_collection.insert_one ({
            'utc_time' : dt,
            'env' : env,
            'summary': summary,
            'exit_signatures': exit_signatures,
        })

        # 2. Store any new exit signatures
        for sig_hash in hashed_exit_signatures:
            if exit_signatures_collection.count_documents({'hash': sig_hash}) == 0:
                print ("Adding new exit signature: %s" % sig_hash)
                exit_signatures_collection.insert_one ( {
                    'hash' : sig_hash,
                    'text' : hashed_exit_signatures[sig_hash]
                })

        flat_metrics = flatten_metrics_for_kibana(metrics, env)

        time_me(starting="Metrics uploading")

        metrics_collection.insert_many(flat_metrics)

        time_me(done=True)

    except pymongo.errors.ServerSelectionTimeoutError as e:
        print ("Warning - the result might not be in the DB due to the following exception:")
        print (e)
else:
    print ('Not writing to DB')

if args.test_pass_pct is not None:
    if not metrics['overall']['pct-pass'] >= args.test_pass_pct:
        sys.exit(12) ;
    else:
        sys.exit(0) ;


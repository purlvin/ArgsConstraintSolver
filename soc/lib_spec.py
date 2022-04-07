#!/usr/bin/env python3
import yaml
import math
import re
import sys
import os
import pprint
import copy

def gen_expanded_yml(yml, outdir):
    spec = {"configs": {}, "tests": {}}
    cfg = yaml.load(open(yml), Loader=yaml.SafeLoader)
    
    # Testcases
    stream = {"configs": "", "templates": "", "testcases": ""}
    ymlout =  os.path.join(outdir, os.path.basename(yml.replace(".yml", "_expanded.yml")))
    # Expanded yml
    print('  -> Generate expended test.yml: {0}'.format(ymlout))
    f = open(ymlout, "w")
    for k,v in cfg["configs"].items():
        stream["configs"] += "  {0}: &{0}\n".format(k)
        for k1,v1 in v.items():
            if (type(v1) == list):
                stream["configs"] += "    {0}: &{1}_{0}\n".format(k1,k)
                for v2 in v1: stream["configs"] += "      - {0}\n".format(v2)
            else: 
                stream["configs"] += "    {0}: {1}\n".format(k1,v1)
    for k,v in cfg["templates"].items():
        stream["templates"] += "  {0}: &{0}\n".format(k)
        for k1,v1 in v.items():
            if (type(v1) == list):
                stream["templates"] += "    {0}: &{1}_{0}\n".format(k1,k)
                for v2 in v1: stream["templates"] += "      - {0}\n".format(v2)
            else: 
                stream["templates"] += "    {0}: {1}\n".format(k1,v1)
    for ymlin in cfg["includes"]:
        ymlin  = os.path.join(os.path.dirname(yml),ymlin)
        category = None
        for line in open(ymlin):
            if re.search("templates\s*:", line):
                category = "templates"
            elif re.search("testcases\s*:", line):
                category = "testcases"
            elif ((category) and (not re.search("^\s*#", line))):  
                stream[category] += line
    f.write("\nconfigs:\n" + stream["configs"])
    f.write("\ntemplates:\n" + stream["templates"])
    f.write("\ntestcases:\n" + stream["testcases"])
    f.close()
    cfg = yaml.load(open(ymlout), Loader=yaml.SafeLoader)
    # Dump yml
    ymlout = ymlout + ".dump"
    #print('  -> Generate test.yml postprocess file: {0}'.format(ymlout))
    f = open(ymlout, "w")
    yaml.Dumper.ignore_aliases = lambda *args : True
    f.write(yaml.dump(cfg))
    f.close()
    
    # Load per test
    spec["configs"] = cfg["configs"]
    tests   = {"groups": {}, "cases": {}}
    for test, test_hash in cfg["testcases"].items():
        def flatten_list(irregular_list):
            return [element for item in irregular_list for element in flatten_list(item)] if type(irregular_list) is list else [irregular_list]
        config = test_hash["_config"] if (test_hash["_config"] in spec["configs"]) else "UNKNOWN"
        if (test not in tests["cases"]): tests["cases"][test] = config
        for group in flatten_list(test_hash["_when"]):
            if group not in tests["groups"]: tests["groups"][group] = {}
            tests["groups"][group][test] = test_hash["_clones"] if ("_clones" in test_hash) else 1
    spec["tests"]   = tests
    return ymlout

# -------------------------------
def get_yml_spec(yml, tgt_test, tgt_group, outdir):
    yml      = gen_expanded_yml(yml, outdir)
    spec     = yaml.load(open(yml), Loader=yaml.SafeLoader)
    yml_spec = {"configs": spec["configs"], "tests": {}}
    # Load constraint groups per test
    test_spec = {}
    for test,test_hash in spec["testcases"].items():
        def flatten_list(irregular_list):
            return [element for item in irregular_list for element in flatten_list(item)] if type(irregular_list) is list else [irregular_list]
        info = {
            "id":       None,
            "base":     test,
            "config":   test_hash["_config"],
            "seed":     test_hash["_seed"] if ("_seed" in test_hash) else None,
            "suite":    test_hash["_suite"],
            "fw":       test_hash["_fw"],
            "defines":  flatten_list(test_hash["_defines"]),
            "args":     flatten_list(test_hash["_args"]),
        }
        groups = flatten_list(test_hash["_when"])
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
    yml_spec["tests"] = test_spec
    return yml_spec


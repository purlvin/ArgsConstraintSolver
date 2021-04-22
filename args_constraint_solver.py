#!/usr/bin/env python3
import argparse
import yaml
import math
import re
import sys
import os

def get_tests(yml, outdir):
    spec   = {}
    cfg    = yaml.load(open(yml), Loader=yaml.SafeLoader)
    ymlout =  os.path.join(outdir, os.path.basename(yml.replace(".yml", "_expanded.yml")))
    # Generate yml
    print('  -> Generate expended test.yml: {0}'.format(ymlout))
    f = open(ymlout, "w")
    f.write("# ->> File: test.yml\n")
    f.write("#------------------------------------------------\n")
    testsuites = []
    for k,v in cfg["templates"].items():
        f.write("{0}: &{0}\n".format(k))
        for k1,v1 in v.items():
            if (type(v1) == list):
                f.write("  {0}: &{1}_{0}\n".format(k1,k))
                for v2 in v1: f.write("    - {0}\n".format(v2))
            else: 
                f.write("  {0}: {1}\n".format(k1,v1))
    for ymlin in cfg["includes"]:
        ymlin = os.path.join(os.path.dirname(yml),ymlin)
        testsuites.append("# ->> File: {0}\n".format(ymlin) + open(ymlin).read())
    f.write("\n{0}".format("\n".join(testsuites)))
    f.close()
    spec = yaml.load(open(ymlout), Loader=yaml.SafeLoader)
    # Dump yml
    ymlout = ymlout + ".dump"
    #print('  -> Generate test.yml postprocess file: {0}'.format(ymlout))
    f = open(ymlout, "w")
    yaml.Dumper.ignore_aliases = lambda *args : True
    f.write(yaml.dump(spec))
    f.close()
    
    # Load constraint groups per test
    tests = {"groups": {}, "cases": {}, "ttx": {}}
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
            if (int(cfg[1])>0): tests["cases"][test].append(cfg[0])
        for group in flatten_list(test_hash["_when"]):
            if group not in tests["groups"]: tests["groups"][group] = {}
            tests["groups"][group][test] = test_hash["_clones"] if ("_clones" in test_hash) else 1
        tests["ttx"][test] = test_hash["_ttx"]
    return tests

def get_constraints(yml):
    constraints = {"files": [], "classes": {}, "remap":{}}
    # Load all .svh
    constr_class = {}
    cfg = yaml.load(open(yml), Loader=yaml.SafeLoader)
    for inc in ["global.svh"] + cfg["includes"]:
        inc = "constraints_" + inc.replace(".yml", ".svh")
        constraints["files"].append(inc)
        class_name = None
        constr_name = None
        inc = os.path.join(os.path.dirname(yml),inc)
        if not os.path.exists(inc): raise ValueError("Constraint file '{}' for test suite is missing!".format(inc, os.path.basename(yml).replace(".yml",""))) 
        for line in open(inc).readlines():
            # Class
            m = re.match(r'.*class\s*(.*)\s*;.*', line)
            if (m):
                class_name = m.group(1)
                m = re.match(r'(\w*)\s*extends\s*(\w*)', class_name)
                if (m):
                    class_name, orig = m.groups()
                else:
                    orig = None
                constr_class[class_name] = {"orig": orig, "vars": {}, "constrs": []}
                constraints["remap"][class_name] = class_name
            # Class - variables
            m = re.match(r'.*rand\s*(\w+)\s*(\w+)\s*;.*', line)
            if (m):
                k, v = m.groups()
                constr_class[class_name]["vars"][v] = k
            # Constraint
            m = re.match(r'.*constraint\s*(\w+)\s*{.*', line)
            if (m):
                constr_name = m.group(1)
                if (constr_name not in constr_class[class_name]["constrs"]):
                    constr_class[class_name]["constrs"].append(constr_name)
    for class_name in constr_class:
        def recesive_get_vars(class_name):
            if (not constr_class[class_name]["orig"]):
                return constr_class[class_name].copy()
            else:
                orig = recesive_get_vars(constr_class[class_name]["orig"])
                for k in constr_class[class_name]["vars"]:
                    orig["vars"][k] = constr_class[class_name]["vars"][k]
                orig["constrs"] = list(set(orig["constrs"]) | set(constr_class[class_name]["constrs"]))
                return orig
        if (constr_class[class_name]["orig"]): 
            constr_class[class_name]["vars"]    = recesive_get_vars(class_name)["vars"]       
            constr_class[class_name]["constrs"] = recesive_get_vars(class_name)["constrs"]
            constraints["remap"][constr_class[class_name]["orig"]] = class_name
    for class_name in constr_class:
        if (constraints["remap"][class_name] == class_name): constraints["classes"][class_name] = constr_class[class_name]

    return constraints
    
    spec   = {}
    cfg    = yaml.load(open(yml), Loader=yaml.SafeLoader)
    ymlout =  os.path.join(outdir, os.path.basename(yml.replace(".yml", "_expanded.yml")))
    # Generate yml
    print('  -> Generate expended test.yml: {0}'.format(ymlout))
    f = open(ymlout, "w")
    f.write("# ->> File: test.yml\n")
    f.write("#------------------------------------------------\n")
    testsuites = []
    for k,v in cfg["templates"].items():
        f.write("{0}: &{0}\n".format(k))
        for k1,v1 in v.items():
            if (type(v1) == list):
                f.write("  {0}: &{1}_{0}\n".format(k1,k))
                for v2 in v1: f.write("    - {0}\n".format(v2))
            else: 
                f.write("  {0}: {1}\n".format(k1,v1))
    for ymlin in cfg["includes"]:
        ymlin = os.path.join(os.path.dirname(yml),ymlin)
        testsuites.append("# ->> File: {0}\n".format(ymlin) + open(ymlin).read())
    f.write("\n{0}".format("\n".join(testsuites)))
    f.close()
    spec = yaml.load(open(ymlout), Loader=yaml.SafeLoader)
    # Dump yml
    ymlout = ymlout + ".dump"
    #print('  -> Generate test.yml postprocess file: {0}'.format(ymlout))
    f = open(ymlout, "w")
    yaml.Dumper.ignore_aliases = lambda *args : True
    f.write(yaml.dump(spec))
    f.close()
    
    # Load constraint groups per test
    tests = {"groups": {}, "cases": {}, "ttx": {}}
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
            if (int(cfg[1])>0): tests["cases"][test].append(cfg[0])
        for group in flatten_list(test_hash["_when"]):
            if group not in tests["groups"]: tests["groups"][group] = {}
            tests["groups"][group][test] = test_hash["_clones"] if ("_clones" in test_hash) else 1
        tests["ttx"][test] = test_hash["_ttx"]
    return tests


def gen_solver_sv(sv, tests, constrains):
    f = open(sv, "w")
    # include
    for inc in constrains["files"]:
        f.write('`include "{0}"\n'.format(inc))
    # program
    f.write('\nimport "DPI-C" function string getenv(input string env_name);\n')
    f.write('\nmodule ttx_generator;\n')
    print(constrains);
    for c,v in constrains["remap"].items():
        if (c == v): 
            f.write('  {0:25} {1:>25}_inst = new();  // <- class \'{2}\'\n'.format(c, c, v))
        else:
            f.write('  //XXX: {0:18} {1:>25}_inst = new();  // <- class \'{2}\'\n'.format(c, v, v))
    
    f.write('\n  //===========================================\n')
    f.write('  // Function: ConfigConstrGrps\n')
    f.write('  function ConfigConstrGrps(input string testname);\n')
    #   Disable all constraints by default
    f.write('    // Disable all constraints by default\n')
    for c in constrains["classes"]:
        f.write('    // -> class "{0}"\n'.format(c))
        for g in constrains["classes"][c]["constrs"]:
            f.write('    {0}_inst.{1}.constraint_mode(0);\n'.format(c, g))
    #   Enable constraints per testcase and testsuite
    f.write('\n    // Enable constraints per testcase and testsuite\n')
    f.write('    case (testname)\n')
    for t in tests["cases"]:
        f.write('      "{0}": begin\n'.format(t))
        f.write('        $display("[constraints_solver] Enable test constraint groups: {0}");\n'.format(tests["cases"][t]))
        for g in tests["cases"][t]:
            arr = g.split(".")
            f.write('        {0}_inst.{1}.constraint_mode(1);\n'.format(constrains["remap"][arr[0]], arr[1]))
        f.write('      end\n')
    f.write('      default: begin\n'.format(t))
    f.write('        $display("[constraints_solver] ERROR: No test is matched, all constraint groups are disalbed by default!");\n'.format(g))
    f.write('      end\n')
    f.write('    endcase\n')
    f.write('  endfunction\n')

    f.write('\n  //===========================================\n')
    f.write('  // Function: RandomizeConstrs\n')
    f.write('  function RandomizeConstrs();\n')
    for c in constrains["classes"]:
        f.write('    // -> {0}\n'.format(c))
        f.write('    {0}_inst.randomize();\n'.format(c))
    f.write('  endfunction\n')

    f.write('\n  //===========================================\n')
    f.write('  function string GetCwdBaseName();\n')
    f.write('    string arr[$] = SplitStr(getenv("PWD"), "/");\n')
    f.write('    return arr[arr.size()-1];\n')
    f.write('  endfunction\n')
    f.write('  typedef string string_arr[$];\n')
    f.write('  function string_arr SplitStr(string src, string sep);\n')
    f.write('    string list[$];\n')
    f.write('    int i,j;\n')
    f.write('    list.delete();\n')
    f.write('    for (i=0,j=0; i<src.len()-sep.len(); i++) begin\n')
    f.write('      if (sep.compare(src.substr(i,i+sep.len()-1))==0) begin\n')
    f.write('        list.push_back(src.substr(j, i-1));\n')
    f.write('        j = i+1;\n')
    f.write('      end\n')
    f.write('    end\n')
    f.write('    list.push_back(src.substr(j+sep.len()-1, src.len()-1));\n')
    f.write('    return list;\n')
    f.write('  endfunction\n')
    f.write('  function string GetTtxName(input string testname);\n')
    f.write('    string ret = "UNKNOWN";\n')
    f.write('    case(testname)\n')
    for t,v in tests["ttx"].items():
        f.write('      "{0}": ret = "{1}";\n'.format(t, v))
    f.write('    endcase\n')
    f.write('    return ret;\n')
    f.write('  endfunction\n')
    f.write('  // Function: GenArgs\n')
    f.write('  function GenArgs(input string testname);\n')
    f.write('    int fd;\n')
    f.write('    string args, val, cmd;\n')
    f.write('    fd = $fopen("ttx_args.cfg", "w");\n')
    f.write('    cmd = "";\n')
    for c in constrains["classes"]:
        f.write('    // -> {0}\n'.format(c))
        for v,t in constrains["classes"][c]["vars"].items():
            var = c + "_inst." + v
            f.write('    //  ->> {0};\n'.format(v))
            f.write('    if ({0} != `INTEGER__DIS) begin\n'.format(var))
            if (t == "integer"):
                f.write('      $sformat(args, "--{1}=%-0d", {0});\n'.format(var, v))
            else:
                f.write('      string arr[$] = SplitStr({0}.name(), "__");\n'.format(var))
                f.write('      val = arr[1];\n'.format(var))
                f.write('      if (val == "EN")\n')
                f.write('        $sformat(args, "--{0}");\n'.format(v))
                f.write('      else\n')
                f.write('        $sformat(args, "--{0}=%-0s", val);\n'.format(v))
            f.write('      cmd = {cmd, " ", args};\n')
            f.write('      $fdisplay(fd, "%s", args);\n')
            f.write('    end\n')
    f.write('    $fclose(fd);\n')
    #f.write('    cmd = {"make -j8 -C ", getenv(\"ROOT\"), "/src/hardware/tb_tensix/tests TEST_OUT=", GetCwdBaseName()," TEST=", GetTtxName(testname)," GENARGS=\'", cmd, "\' compile_test; ", " ln -sf ",getenv(\"ROOT\"), "/src/hardware/tb_tensix/tests/out/", GetCwdBaseName(), "/", GetTtxName(testname), ".ttx core.ttx"};\n')
    f.write('    cmd = {getenv(\"ROOT\"), "/out/pub/ttx/", GetTtxName(testname),"/", GetTtxName(testname), cmd, " && ",  getenv(\"ROOT\"), "/src/test_ckernels/ckti/out/ckti --dir=. --test=", GetTtxName(testname), "; stat /localhome/mchit/work/blackhole_rtl_vcs_2/out/run/conv_basic/single-core-conv.ttx;"};\n')
    f.write('    $display("CMD: %s", cmd);\n')
    f.write('    $system(cmd);\n')
    f.write('    $display("CMD: %s", cmd);\n')
    f.write('    $system(" stat /localhome/mchit/work/blackhole_rtl_vcs_2/out/run/conv_basic/single-core-conv.ttx;");\n')
    f.write('  endfunction\n')

    f.write('\n  //===========================================\n')
    f.write('  // Task: GenImage\n')
    f.write('  task GenImage();\n')
    #   Get test argument
    f.write('    string testname = "UNKNOWN";\n')
    f.write('    $value$plusargs("test=%s", testname);\n')
    f.write('    $display("[constraints_solver] Runtime args: test = %s", testname);\n')

    #   Setup constraint group
    f.write('\n    //--------------------------------------------\n')
    f.write('    // Setup constraint group\n')
    f.write('    ConfigConstrGrps(testname);\n')

    #   Randmize class instance
    f.write('\n    //--------------------------------------------\n')
    f.write('    // Randmize class instance\n')
    f.write('    RandomizeConstrs();\n')
    
    #   Generate arguments
    f.write('\n    //--------------------------------------------\n')
    f.write('    // Generate arguments\n')
    f.write('    GenArgs(testname);\n')
    f.write('  endtask\n')
    f.write('endmodule\n')
    f.close()

def GenConstrintsSolver(yml, sv):
    # Constraints
    constraints = get_constraints(yml)
    tests       = get_tests(yml, os.path.dirname(sv))
    test_info = get_test_info(yml, os.path.dirname(sv))
    #print("\nTests: \n", tests)
    #print("\nConstrains: \n", constraints)
    gen_solver_sv(sv, tests, constraints)


if __name__ == "__main__":
    # Construct the argument parser
    ap = argparse.ArgumentParser()
    ap.add_argument("-y", "--yml", help="Input yaml file")
    ap.add_argument("-o", "--out", help="Output constraint SV file")
    args = vars(ap.parse_args())
    #print("> Input Args ")
    #for k,v in args.items():
    #    if (v): print("  {} : {}".format(k, v))

    # Generate constranint systemveilog module
    GenConstrintsSolver(args["yml"], args["out"])


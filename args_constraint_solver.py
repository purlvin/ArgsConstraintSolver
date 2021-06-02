#!/usr/bin/env python3
import argparse
import yaml
import math
import re
import sys
import os
import pprint
import copy

def get_test_spec(yml, outdir):
    spec = {"constraints": {}, "tests": {}}
    cfg = yaml.load(open(yml), Loader=yaml.SafeLoader)
    
    # Constraint groups
    constraints = {"file": [], "class": {}}
    for inc in ["global.svh"] + cfg["includes"]:
        svh = "constraints_" + inc.replace(".yml", ".svh")
        constraints["file"].append(svh)
        class_name = None
        constr_name = None
        svh = os.path.join(os.path.dirname(yml),svh)
        if not os.path.exists(svh): raise ValueError("Constraint file '{0}' for {1} is missing!".format(svh, os.path.basename(inc.replace(".yml","")))) 
        for line in open(svh).readlines():
            if (re.match(r'^\s*//', line)): continue
            # Class
            m = re.match(r'.*class\s*(.*)\s*;.*', line)
            if (m):
                class_name = m.group(1)
                m = re.match(r'(\w*)\s*extends\s*(\w*)', class_name)
                if (m):
                    class_name, orig = m.groups()
                else:
                    orig = None
                constraints["class"][class_name] = {"orig": orig, "vars": {}, "constrs": []}
            # Class - variables
            m = re.match(r'.*rand\s*(\w+)\s*(\w+)\s*;.*', line)
            if (m):
                k, v = m.groups()
                constraints["class"][class_name]["vars"][v] = k
            # Constraint
            m = re.match(r'.*constraint\s*(\w+)\s*{.*', line)
            if (m):
                constr_name = m.group(1)
                if (constr_name not in constraints["class"][class_name]["constrs"]):
                    constraints["class"][class_name]["constrs"].append(constr_name)
    for class_name in constraints["class"]:
        def recesive_get_vars(class_name):
            if (not constraints["class"][class_name]["orig"]):
                return copy.deepcopy(constraints["class"][class_name])
            else:
                orig = recesive_get_vars(constraints["class"][class_name]["orig"])
                for k in constraints["class"][class_name]["vars"]:
                    orig["vars"][k] = constraints["class"][class_name]["vars"][k]
                orig["constrs"] = list(set(orig["constrs"]) | set(constraints["class"][class_name]["constrs"]))
                return orig.copy()
        if (constraints["class"][class_name]["orig"]): 
            constraints["class"][class_name]["vars"]    = recesive_get_vars(class_name)["vars"]       
            constraints["class"][class_name]["constrs"] = recesive_get_vars(class_name)["constrs"]
    for class_name in constraints["class"]: constraints["class"][class_name]["orig"] = None
    spec["constraints"] = constraints

    # Testcases
    stream = {"templates": "", "testcases": ""}
    ymlout =  os.path.join(outdir, os.path.basename(yml.replace(".yml", "_expanded.yml")))
    # Expanded yml
    print('  -> Generate expended test.yml: {0}'.format(ymlout))
    f = open(ymlout, "w")
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
    
    # Load constraint groups per test
    unused_class = list(spec["constraints"]["class"])
    tests = {"groups": {}, "cases": {}, "ttx": {}}
    for test, test_hash in cfg["testcases"].items():
        def flatten_list(irregular_list):
            return [element for item in irregular_list for element in flatten_list(item)] if type(irregular_list) is list else [irregular_list]
        for constr_grp in flatten_list(test_hash["_constr_grps"]):
            cfg = [i.strip() for i in constr_grp.split("=")]
            if test_hash["_constr_class"] not in spec["constraints"]["class"]: raise ValueError("Invalid constraint class '{0}' specified for test '{1}' (Valid classes: {2})!".format(test_hash["_constr_class"], test, spec["constraints"]["class"].keys())) 
            if cfg[0] not in spec["constraints"]["class"][test_hash["_constr_class"]]["constrs"]: raise ValueError("Invalid constraint group '{0}' specified for test '{1}' (Valid constraint groups: {2})!".format("{0}.{1}".format(test_hash["_constr_class"], cfg[0]), test, spec["constraints"]["class"][test_hash["_constr_class"]]["constrs"])) 
            if (test not in tests["cases"]):        tests["cases"][test] = []
            if ((len(cfg)==1) or (int(cfg[1])>0)):  
                tests["cases"][test].append("_{0}.{1}".format(test_hash["_constr_class"], cfg[0]))
                if (test_hash["_constr_class"] in unused_class): unused_class.remove(test_hash["_constr_class"])
        for group in flatten_list(test_hash["_when"]):
            if group not in tests["groups"]: tests["groups"][group] = {}
            tests["groups"][group][test] = test_hash["_clones"] if ("_clones" in test_hash) else 1
        tests["ttx"][test] = test_hash["_ttx"]
    spec["tests"] = tests
    for c in unused_class: del spec["constraints"]["class"][c]
    return spec


def gen_solver_sv(sv, spec, debug):
    f = open(sv, "w")
    # include
    for inc in spec["constraints"]["file"]:
        f.write('`include "{0}"\n'.format(inc))
    # program
    f.write('\nimport "DPI-C" function string getenv(input string env_name);\n')
    f.write('\nmodule ttx_generator;\n')
    for c,v in spec["constraints"]["class"].items():
        f.write('  {0:28} {1:>25} = new();\n'.format(c, "_"+c))
        f.write('  {0:28} {1:>25};\n'.format("logic", "_"+c+"_enable"))
    
    f.write('\n  //===========================================\n')
    f.write('  // Function: ConfigConstrGrps\n')
    f.write('  function ConfigConstrGrps(input string testname);\n')
    #   Disable all constraints by default
    f.write('    // Disable all constraints by default\n')
    for c,v in spec["constraints"]["class"].items():
        f.write('    // -> class "{0}"\n'.format(c))
        f.write('    {0} = 0;\n'.format("_"+c+"_enable"))
        for g in v["constrs"]:
            f.write('    {0}.{1}.constraint_mode(0);\n'.format("_"+c, g))
    #   Enable constraints per testcase and testsuite
    f.write('\n    // Enable constraints per testcase and testsuite\n')
    f.write('    case (testname)\n')
    for t,v in spec["tests"]["cases"].items():
        f.write('      "{0}": begin\n'.format(t))
        f.write('        $display("[constraints_solver] Enable test constraint groups: {0}");\n'.format(v))
        f.write('        {0} = 1;\n'.format(v[0].split(".")[0]+"_enable"))
        for g in v:
            f.write('        {0}.constraint_mode(1);\n'.format(g))
        f.write('      end\n')
    f.write('      default: begin\n'.format(t))
    f.write('        $display("[constraints_solver] ERROR: No test is matched, all constraint groups are disalbed by default!");\n'.format(g))
    f.write('      end\n')
    f.write('    endcase\n')
    f.write('  endfunction\n')

    f.write('\n  //===========================================\n')
    f.write('  // Function: RandomizeConstrs\n')
    f.write('  function RandomizeConstrs();\n')
    for c in spec["constraints"]["class"]:
        f.write('    // -> {0}\n'.format(c))
        f.write('    if ({0}) begin\n'.format("_"+c+"_enable"))
        f.write('      assert ({0}.randomize()) else $error("sv randomization failed!");\n'.format("_"+c))
        f.write('    end\n')
    f.write('  endfunction\n')

    f.write('\n  //===========================================\n')
    f.write('  function string GetCwdBaseName();\n')
    f.write('    string arr[$];\n')
    f.write('    arr = SplitStr(getenv("PWD"), "/");\n')
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
    f.write('    if (j==0) j -= sep.len() - 1;\n')
    f.write('    list.push_back(src.substr(j+sep.len()-1, src.len()-1));\n')
    f.write('    return list;\n')
    f.write('  endfunction\n')
    f.write('  function string GetTtxName(input string testname);\n')
    f.write('    string ret = "UNKNOWN";\n')
    f.write('    case(testname)\n')
    for t,v in spec["tests"]["ttx"].items():
        f.write('      "{0}": ret = "{1}";\n'.format(t, v))
    f.write('    endcase\n')
    f.write('    return ret;\n')
    f.write('  endfunction\n')
    f.write('  // Function: GenArgs\n')
    f.write('  function GenArgs(input string testname);\n')
    f.write('    int fd, ret;\n')
    f.write('    string args, val, cmd;\n')
    f.write('    fd = $fopen("ttx_args.cfg", "w");\n')
    f.write('    cmd = "";\n')
    for c in spec["constraints"]["class"]:
        f.write('\n    // -> Class {0}\n'.format(c))
        f.write('    if (_{0}_enable) begin\n'.format(c))
        for v,t in spec["constraints"]["class"][c]["vars"].items():
            var = "_" + c + "." + v
            f.write('      //  ->> {0};\n'.format(v))
            f.write('      if ({0} != `INTEGER__DIS) begin\n'.format(var))
            if (t in ["integer"]):
                f.write('        $sformat(args, "--{1}=%-0d", {0});\n'.format(var, v))
            elif ("e_int_x" in t):
                div = t.replace("e_int_x", "") + ".00"
                f.write('        $sformat(args, "--{1}=%-0.2f", {0}/{2});\n'.format(var, v, div))
            else:
                f.write('        string arr[$];\n'.format(var))
                f.write('        arr = SplitStr({0}.name(), "__");\n'.format(var))
                f.write('        val = arr[arr.size()-1];\n'.format(var))
                f.write('        if (val == "EN")\n')
                f.write('          $sformat(args, "--{0}");\n'.format(v))
                f.write('        else\n')
                f.write('          $sformat(args, "--{0}=%-0s", val);\n'.format(v))
            f.write('        cmd = {cmd, " ", args};\n')
            f.write('        $fdisplay(fd, "%s", args);\n')
            f.write('      end\n')
        if (int(debug) == 1): 
            f.write('      cmd = {cmd, " --debug"};\n')
            f.write('      $fdisplay(fd, "%s", "--debug");\n')
        f.write('    end\n')
    f.write('    $fclose(fd);\n\n')
    f.write('    cmd = {"date; ln -sf ", getenv(\"ROOT\"), "/out/pub/fw . && ", getenv(\"ROOT\"), "/out/pub/ttx/", GetTtxName(testname),"/", GetTtxName(testname), cmd, " && cd ",  getenv(\"ROOT\"), "/src/test_ckernels/ckti && out/ckti --dir=", getenv(\"PWD\")," --test=", GetTtxName(testname), "; date;"};\n')
    
    f.write('    $display("CMD: %s", cmd);\n')
    f.write('    ret = $system(cmd);\n')
    f.write('    $display("RET: %d", ret);\n')
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


if __name__ == "__main__":
    # Construct the argument parser
    ap = argparse.ArgumentParser()
    ap.add_argument("-y", "--yml", help="Input yaml file")
    ap.add_argument("-o", "--out", help="Output constraint SV file")
    ap.add_argument("-dbg", "--debug", help="Simplify TTX data")
    args = vars(ap.parse_args())
    print("> Input Args ")
    for k,v in args.items():
        if (v): print("  {} : {}".format(k, v))

    # Generate constranint systemveilog module
    spec = get_test_spec(args["yml"], os.path.dirname(args["out"]))
    #print("\nSpec: \n", spec)
    gen_solver_sv(args["out"], spec, args["debug"])



#/*
#  1) not print or feed into ttx (P1)
#  typedef integer e_int_local;
#  rand e_int_local   abc;
#
#   -> workaround currently dv test limitation (only 1 c testcase file) 
#
#
#  2) supporting array of integer (P2)
#  typedef integer   e_int_coordinate;
#  rand e_int_coordinate coor[4];
#  print out as coor=coor[3],coor[2],coor[1],coor[0]
#
#   -> workaround currently ttx generator format 
#
#
#  3) support more than 32 bits (P4)
#  typedef integer   e_int_ext;
#  rand e_int_ext  long_int[2];
#  print out as long_int=long_int[1]_long_int[0]
#
#
#  4) for e_bool, either print it or not print it , witout the value (P1)
#  typedef bit       e_switch;            
#  rand e_switch     cde;
#
#  instead of 
#       (xxx==e_bool__EN) -> (yyy===`INTEGER__DIS);
#  can code it like this
#       xxx -> !yyy ;
#
#   -> workaround currently ttx generator format 
#   -> instead of fixing ttx, add exception case 
#
#
#   5) plusarg randomization support
#      * list of plusarg & range
#      * runtime constraint is resolved in runtime (not pregen)
#      * how to parse (madeusa / sys_mgtr
#*/
#

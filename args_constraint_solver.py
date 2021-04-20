#!/usr/bin/env python3
import yaml
import math
import re
import sys
import os

def get_tests(yml):
    spec = {}
    # Load all .yml
    cfg = yaml.safe_load(open(yml))
    for inc in cfg.get("testsuites", []):
        inc = os.path.join(os.path.dirname(yml),inc)
        spec.update(yaml.safe_load(open(inc)))

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
            if (int(cfg[1])>0): tests["cases"][test].append(cfg[0].replace('.', '_inst.'))
        for group in flatten_list(test_hash["_when"]):
            if group not in tests["groups"]: tests["groups"][group] = {}
            tests["groups"][group][test] = test_hash["_clones"] if ("_clones" in test_hash) else 1
        tests["ttx"][test] = test_hash["_ttx"]
    return tests

def get_constraints(yml):
    constraints = {"files": [], "classes": {}}
    # Load all .svh
    constr_class = {}
    cfg = yaml.safe_load(open(yml))
    for inc in cfg.get("constraints", []):
        constraints["files"].append(inc)
        class_name = None
        constr_name = None
        inc = os.path.join(os.path.dirname(yml),inc)
        for line in open(inc).readlines():
            # Class
            m = re.match(r'.*class\s*(.*)\s*;.*', line)
            if (m):
                class_name = m.group(1)
                m = re.match(r'(\w*)\s*extends\s*(\w*)', class_name)
                if (m):
                    class_name, father = m.groups()
                else:
                    father = None
                constr_class[class_name] = {"father": father, "vars": {}, "constrs": []}
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
    redundant_class = []
    for class_name in constr_class:
        def recesive_get_vars(class_name):
            if (not constr_class[class_name]["father"]):
                return constr_class[class_name].copy()
            else:
                father = recesive_get_vars(constr_class[class_name]["father"])
                for k in constr_class[class_name]["vars"]:
                    father["vars"][k] = constr_class[class_name]["vars"][k]
                father["constrs"] = list(set(father["constrs"]) | set(constr_class[class_name]["constrs"]))
                return father
        if (constr_class[class_name]["father"]): 
            #constr_class[class_name]["vars"]    = recesive_get_vars(class_name)["vars"]       
            constr_class[class_name]["constrs"] = recesive_get_vars(class_name)["constrs"]
            #redundant_class.append(constr_class[class_name]["father"])
    for class_name in constr_class:
        if class_name not in redundant_class: constraints["classes"][class_name] = constr_class[class_name]
    return constraints

def gen_solver_sv(sv, tests, constrains):
    f = open(sv, "w")
    # include
    for inc in constrains["files"]:
        f.write('`include "{0}"\n'.format(inc))
    # program
    f.write('\nimport "DPI-C" function string getenv(input string env_name);\n')
    f.write('\nmodule ttx_generator;\n')
    for c in constrains["classes"]:
        f.write('  {0:25} {1:>25}_inst = new();  // <- class \'{2}\'\n'.format(c, c, constrains["classes"][c]["father"]))
    
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
            f.write('        {1}.constraint_mode(1);\n'.format(c, g))
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
    #f.write('    cmd = {"make -C ", getenv("ROOT"), "/src/hardware/tb_tensix/tests  TEST=single-core-conv GENARGS=\'", cmd, "\' compile_test SIM=vcs; ", " cp ", getenv("ROOT"), "/src/hardware/tb_tensix/tests/out/single-core-conv/single-core-conv.ttx core.ttx"};\n')
    #f.write('    cmd = {"make -C ", getenv("ROOT"), "/src/hardware/tb_tensix/tests OUTPUT_DIR=out/ttx/conv_basic", ""," TEST=single-core-conv GENARGS=\'", cmd, "\' compile_test SIM=vcs; ", " cp ", getenv("ROOT"), "/src/hardware/tb_tensix/tests/out/ttx/conv_basic/single-core-conv.ttx core.ttx"};\n')
    f.write('    cmd = {"echo ", getenv(\"ROOT\"), "/src/hardware/tb_tensix/tests OUTPUT_DIR=out/ttx/", GetCwdBaseName()," TEST=", testname," GENARGS=\'", cmd, "\' compile_test SIM=vcs; ", " cp ",getenv(\"ROOT\"), "/src/hardware/tb_tensix/tests/out/ttx/", GetCwdBaseName(), "/", GetTtxName(testname), ".ttx core.ttx"};\n')

    f.write('    $display("CMD: %s", cmd);\n')
    f.write('    $system(cmd);\n')
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
    tests       = get_tests(yml)
    constraints = get_constraints(yml)
    #print("\nTests: \n", tests)
    #print("\nConstrains: \n", constraints)
    gen_solver_sv(sv, tests, constraints)


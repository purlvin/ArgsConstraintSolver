#!/usr/bin/env python3
import os
import subprocess
import random
import time
from datetime import datetime

# -------------------------------
# Email
def construct_email_context(meta, run_cmd, tests_status, log_file):
    stage, status = meta.last_stage()
    root          = os.environ.get('ROOT')
    host          = os.environ.get('HOST')
    git_branch    = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip().decode("utf-8")
    git_hash      = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode("utf-8")
    #Subject
    email_subject     = "[run_test] Tensix(:{_git_branch}) - Personal sanity - {_status}".format(_git_branch=git_branch, _status=status)
    #Html Header
    email_body_header = "<html><head><style type='text/css'>body{font-size:15px;}table,th,td{font-size:14px;border: 1px solid #cccccc;border-collapse:collapse;padding:4px 8px;font-family:Calibri;}.row{border:0px;width:800px}.key{border:0px;width:150px;text-align:right;vertical-align:text-top;padding-right:15px;}.value{border:0px;}</style><title>Sanity E-mail</title></head><body><font face='calibri'><pre>\n"
    #Body
    email_body = '''\
<span style='font-size: 22px'><b> DV_CHECK_SUBMIT REPORT </b> - <span style = 'color:{_color}';>{_status}({_stage})</span></span><hr>
<table style='border:0px;font-size:12px'>
  <tr class='row'><td class='key'>Sanity Run ID :</td><td class='value'>{_id}</td></tr>
  <tr class='row'><td class='key'>Workspace :</td><td class='value'>({_host}) {_root}</td></tr>
  <tr class='row'><td class='key'>Reversion :</td><td class='value'>{_git_hash} ({_git_branch})</td></tr>
  <tr class='row'><td class='key'>Log:</td><td class='value'>{_root}/out/run_test.log</td></tr>
  <tr class='row'><td class='key'>Cmdline:</td><td class='value'>{_cmdline}</td></tr>
</table>
</br>
'''.format(_color="green" if (status == "PASS") else "red", _status=status, _stage=stage, _id=meta.id, _host=host, _root=root, _git_hash=git_hash, _git_branch=git_branch, _cmdline=meta.cmdline())
    #   -> Stage summary
    email_body += '''\
<b>STAGE SUMMARY: </b>
<table><tr><th>TOTAL</th><th>PASSED</th><th>FAILED</th>
<tr><td>4</td><td>0</td><td>4</td></tr></table>
'''.format()
    #   -> Sanity summary
    email_body += '''\
<b>SANITY SUMMARY: </b>
<table><tr><th>TOTAL</th><th>PASSED</th><th>FAILED</th>
<tr><td>4</td><td>0</td><td>4</td></tr></table>
'''.format()
    #   -> Primary test status
    email_body += '''\
<b>PRIMARY TESTS STATUS</b>
<table><tr><th>STATUS</th><th>SUITE</th><th>TESTNAME</th><th>CONFIG</th><th>DURATION</th><th>LOGS</th></tr>
<tr>
<td style='color: red;'>FAILED</td><td>bootcode::bootcode</td><td>cold_reset_sanity_blank</td><td>smu_megaip_uvm</td><td>3m</td><td><a  style='text-decoration:none;' href='http://logviewer-atl.amd.com/proj/smu_dev_er_normal_3/puzhang/raphael/megaip/ws1/out/linux_3.10.0_64.VCS/smu_megaip_design_raphael/config/smu_megaip_uvm/pub/sim/vcs_compile.log'>Compile</a> <a  style='text-decoration:none;' href='http://logviewer-atl.amd.com/proj/smu_dev_er_normal_3/puzhang/raphael/megaip/ws1/out/linux_3.10.0_64.VCS/smu_megaip_design_raphael/config/smu_megaip_uvm/run/bootcode/cold_reset_sanity_blank/vcs_run.log'>Run</a></td></tr><tr>
<td style='color: red;'>FAILED</td><td>bootcode::bootcode</td><td>cold_reset_sanity_dpi</td><td>smu_megaip_uvm</td><td></td><td><a  style='text-decoration:none;' href='http://logviewer-atl.amd.com/proj/smu_dev_er_normal_3/puzhang/raphael/megaip/ws1/out/linux_3.10.0_64.VCS/smu_megaip_design_raphael/config/smu_megaip_uvm/pub/sim/vcs_compile.log'>Compile</a> <a  style='text-decoration:none;' href='http://logviewer-atl.amd.com/proj/smu_dev_er_normal_3/puzhang/raphael/megaip/ws1/out/linux_3.10.0_64.VCS/smu_megaip_design_raphael/config/smu_megaip_uvm/run/bootcode/cold_reset_sanity_dpi/vcs_run.log'>Run</a></td></tr><tr>
<td style='color: red;'>FAILED</td><td>bootcode::bootcode</td><td>cold_reset_sanity_proto</td><td>smu_megaip_uvm</td><td></td><td><a  style='text-decoration:none;' href='http://logviewer-atl.amd.com/proj/smu_dev_er_normal_3/puzhang/raphael/megaip/ws1/out/linux_3.10.0_64.VCS/smu_megaip_design_raphael/config/smu_megaip_uvm/pub/sim/vcs_compile.log'>Compile</a> <a  style='text-decoration:none;' href='http://logviewer-atl.amd.com/proj/smu_dev_er_normal_3/puzhang/raphael/megaip/ws1/out/linux_3.10.0_64.VCS/smu_megaip_design_raphael/config/smu_megaip_uvm/run/bootcode/cold_reset_sanity_proto/vcs_run.log'>Run</a></td></tr><tr>
<td style='color: red;'>FAILED</td><td>bootcode::bootcode</td><td>cold_reset_sanity_secure</td><td>smu_megaip_uvm</td><td></td><td><a  style='text-decoration:none;' href='http://logviewer-atl.amd.com/proj/smu_dev_er_normal_3/puzhang/raphael/megaip/ws1/out/linux_3.10.0_64.VCS/smu_megaip_design_raphael/config/smu_megaip_uvm/pub/sim/vcs_compile.log'>Compile</a> <a  style='text-decoration:none;' href='http://logviewer-atl.amd.com/proj/smu_dev_er_normal_3/puzhang/raphael/megaip/ws1/out/linux_3.10.0_64.VCS/smu_megaip_design_raphael/config/smu_megaip_uvm/run/bootcode/cold_reset_sanity_secure/vcs_run.log'>Run</a></td></tr></table>
'''.format()
    #End tags
    email_end_tags = "</pre></font></body></html>";
    
    print("purlivn", meta.stages)
    print("purlivn", stage, status)
    
    #All Email content 
    email_body = email_body_header + email_body + email_end_tags;
    print("purlivn", email_body)
    return (email_subject, email_body);

def send_email(meta, test_list, args):
    user         = os.environ.get('USER')
    subject,body = construct_email_context(meta, "run_test -s=XXXX", "status", "vcs_run.log")
    body = '''\
To: {_user}@atlmail.amd.com
Subject: {_subject}
Content-Type: text/html

<FONT FACE=courier>
{_body}
</FONT>
'''.format(_user=user, _subject=subject, _body=body)
    return_stat = subprocess.run(["/usr/sbin/sendmail", "-t"], input=body.encode())


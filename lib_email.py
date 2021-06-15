#!/usr/bin/env python3
import os
import subprocess
import random
import time
from datetime import datetime

# -------------------------------
# Email
def construct_email_context(meta):
    status      = meta.stages["stages"][0]["status"]
    root        = os.environ.get('ROOT')
    host        = os.environ.get('HOST')
    git_branch  = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip().decode("utf-8")
    git_hash    = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode("utf-8")
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
'''.format(_color="green" if (status == "PASS") else "red", _status=status, _stage=meta.stages["current"], _id=meta.id, _host=host, _root=root, _git_hash=git_hash, _git_branch=git_branch, _cmdline=meta.cmdline())
    #   -> Sanity summary
    total = len(meta.test_stages)
    failed= len([hash["stages"][0] for test,hash in meta.test_stages.items() if hash["stages"][0]['status']=="FAIL"])
    email_body += '''\
<b>SANITY SUMMARY: </b>
<table><tr><th>TOTAL</th><th>PASSED</th><th>FAILED</th>
<tr><td>{_total}</td><td>{_passed}</td><td>{_failed}</td></tr></table>
'''.format(_total=total, _passed=total-failed, _failed=failed)
    #   -> Stage summary
    rows = ["", ""]
    for s in meta.STG:
        stage  = s.name
        status = meta.stage_status(stage)
        rows[0] += "<th>{_stage}</th>".format(_stage=stage)
        rows[1] += "<td style='color: {_color};'>{_status}</td>".format(_color="red" if (status=="FAIL") else "green" if (status=="PASS") else "gray", _status=status)
    email_body += '''\
<b>STAGE SUMMARY: </b>
<table><tr>{_stage_list}</tr>
<tr>{_status_list}</tr></table>
'''.format(_stage_list=rows[0], _status_list=rows[1])
    #   -> Primary test status
    rows = ""
    for test,hash in meta.test_stages.items():
        stage = hash["stages"][0]
        rows += "<tr><td style='color: {_color};'>{_status}</td>".format(_color="red" if (stage["status"]=="FAIL") else "green" if (stage["status"]=="PASS") else "gray", _status=stage["status"] if  (stage["status"]=="PASS") else "{} ({})".format(stage["status"],hash["current"]))
        rows += "<td>{_suite}</td>".format(_suite=stage["suite"])
        rows += "<td>{_test}</td>".format(_test=test)
        rows += "<td>{_duration}</td>".format(_duration=stage["duration"])
        #rows += "<td><a  style='text-decoration:none;' href='{_ref}'>Log</a></td>".format(_ref=stage["log"])
        rows += "<td>{_log}</td>".format(_log=stage["log"])
        rows += "</tr>\n"
    email_body += '''\
<b>PRIMARY TESTS STATUS</b>
<table><tr><th>STATUS</th><th>SUITE</th><th>TESTNAME</th><th>DURATION</th><th>LOG</th></tr>
{_rows}</table>
'''.format(_rows=rows)
    #End tags
    email_end_tags = "</pre></font></body></html>";
    #All Email content 
    email_body = email_body_header + email_body + email_end_tags;
    return (email_subject, email_body);

def send_email(meta):
    user         = os.environ.get('USER')
    subject,body = construct_email_context(meta)
    body = '''\
To: {_user}@mkdcmail.amd.com
Subject: {_subject}
Content-Type: text/html

<FONT FACE=courier>
{_body}
</FONT>
'''.format(_user=user, _subject=subject, _body=body)
    return_stat = subprocess.run(["/usr/sbin/sendmail", "-t"], input=body.encode())


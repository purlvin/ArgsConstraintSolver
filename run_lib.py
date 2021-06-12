#!/usr/bin/env python3
import glob, shutil, os, sys, signal
import subprocess
import yaml
import re
import argparse
import random
import time
import logging;
from datetime import datetime

# -------------------------------
# Email
def construct_email_context(cur_stage, run_cmd, tests_status, log_file):
    stage, result = cur_stage 
    root        = os.environ.get('ROOT')
    host        = os.environ.get('HOST')
    git_hash    = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode("utf-8")
    #Subject
    email_subject     = "[run_test] Tensix - Personal sanity - " + stage + " - " + result
    #Html Header
    email_body_header = "<html><head><style type='text/css'>body{font-size:15px;}table,th,td{font-size:14px;border: 1px solid #cccccc;border-collapse:collapse;padding:4px 8px;font-family:Calibri;}.row{border:0px;width:800px}.key{border:0px;width:150px;text-align:right;vertical-align:text-top;padding-right:15px;}.value{border:0px;}</style><title>Sanity E-mail</title></head><body><font face='calibri'><pre>\n"
    #Body
    email_brief_info  = "<span style='font-size: 22px'><b> DV_CHECK_SUBMIT REPORT </b> - <span style = 'color:"
    email_brief_info +=  "green" if (result == "PASS") else "red"
    
    email_brief_info += "';>{_result}</span></span><hr>\n".format(_result=result) +                                                                                                 \
                           "<table style='border:0px;font-size:14px'>" +                                                                                                            \
                           "  <tr class='row'><td class='key'>Sanity Run ID :</td><td class='value'>$DV_CHECK_SUBMIT_ID</td></tr>\n\n" +                                            \
                           "  <tr class='row'><td class='key'>Workspace :</td><td class='value'>({_host}) {_root}</td></tr>\n\n".format(_host=host, _root=root) +                   \
                           "  <tr class='row'><td class='key'>Reversion :</td><td class='value'>{_git_hash}</td></tr>\n".format(_git_hash=git_hash) +                               \
                           "  <tr class='row'><td class='key'>RUN_TEST Log:</td><td class='value'>{_root}/out/run_test.log</td></tr>\n\n".format(_root=root) +                      \
                           "  <tr class='row'><td class='key'>RUN_TEST Command:</td><td class='value'>$run_cmd</td></tr>\n"
    email_brief_info +=   "</table>\n"; 
    #Summary + details
    email_summary = "<b>SANITY SUMMARY: </b>\n";
#FIXME:    $email_summary .= runtime::gen_test_status_html($tests_status, $SITE, $stage);    
    #End tags
    email_end_tags = "</pre></font></body></html>";
    
    #All Email content 
    email_body = email_body_header + email_brief_info + email_summary + email_end_tags;
    return (email_subject, email_body);

def send_email(cur_stage, test_list, args):
    subject,body = construct_email_context(cur_stage, "run_test -s=XXXX", "status", "vcs_run.log")
    body = '''\
To: puzhang@atlmail.amd.com
Subject: {_subject}
Content-Type: text/html

<FONT FACE=courier>
{_body}
</FONT>
'''.format(_subject=subject, _body=body)
    return_stat = subprocess.run(["/usr/sbin/sendmail", "-t"], input=body.encode())


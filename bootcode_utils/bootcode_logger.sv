
`timescale 1ns/1ps

package bootcode_utils;
  function string GetTimeStr();
    int timescale = 1000;
    GetTimeStr = $psprintf("%.3f us", $realtime/1000);
  endfunction
endpackage


module bootcode_logger (
    Reset,
    PostCode,
    PC
);
import bootcode_utils::*;


//=======================================================================
// PARAMETER/DEFINE
//=======================================================================
parameter  BOOTCODE_IMG_DIR  = "ucode";
`define    PC_WIDTH	         32

//=======================================================================
// I/O PORT
//=======================================================================
input                         Reset;
input [31:0]                  PostCode;
input [`PC_WIDTH-1:0]         PC;

//=======================================================================
// Internal signals
//=======================================================================
reg [31:0] BootromChkEn;
reg [31:0] BootromLogEn;
reg DIS_BOOTROM_LOGGER_CHK;
reg ENABLE_BOOTROM_LOGGER_CHK;
reg DIS_BOOTROM_LOGGER;
reg ENABLE_BOOTROM_LOGGER;
string Pc2Line[int];
string Post2Name[int];
reg    Pc2LineValid   = 0;
reg    PostcodeValid  = 0;
string name = "<unknown>";
string line = "<unknown>";
string strs[$];


//=======================================================================
// Checks/Log Enable
//=======================================================================
// BootromLogEn & BootromChkEn bit decode
//    bit 1 ~ postcode
//    bit 2 ~ pc disasseble
// check control
wire general_assertion_disable     = ($test$plusargs("BOOTROM_ASSERTION_DISABLE_GLOBAL")) ? (1'b1) : ((BootromChkEn[0]==0) || (Reset!==1'b0));
wire postcode_assertion_disable    = ($test$plusargs("BOOTROM_ASSERTION_DISABLE_POSTCODE")) ? (1'b1) : (general_assertion_disable || (BootromChkEn[1]==0));
wire pc_assertion_disable          = ($test$plusargs("BOOTROM_ASSERTION_DISABLE_PC")) ? (1'b1) : (general_assertion_disable || (BootromChkEn[2]==0));
// log control
wire general_log_disable     = ($test$plusargs("BOOTROM_LOG_DISABLE_GLOBAL")) ? (1'b1) : ((BootromLogEn[0]==0));
wire postcode_log_disable    = ($test$plusargs("BOOTROM_LOG_DISABLE_POSTCODE")) ? (1'b1) : (general_log_disable || (BootromLogEn[1]==0));
wire pc_log_disable          = ($test$plusargs("BOOTROM_LOG_DISABLE_PC")) ? (1'b1) : (general_log_disable || (BootromLogEn[2]==0));


task SetBootromChkEn;
  input val;
    begin
      $display ("%m: [%0t] SetBootromChkEn = 0x%x",$time, val);
      BootromChkEn = val;
    end
endtask

task SetBootromLogEn;
  input val;
    begin
      $display ("%m: [%0t] SetBootromLogEn = 0x%x",$time, val);
      BootromLogEn = val;
    end
endtask

function automatic void SplitString (string str, byte sep, ref string values[$]);
  int s = 0, e = 0;
  values.delete();
  while(e < str.len()) begin
    for(s=e; e<str.len(); ++e)
      if(str[e] == sep) break;
    if(s != e)
      values.push_back(str.substr(s,e-1));
    e++;
  end
endfunction


initial begin
  if($value$plusargs("DIS_BOOTROM_LOGGER_CHK=%d",DIS_BOOTROM_LOGGER_CHK)) begin
       BootromChkEn   = 32'h0;
  end else if ($value$plusargs("ENABLE_BOOTROM_LOGGER_CHK=%d",ENABLE_BOOTROM_LOGGER_CHK)) begin
       BootromChkEn   = 32'hffff_ffff;
  end else begin
       // default
       BootromChkEn   = 32'hffff_ffff;
  end
  $display("[%0t] %m: BOOTROM_CHECKER: BootromChkEn<0x%0h>", $time, BootromChkEn);

  if($value$plusargs("DIS_BOOTROM_LOGGER=%d",DIS_BOOTROM_LOGGER)) begin
       BootromLogEn   = 32'h0;
  end else if($value$plusargs("ENABLE_BOOTROM_LOGGER=%d",ENABLE_BOOTROM_LOGGER)) begin
       BootromLogEn   = 32'hffff_ffff;
  end else begin
       // default
       BootromLogEn   = 32'hffff_ffff;
  end
  $display("[%0t] %m: BOOTROM_LOGGER: BootromLogEn<0x%0h>", $time, BootromLogEn);
end

//Preload bootcode uCode
initial begin
  #0;
  load_ucode_info();
end


//=======================================================================
// Postcode log
//=======================================================================
always @ (PostCode) begin
  if (Reset===1'b0) begin
    SplitString(get_bootrom_post_string(PostCode,0), "#", strs);
    name = strs[0];
    line = strs[1];
    if (PostCode[31:24] >= 'hF0) begin          // 'hF1xx_xxxx, 'hF2xx_xxxx, ... , 'hFFxx_xxxx
      if (!postcode_log_disable) $display("[%10s] %10s - BootRom 'ERROR' Postcode = 0x%08x <%0s>, failure detected, bootrom execution halt", GetTimeStr(), name, PostCode,line);
      if (~postcode_assertion_disable) begin
           A_bootrom_post_0: assert (general_assertion_disable) else
              $Fatal("bootcode_logger", $psprintf("ERROR: '%s' BootRom Postcode = %8s <%0s>,",name,$psprintf("0x%0h",PostCode),line));
      end
    end else begin
      if (!postcode_log_disable) begin
        if (name != "<unknown>") begin
          $display("[%10s] %10s - BootRom 'INFO' Postcode = 0x%8x <%0s>", GetTimeStr(), name, PostCode, line);
        end else begin
          $display("[%10s] %10s - BootRom 'WARNING' Postcode = 0x%8x <%0s>", GetTimeStr(), name, PostCode, line);
        end
      end
    end
  end
end


//=======================================================================
// ProgramCounter log
//=======================================================================
always @ (PC) begin
  if (Reset===1'b0) begin
    if (^PC === 1'bX) begin
         bootcode_chk_pc_0 : assert (general_assertion_disable) else
            $Fatal("bootcode_logger", $psprintf("ERROR: BootRom Invalid PC = 0x%0h", PC));
    end
    SplitString(get_file_string(PC,0), "#", strs);
    name = strs[0];
    line = strs[1];
    if ((!pc_log_disable) && (name != "<unknown>")) begin
        //$timeformat(-6, 3, " us", 15);  // $timeformat(unit#(10**<uint#> s), prec#, "unit", minwidth)
        $display("[%10s] %10s - BootRomPc(0x%0h): executing firmware: %0s", GetTimeStr(), name, PC, line);
    end

  end
end


//=======================================================================
// Common Functions/Tasks
//=======================================================================
task load_ucode_info;
  int 	 count, file, idx;
  string group, source;
  source = $psprintf("%s/ucode.inf", BOOTCODE_IMG_DIR);
  file = $fopen(source, "r");
  if (file == 0) begin
    $display("[%0t] %m: WARNING: Failed to open '%s'!", $time, source);
  end else begin
    $display("[%0t] %m: INFO: Loading ucode info from '%s'", $time, source);
    while(!$feof(file)) begin
      count = $fscanf(file,"%h %s %s/n", idx, group, source);
      if (group == "pc") begin
        Pc2LineValid     = 1;
        Pc2Line[idx]     = source;
      end else if (group == "post") begin
        PostcodeValid    = 1;
        Post2Name[idx]   = source;
      end
    end
    $fclose(file);
    $display("[%0t] %m: INFO: Loading ucode info from '%s' Done!", $time, source);
  end
endtask: load_ucode_info

function string get_bootrom_post_string(int bootrom_post, int check_exist);
  if (Post2Name[bootrom_post].len() > 0) begin
	  get_bootrom_post_string = Post2Name[bootrom_post];
  end else begin
    get_bootrom_post_string = "<unknown>#????";
    if (PostcodeValid!==1'b1) begin
      A_bootrom_post_1: assert (postcode_assertion_disable || ~check_exist) else
              $Fatal("[%0t] %m: UNSUPPORTED BootRom post<0x%0h>",$time,bootrom_post);
    end
  end
endfunction


function string get_file_string(int my_pc, int check_exist);
  if (Pc2Line[my_pc].len()>0) begin
    get_file_string = Pc2Line[my_pc];
  end else begin
    get_file_string = "<unknown>#????";
    if (Pc2LineValid!==1'b1) begin
      A_bootcode_chk_pc_1 :assert (pc_assertion_disable || ~check_exist) else 
             $Fatal("bootcode_logger", $psprintf("ERROR: BootRom: Invalid(not found) PC=0x%08h",$time,my_pc));
    end
  end
endfunction

endmodule

module tb;
    reg Reset;
    reg [31:0] PostCode;
    reg [31:0] PC;

    bootcode_logger   bootcode_logger(Reset, PostCode, PC);

    initial begin
      Reset = 1;
      #1;
      Reset = 0;

      #100;
      #10 PC = 'hFFFF0000;
      #10 PC = 'hFFFF0004;
      #10 PC = 'hFFFF0008;
      #10 PC = 'hFFFF0010;

      #100;
      #10 PostCode = 'h1;
      #10 PostCode = 'h2;
      #10 PostCode = 'h3;
      #10 PostCode = 'h4;
      #10 PostCode = 'h5;
      #10 PostCode = 'h5555555;
      #10 PostCode = 'h1111111;
      #10 PostCode = 'h6;

      #100;
      #10 PC = 'hFFFF0080;
      #10 PC = 'hFFFF0084;
      #10 PC = 'hFFFF1088;
      #10 PC = 'hFFFF1090;


      $finish;
    end

endmodule

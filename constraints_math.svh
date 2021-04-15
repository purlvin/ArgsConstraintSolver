
class constraints_math;
  typedef enum { bfp8 } e_fp;
  
  rand e_fp fp_pack;
  rand integer dbg_ovrd;
  rand integer num_sections;
  rand bit norelu;
  rand bit stream;

  // Constraint the members
  constraint global {
    fp_pack       == bfp8;
    dbg_ovrd      inside {[1:100]};
    num_sections  == 'h1;
    norelu        == 'h1;
  }
  constraint conv {
    dbg_ovrd      inside {[10:80]};
  }
  constraint conv_basic {
    dbg_ovrd      == 50;
  }
  constraint conv_multi_section {
    dbg_ovrd      == 60;
  }

  function string getType(e_fp ltype);
    begin
      case(ltype)
       bfp8     : getType = "bfp8";
       default  : getType = "UNKNOWN";
      endcase
    end
  endfunction
endclass




class constraints_suite_conv extends constraints_global;
  typedef enum {e_bool__DIS=`INTEGER__DIS,      e_bool__EN} e_bool;
  typedef enum {e_conv__DIS=`INTEGER__DIS,      e_conv__3x3s1, e_conv__3x3s2} e_conv;
  
  rand e_bool       inline_halo;
  rand e_conv       conv;
  rand integer      filters;
  
  typedef integer   e_int_local;
  rand e_int_local  abc;
  typedef bit       e_switch;            
  rand e_switch     cde;
  typedef integer   e_int_coordinate;
  rand e_int_coordinate coor[4];
  
  typedef integer   e_int_hex;
  rand e_int_hex    hex;
  rand e_switch     PLUSARGS__foo;
  rand integer      PLUSARGS__bar;


  // Test suite default constraints
  constraint suite_conv_default {
    filters   inside {`INTEGER__DIS,  8, 16, 32};
  }

  // Test specific constraints
  constraint conv_basic {
    // "--inline_halo --conv=3x3s2 --filters=16"       # basic, stride of 2
    inline_halo == e_bool__EN;
    conv        == e_conv__3x3s2;
    filters     == 16;

    fidelity    == e_fidelity__DIS;
    fullz       == `INTEGER__DIS;
    slicez      == `INTEGER__DIS;
  }
  constraint conv_compressed {
    //"--inline_halo --conv=3x3s1 --fidelity=lf --fullz=128 --slicez=128 --filters=16 "           # high-z with compression, 95% due to large z
    inline_halo == e_bool__EN;
    conv        == e_conv__3x3s1;
    filters     == 16;
    fidelity    == e_fidelity__lf;

    fullz       == 128;
    slicez      == 128;
  }

endclass


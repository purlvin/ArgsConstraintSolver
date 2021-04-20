
`define INTEGER__DIS -1

class constraints_conv;
  typedef enum {e_bi__DIS=`INTEGER__DIS,        e_bi__EN} e_bi;
  typedef enum {e_conv__DIS=`INTEGER__DIS,      e_conv__1x1s1, e_conv__3x3s1, e_conv__3x3s2} e_conv;
  typedef enum {e_fidelity__DIS=`INTEGER__DIS,  e_fidelity__lf} e_fidelity;
  
  rand e_bi         inline_halo;
  rand e_conv       conv;
  rand integer      filters;
  rand e_fidelity   fidelity;
  rand integer      fullz;
  rand integer      slicez;

  // Default/Test template constraints
  constraint conv_default {
    //inline_halo;
    //conv;
    filters   inside {`INTEGER__DIS,  8, 16, 32};
    //fidelity;
    fullz     inside {`INTEGER__DIS, 64, 128};
    slicez    inside {`INTEGER__DIS, 64, 128};
  }

  // Test specific constraints
  constraint conv_basic {
    // "--inline_halo --conv=3x3s2 --filters=16"       # basic, stride of 2
    inline_halo == e_bi__EN;
    conv        == e_conv__3x3s2;
    filters     == 16;

    fidelity    == e_fidelity__DIS;
    fullz       == `INTEGER__DIS;
    slicez      == `INTEGER__DIS;
  }
  constraint conv_compressed {
    //"--inline_halo --conv=3x3s1 --fidelity=lf --fullz=128 --slicez=128 --filters=16 "           # high-z with compression, 95% due to large z
    inline_halo == e_bi__EN;
    conv        == e_conv__3x3s1;
    filters     == 16;
    fidelity    == e_fidelity__lf;

    fullz       == 128;
    slicez      == 128;
  }

endclass


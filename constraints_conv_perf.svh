

class constraints_conv_perf extends constraints_conv;
  // Default/Test template constraints
  constraint conv_perf_default {
    //inline_halo;
    //conv;
    filters   inside {`INTEGER__DIS, 32};
    //fidelity;
    fullz     inside {`INTEGER__DIS, 128};
    slicez    inside {`INTEGER__DIS, 128};
  }

  // Test specific constraints
  constraint conv_perf_basic {
    inline_halo == e_bi__EN;
    conv        == e_conv__3x3s2;
    fidelity    == e_fidelity__lf;
    filters     == 32;
    fullz       == 128;
    slicez      == 128;
  }

endclass

class constraints_dumm;
endclass

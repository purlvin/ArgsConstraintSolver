

class constraints_suite_sfunc extends constraints_global;
  // Test suite default constraints
  constraint suite_sfunc_default {
    slicez    inside {`INTEGER__DIS, 64};
  }

  // Test specific constraints
  constraint sfunc_basic {
    // "--inline_halo --sfunc=3x3s2 --filters=16"       # basic, stride of 2
    inline_halo == e_bi__EN;
    filters     == 16;

    fidelity    == e_fidelity__DIS;
    fullz       == `INTEGER__DIS;
    slicez      == `INTEGER__DIS;
  }

endclass


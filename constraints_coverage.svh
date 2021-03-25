
typedef enum { bfp8 } e_fp;

  class constraints_coverage;
    rand integer num;

    // Constraint the members
    constraint default {
      num      inside {[1:100]};
    }
    constraint coverage_basic {
      num      == 88;
    }
  endclass

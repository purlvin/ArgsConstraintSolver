
class constraints_coverage;
  rand integer num;

  // Constraint the members
  constraint global {
    num      inside {[1:100]};
  }
  constraint coverage_basic {
    num      == 88;
  }
endclass


`define INTEGER__DIS -1

class constraints_global;
  typedef enum {e_fidelity__DIS=`INTEGER__DIS,  e_fidelity__lf} e_fidelity;
  
  rand e_fidelity   fidelity;
  rand integer      fullz;
  rand integer      slicez;

  // Default/Test template constraints
  constraint global_default {
    //fidelity;
    fullz     inside {`INTEGER__DIS, 64, 128};
    slicez    inside {`INTEGER__DIS, 64, 128};
  }
endclass


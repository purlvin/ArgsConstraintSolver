
program conf_main;
  class conf_constraint;
    rand integer Var1;
    rand integer Var2;
  
    `include "conf_all_constraints.svh"
  endclass

  conf_constraint conf = new();
  initial begin
   void'( $urandom(200));
    
    conf.randomize(); //By default all constraints are active.
    $display(" Var1 : %d Var2 : %d ",conf.Var1,conf.Var2);
    conf.Var_2.constraint_mode(0); //Both constraint Var_1 is are turned off.
    void'(conf.randomize());
    $display(" Var1 : %d Var2 : %d ",conf.Var1,conf.Var2);
    if (conf.Var_1.constraint_mode())
    $display("Var_1 constraint si active");
    else
    $display("Var_1 constraint si inactive");
    
    if (conf.Var_2.constraint_mode())
    $display("Var_2 constraint si active");
    else
    $display("Var_2 constraint si inactive");
    
    void'($urandom(300));
    void'(conf.randomize());
    $display(" Var1 : %d Var2 : %d ",conf.Var1,conf.Var2);
  end
endprogram



module tb;
  ttx_generator ttx();
  
  initial begin
    // Generate TTX image
    ttx.GenImage();
  end
endmodule

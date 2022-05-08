: # -*-Perl-*-
   eval 'exec perl  -S $0 ${1+"$@"}'
   if 0;

   use strict;
   my ($postcode_h_file) = @ARGV;
 
   print "\n";
   print "`ifndef __BOOTCODE_PRELOADER_SVH__\n";
   print "`define __BOOTCODE_PRELOADER_SVH__\n";
   print "\n";
   my %postcode_def;
   open DEFINE_FILE_H,"<$postcode_h_file" or die "Unable to open $postcode_h_file for read";
   my @define_file_lines = <DEFINE_FILE_H>;
   close DEFINE_FILE_H;
   foreach(@define_file_lines){
      if(/#define\s+(\w+)\s+(.*)/){
         next if ($2 eq ""); 
         my $define_name  = $1;
         my $define_value = $2;
         $define_value =~ s/\(uint(\d+)_t\)//;  ## remove (uint_*_t)
         $define_value =~ s/0x/'h/;             ## replace 0x with 'h
         $define_value =~ s/\/\/(.*)//;         ## remove comments
         ##$define_value =~ s/\\/'h0/;          ## mult-line not support
         if ($define_value =~ m/\\/) {} else {
            my $key = sprintf("%-80s", $define_name);
            $postcode_def{$define_name} = $define_value;
      print "  `define  $key $define_value\n";
         }
      }
   }
   print "\n";
   print "`endif\n";
   print "\n";

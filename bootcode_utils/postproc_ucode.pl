# ============================================================================ #
#  Copyright (c) 2009-2018 Advanced Micro Devices, Inc.  All rights reserved.  #
# ============================================================================ #
# use perl
    eval 'exec perl -S $0 ${1+"$@"}'
    if 0;

use Getopt::Long;
use File::Temp qw/ tempfile tempdir /;
use Data::Dumper;

GetOptions (
    "in_name:s" => \@opt_in_name,
    "in_dis:s"  => \@opt_in_dis,
    "in_elf:s"  => \@opt_in_elf,
    "in_post:s" => \@opt_in_post,
    "out_inf:s" => \$opt_out_inf,
    );
if (!defined($opt_out_inf))   {die "-out_inf not specified";}

#############################################################
# Generate %INFO_TABLE
my $count = 0;
my %INFO_TABLE;

while (my ($i, $dis_file) = each @opt_in_dis) {
  my $name      = $opt_in_name[$i];
  my $elf_file  = $opt_in_elf[$i];
  my $post_file = $opt_in_post[$i];
  print("Processing $name: \n");
  print("  - dis:  $dis_file\n");
  print("  - elf:  $elf_file\n");
  print("  - post: $post_file\n");
  # -> PC info
  open (DISFILE, "<$dis_file") or die "Can't open $dis_file!\n";
  ($fh, $filename) = tempfile();
  while (my $line = <DISFILE>) {
    if ($line =~ /^([0-9a-f]*):/) {
      my $id = $1;
      print $fh "$id\n";
      $INFO_TABLE{$count++} = {"ucode" => $name, "group" => "pc", "id" => $id};
    }
  }
  my @lines = `cat $filename | \${GCC_ARM_NONE_EABI_HOME}/bin/arm-none-eabi-addr2line -f -e $elf_file`;
  for (my $i=0; $i<$#lines; $i+=2) {
    my $data;
    $data = (split(" ", $lines[$i]))[0]; chomp $data;
    $INFO_TABLE{$i/2}{function} = $data;
    $data = (split(" ", $lines[$i+1]))[0]; chomp $data;
    if ((split(":", $data))[1] == "?") {
      $data = "<unknown>";
    }
    $INFO_TABLE{$i/2}{source}   = $data;
  }
  close $fh;

  # ->  Postcode info
  if (-e $post_file) {
    open DEFINE_FILE_H,"<$post_file" or die "Unable to open '$post_file' for read";
    @define_file_lines = <DEFINE_FILE_H>;
    close DEFINE_FILE_H;
    foreach(@define_file_lines){
      my $define_name;
      my $define_value;
      if (/#define\s+(\w+)\s+(.*)\s*/) {
        $define_name  = $1;
        $define_value = $2;
        next if ($define_value eq "");
        $define_value =~ s/\(uint(\d+)_t\)//;  ## remove (uint_*_t)
        $define_value =~ s/0x//;               ## replace 0x with 'h
        $define_value =~ s/\/\/(.*)//;         ## remove comments
        $define_value =~ s/\s+$//;             ## remove blackspace
        ##$define_value =~ s/\\/'h0/;          ## mult-line not support
        $define_value = lc(sprintf("%08x", hex $define_value));
        $INFO_TABLE{$count++} = {"ucode" => $name, "group" => "post", "id" => $define_value, "source" => $define_name};
      }
    }
  } else {
    print(" WARNING: Cannot find post file: $post_file\n");
  }
}

#======================================================================
# Generate .inf
open (INFFILE, ">$opt_out_inf") or die "Can't open $opt_out_inf!\n";
foreach my $i (sort {$a <=> $b} keys %INFO_TABLE) {
  my $id     = $INFO_TABLE{$i}{id};
  my $group  = $INFO_TABLE{$i}{group};
  my $source = $INFO_TABLE{$i}{source};
  $source = "<$INFO_TABLE{$i}{function}>".$source if ($group eq "pc");
  print INFFILE "$id $group $INFO_TABLE{$i}{ucode}#$source\n";
}
close INFFILE;



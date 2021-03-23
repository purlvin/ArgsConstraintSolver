#!/usr/bin/env python3
import math, re, sys
from collections import namedtuple
from typing import NamedTuple

# tuple types for register and field:
#class RTup(NamedTuple):
#    name: str
#    offset: int
#    comment: str
#    tags: dict
#    fields: list
#    def __repr__(self) -> str:
#        return f'RTup("{self.name}", 0x{self.offset:02x}, ...)'
#
#class FTup(NamedTuple):
#    name: str
#    msb: int
#    lsb: int
#    reset: str
#    tags: bool
#    comment: str
#    def __repr__(self) -> str:
#        return f'FTup("{self.name}", {self.msb}, {self.lsb}, "{self.reset}", ...)'

def get_header_info(header_str):
    # Extract info from header:
    for line in header_str.split('\n'):
        p = line.split()
        if len(p)>=2:
            if p[0] == "subcomponent":
                subcomponent = p[1]
            if p[0] == "register_block":
                dec = p[1].replace(':','')  # 'dispdec'
            if p[0] == "implement_block":
                block = p[1].replace(':','') # 'pllcs_reg'
            if p[0] == "data_wr_bus_width":
                width = int(p[1])
            if p[0] == "size":
                size = int(p[1], 0)
            if p[0] == "address_bus":
                # address_bus [17..2]
                match = re.match(r'\[(\d+)..(\d+)\]', p[1])
                aMsb = int(match[1])
                aLsb = int(match[2])
    nBytes = math.ceil(width / 8)
    nRegs = math.ceil(size / nBytes)
    return subcomponent, dec, block, width, nBytes, nRegs, aMsb, aLsb


import yaml


if __name__=="__main__":
    #filename = "tmp_reg.txt"
    #filename = sys.argv[1]
    #regs, headerStr = read_reg_text(filename)
    #print_rdl(regs, headerStr)
    print("hello!") 
    with open("test_spec.yml") as file:
        spec = yaml.load(file, Loader=yaml.FullLoader)
        print(spec)


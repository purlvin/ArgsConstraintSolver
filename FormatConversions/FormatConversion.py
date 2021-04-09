import xlrd
import os

IDX_IN  = 0
IDX_OUT = 1
IDX_Packer = 5

#----------------------------------------------------------------------
def std_format(frt):
    a = frt.lower().split(" ")
    if (a[-1] == "a"):
        a.pop()
    ret = "_"
    ret = ret.join(a)
    return ret

def get_format_map(xls):
    format_map = []
    book = xlrd.open_workbook(xls)
    sheet = book.sheet_by_index(0)
    for i in range(0, sheet.nrows):        
        row = sheet.row_slice(i)
        if (row[IDX_Packer].value == "Yes"):
            in_format  = std_format(row[IDX_IN].value)
            out_format = std_format(row[IDX_OUT].value)
            case = ["--fp_pack={}".format(in_format), "--fp_tile_dest={}".format(out_format)]
            format_map.append(case)
    return format_map

def parse_sh(format_map, directory):
    found = []
    for root, subdirectories, files in os.walk(directory):
        for file in files:
            file = os.path.join(root, file)
            if (file.find(".sh") == (len(file)-3)):          
                print("Processing file: ", file)
                Lines = open(file, 'r').readlines()
                count = 0
                for line in Lines:
                    count += 1
                    for p in format_map:
                        if ((line.find(p[0])>=0) and (line.find(p[1])>=0)):
                            found.append(p)
                            print("Found args in file: {}:{} - {}".format(file, count, p))

    print("\n=========================")
    print("Missing args:")
    for p in format_map:
        if p not in found:
            print(p)

#----------------------------------------------------------------------
if __name__ == "__main__":
    xls         = "Black Hole Format Conversions.xls"
    directory   = "C:\\Users\\puzhang\\Downloads"
    format_map = get_format_map(xls)
    parse_sh(format_map, directory)
